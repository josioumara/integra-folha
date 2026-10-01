"""Histórico dos experimentos de avaliação: um registro por experimento, gravado uma vez e nunca sobrescrito.

Cada experimento responde uma pergunta ("a IA ganha do dicionário?", "qual modelo escolher?") e guarda:
- quando foi, o que foi testado, com que amostra e em que modo (sem IA, MOCK ou IA real);
- o resultado de cada configuração ou modelo testado, com as métricas (acurácia, recall e precisão da
  abstenção, custo, tempo...);
- a leitura do resultado, a decisão tomada e de onde vieram os números.

Os registros ficam em data/avaliacao/experimentos/EXP-001_nome.json, EXP-002_..., na ordem em que aconteceram.
Os arquivos de resultado dos scripts (data/avaliacao/resultados/) são regravados a cada nova medição; o registro
não: ele é a "foto" daquele dia. Assim, a história das melhorias pode ser contada (e conferida) depois.
O documento docs/experimentos.md é gerado a partir destes registros (scripts/gerar_historico_de_experimentos.py).
"""
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

# Onde os registros ficam
PASTA_DOS_EXPERIMENTOS = Path(__file__).resolve().parent.parent / "data" / "avaliacao" / "experimentos"
# Os campos que todo registro precisa ter
CAMPOS_OBRIGATORIOS = ("titulo", "tipo", "pergunta", "o_que_testamos", "amostra", "modo", "resultados", "leitura")
# Os números guardados para um experimento já medido que ainda não juntou à versão principal: {número: o que é}.
# O número fica de fora da sequência (e aparece como "reservado" no docs/experimentos.md) até o registro dele chegar,
# gravado com registrar(experimento, numero=...); quando ele chegar, a linha sai daqui
NUMEROS_RESERVADOS = {}


class RegistroInvalido(ValueError):
    """O registro não tem o mínimo para contar a história (ex.: sem pergunta ou sem resultados)."""


def _nome_curto(titulo: str) -> str:
    """O título em forma de nome de arquivo: minúsculas, sem acento, com "_". Ex.: "Baseline B0" → "baseline_b0"."""
    # Tira os acentos
    sem_acento = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode("ascii")
    # Troca tudo o que não é letra ou número por "_"
    nome = re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")
    # Nome de arquivo curto
    return nome[:50]


def listar() -> list[dict]:
    """Todos os registros, do primeiro ao último."""
    if not PASTA_DOS_EXPERIMENTOS.exists():
        return []
    registros = []
    for caminho in sorted(PASTA_DOS_EXPERIMENTOS.glob("EXP-*.json")):
        registros.append(json.loads(caminho.read_text(encoding="utf-8")))
    return registros


def _proximo_numero() -> int:
    """O número do próximo experimento (1 se ainda não há nenhum)."""
    maior = 0
    for registro in listar():
        numero = int(registro["id"].split("-")[1])
        if numero > maior:
            maior = numero
    return maior + 1


def _numero_ja_usado(numero: int) -> bool:
    """True se algum registro já tem este número (ex.: 19 → existe o EXP-019)."""
    for registro in listar():
        if int(registro["id"].split("-")[1]) == numero:
            return True
    return False


def registrar(experimento: dict, numero: int | None = None) -> Path:
    """Grava um experimento novo e devolve o caminho do arquivo.

    experimento: os campos de CAMPOS_OBRIGATORIOS e, se houver, "data", "decisao", "custo_usd", "fonte", "commit".
    numero: sem informar, o próximo depois do maior. Informado, é um número reservado: serve quando um experimento
    medido antes ainda não juntou e o número dele fica guardado (ex.: o 20 guardado, e este é o 21). Um número que já
    existe é recusado.
    Um registro nunca sobrescreve outro: se o arquivo já existir, é recusado.
    """
    # O mínimo para contar a história
    faltando = []
    for campo in CAMPOS_OBRIGATORIOS:
        if not experimento.get(campo):
            faltando.append(campo)
    if faltando:
        raise RegistroInvalido("Faltam no registro: " + ", ".join(faltando))
    if numero is None:
        numero = _proximo_numero()
    elif _numero_ja_usado(numero):
        raise RegistroInvalido(f"O número EXP-{numero:03d} já é de outro experimento.")
    registro = {"id": f"EXP-{numero:03d}", "data": experimento.get("data", date.today().isoformat())}
    registro.update(experimento)
    caminho = PASTA_DOS_EXPERIMENTOS / f"{registro['id']}_{_nome_curto(experimento['titulo'])}.json"
    # Um registro é uma foto: nunca é sobrescrito
    if caminho.exists():
        raise RegistroInvalido(f"O registro {caminho.name} já existe e não pode ser sobrescrito.")
    PASTA_DOS_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return caminho


def resultado_do_interpretador(nome: str, modelo: str, medida: dict) -> dict:
    """Um resultado do Interpretador no formato do histórico, a partir das medidas de eval/metricas.py.

    Ex.: resultado_do_interpretador("B3", "claude-sonnet-5", medida) → {"nome": "B3", "modelo": ..., "metricas": {...}}
    """
    metricas = {}
    # Só as medidas que existem nesta medição (nunca um número inventado)
    for chave in ("acuracia_por_campo", "ic95_acuracia_por_campo", "abstencao_recall", "abstencao_precisao",
                  "acerto_geral", "custo_usd", "custo_por_planilha_usd", "segundos_por_planilha",
                  "respostas_fora_do_contrato", "planilhas_pontuadas"):
        if chave in medida:
            metricas[chave] = medida[chave]
    return {"nome": nome, "modelo": modelo, "metricas": metricas}
