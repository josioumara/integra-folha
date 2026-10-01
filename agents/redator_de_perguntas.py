"""Redator de perguntas: a IA escreve a primeira fala do Agente de validação sobre cada pendência, mais natural que uma
frase fixa montada por regra (pendências por conversa, ADR-118).

Como funciona, em linguagem simples:
    1. o serviço (services/perguntas_das_pendencias.py) junta as pendências de UM envio que ainda não têm pergunta
       guardada e manda tudo numa chamada só ao modelo PEQUENO (mais barato e rápido; a tarefa é escrever uma frase);
    2. o prompt (prompts/pergunta_da_pendencia_v4.md) leva a diretriz de tom de voz e os dados de cada pendência;
    3. cada frase que volta passa por uma CONFERÊNCIA no código (conferir_pergunta): tamanho, termina em UMA pergunta,
       tem o valor lido e o palpite quando há, nada de nome técnico. O que não passa fica de fora, e o serviço usa a
       frase de reserva (services/pergunta_da_pendencia.py);
    4. a IA tem um tempo máximo (LIMITE_DE_SEGUNDOS): passou disso, a lista aparece com as frases de reserva e a IA
       tenta de novo na próxima vez. A lista nunca espera a IA mais que isso.

No modo MOCK, a IA simulada devolve as próprias frases de reserva (simular_perguntas).
"""
import contextvars
import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TempoEsgotado
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from agents import tom_de_voz
from services import pergunta_da_pendencia
from services.llm_client import LLMClient

# Pasta raiz do projeto (para achar o prompt)
RAIZ = Path(__file__).resolve().parent.parent
# Versão do prompt e nome da tarefa no cliente de IA (a v4 escreve "única por funcionário", ADR-153)
VERSAO_PROMPT = "pergunta_da_pendencia_v4"
# As palavras que a frase da informação única por funcionário precisa ter (valem "única" e "único")
PALAVRAS_DA_INFORMACAO_UNICA = "por funcionário"
TAREFA = "escrever_perguntas"
# O maior texto aceito numa pergunta (cabe no balão sem virar parágrafo)
LIMITE_DE_CARACTERES = 220
# Quanto a lista espera a IA, no máximo (depois disso, valem as frases de reserva)
LIMITE_DE_SEGUNDOS = 8
# Palavras que a fala não pode ter (termos técnicos, pela diretriz de tom de voz)
PALAVRAS_PROIBIDAS = ("regra", "validador", "payload")
# Regras cuja frase não precisa repetir o valor lido (o valor é o CPF que identifica a pessoa, ou não há valor)
REGRAS_SEM_O_VALOR_NA_FRASE = ("PESSOA_DUPLICADA", "PESSOA_EM_OUTRO_ENVIO", "CONFERENCIA_DE_TOTAIS",
                               "DATA_AMBIGUA", "ZEROS_A_ESQUERDA")


@dataclass
class PendenciaParaEscrever:
    """O que a IA recebe de uma pendência (tudo em linguagem simples; nada de nome técnico de campo)."""

    id: str                     # a chave da pendência (a resposta volta com ela)
    regra: str                  # o código interno da regra (a IA não escreve; a conferência e o MOCK usam)
    gravidade: str              # BLOQUEANTE ou ALERTA
    pessoa: str                 # o primeiro nome ("" no arquivo inteiro)
    informacao: str             # o nome da informação, pela descrição do parâmetro
    valor_lido: str             # o que veio no arquivo ("" quando não veio nada)
    o_que_aconteceu: str        # a mensagem do Validador, sem nome técnico de campo
    tipo: str                   # "corrigir" ou "confirmar"
    opcoes: list[str] = field(default_factory=list)   # os valores aceitos, num campo de lista
    palpite: str = ""           # o valor que o agente acredita ser o certo ("" sem palpite seguro)
    quantidade_de_pessoas: int = 1   # quantas pessoas vieram com este mesmo valor (mais de 1 = pergunta do grupo)
    igual_para_todos: bool = True    # False: a informação é de cada pessoa (a marcação do parâmetro, ADR-124)


@lru_cache(maxsize=1)
def carregar_prompt() -> tuple[str, str]:
    """Devolve (sistema, pedido) do arquivo versionado em prompts/, com a diretriz de tom de voz já no sistema."""
    texto = (RAIZ / "prompts" / f"{VERSAO_PROMPT}.md").read_text(encoding="utf-8")
    _, sistema, pedido = re.split(r"^## (?:SISTEMA|PEDIDO)\s*$", texto, flags=re.M)
    return tom_de_voz.com_a_diretriz(sistema.strip()), pedido.strip()


def montar_pedido(pendencias: list[PendenciaParaEscrever]) -> str:
    """O pedido: as pendências em JSON, uma por linha."""
    _, pedido = carregar_prompt()
    linhas = []
    for pendencia in pendencias:
        linhas.append(json.dumps(asdict(pendencia), ensure_ascii=False))
    return pedido.replace("{pendencias}", "\n".join(linhas))


def conferir_pergunta(texto, pendencia: PendenciaParaEscrever) -> bool:
    """A conferência da frase que a IA escreveu (no código, não no prompt): True se ela pode ir para a tela.

    Regras: texto de até LIMITE_DE_CARACTERES; termina com UMA pergunta (um só "?", no fim); sem "!" e sem "_" (nome
    técnico de campo); sem as palavras proibidas; com o valor lido (quando a regra pede), com o palpite entre aspas
    (quando há) e, numa pergunta do grupo (ADR-120), com o número de pessoas em algarismos.
    Ex.: 'No arquivo, o estado civil de Diego veio "Solteiro(a)". Posso usar "Solteiro"?' → True (com esse palpite).
    """
    if not isinstance(texto, str):
        return False
    frase = texto.strip()
    if not frase or len(frase) > LIMITE_DE_CARACTERES:
        return False
    # Uma pergunta só, no fim
    if not frase.endswith("?") or frase.count("?") != 1:
        return False
    # Sem exclamação e sem nome técnico
    if "!" in frase or "_" in frase:
        return False
    minusculas = frase.lower()
    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in minusculas:
            return False
    # O valor lido, quando a regra pede, e o palpite, quando há
    precisa_do_valor = pendencia.valor_lido and pendencia.regra not in REGRAS_SEM_O_VALOR_NA_FRASE
    if precisa_do_valor and pendencia.valor_lido not in frase:
        return False
    # O palpite entre aspas (só o nome solto pode estar dentro do valor lido: "Solteiro" em "Solteiro(a)")
    if pendencia.palpite and f'"{pendencia.palpite}"' not in frase:
        return False
    # A pergunta do grupo diz quantas pessoas são (ex.: "23 pessoas")
    if pendencia.quantidade_de_pessoas > 1 and str(pendencia.quantidade_de_pessoas) not in frase:
        return False
    # A informação única por funcionário que falta no arquivo inteiro nunca pede "o valor para todos" (a marcação do
    # parâmetro): a frase precisa dizer que ela é única por funcionário
    sem_coluna_de_cada_pessoa = pendencia.regra == "OBRIGATORIO_SEM_COLUNA" and not pendencia.igual_para_todos
    if sem_coluna_de_cada_pessoa and PALAVRAS_DA_INFORMACAO_UNICA not in minusculas:
        return False
    return True


def _perguntas_da_resposta(texto: str) -> list:
    """A lista "perguntas" do JSON da resposta. Levanta ValueError se a resposta não é um objeto com essa lista."""
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("a resposta não contém um objeto JSON")
    perguntas = json.loads(texto[inicio:fim + 1]).get("perguntas")
    if not isinstance(perguntas, list):
        raise ValueError("a resposta não tem a lista de perguntas")
    return perguntas


def _chamar_a_ia(cliente: LLMClient, pedido: str):
    """A chamada em si (roda numa linha de execução à parte, para a lista poder desistir de esperar)."""
    sistema, _ = carregar_prompt()
    return cliente.gerar(TAREFA, pedido, sistema, modelo="pequeno", temperatura=0.0)


def escrever(pendencias: list[PendenciaParaEscrever], cliente: LLMClient,
             limite_de_segundos: float | None = None) -> tuple[dict[str, str], object]:
    """Pede à IA a pergunta de cada pendência e devolve só as que passaram na conferência.

    Recebe: as pendências de um envio; o cliente da IA; quanto esperar, no máximo (sem informar, LIMITE_DE_SEGUNDOS).
    Devolve: ({id: pergunta conferida}, a resposta da IA). Levanta TimeoutError se a IA passar do tempo e ValueError se
    a resposta vier fora do formato (quem chama usa a reserva e registra a falha).
    """
    pedido = montar_pedido(pendencias)
    if limite_de_segundos is None:
        limite_de_segundos = LIMITE_DE_SEGUNDOS
    # Uma linha de execução à parte: se a IA demorar, a lista segue sem esperar (a chamada termina sozinha depois)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        # copy_context: a outra linha de execução enxerga a medição aberta por quem chamou (tokens e custo; ADR-131)
        contexto = contextvars.copy_context()
        resposta = executor.submit(contexto.run, _chamar_a_ia, cliente, pedido).result(timeout=limite_de_segundos)
    except TempoEsgotado as erro:
        raise TimeoutError(f"a IA passou de {limite_de_segundos} s") from erro
    finally:
        executor.shutdown(wait=False)
    # Cada pendência pelo id, para conferir a frase com os dados dela
    pendencia_por_id = {}
    for pendencia in pendencias:
        pendencia_por_id[pendencia.id] = pendencia
    conferidas = {}
    for item in _perguntas_da_resposta(resposta.texto):
        if not isinstance(item, dict) or item.get("id") not in pendencia_por_id:
            continue
        texto = item.get("pergunta")
        if conferir_pergunta(texto, pendencia_por_id[item["id"]]):
            conferidas[item["id"]] = texto.strip()
    return conferidas, resposta


# ---------------- MOCK: a IA simulada escreve as frases de reserva ----------------

def simular_perguntas(pedido: str) -> str:
    """Lê as pendências do pedido e devolve, para cada uma, a frase de reserva (services/pergunta_da_pendencia.py)."""
    perguntas = []
    for linha in pedido.splitlines():
        linha = linha.strip()
        if not linha.startswith("{"):
            continue
        dados = json.loads(linha)
        frase = pergunta_da_pendencia.perguntar(dados["regra"], dados["gravidade"], None, dados["informacao"],
                                                dados["valor_lido"] or None, dados["o_que_aconteceu"],
                                                pessoa=dados["pessoa"] or None, palpite=dados["palpite"] or None,
                                                descricao=dados["informacao"],
                                                quantidade=dados.get("quantidade_de_pessoas", 1),
                                                igual_para_todos=dados.get("igual_para_todos", True))
        perguntas.append({"id": dados["id"], "pergunta": frase})
    return json.dumps({"perguntas": perguntas}, ensure_ascii=False)


def cliente_padrao() -> LLMClient:
    """Cliente do modo configurado; no MOCK, as perguntas são as frases de reserva."""
    return LLMClient(respostas_mock={TAREFA: simular_perguntas})
