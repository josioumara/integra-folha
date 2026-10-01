"""Teto de gasto com IA por dia e por mês, valendo para a aplicação inteira (ADR-131).

Por que existe: o cliente de IA (services/llm_client.py) já tinha um teto, mas ele vale para UM cliente, e cada pedido
feito à aplicação cria o seu. Cem pedidos de US$ 0,50 passavam, um por um, por baixo de um teto de US$ 10. Este
arquivo soma o custo de TODAS as chamadas reais numa tabela do banco e compara com dois tetos: o do dia e o do mês.
O que for atingido primeiro pausa a IA: o cliente de IA deixa de chamar o provedor até o dia (ou o mês) virar, ou até
o banco subir o teto.

Analogia: é o limite do cartão, com um limite diário e um mensal. Cada compra pode ser pequena, mas a soma tem limite,
seja qual for a loja (o agente) ou o caixa (o pedido); estourou qualquer um dos dois, o cartão para de passar.

Os tetos moram no banco de dados, e não no código: o especialista do banco vai poder
ajustá-los numa tela (pedido separado). Aqui ficam as funções que leem e gravam o valor (ler_tetos e gravar_teto).
Na primeira leitura, os dois começam em US$ 20.

Detalhes:
- o "dia" e o "mês" são os do calendário de Brasília (UTC−3), os mesmos do filtro de período da Telemetria;
- a tabela gasto_da_ia_por_dia tem uma linha por dia (o custo somado e quantas chamadas reais houve); o gasto do mês
  é a soma dos dias do mês;
- a tabela limites_de_gasto_da_ia tem uma linha por período ("dia" e "mes"), com o valor, quando mudou e quem mudou;
- se o banco não responder, a chamada à IA segue (e o teto do cliente continua valendo): uma falha na conta do teto
  nunca derruba o trabalho da empresa. A falha fica no registro do servidor (log);
- nada pessoal é gravado: só datas, custos, quantidades e o usuário que mudou o teto.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from services import banco

# O registro do servidor (log), para a falha da conta do teto não passar em silêncio
registro = logging.getLogger(__name__)

# Os dois períodos que têm teto
PERIODO_DIA = "dia"
PERIODO_MES = "mes"
PERIODOS = (PERIODO_DIA, PERIODO_MES)
# Os valores com que os tetos começam, na primeira leitura (US$ 20 por dia e por mês)
TETOS_INICIAIS_USD = {PERIODO_DIA: 20.0, PERIODO_MES: 20.0}
# O maior teto aceito: uma trava contra erro de digitação (ex.: 2000 em vez de 20,00)
TETO_MAXIMO_USD = 1000.0
# O motivo que o cliente de IA grava quando um teto barra a chamada (a Telemetria reconhece por estes textos)
MOTIVO_DO_TETO_DO_DIA = "teto de gasto do dia atingido"
MOTIVO_DO_TETO_DO_MES = "teto de gasto do mês atingido"
MOTIVOS_DO_TETO = {PERIODO_DIA: MOTIVO_DO_TETO_DO_DIA, PERIODO_MES: MOTIVO_DO_TETO_DO_MES}
# Os recados da pausa. Para a empresa, num envio que já existe (ele fica esperando):
# (o texto não manda clicar em nada: nas outras telas, não há o botão "Tentar de novo")
RECADO_PARA_A_EMPRESA = "A análise automática está indisponível agora. Seu envio fica guardado, e o banco já foi avisado."
# O recado que a empresa vê no próprio envio pausado, na tela do cadastro, onde o botão "Tentar de novo" existe
# (ADR-139). O recado acima continua nas outras telas (ex.: o Assistente de Correção)
RECADO_DO_ENVIO_PAUSADO = ("A análise automática está indisponível agora. Seu envio fica guardado: clique em "
                           "\"Tentar de novo\" mais tarde.")
# Para a empresa, num arquivo que precisa da IA para ser lido (Word, fichas): ele não entra, e ela continua com ele
RECADO_DO_ARQUIVO_RECUSADO = "A análise automática está indisponível agora; tente enviar de novo mais tarde."
# Para o especialista do banco (Endomarketing): quem pode subir o teto
RECADO_PARA_O_BANCO = ("Os agentes estão pausados: o teto de custo com agentes foi atingido. Eles voltam quando o dia "
                       "(ou o mês) virar, ou quando o teto for ajustado.")
# O horário de Brasília (UTC−3): o dia e o mês do teto são os do calendário da especialista
FUSO_DE_BRASILIA = timezone(timedelta(hours=-3))


class TetoDeGastoAtingido(Exception):
    """A IA está pausada: o gasto do dia ou do mês chegou ao teto. A mensagem é o recado para a empresa.

    Ex.: TetoDeGastoAtingido("mes").periodo → "mes"; str(...) → RECADO_PARA_A_EMPRESA.
    """

    def __init__(self, periodo: str):
        """Recebe o período cujo teto foi atingido ("dia" ou "mes")."""
        # A mensagem da exceção é o recado simples, que pode ir direto para a tela
        super().__init__(RECADO_PARA_A_EMPRESA)
        # O período fica guardado para o registro (qual teto parou a IA)
        self.periodo = periodo


def hoje_em_brasilia() -> date:
    """A data de hoje no calendário de Brasília. Ex.: às 22h de 28/09 em Brasília (01h de 29/09 em UTC) → 28/09."""
    return datetime.now(FUSO_DE_BRASILIA).date()


def _preparar(conexao) -> None:
    """Cria as duas tabelas (o gasto por dia e os tetos), se ainda não existirem.

    Só cria: não grava nada nem confirma a transação de quem chamou. Os tetos iniciais
    não são gravados: enquanto ninguém mudou um teto, vale o valor inicial (ver _tetos).
    """
    # O gasto: uma linha por dia
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS gasto_da_ia_por_dia (
               dia        TEXT PRIMARY KEY,           -- AAAA-MM-DD, no calendário de Brasília
               custo_usd  DOUBLE PRECISION NOT NULL,  -- soma do custo das chamadas reais do dia
               chamadas   INTEGER NOT NULL            -- quantas chamadas reais foram somadas
           )"""
    )
    # Os tetos: uma linha por período ("dia" e "mes")
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS limites_de_gasto_da_ia (
               periodo       TEXT PRIMARY KEY,           -- "dia" ou "mes"
               valor_usd     DOUBLE PRECISION NOT NULL,  -- o teto, em dólares
               alterado_em   TEXT NOT NULL,              -- quando o valor foi gravado (UTC, ISO)
               alterado_por  TEXT NOT NULL               -- o login de quem gravou
           )"""
    )


# ---------------- Os tetos (lidos e gravados no banco) ----------------

def _tetos(conexao) -> dict:
    """Os tetos em vigor, com as tabelas já preparadas por quem chamou.

    Recebe: a conexão. Devolve: {"dia": valor, "mes": valor}; o período que ninguém mudou fica com o valor inicial.
    """
    # Começa pelos valores iniciais (US$ 20 e US$ 20)
    tetos = dict(TETOS_INICIAIS_USD)
    # Uma linha por período que o banco já mudou
    linhas = conexao.execute("SELECT periodo, valor_usd FROM limites_de_gasto_da_ia").fetchall()
    for linha in linhas:
        # O valor gravado vale no lugar do inicial
        tetos[linha[0]] = float(linha[1])
    return tetos


def ler_tetos(conexao) -> dict:
    """Os tetos em vigor.

    Recebe: a conexão com o banco.
    Devolve: {"dia": valor, "mes": valor}, em dólares. Ex.: num banco novo → {"dia": 20.0, "mes": 20.0}.
    """
    # Garante as tabelas (só cria; não grava nada)
    _preparar(conexao)
    return _tetos(conexao)


def gravar_teto(conexao, periodo: str, valor_usd, quem: str) -> dict:
    """Grava um teto novo (a tela do especialista do banco vai chamar esta função).

    Recebe: a conexão, o período ("dia" ou "mes"), o valor em dólares e o usuário que mudou.
    Devolve: os tetos em vigor depois da mudança, como ler_tetos.
    Recusa (ValueError, com o motivo em português): período desconhecido, valor que não é número, zero ou negativo,
    ou acima de TETO_MAXIMO_USD. Ex.: gravar_teto(conexao, "mes", 35, "especialista.banco") → {"dia": 20.0, "mes": 35.0}.
    """
    # Só os dois períodos existentes
    if periodo not in PERIODOS:
        raise ValueError(f"Período desconhecido: {periodo!r}. Use 'dia' ou 'mes'.")
    # O valor precisa ser um número (texto como "vinte" é recusado; True/False também, apesar de o Python os aceitar)
    if isinstance(valor_usd, bool) or not isinstance(valor_usd, (int, float)):
        raise ValueError("O teto precisa ser um número, em dólares.")
    # Zero ou negativo pausaria a IA para sempre: recusado
    if valor_usd <= 0:
        raise ValueError("O teto precisa ser maior que zero.")
    # A trava contra erro de digitação
    if valor_usd > TETO_MAXIMO_USD:
        raise ValueError(f"O teto passa do máximo de US$ {TETO_MAXIMO_USD:.2f}.")
    # Quem mudou precisa estar identificado (a mudança é auditável)
    if not quem or not quem.strip():
        raise ValueError("Informe quem está mudando o teto.")
    # Garante as tabelas
    _preparar(conexao)
    # "Insere ou troca": a primeira mudança do período cria a linha; as seguintes trocam o valor, o momento e quem
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conexao.execute(
        "INSERT INTO limites_de_gasto_da_ia (periodo, valor_usd, alterado_em, alterado_por) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (periodo) DO UPDATE SET valor_usd = excluded.valor_usd, alterado_em = excluded.alterado_em, "
        "alterado_por = excluded.alterado_por",
        (periodo, float(valor_usd), agora, quem.strip()))
    # Grava de vez (é uma mudança pedida pelo especialista)
    conexao.commit()
    return _tetos(conexao)


# ---------------- O gasto (somado a cada chamada real) ----------------

def gasto_do_dia(conexao, dia: date | None = None) -> float:
    """Quanto a aplicação já gastou com IA num dia.

    Recebe: a conexão com o banco e o dia (sem informar, hoje em Brasília).
    Devolve: o custo somado, em dólares; dia sem chamadas → 0.0. Ex.: 3 chamadas de US$ 0,01 hoje → 0.03.
    """
    # Garante que as tabelas existem (só cria; não grava nada)
    _preparar(conexao)
    return _gasto_do_dia(conexao, dia)


def _gasto_do_dia(conexao, dia: date | None = None) -> float:
    """O mesmo que gasto_do_dia, com as tabelas já preparadas por quem chamou."""
    # Sem dia informado, vale o de hoje no calendário de Brasília
    dia = dia or hoje_em_brasilia()
    # A linha do dia (uma por dia), se já houve alguma chamada
    linha = conexao.execute("SELECT custo_usd FROM gasto_da_ia_por_dia WHERE dia = ?", (dia.isoformat(),)).fetchone()
    # Nenhuma chamada no dia: nada gasto
    if linha is None:
        return 0.0
    # O custo somado do dia, como número
    return float(linha[0])


def _primeiro_dia_do_mes_seguinte(dia: date) -> date:
    """O dia 1º do mês depois do dia dado. Ex.: 29/09/2026 → 01/10/2026; 15/12/2026 → 01/01/2027."""
    if dia.month == 12:
        # Dezembro: o mês seguinte é janeiro do ano seguinte
        return date(dia.year + 1, 1, 1)
    return date(dia.year, dia.month + 1, 1)


def gasto_do_mes(conexao, dia: date | None = None) -> float:
    """Quanto a aplicação já gastou com IA no mês de um dia (a soma dos dias do mês).

    Recebe: a conexão e um dia do mês (sem informar, hoje em Brasília).
    Devolve: o custo somado do dia 1º até o último dia do mês, em dólares. Ex.: US$ 3 em 02/09 e US$ 4 em 29/09 → 7.0.
    """
    # Garante que as tabelas existem (só cria; não grava nada)
    _preparar(conexao)
    return _gasto_do_mes(conexao, dia)


def _gasto_do_mes(conexao, dia: date | None = None) -> float:
    """O mesmo que gasto_do_mes, com as tabelas já preparadas por quem chamou."""
    # Sem dia informado, vale o mês de hoje
    dia = dia or hoje_em_brasilia()
    # O mês vai do dia 1º (incluído) ao dia 1º do mês seguinte (fora); as datas ISO comparam como texto
    primeiro_dia = date(dia.year, dia.month, 1)
    primeiro_dia_do_seguinte = _primeiro_dia_do_mes_seguinte(dia)
    linha = conexao.execute("SELECT COALESCE(SUM(custo_usd), 0) FROM gasto_da_ia_por_dia WHERE dia >= ? AND dia < ?",
                            (primeiro_dia.isoformat(), primeiro_dia_do_seguinte.isoformat())).fetchone()
    # A soma do mês, como número
    return float(linha[0])


def somar_no_dia(conexao, custo_usd: float, dia: date | None = None) -> None:
    """Soma o custo de uma chamada real no dia, criando a linha do dia se for a primeira.

    Recebe: a conexão, o custo da chamada em dólares e o dia (sem informar, hoje em Brasília).
    Devolve: nada; a linha do dia fica com o custo somado e uma chamada a mais.
    """
    # Garante que as tabelas existem
    _preparar(conexao)
    # Sem dia informado, vale o de hoje
    dia = dia or hoje_em_brasilia()
    # "Insere ou soma": a primeira chamada do dia cria a linha; as seguintes somam nela
    conexao.execute(
        "INSERT INTO gasto_da_ia_por_dia (dia, custo_usd, chamadas) VALUES (?, ?, 1) "
        "ON CONFLICT (dia) DO UPDATE SET custo_usd = gasto_da_ia_por_dia.custo_usd + excluded.custo_usd, "
        "chamadas = gasto_da_ia_por_dia.chamadas + 1",
        (dia.isoformat(), custo_usd))
    # Grava de vez (a soma não pode se perder se o servidor cair logo depois)
    conexao.commit()


# ---------------- A conferência (antes de cada chamada real) ----------------

def periodo_atingido(conexao) -> str | None:
    """Qual teto já foi atingido: "dia", "mes" ou None (nenhum; a IA pode seguir).

    Recebe: a conexão com o banco.
    Devolve: o primeiro período cujo gasto chegou ao teto (o dia é conferido antes do mês). Ex.: gasto do mês US$ 20
    com teto de US$ 20 → "mes", mesmo que o do dia ainda caiba.
    """
    # Garante as tabelas uma vez só, para as três leituras abaixo
    _preparar(conexao)
    return _periodo_atingido(conexao)


def _periodo_atingido(conexao) -> str | None:
    """O mesmo que periodo_atingido, com as tabelas já preparadas por quem chamou."""
    # Os tetos em vigor (do banco, ou os iniciais)
    tetos = _tetos(conexao)
    # O dia primeiro: é o que vira antes
    if _gasto_do_dia(conexao) >= tetos[PERIODO_DIA]:
        return PERIODO_DIA
    # Depois o mês
    if _gasto_do_mes(conexao) >= tetos[PERIODO_MES]:
        return PERIODO_MES
    return None


def teto_atingido() -> str | None:
    """Diz se algum teto já foi atingido (chamado pelo cliente de IA antes de cada chamada real).

    Recebe: nada (abre a conexão com o banco da aplicação).
    Devolve: "dia", "mes" ou None; se o banco falhar, None (a chamada segue; ver o topo).
    Risco conhecido (ADR-131): a conferência e a soma não são uma operação só. Pedidos ao mesmo tempo podem passar
    juntos pela conferência e ultrapassar o teto em poucas chamadas; o teto do cliente continua limitando cada pedido.
    """
    try:
        # Abre a conexão com o banco da aplicação (PostgreSQL ou SQLite, conforme o .env)
        conexao = banco.conectar()
        try:
            # Compara o gasto do dia e do mês com os tetos
            return periodo_atingido(conexao)
        finally:
            # Fecha a conexão, dando certo ou não
            conexao.close()
    except Exception as erro:
        # Sem a conta do teto, vale o teto do cliente; o tipo do erro vai para o log (sem dado nenhum)
        registro.warning("Não deu para ler o gasto da IA (%s); vale só o teto do cliente.", type(erro).__name__)
        return None


def anotar_custo(custo_usd: float | None, modelo: str = "") -> None:
    """Soma no dia o custo de uma chamada real (chamado pelo cliente de IA depois de cada resposta real).

    Recebe: o custo da chamada em dólares e o modelo que respondeu (só para o aviso no log).
    Devolve: nada. Custo None quer dizer que o modelo não tem preço na tabela: a chamada não entra no teto,
    e o log avisa, para ninguém achar que o teto está protegendo um modelo que ele não enxerga.
    """
    if custo_usd is None:
        # Chamada real sem preço: o teto não a vê; o aviso diz qual modelo precisa entrar na tabela de preços
        registro.warning("O modelo %r respondeu sem preço na tabela: esta chamada real não entra no teto de gasto.",
                         modelo)
        return
    try:
        # Abre a conexão com o banco da aplicação
        conexao = banco.conectar()
        try:
            # Soma o custo desta chamada no dia de hoje (o mês é a soma dos dias)
            somar_no_dia(conexao, custo_usd)
        finally:
            # Fecha a conexão, dando certo ou não
            conexao.close()
    except Exception as erro:
        # A chamada já aconteceu: a falha ao anotar não pode derrubar o trabalho; fica no log
        registro.warning("Não deu para somar o custo da IA no dia (%s).", type(erro).__name__)


def situacao_dos_tetos(conexao) -> dict:
    """O gasto de hoje e do mês, com os tetos, para o cartão da tela (Acompanhamento dos agentes).

    Recebe: a conexão com o banco.
    Devolve: {"dia", "gasto_dia_usd", "teto_dia_usd", "gasto_mes_usd", "teto_mes_usd", "atingido"}, em que
    "atingido" é "dia", "mes" ou None. Ex.: {"dia": "2026-09-29", "gasto_dia_usd": 1.23, "teto_dia_usd": 20.0,
    "gasto_mes_usd": 7.5, "teto_mes_usd": 20.0, "atingido": None}.
    """
    # Garante as tabelas uma vez só, para as leituras abaixo
    _preparar(conexao)
    # Os tetos em vigor
    tetos = _tetos(conexao)
    # O resumo para a tela (os gastos arredondados para não mostrar ruído de ponto flutuante)
    return {"dia": hoje_em_brasilia().isoformat(),
            "gasto_dia_usd": round(_gasto_do_dia(conexao), 6), "teto_dia_usd": tetos[PERIODO_DIA],
            "gasto_mes_usd": round(_gasto_do_mes(conexao), 6), "teto_mes_usd": tetos[PERIODO_MES],
            "atingido": _periodo_atingido(conexao)}
