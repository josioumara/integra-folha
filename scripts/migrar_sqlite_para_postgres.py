"""Copia os dados do banco SQLite local para o PostgreSQL (ADR-67; docs/banco_de_dados.md).

Serve para a troca de banco sem perder o que já foi cadastrado na máquina: usuários, parâmetros, catálogos,
processamentos, execuções e também os pontos de salvamento do fluxo (onde cada processamento parou no LangGraph).

Como funciona:
1. recusa seguir se o PostgreSQL já tiver dados (nunca sobrescreve nada);
2. cria no PostgreSQL todas as tabelas do sistema (as mesmas funções que a aplicação usa ao abrir). A criação do
   catálogo carrega sozinha a versão 1 dos documentos; essa carga automática é apagada, porque os documentos
   (com as versões que o banco já tenha cadastrado) vêm do SQLite;
3. copia cada tabela, linha por linha, na ordem em que as linhas entraram no SQLite;
4. acerta o contador das tabelas com número automático (o próximo número continua de onde o SQLite parou);
5. copia os pontos de salvamento do fluxo, do mais antigo para o mais recente;
6. confere: cada tabela tem de ter o mesmo número de linhas nos dois bancos.

O arquivo SQLite não é alterado. Para rodar: python scripts/migrar_sqlite_para_postgres.py
(antes: POSTGRES_URL no .env, criada por scripts/preparar_postgres.py)
"""
import sqlite3
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agents import endomarketing  # noqa: E402
from services import (auditoria, auth, banco, catalogo, config, correcoes, execucoes, homologacao,  # noqa: E402
                      mapeamentos, motor_planejamento, normalizador, parametros, processamentos, sessoes,
                      tentativas_de_login, validador)

# As funções que criam as tabelas de cada parte do sistema (as mesmas que a aplicação chama)
FUNCOES_QUE_CRIAM_TABELAS = (
    auth.preparar_tabela, auditoria._preparar, catalogo._preparar, correcoes._preparar, execucoes._preparar,
    homologacao._preparar, mapeamentos._preparar, motor_planejamento.preparar_tabelas, normalizador._preparar, parametros._preparar,
    processamentos._preparar, sessoes.preparar_tabela, tentativas_de_login.preparar_tabela, validador._preparar,
    endomarketing._preparar,
)
# Tabelas com número automático (id): depois da cópia, o contador precisa continuar do maior número copiado
TABELAS_COM_NUMERO_AUTOMATICO = ("eventos", "execucoes_agentes", "simulacao_ganho")
# Tabela interna do SQLite (guarda os contadores dele): não é dado do sistema
TABELAS_INTERNAS_DO_SQLITE = ("sqlite_sequence",)


def tabelas_do_sqlite(conexao_sqlite) -> list[str]:
    """Os nomes das tabelas de dados do arquivo SQLite, em ordem alfabética (sem as internas e sem as visões)."""
    consulta = conexao_sqlite.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    nomes = []
    for (nome,) in consulta:
        # A tabela de contadores é do próprio SQLite
        if nome not in TABELAS_INTERNAS_DO_SQLITE:
            nomes.append(nome)
    return nomes


def contar_linhas(conexao, tabela: str) -> int:
    """Quantas linhas a tabela tem."""
    return conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def criar_tabelas_no_postgres(conexao_postgres) -> None:
    """Cria no PostgreSQL todas as tabelas do sistema (as que já existem ficam como estão)."""
    for criar_tabelas in FUNCOES_QUE_CRIAM_TABELAS:
        criar_tabelas(conexao_postgres)
    conexao_postgres.commit()


def tabelas_com_dados(conexao_postgres, tabelas: list[str]) -> list[str]:
    """As tabelas que já existem no PostgreSQL e têm alguma linha (se houver, a migração não segue)."""
    com_dados = []
    for tabela in tabelas:
        # Tabela sem colunas é tabela que ainda não existe: não tem dados
        tabela_existe = len(banco.colunas_da_tabela(conexao_postgres, tabela)) > 0
        if tabela_existe and contar_linhas(conexao_postgres, tabela) > 0:
            com_dados.append(tabela)
    return com_dados


def apagar_carga_automatica_do_catalogo(conexao_postgres) -> None:
    """Apaga os documentos da versão 1 que a criação da tabela do catálogo carregou sozinha."""
    conexao_postgres.execute("DELETE FROM catalogo_documentos WHERE criado_por = ?", (catalogo.AUTOR_DA_VERSAO_1,))


def copiar_tabela(conexao_sqlite, conexao_postgres, tabela: str) -> None:
    """Copia todas as linhas de uma tabela, na ordem em que entraram no SQLite."""
    # As colunas vêm do SQLite; no PostgreSQL a coluna rowid se preenche sozinha, na mesma ordem
    colunas = banco.colunas_da_tabela(conexao_sqlite, tabela)
    lista_de_colunas = ", ".join(colunas)
    # Um "?" para cada coluna
    sinais = ", ".join(["?"] * len(colunas))
    comando_de_insercao = f"INSERT INTO {tabela} ({lista_de_colunas}) VALUES ({sinais})"
    # ORDER BY rowid: a ordem em que as linhas foram gravadas no SQLite
    for linha in conexao_sqlite.execute(f"SELECT {lista_de_colunas} FROM {tabela} ORDER BY rowid"):
        conexao_postgres.execute(comando_de_insercao, linha)


def acertar_contador(conexao_postgres, tabela: str) -> None:
    """Faz o número automático (id) da tabela continuar depois do maior id copiado."""
    maior_id = conexao_postgres.execute(f"SELECT MAX(id) FROM {tabela}").fetchone()[0]
    # Tabela vazia: o contador continua no começo
    if maior_id is None:
        return
    # pg_get_serial_sequence acha o contador da coluna id; setval diz qual foi o último número usado
    conexao_postgres.execute(f"SELECT setval(pg_get_serial_sequence('{tabela}', 'id'), ?)", (maior_id,))


def copiar_pontos_de_salvamento(caminho_dos_pontos: Path, conexao_postgres) -> int:
    """Copia os pontos de salvamento do fluxo (LangGraph) do arquivo SQLite para o PostgreSQL. Devolve quantos.

    Usa as próprias bibliotecas do LangGraph: lê cada ponto do SQLite e grava no PostgreSQL, do mais antigo para o
    mais recente, junto com as gravações pendentes de cada um (o que uma etapa deixou para a próxima).
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    from workflows import fluxo_empresa
    # Sem o arquivo, não há o que copiar
    if not caminho_dos_pontos.exists():
        return 0
    origem = SqliteSaver(sqlite3.connect(caminho_dos_pontos, check_same_thread=False))
    # O ponto de salvamento no mesmo banco (e esquema) da conexão do PostgreSQL
    destino = fluxo_empresa.abrir_checkpointer(conexao_postgres)
    # list(None) traz todos os pontos, do mais recente para o mais antigo: invertemos
    pontos = list(origem.list(None))
    pontos.reverse()
    for ponto in pontos:
        # O ponto é gravado "depois" do ponto anterior (parent), como o LangGraph faz ao rodar
        configuracao_do_pai = ponto.parent_config or {"configurable": {
            "thread_id": ponto.config["configurable"]["thread_id"],
            "checkpoint_ns": ponto.config["configurable"].get("checkpoint_ns", "")}}
        nova_configuracao = destino.put(configuracao_do_pai, ponto.checkpoint, ponto.metadata,
                                        ponto.checkpoint["channel_versions"])
        copiar_gravacoes_pendentes(destino, nova_configuracao, ponto.pending_writes or [])
    return len(pontos)


def copiar_gravacoes_pendentes(destino, configuracao, gravacoes_pendentes) -> None:
    """Grava no destino as gravações pendentes de um ponto, agrupadas pela tarefa que as fez."""
    gravacoes_por_tarefa = {}
    # Cada gravação pendente é (tarefa, canal, valor)
    for tarefa, canal, valor in gravacoes_pendentes:
        # Primeira gravação desta tarefa: começa a lista dela
        if tarefa not in gravacoes_por_tarefa:
            gravacoes_por_tarefa[tarefa] = []
        gravacoes_por_tarefa[tarefa].append((canal, valor))
    for tarefa, gravacoes in gravacoes_por_tarefa.items():
        destino.put_writes(configuracao, gravacoes, tarefa)


class PostgresJaTemDados(Exception):
    """O PostgreSQL já tem dados: a migração não copia nada, para nunca sobrescrever."""


def migrar(caminho_sqlite: Path, caminho_dos_pontos: Path, conexao_postgres) -> dict:
    """Copia o banco SQLite e os pontos de salvamento para o PostgreSQL da conexão.

    Devolve {"tabelas": {tabela: (linhas no SQLite, linhas no PostgreSQL)}, "pontos_de_salvamento": quantidade}.
    """
    conexao_sqlite = sqlite3.connect(caminho_sqlite)
    tabelas = tabelas_do_sqlite(conexao_sqlite)
    # Nunca sobrescreve: se o PostgreSQL já tem dados, para aqui (antes de criar qualquer coisa)
    ja_preenchidas = tabelas_com_dados(conexao_postgres, tabelas)
    if ja_preenchidas:
        conexao_sqlite.close()
        raise PostgresJaTemDados(f"O PostgreSQL já tem dados em {', '.join(ja_preenchidas)}; nada foi copiado.")
    criar_tabelas_no_postgres(conexao_postgres)
    # O catálogo vem do SQLite: a carga automática da criação da tabela sai, para não duplicar
    if "catalogo_documentos" in tabelas:
        apagar_carga_automatica_do_catalogo(conexao_postgres)
    for tabela in tabelas:
        copiar_tabela(conexao_sqlite, conexao_postgres, tabela)
    for tabela in TABELAS_COM_NUMERO_AUTOMATICO:
        acertar_contador(conexao_postgres, tabela)
    # Tudo numa transação só: ou copia tudo, ou nada
    conexao_postgres.commit()
    # Conferência: quantas linhas cada tabela tem nos dois bancos
    contagens = {}
    for tabela in tabelas:
        contagens[tabela] = (contar_linhas(conexao_sqlite, tabela), contar_linhas(conexao_postgres, tabela))
    conexao_sqlite.close()
    pontos = copiar_pontos_de_salvamento(caminho_dos_pontos, conexao_postgres)
    return {"tabelas": contagens, "pontos_de_salvamento": pontos}


def main() -> None:
    """Migra o SQLite do .env para o PostgreSQL do .env e mostra a conferência."""
    if not config.POSTGRES_URL:
        sys.exit("Falta POSTGRES_URL no .env (rode antes scripts/preparar_postgres.py).")
    if not config.CAMINHO_BANCO.exists():
        sys.exit(f"Não achei o banco SQLite em {config.CAMINHO_BANCO}.")
    # O destino é sempre o PostgreSQL, qualquer que seja o BANCO do .env
    conexao_postgres = banco.conectar_postgres(config.POSTGRES_URL)
    try:
        resultado = migrar(config.CAMINHO_BANCO, config.CAMINHO_CHECKPOINTS, conexao_postgres)
    except PostgresJaTemDados as aviso:
        sys.exit(str(aviso))
    for tabela, (no_sqlite, no_postgres) in resultado["tabelas"].items():
        situacao = "ok" if no_sqlite == no_postgres else "DIFERENTE"
        print(f"migrar: {tabela}: SQLite {no_sqlite} -> PostgreSQL {no_postgres} ({situacao})")
    print(f"migrar: pontos de salvamento do fluxo copiados: {resultado['pontos_de_salvamento']}")


if __name__ == "__main__":
    main()
