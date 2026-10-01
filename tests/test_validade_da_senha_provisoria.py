"""Testes da validade da senha provisória (ADR-154): ela vale por 48 horas, contadas de quando o banco a gerou.

O que conferimos:
- a conta das 48 horas: no limite ainda vale; um minuto depois, venceu; a senha definitiva e a provisória sem a hora
  gravada nunca vencem;
- quem já está com a senha provisória no dia em que a coluna nasce ganha a hora da mudança (o prazo não conta do
  passado, e ninguém fica com a senha vencida na hora);
- a senha dentro do prazo entra, e a pessoa cai na troca obrigatória (a senha continua provisória);
- a vencida é recusada no login com o aviso claro, sem criar a sessão e sem contar como senha errada: repetir a senha
  certa (vencida) não bloqueia o login, e a senha errada continua com a mensagem de sempre;
- a "Nova senha provisória" do banco zera o prazo, e o convite também grava a hora; a troca feita pela própria pessoa
  apaga a hora (a senha passa a ser definitiva);
- a grade de usuários do banco diz quem está com a senha provisória vencida; a empresa não usa essa rota, e sem login
  ela recusa.
Tudo no banco temporário dos testes (tests/conftest.py): os logins daqui começam com "validade." e não se repetem em
outro arquivo.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.principal import MENSAGEM_LOGIN_RECUSADO, aplicacao
from models.contratos import Perfil
from services import auth, banco, sessoes, tentativas_de_login

# A senha dos usuários fixos deste arquivo (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-da-validade-123"
# O especialista do banco e uma pessoa de empresa com senha definitiva
LOGIN_DO_BANCO = "validade.banco"
LOGIN_DA_EMPRESA = "validade.empresa"


@pytest.fixture(scope="module", autouse=True)
def usuarios_fixos():
    """Cadastra o especialista do banco e uma pessoa de empresa, com senha definitiva, uma vez para este arquivo."""
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao, LOGIN_DA_EMPRESA, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao.close()


def entrar(login: str, senha: str) -> tuple[TestClient, object]:
    """Tenta entrar com um navegador de mentira novo. Devolve o navegador e a resposta do login."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": senha})
    return navegador, resposta


def cadastrar_com_senha_provisoria(login: str, senha: str, horas_atras: float | None) -> None:
    """Cadastra uma pessoa da Aurora com senha provisória gerada há `horas_atras` horas (None: sem a hora gravada).

    Recebe: login; senha; horas_atras — quantas horas antes de agora o banco gerou a senha, ou None para simular a
    provisória de antes da regra. Devolve: nada. A hora é gravada direto no banco temporário (não dá para esperar 48
    horas num teste).
    """
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, login, senha, Perfil.EMPRESA, "EMP001", senha_provisoria=True)
    # A hora que o teste quer (ou nenhuma)
    hora = None
    if horas_atras is not None:
        hora = (datetime.now(timezone.utc) - timedelta(hours=horas_atras)).isoformat(timespec="seconds")
    conexao.execute("UPDATE usuarios SET senha_provisoria_gerada_em = ? WHERE login = ?", (hora, login))
    conexao.commit()
    conexao.close()


def hora_gravada(login: str) -> str | None:
    """A hora da senha provisória que está no banco para o login (None quando não há)."""
    conexao = auth.conectar()
    linha = conexao.execute("SELECT senha_provisoria_gerada_em FROM usuarios WHERE login = ?", (login,)).fetchone()
    conexao.close()
    return linha[0]


# ---------------- A conta das 48 horas ----------------

def test_a_hora_gravada_e_a_conta_das_48_horas():
    """A hora só existe na senha provisória; no limite das 48 horas ela ainda vale, e um minuto depois venceu."""
    agora = datetime(2026, 9, 30, 17, 5, tzinfo=timezone.utc)
    # A hora gravada: a de agora na provisória, nenhuma na definitiva
    assert auth.hora_da_senha_provisoria(True, agora) == "2026-09-30T17:05:00+00:00"
    assert auth.hora_da_senha_provisoria(False, agora) is None
    # Uma provisória gerada 48 horas antes de "agora"
    gerada_ha_48_horas = (agora - timedelta(hours=48)).isoformat(timespec="seconds")
    pessoa = auth.Usuario(login="x", perfil=Perfil.EMPRESA, empresa_id="EMP001", senha_provisoria=True,
                          senha_provisoria_gerada_em=gerada_ha_48_horas)
    # No limite, ainda vale; um minuto depois, venceu
    assert auth.senha_provisoria_venceu(pessoa, agora) is False
    assert auth.senha_provisoria_venceu(pessoa, agora + timedelta(minutes=1)) is True
    # A mesma hora numa senha definitiva, e a provisória sem a hora (de antes da regra): nunca vencem
    definitiva = auth.Usuario(login="x", perfil=Perfil.EMPRESA, empresa_id="EMP001", senha_provisoria=False,
                              senha_provisoria_gerada_em=gerada_ha_48_horas)
    sem_hora = auth.Usuario(login="x", perfil=Perfil.EMPRESA, empresa_id="EMP001", senha_provisoria=True)
    assert auth.senha_provisoria_venceu(definitiva, agora + timedelta(days=30)) is False
    assert auth.senha_provisoria_venceu(sem_hora, agora + timedelta(days=30)) is False
    # A regra é a das 48 horas
    assert auth.VALIDADE_DA_SENHA_PROVISORIA_HORAS == 48


# ---------------- O login ----------------

def test_senha_provisoria_dentro_do_prazo_entra_e_cai_na_troca_obrigatoria():
    """Gerada há 47 horas, a senha entra, e o login avisa que ela é provisória (a tela abre a troca obrigatória)."""
    cadastrar_com_senha_provisoria("validade.no.prazo@aurora.com.br", "provisoria-no-prazo", 47)
    navegador, resposta = entrar("validade.no.prazo@aurora.com.br", "provisoria-no-prazo")
    assert resposta.status_code == 200 and resposta.json()["senha_provisoria"] is True
    # A sessão existe, e o cabeçalho pede a troca
    assert navegador.get("/api/cabecalho").json()["senha_provisoria"] is True


def test_senha_provisoria_vencida_e_recusada_sem_sessao_e_sem_contar_como_erro():
    """Gerada há 49 horas, a senha certa é recusada com o aviso, sem cookie de sessão, e repetir não bloqueia."""
    login = "validade.vencida@aurora.com.br"
    cadastrar_com_senha_provisoria(login, "provisoria-vencida", 49)
    navegador, resposta = entrar(login, "provisoria-vencida")
    # O aviso claro, com o caminho
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == auth.MENSAGEM_SENHA_PROVISORIA_VENCIDA
    assert resposta.json()["detail"] == ("A sua senha provisória venceu. Peça uma nova ao especialista do banco que "
                                         "cuida do relacionamento com a sua empresa.")
    # Nenhuma sessão: sem o cookie, e as rotas continuam fechadas
    assert sessoes.NOME_COOKIE not in navegador.cookies
    assert navegador.get("/api/cabecalho").status_code == 401
    # Repetir a senha certa (vencida) 6 vezes não bloqueia: não conta como senha errada
    for _ in range(6):
        assert entrar(login, "provisoria-vencida")[1].status_code == 403
    conexao = auth.conectar()
    assert tentativas_de_login.minutos_de_bloqueio(conexao, login) == 0
    conexao.close()
    # A senha errada continua com a mensagem de sempre (o aviso não aparece para quem não sabe a senha)
    recusado = entrar(login, "senha-errada-000")[1]
    assert recusado.status_code == 401 and recusado.json()["detail"] == MENSAGEM_LOGIN_RECUSADO


def test_provisoria_sem_a_hora_nao_vence():
    """Sem a hora gravada (um caminho que não a gravou), a senha continua entrando: a regra nunca bloqueia por falta
    da hora."""
    cadastrar_com_senha_provisoria("validade.sem.hora@aurora.com.br", "provisoria-sem-hora", None)
    resposta = entrar("validade.sem.hora@aurora.com.br", "provisoria-sem-hora")[1]
    assert resposta.status_code == 200 and resposta.json()["senha_provisoria"] is True


def test_quem_ja_tem_senha_provisoria_ganha_o_prazo_a_partir_da_mudanca(tmp_path):
    """Num banco de antes da regra (sem a coluna), quem está com a senha provisória ganha a hora do dia da mudança:
    continua entrando agora e só vence 48 horas depois. A senha definitiva continua sem hora."""
    # Um banco SQLite antigo, com a tabela de usuários de antes da coluna nova
    conexao = banco.conectar(tmp_path / "antigo.db")
    conexao.execute("CREATE TABLE usuarios (login TEXT PRIMARY KEY, senha_hash TEXT NOT NULL, perfil TEXT NOT NULL, "
                    "empresa_id TEXT, ativo INTEGER NOT NULL DEFAULT 1, senha_provisoria INTEGER NOT NULL DEFAULT 0)")
    for login, provisoria in (("antiga.provisoria", 1), ("antiga.definitiva", 0)):
        conexao.execute("INSERT INTO usuarios (login, senha_hash, perfil, empresa_id, senha_provisoria) "
                        "VALUES (?, 'hash', 'EMPRESA', 'EMP001', ?)", (login, provisoria))
    conexao.commit()
    antes = datetime.now(timezone.utc)
    # A preparação da tabela cria a coluna e grava a hora de agora em quem está com a senha provisória
    auth.preparar_tabela(conexao)
    pessoas = {}
    for usuario in auth.listar_usuarios(conexao):
        pessoas[usuario.login] = usuario
    conexao.close()
    # A hora é a da mudança (gravada até os segundos), e a definitiva fica sem hora
    gerada_em = datetime.fromisoformat(pessoas["antiga.provisoria"].senha_provisoria_gerada_em)
    assert antes - timedelta(seconds=1) <= gerada_em <= datetime.now(timezone.utc)
    assert pessoas["antiga.definitiva"].senha_provisoria_gerada_em is None
    # Agora ela ainda entra; 48 horas e 1 minuto depois da mudança, venceu
    assert auth.senha_provisoria_venceu(pessoas["antiga.provisoria"]) is False
    depois_do_prazo = gerada_em + timedelta(hours=48, minutes=1)
    assert auth.senha_provisoria_venceu(pessoas["antiga.provisoria"], depois_do_prazo) is True


# ---------------- A senha nova zera o prazo; a troca apaga a hora ----------------

def test_nova_senha_provisoria_do_banco_zera_o_prazo():
    """A pessoa com a senha vencida recebe uma nova do banco: a hora recomeça agora, e a nova entra."""
    login = "validade.renovada@aurora.com.br"
    cadastrar_com_senha_provisoria(login, "provisoria-velha", 72)
    assert entrar(login, "provisoria-velha")[1].status_code == 403
    # O especialista gera a senha nova na aba Usuários
    banco = entrar(LOGIN_DO_BANCO, SENHA_DE_TESTE)[0]
    resposta = banco.post("/api/banco/empresas/usuarios/" + login + "/nova-senha")
    assert resposta.status_code == 200
    senha_nova = resposta.json()["senha_provisoria"]
    # A hora gravada é a de agora (menos de um minuto atrás)
    gerada_em = datetime.fromisoformat(hora_gravada(login))
    assert datetime.now(timezone.utc) - gerada_em < timedelta(minutes=1)
    # A nova entra, provisória; a velha, não
    assert entrar(login, senha_nova)[1].json()["senha_provisoria"] is True
    assert entrar(login, "provisoria-velha")[1].status_code == 401


def test_o_convite_grava_a_hora_e_a_troca_pela_pessoa_apaga():
    """O convite grava a hora da senha provisória; quando a própria pessoa troca a senha, a hora some."""
    banco = entrar(LOGIN_DO_BANCO, SENHA_DE_TESTE)[0]
    convite = banco.post("/api/banco/empresas/EMP001/convite", json={"email": "validade.convite@aurora.com.br"})
    assert convite.status_code == 200
    login = convite.json()["login"]
    senha_do_convite = convite.json()["senha_provisoria"]
    # A hora do convite ficou gravada
    assert hora_gravada(login) is not None
    # A pessoa entra e troca a senha: a nova é definitiva, sem hora
    pessoa = entrar(login, senha_do_convite)[0]
    troca = {"senha_atual": senha_do_convite, "nova_senha": "so-minha-da-validade",
             "confirmacao": "so-minha-da-validade"}
    assert pessoa.post("/api/minha-senha", json=troca).status_code == 200
    assert hora_gravada(login) is None
    assert entrar(login, "so-minha-da-validade")[1].json()["senha_provisoria"] is False


# ---------------- A grade de usuários do banco ----------------

def test_a_grade_de_usuarios_do_banco_mostra_a_senha_provisoria_vencida():
    """Na carteira do banco, a pessoa com a senha vencida vem marcada; as outras, não. Só o banco usa a rota."""
    cadastrar_com_senha_provisoria("validade.na.grade@aurora.com.br", "provisoria-da-grade", 50)
    banco = entrar(LOGIN_DO_BANCO, SENHA_DE_TESTE)[0]
    resposta = banco.get("/api/banco/empresas")
    assert resposta.status_code == 200
    # As pessoas da Aurora, pelo login
    pessoas_por_login = {}
    for empresa in resposta.json():
        if empresa["id"] == "EMP001":
            for pessoa in empresa["usuarios"]:
                pessoas_por_login[pessoa["login"]] = pessoa
    assert pessoas_por_login["validade.na.grade@aurora.com.br"]["senha_provisoria_vencida"] is True
    assert pessoas_por_login[LOGIN_DA_EMPRESA]["senha_provisoria_vencida"] is False
    # A empresa não usa a rota do banco, e sem login ela recusa
    assert entrar(LOGIN_DA_EMPRESA, SENHA_DE_TESTE)[0].get("/api/banco/empresas").status_code == 403
    assert TestClient(aplicacao).get("/api/banco/empresas").status_code == 401
