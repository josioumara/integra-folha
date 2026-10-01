"""Gera os dados de demonstração do joinha: as opiniões das pessoas sobre os agentes nos últimos 90 dias, para as
empresas da base viva (ADR-151). Sem IA: é só uma carga de números, com semente fixa.

Para que serve: a seção "O que as pessoas acham das respostas dos agentes", da tela Acompanhamento dos agentes, precisa
de votos para mostrar a satisfação e a tendência. A base viva (scripts/carregar_base_viva.py) simula uns 3 meses de uso sem a IA, então não há conversas
com os agentes guardadas. Esta carga põe votos plausíveis, com taxas diferentes por agente, marcados com a origem
"carga sintética": a tabela separa esses votos dos que as pessoas dão na tela, e o --remover tira só eles.

Como os votos nascem (semente fixa: no mesmo dia, a mesma carga sempre dá os mesmos votos):
    - cada empresa tem o seu sorteio (a semente e o código dela): mudar a lista de empresas não muda os votos de uma;
    - quantos votos cada agente recebe na empresa: um número numa faixa própria do agente. O Leitor e o Conferidor
      só aparecem numa parte das empresas (as que mandaram documentos em texto);
    - quando: nos últimos 90 dias, com mais votos nas semanas recentes (o uso cresce), em horário comercial de Brasília;
    - para cima ou para baixo, pela taxa do agente naquele dia: a do Agente de validação sobe com o tempo (de 70% para
      88%, como se o agente tivesse melhorado); a do Leitor fica em 72%; a do Conferidor, em 60%; a do Endomarketing,
      em 85%;
    - quem votou: um login do RH da empresa (Agente de validação, Leitor e Conferidor) ou o login do banco
      (Endomarketing). Empresa sem login do RH recebe só os votos do banco;
    - o comentário: em parte dos votos para baixo, uma frase de uma lista fixa, sem nenhum dado pessoal (no joinha
      para cima não há comentário, como na tela);
    - a referência é "sintetico|<agente>|<empresa>|<número>": não aponta para nenhuma conversa nem material de verdade.

Para rodar (na pasta integra-folha):
    python scripts/gerar_opinioes_dos_agentes.py                           (as empresas da base viva que existem no banco)
    python scripts/gerar_opinioes_dos_agentes.py --empresas EMP001,EMP002  (outras empresas, ex.: no banco de teste)
    python scripts/gerar_opinioes_dos_agentes.py --remover                 (tira só a carga sintética)
No PostgreSQL (o banco de todos), a carga só roda com --confirmo-o-postgres, depois da cópia de segurança
(scripts/copia_de_seguranca.py). Rodar de novo refaz a carga: as opiniões sintéticas de antes saem e entram as novas;
as dadas na tela ficam.
"""
import argparse
import os
import random
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

# A carga nunca chama a IA: o modo MOCK vale antes de qualquer serviço ler o .env
os.environ["MODE"] = "mock"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from models.contratos import Perfil  # noqa: E402
from services import auth, banco, config, empresas, opiniao_dos_agentes  # noqa: E402

# A semente fixa do sorteio (o número do ADR do joinha): a mesma carga, no mesmo dia, dá sempre os mesmos votos
SEMENTE = 151
# Quantos dias para trás os votos se espalham
DIAS_DA_CARGA = 90
# As empresas da base viva: EMP007 a EMP023 e EMP025 a EMP029, em duas faixas (a primeira e a última de cada uma)
FAIXAS_DA_BASE_VIVA = ((7, 23), (25, 29))
# O horário comercial em que os votos acontecem, em Brasília (das 8h às 19h)
PRIMEIRA_HORA = 8
ULTIMA_HORA = 19
# O horário de Brasília (3 horas atrás do horário universal)
FUSO_DE_BRASILIA = timezone(timedelta(hours=-3))
# O que cada agente recebe, por empresa:
#   - faixa: o menor e o maior número de votos;
#   - chance_de_aparecer: a parte das empresas em que o agente trabalhou (1 = todas);
#   - taxa_antes e taxa_agora: a chance de o voto ser para cima 90 dias atrás e hoje (entre as duas, uma reta);
#   - chance_de_comentar: a chance de um voto para baixo trazer um comentário.
PERFIL_DOS_VOTOS = {
    "agente_de_validacao": {"faixa": (10, 28), "chance_de_aparecer": 1.0, "taxa_antes": 0.70, "taxa_agora": 0.88,
                            "chance_de_comentar": 0.35},
    "leitor": {"faixa": (2, 9), "chance_de_aparecer": 0.6, "taxa_antes": 0.72, "taxa_agora": 0.72,
               "chance_de_comentar": 0.30},
    "conferidor": {"faixa": (1, 5), "chance_de_aparecer": 0.4, "taxa_antes": 0.60, "taxa_agora": 0.60,
                   "chance_de_comentar": 0.30},
    "endomarketing": {"faixa": (1, 5), "chance_de_aparecer": 1.0, "taxa_antes": 0.85, "taxa_agora": 0.85,
                      "chance_de_comentar": 0.40},
}
# O tipo de interação de cada agente (os mesmos do serviço)
TIPO_DO_AGENTE = {
    "agente_de_validacao": opiniao_dos_agentes.TIPO_RESPOSTA_DA_CONVERSA,
    "leitor": opiniao_dos_agentes.TIPO_PERGUNTA_DA_LEITURA,
    "conferidor": opiniao_dos_agentes.TIPO_PERGUNTA_DA_LEITURA,
    "endomarketing": opiniao_dos_agentes.TIPO_MATERIAL_DO_ENDOMARKETING,
}
# Os comentários possíveis de um voto para baixo, por agente (frases fixas, sem nenhum dado pessoal)
COMENTARIOS = {
    "agente_de_validacao": ("A resposta não resolveu a pendência.", "O agente não entendeu o que eu pedi.",
                            "Precisei explicar duas vezes.", "A resposta ficou longa demais."),
    "leitor": ("A pergunta não fazia sentido para este funcionário.", "O dado estava claro no documento."),
    "conferidor": ("O valor lido já estava certo.", "A pergunta repetiu o que eu já tinha informado."),
    "endomarketing": ("O texto ficou longo para o canal.", "Faltou citar o benefício principal.",
                      "O tom ficou formal demais."),
}


class CargaRecusada(Exception):
    """A carga não pode seguir (ex.: o banco é o PostgreSQL de todos e ninguém confirmou)."""


def empresas_da_base_viva() -> list[str]:
    """Os códigos das empresas da base viva, em ordem. Ex.: ["EMP007", ..., "EMP023", "EMP025", ..., "EMP029"]."""
    codigos = []
    for primeira, ultima in FAIXAS_DA_BASE_VIVA:
        for numero in range(primeira, ultima + 1):
            codigos.append(f"EMP{numero:03d}")
    return codigos


def conferir_o_banco(banco_do_env: str, confirmou_o_postgres: bool) -> None:
    """Recusa a carga no PostgreSQL de todos sem a confirmação de propósito (--confirmo-o-postgres).

    Recebe: banco_do_env — "sqlite" ou "postgres" (o BANCO do .env); confirmou_o_postgres — a opção da linha de
    comando. Levanta CargaRecusada. Por quê: um script solto que grava no banco de todos por engano já aconteceu.
    """
    if banco_do_env == "postgres" and not confirmou_o_postgres:
        raise CargaRecusada("O banco do .env é o PostgreSQL de todos. Faça a cópia de segurança e rode com "
                            "--confirmo-o-postgres (ou use BANCO=sqlite para um banco de teste).")


def logins_de_quem_vota(conexao) -> tuple[dict, str | None]:
    """Os logins ativos do RH de cada empresa e o primeiro login ativo do banco (em ordem alfabética).

    Devolve: ({empresa_id: [logins]}, login do banco ou None).
    """
    do_rh = {}
    do_banco = None
    for usuario in auth.listar_usuarios(conexao):
        # Usuário desativado não vota
        if not usuario.ativo:
            continue
        if usuario.perfil == Perfil.EMPRESA and usuario.empresa_id:
            # A primeira pessoa do RH desta empresa abre a lista dela
            if usuario.empresa_id not in do_rh:
                do_rh[usuario.empresa_id] = []
            do_rh[usuario.empresa_id].append(usuario.login)
        elif usuario.perfil == Perfil.BANCO and do_banco is None:
            do_banco = usuario.login
    return do_rh, do_banco


def taxa_do_dia(agente: str, dias_atras: float) -> float:
    """A chance de o voto ser para cima naquele dia: uma reta da taxa de 90 dias atrás até a de hoje.

    Ex.: Agente de validação, 45 dias atrás → a metade do caminho entre 0,70 e 0,88 = 0,79.
    """
    perfil = PERFIL_DOS_VOTOS[agente]
    quanto_do_caminho = 1 - dias_atras / DIAS_DA_CARGA
    return perfil["taxa_antes"] + (perfil["taxa_agora"] - perfil["taxa_antes"]) * quanto_do_caminho


def momento_do_voto(sorteio: random.Random, agora: datetime) -> tuple[datetime, float]:
    """Sorteia quando o voto aconteceu: nos últimos DIAS_DA_CARGA dias, mais perto de hoje, em horário comercial.

    Devolve: (o momento, no horário universal; quantos dias atrás). A distribuição "triangular" com o pico em 0 dá
    mais votos nos dias recentes, como um uso que cresce.
    """
    dias_atras = sorteio.triangular(0, DIAS_DA_CARGA, 0)
    dia = (agora.astimezone(FUSO_DE_BRASILIA) - timedelta(days=dias_atras)).date()
    hora = time(sorteio.randint(PRIMEIRA_HORA, ULTIMA_HORA - 1), sorteio.randint(0, 59), tzinfo=FUSO_DE_BRASILIA)
    momento = datetime.combine(dia, hora)
    # Um voto nunca fica no futuro (hoje, antes da hora sorteada)
    if momento > agora:
        momento = agora - timedelta(minutes=sorteio.randint(1, 120))
    return momento.astimezone(timezone.utc), dias_atras


def opinioes_da_empresa(empresa_id: str, logins_do_rh: list[str], login_do_banco: str | None,
                        agora: datetime) -> list[dict]:
    """Os votos de demonstração de uma empresa, prontos para opiniao_dos_agentes.gravar.

    Recebe: empresa_id; logins_do_rh — os logins do RH dela (vazio: sem votos da empresa); login_do_banco (None: sem
    votos no Endomarketing); agora — o momento da carga.
    Devolve: a lista de opiniões. O sorteio é só desta empresa (semente e código): a mesma empresa dá sempre os mesmos
    votos.
    """
    sorteio = random.Random(f"{SEMENTE}-{empresa_id}")
    opinioes = []
    for agente, perfil in PERFIL_DOS_VOTOS.items():
        # Quem vota neste agente: o banco no Endomarketing; o RH nos outros
        if agente == "endomarketing":
            quem_pode_votar = []
            if login_do_banco:
                quem_pode_votar = [login_do_banco]
            perfil_de_quem_vota = Perfil.BANCO.value
        else:
            quem_pode_votar = logins_do_rh
            perfil_de_quem_vota = Perfil.EMPRESA.value
        # O agente não trabalhou nesta empresa, ou ninguém pode votar nele: nenhum voto
        aparece = sorteio.random() < perfil["chance_de_aparecer"]
        quantos = sorteio.randint(perfil["faixa"][0], perfil["faixa"][1])
        if not aparece or not quem_pode_votar:
            continue
        for numero in range(1, quantos + 1):
            momento, dias_atras = momento_do_voto(sorteio, agora)
            voto = opiniao_dos_agentes.PARA_BAIXO
            if sorteio.random() < taxa_do_dia(agente, dias_atras):
                voto = opiniao_dos_agentes.PARA_CIMA
            # O comentário: só em parte dos votos para baixo (como na tela, o joinha para cima não tem comentário)
            comentario = None
            if voto == opiniao_dos_agentes.PARA_BAIXO and sorteio.random() < perfil["chance_de_comentar"]:
                comentario = sorteio.choice(COMENTARIOS[agente])
            opinioes.append({
                "tipo": TIPO_DO_AGENTE[agente], "referencia": f"sintetico|{agente}|{empresa_id}|{numero}",
                "login": sorteio.choice(quem_pode_votar), "agente": agente, "perfil": perfil_de_quem_vota,
                "empresa_id": empresa_id, "processamento_id": None, "voto": voto, "comentario": comentario,
                "origem": opiniao_dos_agentes.ORIGEM_DA_CARGA_SINTETICA,
                "quando": momento.isoformat(timespec="seconds"),
            })
    return opinioes


def carregar(conexao, empresas_pedidas: list[str], agora: datetime | None = None) -> dict:
    """Refaz a carga sintética nas empresas pedidas que existem no banco. Devolve o resumo.

    Recebe: conexao; empresas_pedidas — os códigos; agora — o momento da carga (os testes informam; padrão: agora).
    Devolve: {empresas: [as carregadas], faltaram: [as pedidas que não existem no banco], votos: {agente: quantos},
    total}. As opiniões sintéticas de antes saem primeiro; as da tela ficam.
    """
    momento = agora or datetime.now(timezone.utc)
    opiniao_dos_agentes._preparar(conexao)
    # As empresas que existem no banco (a pedida que não existe é avisada, e não inventada)
    existentes = set()
    for empresa in empresas.listar(conexao):
        existentes.add(empresa["empresa_id"])
    carregadas = []
    faltaram = []
    for empresa_id in empresas_pedidas:
        if empresa_id in existentes:
            carregadas.append(empresa_id)
        else:
            faltaram.append(empresa_id)
    logins_do_rh, login_do_banco = logins_de_quem_vota(conexao)
    opiniao_dos_agentes.remover_carga_sintetica(conexao)
    votos_por_agente = {}
    for agente in PERFIL_DOS_VOTOS:
        votos_por_agente[agente] = 0
    for empresa_id in carregadas:
        for opiniao in opinioes_da_empresa(empresa_id, logins_do_rh.get(empresa_id, []), login_do_banco, momento):
            opiniao_dos_agentes.gravar(conexao, opiniao)
            votos_por_agente[opiniao["agente"]] = votos_por_agente[opiniao["agente"]] + 1
    # Tudo de uma vez: ou a carga inteira entra, ou nada
    conexao.commit()
    total = 0
    for quantos in votos_por_agente.values():
        total = total + quantos
    return {"empresas": carregadas, "faltaram": faltaram, "votos": votos_por_agente, "total": total}


def main() -> None:
    """Lê as opções, confere o banco do .env e refaz (ou remove) a carga sintética. Escreve só números."""
    leitor = argparse.ArgumentParser(description="Gera os votos de demonstração do joinha (sem IA, semente fixa).")
    leitor.add_argument("--empresas", default="", help="os códigos separados por vírgula (padrão: a base viva)")
    leitor.add_argument("--remover", action="store_true", help="tira só a carga sintética")
    leitor.add_argument("--confirmo-o-postgres", action="store_true",
                        help="permite gravar no PostgreSQL de todos (depois da cópia de segurança)")
    opcoes = leitor.parse_args()
    try:
        conferir_o_banco(config.BANCO, opcoes.confirmo_o_postgres)
    except CargaRecusada as motivo:
        print("A carga parou:", motivo)
        sys.exit(1)
    conexao = banco.conectar()
    # Onde a carga grava, antes de gravar (o caminho do SQLite, ou o PostgreSQL)
    if banco.e_postgres(conexao):
        print("Banco: PostgreSQL")
    else:
        print("Banco: SQLite em", config.CAMINHO_BANCO)
    try:
        if opcoes.remover:
            print("Opiniões sintéticas removidas:", opiniao_dos_agentes.remover_carga_sintetica(conexao))
            return
        # As empresas pedidas, ou as da base viva
        pedidas = empresas_da_base_viva()
        if opcoes.empresas:
            pedidas = []
            for codigo in opcoes.empresas.split(","):
                if codigo.strip():
                    pedidas.append(codigo.strip())
        resumo = carregar(conexao, pedidas)
        print(f"Empresas com votos: {len(resumo['empresas'])}; total de votos: {resumo['total']}.")
        print("Votos por agente:", resumo["votos"])
        if resumo["faltaram"]:
            print("Não estão neste banco (ficaram sem votos):", ", ".join(resumo["faltaram"]))
        # A satisfação de cada agente desde o começo, para conferir as taxas
        numeros = opiniao_dos_agentes.satisfacao_dos_agentes(conexao)
        for agente in numeros["agentes"]:
            print(f"  {agente['nome']}: {agente['votos']} votos, satisfação {agente['satisfacao']}%")
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
