"""Execuções das etapas do fluxo (AgentRunEvent): o que a telemetria mostra de cada etapa.

Cada etapa que roda no fluxo da empresa grava um registro: qual etapa, quem executou (um agente de IA,
uma regra ou uma pessoa), quando começou e terminou, quanto durou, se deu certo e, em caso de erro, o
TIPO do erro (nunca a mensagem com dados). Tokens e custo vêm da medição da execução (services/uso_da_ia.py;
ADR-131) e ficam vazios quando não foram medidos: um número inventado nunca pode aparecer como medição (ADR-36).

Nada pessoal entra aqui: só identificadores, nomes de etapas, horários e contagens.
Exemplo: etapa "interpretar", agente "Interpretador", status "OK", duração 0,4 s, modelo "mock".
"""
from datetime import datetime, timezone

from services.uso_da_ia import Uso

# As situações possíveis de uma execução: deu certo, quebrou, ou um guardrail barrou
OK, ERRO, BLOQUEADO = "OK", "ERRO", "BLOQUEADO"
# O tipo do erro quando a IA real caiu para o MOCK (provedor fora, limite ou teto da sessão)
TIPO_DA_QUEDA = "IAIndisponivel"
# O tipo do erro quando a IA foi pausada pelo teto de gasto do dia ou do mês (services/teto_de_gasto.py; ADR-131)
TIPO_DA_PAUSA_PELO_TETO = "TetoDeGastoAtingido"
# As colunas da tabela, na ordem (usada para montar os dicionários na leitura)
COLUNAS = ("processamento_id", "empresa_id", "etapa", "agente", "modelo", "versao_prompt", "inicio", "fim",
           "duracao_s", "status", "tokens_entrada", "tokens_saida", "custo_usd", "tipo_erro",
           "guardrail_disparado", "origem")


def _preparar(conexao) -> None:
    """Cria a tabela das execuções, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS execucoes_agentes (
               id                  INTEGER PRIMARY KEY AUTOINCREMENT,
               processamento_id    TEXT NOT NULL,
               empresa_id          TEXT NOT NULL,
               etapa               TEXT NOT NULL,
               agente              TEXT NOT NULL,      -- agente de IA, "Regra" ou "Humano"
               modelo              TEXT,               -- ex.: "mock"; vazio quando não há LLM
               versao_prompt       TEXT,
               inicio              TEXT NOT NULL,
               fim                 TEXT NOT NULL,
               duracao_s           DOUBLE PRECISION NOT NULL,
               status              TEXT NOT NULL,      -- OK, ERRO ou BLOQUEADO
               tokens_entrada      INTEGER,            -- vazio = não medido
               tokens_saida        INTEGER,
               custo_usd           DOUBLE PRECISION,
               tipo_erro           TEXT,               -- só o tipo (ex.: "NotImplementedError"), sem dados
               guardrail_disparado INTEGER NOT NULL,   -- 1 se um guardrail agiu nesta etapa
               origem              TEXT NOT NULL       -- REAL (medido) ou MOCK (simulado)
           )"""
    )


def _em_texto(momento: datetime) -> str:
    """O horário em texto, no padrão internacional (UTC)."""
    return momento.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def registrar(conexao, processamento_id: str, empresa_id: str, etapa: str, agente: str, inicio: datetime,
              fim: datetime, status: str, modelo: str | None = None, versao_prompt: str | None = None,
              tipo_erro: str | None = None, guardrail_disparado: bool = False, uso: Uso | None = None) -> None:
    """Grava a execução de uma etapa.

    uso: o que a IA gastou nesta execução (services/uso_da_ia.py: chamadas, tokens, custo). Sem uso, ou sem medição
    do provedor (ex.: o MOCK), tokens e custo ficam vazios: "não medido", nunca um zero inventado (ADR-36).
    Se a IA real deveria ter respondido e caiu para o MOCK (limite, teto da sessão, provedor fora), a execução não é
    "OK": vira ERRO, com o tipo IAIndisponivel (ADR-131). Uma resposta simulada nunca passa por real.
    """
    _preparar(conexao)
    duracao = round((fim - inicio).total_seconds(), 3)
    uso = uso or Uso()
    # A IA real não respondeu: o que a execução entregou foi simulado, e o painel precisa mostrar isso
    if uso.motivo_da_queda and status == OK:
        status = ERRO
        tipo_erro = tipo_erro or TIPO_DA_QUEDA
    # Com modelo "mock", a execução é simulada; sem modelo (regra ou pessoa), ela é real
    origem = "MOCK" if modelo == "mock" else "REAL"
    conexao.execute(
        "INSERT INTO execucoes_agentes (processamento_id, empresa_id, etapa, agente, modelo, versao_prompt, inicio, "
        "fim, duracao_s, status, tokens_entrada, tokens_saida, custo_usd, tipo_erro, guardrail_disparado, origem) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (processamento_id, empresa_id, etapa, agente, modelo, versao_prompt, _em_texto(inicio), _em_texto(fim),
         duracao, status, uso.tokens_entrada, uso.tokens_saida, uso.custo_usd, tipo_erro,
         1 if guardrail_disparado else 0, origem))
    conexao.commit()


def registrar_pausa_pelo_teto(conexao, identificador: str, empresa_id: str, etapa: str, agente: str,
                              inicio: datetime, uso: Uso | None = None) -> None:
    """Grava a execução que a IA não fez porque o teto de gasto a pausou (ADR-131).

    Recebe: o identificador (envio, conversa ou material), a empresa, a etapa, o agente, o começo e o uso medido até
    a pausa (as chamadas feitas antes contam no custo).
    Devolve: nada; a linha fica com ERRO e o tipo TetoDeGastoAtingido, que é como o banco "fica sabendo" da pausa na
    Telemetria. Ex.: registrar_pausa_pelo_teto(conexao, "PROC-1", "EMP001", "conversa:pausada",
    "Assistente de Correção", inicio).
    """
    # O fim é agora: a execução parou no momento em que o teto barrou a chamada
    registrar(conexao, identificador, empresa_id, etapa, agente, inicio, datetime.now(timezone.utc), ERRO,
              tipo_erro=TIPO_DA_PAUSA_PELO_TETO, uso=uso)


def registrar_queda_da_ia(conexao, identificador: str, empresa_id: str, etapa: str, agente: str,
                          inicio: datetime, uso: Uso | None = None) -> None:
    """Grava a execução que a IA não fez porque a IA real não respondeu (o provedor falhou, ou o limite da operação;
    ADR-145). Nada foi simulado no lugar: o trabalho pausou.

    Recebe: o identificador (envio, conversa ou material), a empresa, a etapa, o agente, o começo e o uso medido até a
    falha (as chamadas feitas antes contam no custo).
    Devolve: nada; a linha fica com ERRO e o tipo IAIndisponivel, que é como o banco vê a falha na Telemetria.
    Ex.: registrar_queda_da_ia(conexao, "PROC-1", "EMP001", "conversa:pausada", "Assistente de Correção", inicio).
    """
    # O fim é agora: a execução parou no momento em que a IA real não respondeu
    registrar(conexao, identificador, empresa_id, etapa, agente, inicio, datetime.now(timezone.utc), ERRO,
              tipo_erro=TIPO_DA_QUEDA, uso=uso)


def listar(conexao, processamento_id: str | None = None) -> list[dict]:
    """As execuções, na ordem em que aconteceram. Com processamento_id, só as daquele processamento."""
    _preparar(conexao)
    consulta = conexao.execute(
        f"SELECT {', '.join(COLUNAS)} FROM execucoes_agentes WHERE (? IS NULL OR processamento_id = ?) ORDER BY id",
        (processamento_id, processamento_id))
    execucoes = []
    for linha in consulta:
        # Junta o nome de cada coluna com o seu valor
        execucao = dict(zip(COLUNAS, linha))
        execucao["guardrail_disparado"] = bool(execucao["guardrail_disparado"])
        execucoes.append(execucao)
    return execucoes
