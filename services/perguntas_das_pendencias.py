"""As perguntas das pendências escritas pela IA, guardadas por envio (pendências por conversa).

Para que serve: a primeira fala do Agente de validação sobre cada pendência é escrita pela IA
(agents/redator_de_perguntas.py). Para não pagar a mesma frase toda vez que a lista abre, cada pergunta aceita fica
GUARDADA numa tabela, pela chave envio + regra + linha + valor lido: só se escreve de novo quando o valor lido muda
(ex.: a empresa corrigiu e o valor novo ainda tem problema).

As regras:
    - uma chamada à IA por envio, só com as pendências que ainda não têm pergunta guardada (no máximo
      MAXIMO_POR_CHAMADA; as outras ficam para a próxima vez);
    - a lista nunca fica esperando: com a IA fora, lenta (redator_de_perguntas.LIMITE_DE_SEGUNDOS) ou com a resposta
      fora do formato, vale a frase de reserva (services/pergunta_da_pendencia.py), e nada é guardado;
    - cada chamada é gravada na Telemetria (services/execucoes.py), como a dos outros agentes, com o modelo e a versão
      do prompt;
    - pergunta guardada no modo MOCK não vale quando a aplicação está no modo real (a IA de verdade escreve a sua).

Exemplo de uso:
    perguntas = perguntas_do_envio(conexao, "a1b2c3", "EMP001", pendencias)   # {chave: pergunta}
"""
from datetime import datetime, timezone

from agents import redator_de_perguntas
from services import config, execucoes, uso_da_ia

# No máximo quantas pendências vão numa chamada (um envio com muitas pendências é escrito aos poucos)
MAXIMO_POR_CHAMADA = 40
# Como a execução aparece na Telemetria
NOME_DO_AGENTE = "Agente de validação (perguntas)"
ETAPA = "escrever_perguntas"


def _preparar(conexao) -> None:
    """Cria a tabela das perguntas guardadas, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS perguntas_das_pendencias (
               processamento_id TEXT NOT NULL,
               chave            TEXT NOT NULL,     -- regra|linha|valor lido (ver chave_da_pendencia)
               pergunta         TEXT NOT NULL,
               modelo           TEXT NOT NULL,     -- quem escreveu ("mock" no modo simulado)
               versao_prompt    TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               PRIMARY KEY (processamento_id, chave)
           )"""
    )


def chave_da_pendencia(regra_id: str, linha: int | None, valor_lido: str | None, campo: str | None) -> str:
    """A chave de uma pendência dentro do envio: a regra, a linha, o campo e o valor lido.

    Ex.: ("CPF_INVALIDO", 8, "123.456.789-00", "cpf") → "CPF_INVALIDO|8|cpf|123.456.789-00"; sem linha nem valor:
    "OBRIGATORIO_SEM_COLUNA||matricula|". O campo entra porque a mesma regra aparece uma vez por campo na mesma linha
    (sem ele, a pergunta escrita para a UF apareceria no cartão da matrícula).
    """
    linha_em_texto = "" if linha is None else str(linha)
    return f"{regra_id}|{linha_em_texto}|{campo or ''}|{valor_lido or ''}"


def guardadas(conexao, processamento_id: str) -> dict[str, str]:
    """As perguntas já guardadas do envio: {chave: pergunta}. No modo real, as escritas pelo MOCK ficam de fora."""
    _preparar(conexao)
    consulta = conexao.execute("SELECT chave, pergunta, modelo FROM perguntas_das_pendencias "
                               "WHERE processamento_id = ?", (processamento_id,))
    perguntas = {}
    for chave, pergunta, modelo in consulta:
        if modelo == "mock" and config.MODO == "llm":
            continue
        perguntas[chave] = pergunta
    return perguntas


def _guardar(conexao, processamento_id: str, perguntas: dict[str, str], modelo: str) -> None:
    """Grava (ou troca) as perguntas aceitas do envio ("ON CONFLICT": a mesma forma no SQLite e no PostgreSQL)."""
    _preparar(conexao)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for chave, pergunta in perguntas.items():
        conexao.execute(
            "INSERT INTO perguntas_das_pendencias (processamento_id, chave, pergunta, modelo, versao_prompt, "
            "criado_em) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (processamento_id, chave) DO UPDATE SET "
            "pergunta = excluded.pergunta, modelo = excluded.modelo, versao_prompt = excluded.versao_prompt, "
            "criado_em = excluded.criado_em",
            (processamento_id, chave, pergunta, modelo, redator_de_perguntas.VERSAO_PROMPT, agora))
    conexao.commit()


def _escrever_as_que_faltam(conexao, processamento_id: str, empresa_id: str, faltam: list, cliente) -> dict[str, str]:
    """Chama a IA para as pendências sem pergunta guardada, grava a execução na Telemetria e guarda as aceitas.

    Devolve: {chave: pergunta} só das que passaram na conferência. Com a IA fora, lenta ou fora do formato: vazio.
    """
    inicio = datetime.now(timezone.utc)
    escritas = {}
    modelo = None
    tipo_erro = None
    # O taxímetro da escrita: a chamada à IA soma aqui, mesmo quando a resposta vem fora do formato (ADR-131)
    with uso_da_ia.medir() as uso:
        try:
            escritas, resposta = redator_de_perguntas.escrever(faltam, cliente or redator_de_perguntas.cliente_padrao())
            modelo = resposta.modelo
        except TimeoutError:
            tipo_erro = "TempoEsgotado"
        except ValueError:
            tipo_erro = "RespostaForaDoContrato"
        except Exception as erro:
            # A IA falhou de outro jeito (ex.: configuração): a lista segue com as frases de reserva
            tipo_erro = type(erro).__name__
    status = execucoes.OK if tipo_erro is None else execucoes.ERRO
    execucoes.registrar(conexao, processamento_id, empresa_id, ETAPA, NOME_DO_AGENTE, inicio,
                        datetime.now(timezone.utc), status, modelo=modelo,
                        versao_prompt=redator_de_perguntas.VERSAO_PROMPT, tipo_erro=tipo_erro, uso=uso)
    if escritas:
        _guardar(conexao, processamento_id, escritas, modelo or "mock")
    return escritas


def perguntas_do_envio(conexao, processamento_id: str, empresa_id: str, pendencias: list,
                       reservas: dict[str, str], cliente=None) -> dict[str, str]:
    """A pergunta de cada pendência do envio: a guardada, a que a IA escreveu agora, ou a de reserva.

    Recebe: o envio e a empresa; pendencias — [redator_de_perguntas.PendenciaParaEscrever], com id = a chave
    (chave_da_pendencia); reservas — {chave: frase de reserva}; cliente — o da IA (os testes passam um falso).
    Devolve: {chave: pergunta}, uma para cada pendência. Nunca levanta erro por causa da IA.
    """
    ja_guardadas = guardadas(conexao, processamento_id)
    # As que ainda não têm pergunta, até o máximo por chamada
    faltam = []
    for pendencia in pendencias:
        if pendencia.id not in ja_guardadas and len(faltam) < MAXIMO_POR_CHAMADA:
            faltam.append(pendencia)
    escritas = {}
    if faltam:
        escritas = _escrever_as_que_faltam(conexao, processamento_id, empresa_id, faltam, cliente)
    # A guardada, a escrita agora, ou a reserva
    perguntas = {}
    for chave, reserva in reservas.items():
        perguntas[chave] = ja_guardadas.get(chave) or escritas.get(chave) or reserva
    return perguntas
