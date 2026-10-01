"""A porta única para o banco de dados: SQLite ou PostgreSQL, escolhido no .env (ADR-67; docs/banco_de_dados.md).

O resto do sistema abre o banco sempre por aqui e escreve SQL portátil, que funciona nos dois. Esta porta cuida das
poucas diferenças que sobram:
- o sinal dos valores nos comandos: o SQLite usa "?", o PostgreSQL usa "%s" (a tradução é automática);
- o número automático de linha: "INTEGER PRIMARY KEY AUTOINCREMENT" no SQLite vira "BIGSERIAL PRIMARY KEY";
- a visão (VIEW): o PostgreSQL não tem "CREATE VIEW IF NOT EXISTS"; esta porta confere antes se a visão existe;
- quando a transação abre: como o sqlite3 do Python, só antes de uma gravação (INSERT, UPDATE, DELETE), e fecha no
  commit. Uma leitura não deixa transação aberta: no PostgreSQL, transação aberta segura "travas" que fariam outra
  conexão esperar (ex.: ao recriar uma visão);
- a ordem de gravação: toda tabela do SQLite tem, escondida, a coluna "rowid" (1, 2, 3... na ordem em que as linhas
  entraram). O PostgreSQL não tem; esta porta acrescenta a coluna rowid em cada tabela criada lá, para que
  "ORDER BY criado_em, rowid" funcione igual nos dois;
- a lista de colunas de uma tabela: cada banco pergunta de um jeito (colunas_da_tabela).
O que é igual nos dois fica igual no código: por exemplo, "INSERT ... ON CONFLICT (...) DO UPDATE" (gravar ou atualizar)
e "ON CONFLICT DO NOTHING" (gravar só se ainda não existe) funcionam no SQLite e no PostgreSQL.

Quando usar cada um:
- SQLite (padrão): um arquivo, sem servidor. É o banco dos testes automáticos e de quem clona o projeto para
  reproduzir tudo sem instalar nada;
- PostgreSQL: o ambiente local de uso e a produção. Aceita muitas gravações ao mesmo tempo, usuários e permissões no
  banco, backup e réplica (os motivos da escolha estão em docs/banco_de_dados.md).
"""
import sqlite3
from pathlib import Path

from services import config

# O que só existe no SQLite e o equivalente no PostgreSQL (usado para traduzir os comandos de criação de tabela)
TRADUCOES_PARA_POSTGRES = (
    ("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY"),
)
# Os comandos que gravam dados: antes deles, a porta abre uma transação (como o sqlite3 do Python)
COMANDOS_DE_GRAVACAO = ("INSERT", "UPDATE", "DELETE")
# Como começa a criação de uma visão no SQLite
CRIACAO_DE_VISAO = "CREATE VIEW IF NOT EXISTS"


def traduzir_para_postgres(comando: str) -> str:
    """O comando SQL escrito para o SQLite, do jeito que o PostgreSQL entende.

    Ex.: "SELECT login FROM usuarios WHERE login = ?" → "SELECT login FROM usuarios WHERE login = %s".
    """
    # Troca cada trecho que só o SQLite entende pelo equivalente do PostgreSQL
    for do_sqlite, do_postgres in TRADUCOES_PARA_POSTGRES:
        comando = comando.replace(do_sqlite, do_postgres)
    # Criação de tabela: acrescenta a coluna rowid, a ordem de gravação que o SQLite tem sozinho
    if comando.lstrip().startswith("CREATE TABLE"):
        comando = _acrescentar_rowid(comando)
    # O sinal dos valores: "?" no SQLite, "%s" no PostgreSQL (nenhum comando do projeto usa "?" dentro de texto)
    return comando.replace("?", "%s")


def _acrescentar_rowid(comando_de_criacao: str) -> str:
    """Acrescenta a coluna rowid (número automático na ordem de gravação) antes do último parêntese da tabela.

    Ex.: "CREATE TABLE t (a TEXT)" → "CREATE TABLE t (a TEXT, rowid BIGSERIAL)".
    """
    # O último ")" fecha a lista de colunas
    posicao_do_fim = comando_de_criacao.rindex(")")
    # Em linha própria: a última coluna pode terminar com um comentário ("-- ..."), que engoliria o resto da linha
    return comando_de_criacao[:posicao_do_fim] + "\n, rowid BIGSERIAL" + comando_de_criacao[posicao_do_fim:]


class ConexaoPostgres:
    """Uma conexão com o PostgreSQL que se comporta como a do SQLite para o resto do sistema.

    O sistema chama conexao.execute(comando, valores), conexao.commit() e percorre ou lê o resultado com fetchone():
    esta classe traduz o comando e repassa à conexão do psycopg (a biblioteca oficial do PostgreSQL para Python).
    """

    def __init__(self, conexao_psycopg, url: str, esquema: str | None = None):
        """conexao_psycopg: a conexão aberta pelo psycopg; url e esquema: onde ela foi aberta.

        url e esquema ficam guardados para o ponto de salvamento do fluxo (LangGraph) abrir a sua própria conexão
        no mesmo lugar (workflows/fluxo_empresa.py).
        """
        self.conexao = conexao_psycopg
        self.url = url
        self.esquema = esquema

    def execute(self, comando: str, valores=()):
        """Executa o comando (traduzido) e devolve o cursor, que se lê como o do SQLite."""
        # A primeira palavra diz o tipo do comando (SELECT, INSERT, CREATE...)
        primeira_palavra = comando.lstrip().split(" ", 1)[0].upper()
        # Gravação fora de transação: abre uma, que fica aberta até o commit (ou o rollback)
        if primeira_palavra in COMANDOS_DE_GRAVACAO and not self._em_transacao():
            self.conexao.execute("BEGIN")
        # Visão que já existe não é recriada (é o que "IF NOT EXISTS" quer dizer no SQLite)
        if comando.lstrip().startswith(CRIACAO_DE_VISAO) and self._visao_existe(comando):
            return self.conexao.execute("SELECT 1 WHERE false")
        try:
            return self.conexao.execute(traduzir_para_postgres(comando).replace(CRIACAO_DE_VISAO, "CREATE VIEW"),
                                        valores)
        except Exception:
            # No PostgreSQL, um erro "trava" a transação até ela ser desfeita: desfaz e avisa o erro original
            self.rollback()
            raise

    def _em_transacao(self) -> bool:
        """True se há uma transação aberta nesta conexão."""
        from psycopg.pq import TransactionStatus
        return self.conexao.info.transaction_status != TransactionStatus.IDLE

    def _visao_existe(self, comando_de_criacao: str) -> bool:
        """True se a visão do comando "CREATE VIEW IF NOT EXISTS nome AS ..." já existe no esquema em uso."""
        # O nome é a palavra logo depois de "CREATE VIEW IF NOT EXISTS"
        nome_da_visao = comando_de_criacao.lstrip()[len(CRIACAO_DE_VISAO):].split()[0]
        # to_regclass devolve vazio (NULL) quando o nome não existe
        consulta = self.conexao.execute("SELECT to_regclass(%s)", (nome_da_visao,))
        return consulta.fetchone()[0] is not None

    def commit(self) -> None:
        """Confirma as gravações da transação aberta (sem transação aberta, não há o que confirmar)."""
        if self._em_transacao():
            self.conexao.execute("COMMIT")

    def rollback(self) -> None:
        """Desfaz as gravações ainda não confirmadas."""
        if self._em_transacao():
            self.conexao.execute("ROLLBACK")

    def close(self) -> None:
        """Fecha a conexão."""
        self.conexao.close()


def _numero_como_no_sqlite(texto_do_numero: str):
    """Um número "numeric" do PostgreSQL como o SQLite devolveria: inteiro se não tem casas decimais; senão, float.

    Ex.: "52" → 52; "52.5" → 52.5. Sem isso, as somas (SUM) chegariam como Decimal e quebrariam o JSON das telas.
    """
    if "." in texto_do_numero:
        return float(texto_do_numero)
    return int(texto_do_numero)


def _ensinar_numeros_como_no_sqlite(conexao_psycopg) -> None:
    """Faz a conexão ler os números "numeric" (o tipo das somas no PostgreSQL) do jeito do SQLite."""
    from psycopg.adapt import Loader

    class LeitorDeNumero(Loader):
        """Lê um valor numeric (em texto) com _numero_como_no_sqlite."""

        def load(self, dados):
            return _numero_como_no_sqlite(bytes(dados).decode("ascii"))

    # Vale só para esta conexão
    conexao_psycopg.adapters.register_loader("numeric", LeitorDeNumero)


def opcoes_do_esquema(esquema: str | None) -> str:
    """A opção de conexão que faz o PostgreSQL usar o esquema (vazio: o esquema padrão, "public").

    Esquema é uma "pasta" de tabelas dentro do banco; os testes usam um esquema novo por teste.
    """
    if not esquema:
        return ""
    # search_path diz em qual esquema as tabelas são criadas e procuradas
    return f"-c search_path={esquema}"


def conectar_postgres(url: str, esquema: str | None = None) -> ConexaoPostgres:
    """Abre uma conexão com o PostgreSQL. esquema: uma "pasta" separada dentro do banco (usada pelos testes)."""
    # Importado só aqui: quem usa SQLite não precisa ter o psycopg instalado
    import psycopg
    opcoes = opcoes_do_esquema(esquema)
    # ClientCursor: os valores entram no comando antes de ele ir ao servidor, como no SQLite. Sem isso, o PostgreSQL
    # recusa "(? IS NULL OR status = ?)" quando o valor é vazio, porque não consegue descobrir o tipo dele.
    # autocommit=True: cada comando vale na hora; a transação só é aberta antes de uma gravação (veja execute)
    conexao_psycopg = psycopg.connect(url, options=opcoes, cursor_factory=psycopg.ClientCursor, autocommit=True)
    # Somas voltam como inteiro (ou float), igual ao SQLite, e não como Decimal
    _ensinar_numeros_como_no_sqlite(conexao_psycopg)
    return ConexaoPostgres(conexao_psycopg, url, esquema)


def conectar(caminho_sqlite: Path | None = None):
    """Abre o banco configurado no .env: PostgreSQL (BANCO=postgres) ou o arquivo SQLite.

    caminho_sqlite: no SQLite, qual arquivo abrir (sem informar, o do .env).
    """
    if config.BANCO == "postgres":
        if not config.POSTGRES_URL:
            raise RuntimeError("BANCO=postgres, mas falta POSTGRES_URL no .env (rode scripts/preparar_postgres.py).")
        return conectar_postgres(config.POSTGRES_URL)
    caminho_do_banco = Path(caminho_sqlite or config.CAMINHO_BANCO)
    # Cria a pasta do arquivo, se ainda não existir
    caminho_do_banco.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: a API atende cada pedido numa "thread" (linha de execução) diferente
    return sqlite3.connect(caminho_do_banco, check_same_thread=False)


def e_postgres(conexao) -> bool:
    """True se a conexão é com o PostgreSQL."""
    return isinstance(conexao, ConexaoPostgres)


def colunas_da_tabela(conexao, tabela: str) -> list[str]:
    """Os nomes das colunas de uma tabela (vazio se ela não existe). Usado para acrescentar colunas novas.

    Ex.: colunas_da_tabela(conexao, "usuarios") → ["login", "senha_hash", "perfil", ...].
    """
    nomes = []
    if e_postgres(conexao):
        # No PostgreSQL, o catálogo de colunas do esquema em uso
        consulta = conexao.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? ORDER BY ordinal_position", (tabela,))
        for (nome,) in consulta:
            nomes.append(nome)
        return nomes
    # No SQLite, o PRAGMA table_info descreve cada coluna; a posição 1 é o nome
    for informacao in conexao.execute(f"PRAGMA table_info({tabela})"):
        nomes.append(informacao[1])
    return nomes
