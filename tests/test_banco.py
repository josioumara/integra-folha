"""A porta do banco (services/banco.py) e a migração do SQLite para o PostgreSQL (ADR-67).

As primeiras provas rodam em qualquer máquina: conferem a tradução dos comandos. As outras precisam do PostgreSQL
(POSTGRES_URL_TESTES no .env) e são puladas quando ele não existe; cada uma usa um esquema novo, apagado no fim.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import pytest
from dotenv import dotenv_values
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from models.contratos import Perfil
from scripts import migrar_sqlite_para_postgres
from services import auth, banco, catalogo, execucoes
from workflows import fluxo_empresa

# O endereço do banco de testes do PostgreSQL (vazio: as provas do PostgreSQL são puladas)
URL_DOS_TESTES = dotenv_values(Path(__file__).resolve().parent.parent / ".env").get("POSTGRES_URL_TESTES", "")
precisa_do_postgres = pytest.mark.skipif(not URL_DOS_TESTES, reason="sem POSTGRES_URL_TESTES no .env")


def test_sinal_dos_valores_vira_o_do_postgres():
    """O "?" do SQLite vira o "%s" do PostgreSQL."""
    traduzido = banco.traduzir_para_postgres("SELECT login FROM usuarios WHERE login = ? AND ativo = ?")
    assert traduzido == "SELECT login FROM usuarios WHERE login = %s AND ativo = %s"


def test_numero_automatico_vira_bigserial_e_toda_tabela_ganha_rowid():
    """AUTOINCREMENT vira BIGSERIAL, e a tabela ganha a coluna rowid mesmo com comentário na última linha."""
    comando = """CREATE TABLE IF NOT EXISTS t (
                     id     INTEGER PRIMARY KEY AUTOINCREMENT,
                     origem TEXT NOT NULL   -- REAL ou MOCK
                 )"""
    traduzido = banco.traduzir_para_postgres(comando)
    assert "BIGSERIAL PRIMARY KEY" in traduzido
    # A coluna nova fica numa linha própria, depois do comentário (que termina no fim da linha dele)
    assert traduzido.endswith("\n, rowid BIGSERIAL)")
    assert traduzido.index("-- REAL ou MOCK") < traduzido.index("rowid BIGSERIAL")


def test_soma_volta_como_no_sqlite():
    """Número sem casas decimais vira inteiro; com casas, float (e nunca Decimal)."""
    assert banco._numero_como_no_sqlite("52") == 52
    assert banco._numero_como_no_sqlite("52.5") == 52.5


@pytest.fixture
def esquema_novo():
    """Um esquema vazio no banco de testes do PostgreSQL; devolve o nome e apaga tudo no fim."""
    nome_do_esquema = f"teste_banco_{uuid.uuid4().hex[:12]}"
    conexao_de_preparo = banco.conectar_postgres(URL_DOS_TESTES)
    conexao_de_preparo.execute(f"CREATE SCHEMA {nome_do_esquema}")
    yield nome_do_esquema
    # Fecha os pontos de salvamento que o teste tenha aberto neste esquema
    for checkpointer in fluxo_empresa.CHECKPOINTERS_DO_POSTGRES.values():
        checkpointer.conn.close()
    fluxo_empresa.CHECKPOINTERS_DO_POSTGRES.clear()
    conexao_de_preparo.execute(f"DROP SCHEMA {nome_do_esquema} CASCADE")
    conexao_de_preparo.close()


@precisa_do_postgres
def test_leitura_nao_deixa_transacao_aberta_que_trave_outra_conexao(esquema_novo):
    """Uma conexão lê a visão; outra consegue apagá-la na hora (antes, a leitura segurava a trava e tudo parava)."""
    leitora = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    outra = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    leitora.execute("CREATE TABLE numeros (valor INTEGER)")
    leitora.execute("CREATE VIEW IF NOT EXISTS resumo AS SELECT SUM(valor) AS total FROM numeros")
    leitora.execute("SELECT total FROM resumo").fetchone()
    # Se a leitura tivesse deixado a transação aberta, este comando esperaria; com o limite, daria erro em 2 s
    outra.execute("SET lock_timeout = '2s'")
    outra.execute("DROP VIEW resumo")


@precisa_do_postgres
def test_visao_que_ja_existe_nao_e_recriada(esquema_novo):
    """CREATE VIEW IF NOT EXISTS duas vezes: a segunda não faz nada, como no SQLite."""
    conexao = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    conexao.execute("CREATE TABLE numeros (valor INTEGER)")
    conexao.execute("CREATE VIEW IF NOT EXISTS resumo AS SELECT SUM(valor) AS total FROM numeros")
    conexao.execute("CREATE VIEW IF NOT EXISTS resumo AS SELECT 1 AS outra_coluna")
    assert banco.colunas_da_tabela(conexao, "resumo") == ["total"]


@precisa_do_postgres
def test_gravacao_so_vale_depois_do_commit(esquema_novo):
    """Gravação sem commit é desfeita pelo rollback; com commit, fica."""
    conexao = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    auth.preparar_tabela(conexao)
    auth.cadastrar_usuario(conexao, "banco.teste", "senha-forte-1", Perfil.BANCO)
    conexao.execute("UPDATE usuarios SET ativo = 0 WHERE login = ?", ("banco.teste",))
    conexao.rollback()
    # O rollback desfez só a desativação; o cadastro já tinha sido confirmado
    assert auth.listar_usuarios(conexao)[0].ativo is True


@precisa_do_postgres
def test_usuario_da_aplicacao_nao_e_superusuario(esquema_novo):
    """A aplicação entra no banco com um usuário comum (menor privilégio)."""
    conexao = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    superusuario = conexao.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]
    assert superusuario is False


class EstadoDoContador(TypedDict):
    """O estado do fluxo mínimo usado na prova da migração."""
    passos: int


def _somar_um(estado: EstadoDoContador) -> dict:
    """Etapa do fluxo mínimo: soma 1 ao contador."""
    return {"passos": estado["passos"] + 1}


def _montar_banco_sqlite(pasta: Path) -> tuple[Path, Path]:
    """Um banco SQLite com usuários e execuções, e um arquivo de pontos de salvamento com um fluxo já rodado."""
    caminho_do_banco = pasta / "origem.db"
    # Aberto direto no SQLite: a origem da migração é sempre um arquivo, qualquer que seja o banco da rodada
    conexao = sqlite3.connect(caminho_do_banco)
    auth.preparar_tabela(conexao)
    auth.cadastrar_usuario(conexao, "empresa.aurora", "senha-forte-1", Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "banco.especialista", "senha-forte-2", Perfil.BANCO)
    # O catálogo nasce com a versão 1 de cada empresa (carga automática)
    catalogo._preparar(conexao)
    agora = datetime.now(timezone.utc)
    execucoes.registrar(conexao, "proc-1", "EMP001", "perfilar", "Regra", agora, agora, "OK")
    execucoes.registrar(conexao, "proc-1", "EMP001", "mapear", "Interpretador", agora, agora, "OK", modelo="mock")
    conexao.close()
    # Um fluxo mínimo rodado com o ponto de salvamento no SQLite
    caminho_dos_pontos = pasta / "pontos.db"
    fluxo = _fluxo_minimo().compile(
        checkpointer=SqliteSaver(sqlite3.connect(caminho_dos_pontos, check_same_thread=False)))
    fluxo.invoke({"passos": 0}, {"configurable": {"thread_id": "proc-1"}})
    return caminho_do_banco, caminho_dos_pontos


def _fluxo_minimo() -> StateGraph:
    """Um fluxo de uma etapa só (somar_um), para provar que o ponto de salvamento migra."""
    grafo = StateGraph(EstadoDoContador)
    grafo.add_node("somar_um", _somar_um)
    grafo.add_edge(START, "somar_um")
    grafo.add_edge("somar_um", END)
    return grafo


@precisa_do_postgres
def test_migracao_copia_tudo_e_o_login_continua_funcionando(tmp_path, esquema_novo):
    """Depois da migração: mesmas contagens, login com a mesma senha, próximo id certo e o fluxo no mesmo ponto."""
    caminho_do_banco, caminho_dos_pontos = _montar_banco_sqlite(tmp_path)
    destino = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    resultado = migrar_sqlite_para_postgres.migrar(caminho_do_banco, caminho_dos_pontos, destino)
    # Cada tabela tem o mesmo número de linhas nos dois bancos
    for no_sqlite, no_postgres in resultado["tabelas"].values():
        assert no_sqlite == no_postgres
    assert resultado["tabelas"]["usuarios"] == (2, 2)
    # O catálogo não fica duplicado: a carga automática do PostgreSQL deu lugar aos documentos do SQLite
    assert resultado["tabelas"]["catalogo_documentos"] == (6, 6)
    # A senha continua valendo: o hash foi copiado como estava
    assert auth.autenticar(destino, "empresa.aurora", "senha-forte-1").empresa_id == "EMP001"
    # O número automático continua de onde parou: a próxima execução recebe o id 3
    agora = datetime.now(timezone.utc)
    execucoes.registrar(destino, "proc-2", "EMP001", "perfilar", "Regra", agora, agora, "OK")
    ids = []
    for (numero,) in destino.execute("SELECT id FROM execucoes_agentes ORDER BY id"):
        ids.append(numero)
    assert ids == [1, 2, 3]
    # O fluxo migrado está no mesmo ponto: o contador vale 1 no PostgreSQL
    assert resultado["pontos_de_salvamento"] > 0
    fluxo = _fluxo_minimo().compile(checkpointer=fluxo_empresa.abrir_checkpointer(destino))
    assert fluxo.get_state({"configurable": {"thread_id": "proc-1"}}).values == {"passos": 1}


@precisa_do_postgres
def test_migracao_nunca_sobrescreve_um_postgres_com_dados(tmp_path, esquema_novo):
    """Se o PostgreSQL já tem dados, a migração para sem copiar nada."""
    caminho_do_banco, caminho_dos_pontos = _montar_banco_sqlite(tmp_path)
    destino = banco.conectar_postgres(URL_DOS_TESTES, esquema_novo)
    migrar_sqlite_para_postgres.migrar(caminho_do_banco, caminho_dos_pontos, destino)
    with pytest.raises(migrar_sqlite_para_postgres.PostgresJaTemDados):
        migrar_sqlite_para_postgres.migrar(caminho_do_banco, caminho_dos_pontos, destino)
    # Continuam só os 2 usuários da primeira migração
    assert len(auth.listar_usuarios(destino)) == 2
