"""Configuração dos testes: nunca tocar no banco local de verdade.

Roda antes de qualquer import do projeto e aponta CAMINHO_BANCO para um arquivo temporário. Assim, a
API aberta pelo TestClient usa um banco descartável, e os usuários do banco local continuam intactos.

Os testes rodam no SQLite (padrão), mesmo que o .env da máquina diga BANCO=postgres. Para rodar a mesma bateria no
PostgreSQL (ADR-67), no banco de TESTES (POSTGRES_URL_TESTES, nunca o da aplicação):
    set BANCO_DOS_TESTES=postgres   (no PowerShell: $env:BANCO_DOS_TESTES="postgres")
    python -m pytest
Lá, cada arquivo de banco que um teste abriria vira um esquema novo (uma "pasta" de tabelas), apagado no fim.
"""
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from dotenv import dotenv_values

# Em qual banco esta rodada de testes acontece: "sqlite" (padrão) ou "postgres"
BANCO_DOS_TESTES = os.environ.get("BANCO_DOS_TESTES", "sqlite").strip().lower()
# O banco da aplicação nunca é usado nos testes: no PostgreSQL, só o endereço do banco de testes
os.environ["BANCO"] = BANCO_DOS_TESTES
os.environ["POSTGRES_URL"] = ""
if BANCO_DOS_TESTES == "postgres":
    # Lido direto do .env: a variável do banco de testes vira o endereço que a aplicação usa nesta rodada
    os.environ["POSTGRES_URL"] = dotenv_values(Path(__file__).resolve().parent.parent / ".env").get(
        "POSTGRES_URL_TESTES", "")

# Banco de dados descartável, numa pasta temporária
os.environ["CAMINHO_BANCO"] = str(Path(tempfile.mkdtemp()) / "teste_integra_folha.db")
# Testes sempre no modo MOCK: sem chave e sem custo
os.environ["MODE"] = "mock"
# O MOCK de reserva desligado, como no servidor (ADR-145): a IA real que não responde pausa. Cada teste da reserva a
# liga por conta própria; assim, o .env de quem roda não muda o resultado da bateria
os.environ["MOCK_DE_RESERVA"] = "nao"
# Originais enviados nos testes
os.environ["PASTA_UPLOADS"] = str(Path(tempfile.mkdtemp()) / "uploads")
# Arquivos finais homologados nos testes
os.environ["PASTA_HOMOLOGADOS"] = str(Path(tempfile.mkdtemp()) / "homologados")
# Pontos de salvamento do fluxo nos testes
os.environ["CAMINHO_CHECKPOINTS"] = str(Path(tempfile.mkdtemp()) / "checkpoints.db")
# O aprendizado do RAG fica desligado nos testes: nenhuma homologação de teste mexe no índice real (ADR-70)
os.environ["APRENDIZADO_DO_RAG"] = "desligado"
# Nenhum teste pode chegar às chaves reais dos provedores (nem gastar dinheiro): vazias antes de ler o .env.
# O load_dotenv não sobrescreve uma variável que já existe, então o .env não consegue preenchê-las
for variavel in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_BEARER_TOKEN_BEDROCK", "MODELO_GRANDE", "MODELO_PEQUENO"):
    os.environ[variavel] = ""
# Os testes partem sempre da rota direta (cada teste da rota Bedrock liga a rota por conta própria)
os.environ["ROTA_DA_IA"] = "direta"
# E com o formato garantido desligado, como no EXP-008 (cada teste do formato garantido liga por conta própria, ADR-107)
os.environ["INTERPRETADOR_FORMATO_GARANTIDO"] = "nao"
# E com o prompt padrão do Endomarketing, o que leva as KBs (cada teste do prompt v3, que fica como histórico, desliga
# a chave por conta própria); assim, o .env de quem roda não muda o resultado da bateria
os.environ["ENDOMARKETING_COM_AS_KBS"] = "sim"
# Os testes nunca gravam no painel de acompanhamento da sessão do Claude Code que os roda. Cada sessão tem a sua pasta no
# painel, achada por esta variável; sem ela, o painel usa a pasta padrão, que os testes trocam por uma pasta temporária
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
# Os testes nunca mexem no índice do RAG de verdade (storage/indices), que é o que o servidor da porta 8000 usa. Alguns
# testes gravam no índice que recebem: a bateria mudava 3 arquivos dele logo no começo, e o ChromaDB não foi feito para
# dois processos usarem a mesma pasta. Cada rodada usa uma cópia temporária (5 MB), pela variável PASTA_INDICES
PASTA_DOS_INDICES_DE_VERDADE = Path(__file__).resolve().parent.parent / "storage" / "indices"
PASTA_DOS_INDICES_DA_RODADA = Path(tempfile.mkdtemp()) / "indices"
if PASTA_DOS_INDICES_DE_VERDADE.exists():
    shutil.copytree(PASTA_DOS_INDICES_DE_VERDADE, PASTA_DOS_INDICES_DA_RODADA)
os.environ["PASTA_INDICES"] = str(PASTA_DOS_INDICES_DA_RODADA)


# Os esquemas criados nesta rodada no PostgreSQL (apagados no fim)
ESQUEMAS_CRIADOS = set()


def _esquema_do_arquivo(caminho) -> str:
    """O nome do esquema que faz o papel de um arquivo SQLite. Ex.: .../teste.db → "teste_3f9a1c..."."""
    impressao_digital = hashlib.sha1(str(caminho).encode("utf-8")).hexdigest()[:20]
    return f"teste_{impressao_digital}"


def _conectar_no_esquema_do_teste(caminho_sqlite=None):
    """No lugar de banco.conectar nos testes do PostgreSQL: cada arquivo vira um esquema novo e vazio."""
    from services import banco, config
    esquema = _esquema_do_arquivo(caminho_sqlite or config.CAMINHO_BANCO)
    # Na primeira vez em que o arquivo aparece, o esquema é criado do zero (apagando sobra de rodada anterior)
    if esquema not in ESQUEMAS_CRIADOS:
        conexao_de_preparo = banco.conectar_postgres(config.POSTGRES_URL)
        conexao_de_preparo.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")
        conexao_de_preparo.execute(f"CREATE SCHEMA {esquema}")
        conexao_de_preparo.commit()
        conexao_de_preparo.close()
        ESQUEMAS_CRIADOS.add(esquema)
    # A conexão fecha sozinha quando o teste deixa de usá-la (o Python recolhe o objeto)
    return banco.conectar_postgres(config.POSTGRES_URL, esquema)


@pytest.fixture(autouse=True)
def fechar_conexoes_do_postgres():
    """Depois de cada teste no PostgreSQL, fecha os pontos de salvamento do fluxo que ele abriu.

    Eles ficam guardados para reaproveitar (workflows/fluxo_empresa.py); sem fechar, cada teste deixaria uma conexão
    aberta, e o servidor aceita um número limitado. Se o próximo teste precisar, um novo é aberto.
    """
    yield
    if BANCO_DOS_TESTES != "postgres":
        return
    from workflows import fluxo_empresa
    # Pontos de salvamento do fluxo: um por esquema, e cada teste tem o seu
    for checkpointer in fluxo_empresa.CHECKPOINTERS_DO_POSTGRES.values():
        checkpointer.conn.close()
    fluxo_empresa.CHECKPOINTERS_DO_POSTGRES.clear()


def pytest_configure(config):
    """Registra a marca somente_sqlite e, na rodada do PostgreSQL, troca a abertura do banco."""
    config.addinivalue_line("markers", "somente_sqlite: teste do próprio arquivo SQLite (pulado no PostgreSQL)")
    if BANCO_DOS_TESTES != "postgres":
        return
    if not os.environ["POSTGRES_URL"]:
        raise pytest.UsageError("BANCO_DOS_TESTES=postgres, mas falta POSTGRES_URL_TESTES no .env.")
    from services import banco
    banco.conectar = _conectar_no_esquema_do_teste


def pytest_collection_modifyitems(config, items):
    """Na rodada do PostgreSQL, pula os testes marcados como somente_sqlite."""
    if BANCO_DOS_TESTES != "postgres":
        return
    pulo = pytest.mark.skip(reason="testa o arquivo SQLite; não se aplica ao PostgreSQL")
    for teste in items:
        if "somente_sqlite" in teste.keywords:
            teste.add_marker(pulo)


def pytest_sessionfinish(session, exitstatus):
    """Na rodada do PostgreSQL, apaga os esquemas criados pelos testes."""
    if BANCO_DOS_TESTES != "postgres" or not ESQUEMAS_CRIADOS:
        return
    from services import banco, config
    conexao_de_limpeza = banco.conectar_postgres(config.POSTGRES_URL)
    for esquema in ESQUEMAS_CRIADOS:
        conexao_de_limpeza.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")
    conexao_de_limpeza.commit()
    conexao_de_limpeza.close()
