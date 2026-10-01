"""Cadastro de usuários e login (ADR-32).

Cada usuário tem login, perfil (EMPRESA ou BANCO) e, se for EMPRESA, a empresa a que
pertence. O perfil vem sempre do cadastro, nunca de uma escolha na tela: é isso que garante que o
usuário da Empresa A não veja a Empresa B.

A senha nunca é guardada: guardamos só o "hash" bcrypt dela, uma impressão digital que permite
conferir se a senha digitada está certa, mas não permite descobrir a senha a partir dela.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import bcrypt

from models.contratos import Perfil
from services import banco, config

# Senha mais curta que isso é recusada
TAMANHO_MINIMO_SENHA = 8
# O limite do bcrypt: ele só aceita até 72 bytes de senha (a versão 5 levanta erro acima disso)
TAMANHO_MAXIMO_SENHA_EM_BYTES = 72
# Validade do acesso da empresa (ADR-146): sem entrar por mais que isso, o acesso é suspenso
DIAS_SEM_USO_PARA_SUSPENDER = 90
# Por quantos dias o acesso vale depois de criado ou renovado (12 meses)
DIAS_DE_VALIDADE_DO_ACESSO = 365
# Os tipos de suspensão (a tela do banco mostra no selo da pessoa, com o botão "Reativar")
SUSPENSAO_POR_FALTA_DE_USO = "sem_uso"
SUSPENSAO_POR_VALIDADE = "vencido"
# O que a tela de login mostra em cada caso (o especialista do banco reativa com o botão "Ativar")
MENSAGEM_ACESSO_PARADO = ("Seu acesso foi suspenso por falta de uso (mais de 90 dias sem entrar). Peça ao "
                          "especialista do banco para reativar.")
MENSAGEM_ACESSO_VENCIDO = ("Seu acesso venceu (ele vale por 12 meses e precisa ser renovado). Peça ao especialista "
                           "do banco para renovar.")
# Por quantas horas a senha provisória vale, contadas de quando o especialista do banco a gerou (no convite ou na
# "Nova senha provisória"; ADR-154). Vencida, o login recusa, e o especialista gera uma nova
VALIDADE_DA_SENHA_PROVISORIA_HORAS = 48
# O que a tela de login mostra quando a senha provisória venceu
MENSAGEM_SENHA_PROVISORIA_VENCIDA = ("A sua senha provisória venceu. Peça uma nova ao especialista do banco que cuida "
                                     "do relacionamento com a sua empresa.")
# Um hash bcrypt de uma senha que ninguém usa, com o mesmo custo (12) dos hashes de verdade. Quando o login não
# existe, conferimos a senha contra ele só para a resposta levar o mesmo tempo (~0,25 s): sem isso, o login que não
# existe respondia em 0,01 s, e medindo o tempo dava para descobrir quais logins existem (A-02)
HASH_FALSO_PARA_GASTAR_O_MESMO_TEMPO = "$2b$12$ySXTOG9sajRweCeR2aPs/.YatJIPXk7ujxygsTUX4RyHZy76aPOr6"


@dataclass
class Usuario:
    """Quem está usando o sistema. Nunca carrega a senha nem o hash dela."""

    login: str               # o nome de acesso (ex.: "empresa.aurora")
    perfil: Perfil           # EMPRESA ou BANCO
    empresa_id: str | None   # obrigatório para EMPRESA; vazio para BANCO
    ativo: bool = True       # usuário desativado não entra, mas continua no histórico
    senha_provisoria: bool = False  # True: a senha foi gerada pelo banco (convite ou redefinição) e precisa ser
                                    # trocada pela própria pessoa antes de usar o sistema (ADR-109)
    senha_provisoria_gerada_em: str | None = None  # quando o banco gerou a senha provisória, em UTC (ADR-154:
                                                   # ela vale por 48 horas); vazio na senha definitiva


def conectar(caminho: Path | None = None):
    """Abre o banco do .env (SQLite ou PostgreSQL, ADR-67) e garante que a tabela de usuários existe e está em dia.

    caminho: no SQLite, qual arquivo abrir (sem informar, o do .env); no PostgreSQL, é ignorado.
    """
    # A porta única do banco escolhe SQLite ou PostgreSQL pelo .env
    conexao = banco.conectar(caminho)
    preparar_tabela(conexao)
    return conexao


def preparar_tabela(conexao) -> None:
    """Cria a tabela de usuários, se ainda não existir, e acrescenta as colunas que faltarem."""
    # Cria a tabela de usuários, se ainda não existir
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS usuarios (
               login      TEXT PRIMARY KEY,
               senha_hash TEXT NOT NULL,
               perfil     TEXT NOT NULL,
               empresa_id TEXT,
               ativo      INTEGER NOT NULL DEFAULT 1,
               senha_provisoria INTEGER NOT NULL DEFAULT 0
           )"""
    )
    # As colunas que já existem na tabela (bancos antigos podem não ter as mais novas)
    colunas_existentes = banco.colunas_da_tabela(conexao, "usuarios")
    # Bancos antigos não tinham a coluna "ativo": acrescenta sem perder os usuários já cadastrados
    if "ativo" not in colunas_existentes:
        conexao.execute("ALTER TABLE usuarios ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1")
    # Bancos criados antes do ADR-109 não tinham a marca de senha provisória: quem já existe fica com senha definitiva
    if "senha_provisoria" not in colunas_existentes:
        conexao.execute("ALTER TABLE usuarios ADD COLUMN senha_provisoria INTEGER NOT NULL DEFAULT 0")
    # Validade do acesso da empresa (ADR-146): o dia do último login e até quando o acesso vale (AAAA-MM-DD).
    # Vazias em quem já existia: a contagem começa no próximo login, e ninguém é bloqueado no dia da mudança
    if "ultimo_acesso" not in colunas_existentes:
        conexao.execute("ALTER TABLE usuarios ADD COLUMN ultimo_acesso TEXT")
    if "acesso_valido_ate" not in colunas_existentes:
        conexao.execute("ALTER TABLE usuarios ADD COLUMN acesso_valido_ate TEXT")
    # Quando o banco gerou a senha provisória (ADR-154: ela vale por 48 horas). Quem já está com uma provisória no dia
    # em que a coluna nasce ganha a hora de agora: o prazo conta da mudança, e não do passado, e ninguém fica com a
    # senha vencida na hora
    if "senha_provisoria_gerada_em" not in colunas_existentes:
        conexao.execute("ALTER TABLE usuarios ADD COLUMN senha_provisoria_gerada_em TEXT")
        conexao.execute("UPDATE usuarios SET senha_provisoria_gerada_em = ? WHERE senha_provisoria = 1",
                        (hora_da_senha_provisoria(True),))
    # Confirma a criação da tabela (no PostgreSQL, até a criação de tabela precisa ser confirmada)
    conexao.commit()


def _gerar_hash_da_senha(senha: str) -> str:
    """Confere o tamanho mínimo e o máximo e devolve o hash bcrypt da senha (é isso que vai para o banco)."""
    # Senha curta demais é recusada com uma mensagem clara
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")
    # O bcrypt só usa os primeiros 72 bytes da senha (letra com acento ocupa 2): acima disso, recusa com mensagem clara
    if len(senha.encode("utf-8")) > TAMANHO_MAXIMO_SENHA_EM_BYTES:
        raise ValueError("A senha pode ter no máximo 72 caracteres (menos, se tiver letras com acento).")
    # gensalt() sorteia um "sal": duas pessoas com a mesma senha ficam com hashes diferentes
    hash_em_bytes = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt())
    return hash_em_bytes.decode("utf-8")


def _senha_confere(senha_digitada: str, senha_hash: str) -> bool:
    """True se a senha digitada corresponde ao hash guardado.

    Senha digitada com mais de 72 bytes nunca foi cadastrada (o cadastro recusa): é simplesmente errada. Sem esta
    conferência, o bcrypt 5 levanta erro e o login devolveria "erro 500" em vez de "usuário ou senha incorretos".
    """
    senha_em_bytes = senha_digitada.encode("utf-8")
    if len(senha_em_bytes) > TAMANHO_MAXIMO_SENHA_EM_BYTES:
        return False
    return bcrypt.checkpw(senha_em_bytes, senha_hash.encode("utf-8"))


def cadastrar_usuario(conexao, login: str, senha: str, perfil: Perfil, empresa_id: str | None = None,
                      senha_provisoria: bool = False):
    """Cadastra (ou substitui) um usuário. EMPRESA exige empresa_id; os outros perfis não têm empresa.

    senha_provisoria: True quando a senha foi gerada pelo banco (o convite): a pessoa precisa trocá-la no primeiro
    acesso, antes de usar o sistema (ADR-109).
    """
    # Tira espaços das pontas do login
    login = login.strip()
    # Login vazio não pode
    if not login:
        raise ValueError("O login não pode ser vazio.")
    # Usuário de empresa precisa dizer de qual empresa é
    if perfil == Perfil.EMPRESA and not empresa_id:
        raise ValueError("Usuário do perfil EMPRESA precisa de uma empresa.")
    # O banco nunca fica preso a uma empresa
    if perfil != Perfil.EMPRESA:
        empresa_id = None
    # A hora em que o banco gerou a senha provisória (a validade de 48 horas conta daí); a definitiva fica sem ela
    gerada_em = hora_da_senha_provisoria(senha_provisoria)
    # Grava (ou substitui) o usuário, já ativo, guardando só o hash da senha, a marca de senha provisória e a hora dela.
    # "ON CONFLICT (login) DO UPDATE": se o login já existe, atualiza (a mesma forma no SQLite e no PostgreSQL)
    conexao.execute(
        "INSERT INTO usuarios (login, senha_hash, perfil, empresa_id, ativo, senha_provisoria, "
        "senha_provisoria_gerada_em) VALUES (?, ?, ?, ?, 1, ?, ?) "
        "ON CONFLICT (login) DO UPDATE SET senha_hash = excluded.senha_hash, perfil = excluded.perfil, "
        "empresa_id = excluded.empresa_id, ativo = excluded.ativo, senha_provisoria = excluded.senha_provisoria, "
        "senha_provisoria_gerada_em = excluded.senha_provisoria_gerada_em",
        (login, _gerar_hash_da_senha(senha), perfil.value, empresa_id, int(senha_provisoria), gerada_em),
    )
    conexao.commit()


def remover_usuarios_de_perfis_extintos(conexao) -> list[str]:
    """Apaga os usuários (e as sessões deles) de perfis que não existem mais. Devolve os logins apagados.

    Por quê: o perfil CIENTISTA saiu do sistema (ADR-78). Um banco criado antes ainda tem o usuário "cientista.dados";
    sem apagar, a lista de usuários quebraria ao ler um perfil que o sistema não conhece. Roda na preparação do
    servidor e pode rodar de novo sem efeito (se não houver nada a apagar, não apaga nada).
    """
    # Importado aqui dentro: o módulo de sessões usa este módulo, e importar no topo faria um laço de importação
    from services import sessoes
    preparar_tabela(conexao)
    perfis_que_existem = set()
    for perfil in Perfil:
        perfis_que_existem.add(perfil.value)
    apagados = []
    for login, perfil in conexao.execute("SELECT login, perfil FROM usuarios").fetchall():
        if perfil not in perfis_que_existem:
            apagados.append(login)
    for login in apagados:
        sessoes.preparar_tabela(conexao)
        conexao.execute("DELETE FROM sessoes WHERE login = ?", (login,))
        conexao.execute("DELETE FROM usuarios WHERE login = ?", (login,))
    conexao.commit()
    return apagados


def autenticar(conexao, login: str, senha: str) -> Usuario | None:
    """Devolve o usuário se login e senha conferem e ele está ativo; senão, None.

    A resposta é a mesma para qualquer falha: não revela se o erro foi no login ou na senha.
    """
    # Procura o usuário pelo login
    consulta = conexao.execute("SELECT senha_hash, perfil, empresa_id, ativo, senha_provisoria, "
                               "senha_provisoria_gerada_em FROM usuarios WHERE login = ?", (login,))
    linha = consulta.fetchone()
    # Login inexistente: confere a senha contra o hash falso só para gastar o mesmo tempo, e recusa (A-02)
    if linha is None:
        _senha_confere(senha, HASH_FALSO_PARA_GASTAR_O_MESMO_TEMPO)
        return None
    senha_hash, perfil, empresa_id, ativo, senha_provisoria, senha_provisoria_gerada_em = linha
    # Usuário desativado não entra (a senha dele é conferida, e o resultado descartado, pelo mesmo motivo do tempo)
    if not ativo:
        _senha_confere(senha, senha_hash)
        return None
    # Senha errada não entra
    if not _senha_confere(senha, senha_hash):
        return None
    # Tudo certo: devolve quem é, com o perfil e a empresa do cadastro (e se a senha ainda é a provisória, e desde
    # quando: o login confere a validade dela)
    return Usuario(login=login, perfil=Perfil(perfil), empresa_id=empresa_id, ativo=True,
                   senha_provisoria=bool(senha_provisoria), senha_provisoria_gerada_em=senha_provisoria_gerada_em)


def listar_usuarios(conexao) -> list[Usuario]:
    """Todos os usuários, ordenados por perfil e login (sem o hash da senha)."""
    consulta = conexao.execute("SELECT login, perfil, empresa_id, ativo, senha_provisoria, senha_provisoria_gerada_em "
                               "FROM usuarios ORDER BY perfil, login")
    usuarios = []
    for login, perfil, empresa_id, ativo, senha_provisoria, senha_provisoria_gerada_em in consulta:
        # O banco guarda "ativo" e a marca da senha provisória como 0 ou 1; aqui viram verdadeiro ou falso
        usuarios.append(Usuario(login=login, perfil=Perfil(perfil), empresa_id=empresa_id, ativo=bool(ativo),
                                senha_provisoria=bool(senha_provisoria),
                                senha_provisoria_gerada_em=senha_provisoria_gerada_em))
    return usuarios


def redefinir_senha(conexao, login: str, nova_senha: str, senha_provisoria: bool = False) -> None:
    """Grava uma senha nova para alguém.

    senha_provisoria: True quando quem gerou foi o banco (a pessoa esqueceu a senha): ela precisa trocar no próximo
    acesso; False quando é a própria pessoa trocando (a senha passa a ser definitiva).
    """
    # A provisória ganha a hora em que o banco a gerou (a validade de 48 horas recomeça daí); a definitiva fica sem ela
    gerada_em = hora_da_senha_provisoria(senha_provisoria)
    # Troca o hash guardado pelo hash da nova senha e grava se ela é provisória, e desde quando
    resultado = conexao.execute("UPDATE usuarios SET senha_hash = ?, senha_provisoria = ?, "
                                "senha_provisoria_gerada_em = ? WHERE login = ?",
                                (_gerar_hash_da_senha(nova_senha), int(senha_provisoria), gerada_em, login))
    # Nenhuma linha alterada: o login não existe
    if resultado.rowcount == 0:
        raise ValueError(f"Usuário {login!r} não encontrado.")
    conexao.commit()


def trocar_propria_senha(conexao, login: str, senha_atual: str, nova_senha: str) -> None:
    """A própria pessoa troca a senha; para isso, precisa digitar a senha atual."""
    # Confere a senha atual antes de trocar
    if autenticar(conexao, login, senha_atual) is None:
        raise ValueError("A senha atual não confere.")
    # Trocar pela mesma senha não adianta (ex.: manter a provisória, que o banco viu)
    if nova_senha == senha_atual:
        raise ValueError("A nova senha precisa ser diferente da atual.")
    # Grava a nova senha, agora definitiva (só a pessoa a conhece)
    redefinir_senha(conexao, login, nova_senha, senha_provisoria=False)


def definir_ativo(conexao, login: str, ativo: bool) -> None:
    """Desativa (ou reativa) um usuário. Desativado não entra, mas o histórico dele é preservado.

    Reativar também renova o acesso (ADR-146): a contagem dos dias sem uso recomeça hoje, e a validade passa a ser de
    mais 12 meses. É o mesmo botão "Ativar" que o especialista do banco já usa, para o suspenso voltar a entrar.
    """
    # Grava 1 (ativo) ou 0 (desativado)
    resultado = conexao.execute("UPDATE usuarios SET ativo = ? WHERE login = ?", (int(ativo), login))
    # Nenhuma linha alterada: o login não existe
    if resultado.rowcount == 0:
        raise ValueError(f"Usuário {login!r} não encontrado.")
    # Reativou: o acesso é renovado a partir de hoje
    if ativo:
        dia = date.today()
        conexao.execute("UPDATE usuarios SET ultimo_acesso = ?, acesso_valido_ate = ? WHERE login = ?",
                        (dia.isoformat(), _fim_da_validade(dia).isoformat(), login))
    conexao.commit()


# ---------------- Validade do acesso da empresa (ADR-146) ----------------

def _fim_da_validade(dia: date) -> date:
    """O último dia de um acesso que começa (ou é renovado) em `dia`. Ex.: 2026-09-30 → 2027-09-30."""
    return dia + timedelta(days=DIAS_DE_VALIDADE_DO_ACESSO)


def motivo_do_acesso_suspenso(conexao, login: str) -> str | None:
    """Diz por que o acesso de uma pessoa de empresa está suspenso, ou None se ela pode entrar.

    Recebe: conexao; login (que já passou pela senha certa). Devolve: a mensagem para a tela de login, ou None.
    Exemplo: último acesso há 91 dias → "Seu acesso foi suspenso por falta de uso..."
    """
    # O tipo da suspensão (ou None), e a mensagem de cada tipo
    tipo_da_suspensao = suspensao_do_acesso(conexao, login)
    if tipo_da_suspensao == SUSPENSAO_POR_VALIDADE:
        return MENSAGEM_ACESSO_VENCIDO
    if tipo_da_suspensao == SUSPENSAO_POR_FALTA_DE_USO:
        return MENSAGEM_ACESSO_PARADO
    return None


def suspensao_do_acesso(conexao, login: str) -> str | None:
    """O tipo da suspensão do acesso de uma pessoa de empresa: "vencido", "sem_uso" ou None (pode entrar).

    Recebe: conexao; login. Devolve: o tipo, que a tela do banco mostra no selo da pessoa (com o botão "Reativar")
    e o login transforma na mensagem. Só vale para o perfil EMPRESA: o especialista do banco nunca é suspenso.
    Por quê: quem sai da empresa para de entrar, e o RH nem sempre avisa o banco. Sem uso por 90 dias, ou depois
    de 12 meses sem renovar, o acesso esquecido deixa de valer sozinho.
    Exemplo: último acesso há 91 dias → "sem_uso".
    """
    dia = date.today()
    # O perfil e as duas datas da pessoa
    consulta = conexao.execute("SELECT perfil, ultimo_acesso, acesso_valido_ate FROM usuarios WHERE login = ?",
                               (login,))
    linha = consulta.fetchone()
    # Login que não existe, ou do banco: nada a suspender aqui
    if linha is None or linha[0] != Perfil.EMPRESA.value:
        return None
    _, ultimo_acesso, acesso_valido_ate = linha
    # A validade venceu (vazia: quem já existia antes da regra, que ganha a validade no próximo login)
    if acesso_valido_ate and date.fromisoformat(acesso_valido_ate) < dia:
        return SUSPENSAO_POR_VALIDADE
    # Tempo demais sem entrar (vazio: ainda não entrou desde a regra)
    if ultimo_acesso and (dia - date.fromisoformat(ultimo_acesso)).days > DIAS_SEM_USO_PARA_SUSPENDER:
        return SUSPENSAO_POR_FALTA_DE_USO
    return None


def registrar_acesso(conexao, login: str) -> None:
    """Grava o dia do login certo; quem ainda não tinha validade ganha 12 meses a partir de hoje.

    Recebe: conexao; login. Devolve: nada.
    """
    dia = date.today()
    # O último acesso passa a ser hoje
    conexao.execute("UPDATE usuarios SET ultimo_acesso = ? WHERE login = ?", (dia.isoformat(), login))
    # Sem validade ainda (quem já existia antes da regra): começa a contar hoje
    conexao.execute("UPDATE usuarios SET acesso_valido_ate = ? WHERE login = ? AND acesso_valido_ate IS NULL",
                    (_fim_da_validade(dia).isoformat(), login))
    conexao.commit()


# ---------------- Validade da senha provisória (ADR-154) ----------------

def hora_da_senha_provisoria(senha_provisoria: bool, agora: datetime | None = None) -> str | None:
    """A hora que fica gravada junto com uma senha nova: a de agora, se ela é provisória; nenhuma, se é definitiva.

    Recebe: senha_provisoria — True quando o banco gerou a senha (convite ou "Nova senha provisória"); agora — o
    instante (sem informar, o de agora; os testes informam). Devolve: a hora em UTC, no formato ISO, ou None.
    UTC é o horário de referência do mundo, sem o fuso de cada lugar: a conta das 48 horas não muda com o horário
    de verão nem com o fuso do servidor.
    Exemplo: (True) às 14h05 de Brasília → "2026-09-30T17:05:00+00:00"; (False) → None.
    """
    # A senha definitiva (a que a própria pessoa criou) não vence por esta regra: não guarda hora
    if not senha_provisoria:
        return None
    # O instante de referência: o informado, ou o de agora
    if agora is None:
        agora = datetime.now(timezone.utc)
    # Em texto, até os segundos (é assim que o banco guarda)
    return agora.isoformat(timespec="seconds")


def senha_provisoria_venceu(usuario: Usuario, agora: datetime | None = None) -> bool:
    """Diz se a senha provisória da pessoa já venceu: ela vale por 48 horas, contadas de quando o banco a gerou.

    Recebe: usuario — com a marca e a hora da senha provisória (de autenticar ou listar_usuarios); agora — o instante
    de referência (sem informar, o de agora; os testes informam). Devolve: True só quando a senha é provisória, tem a
    hora gravada e o prazo passou. A senha definitiva nunca vence por esta regra. A provisória sem a hora (um caminho
    que não a gravou) também não: a regra nunca bloqueia alguém por falta da hora.
    Exemplo: gerada em 2026-09-28 às 10h00 e agora 2026-09-30 às 10h01 (48 horas e 1 minuto depois) → True.
    """
    # Senha definitiva, ou provisória sem a hora: não vence
    if not usuario.senha_provisoria or not usuario.senha_provisoria_gerada_em:
        return False
    # O instante de referência: o informado, ou o de agora (em UTC, como a hora gravada)
    if agora is None:
        agora = datetime.now(timezone.utc)
    # Quando a senha foi gerada, e até quando ela vale
    gerada_em = datetime.fromisoformat(usuario.senha_provisoria_gerada_em)
    vale_ate = gerada_em + timedelta(hours=VALIDADE_DA_SENHA_PROVISORIA_HORAS)
    # Venceu quando o instante de agora passou do fim da validade
    return agora > vale_ate
