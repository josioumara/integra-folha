"""Comparação dos modelos de IA na interpretação das planilhas (ADR-11, ADR-65; docs/avaliacao.md, seção 12).

Os modelos selecionados na triagem (data/avaliacao/modelos_candidatos.json, decisão "testar") fazem a mesma tarefa:
interpretar as colunas de 30 planilhas da prova congelada, na configuração B3 (com RAG). O B0 (dicionário, sem IA)
faz o mesmo, de graça, como régua. Para cada modelo são medidos:
- acurácia por campo (com intervalo de confiança de 95%) e abstenção (pedir ajuda em vez de chutar);
- respostas fora do contrato e vezes em que a IA falhou duas vezes (e o dicionário assumiu);
- custo real (tokens informados pelo provedor × tabela de preços), tokens e tempo de resposta.

Proteções de dinheiro e de honestidade:
- teto de gasto para a comparação inteira: atingido, o modelo em andamento fica "parcial" e os seguintes não rodam;
- se o provedor falhar, a resposta simulada (MOCK) NÃO é aceita no lugar: a planilha conta como erro do provedor;
- falta de chave ou de configuração para tudo antes de gastar;
- o resultado é gravado depois de cada modelo; rodar de novo continua de onde parou.

A planilha da prova tem só os nomes das colunas (sem amostras de dados): é a mesma informação que o B0 recebe,
então a comparação é justa. No uso real, a IA também vê amostras mascaradas, o que tende a ajudá-la.
"""
import json
import random
import time
from datetime import date
from pathlib import Path

from agents import interpretador
from baselines.baseline_mapper import BaselineMapper
from eval.metricas import contar, intervalo_bootstrap, resumir
from models.contratos import ColunaPerfil, EstadoProcessamento, FileProfile, TipoCarga, carregar_layout
from services import config, provedores_de_ia
from services.llm_client import LLMClient

# Pasta raiz do projeto e os arquivos usados
RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_DA_PROVA = RAIZ / "data" / "avaliacao" / "cabecalhos_teste.jsonl"
CAMINHO_DA_AMOSTRA = RAIZ / "data" / "avaliacao" / "amostra_comparacao_modelos.json"
CAMINHO_DOS_CANDIDATOS = RAIZ / "data" / "avaliacao" / "modelos_candidatos.json"
CAMINHO_DO_RESULTADO = RAIZ / "data" / "avaliacao" / "resultados" / "comparacao_modelos.json"
# Tamanho da amostra e a semente do sorteio (a mesma semente sorteia sempre as mesmas planilhas)
TAMANHO_DA_AMOSTRA = 30
SEMENTE_DO_SORTEIO = 2026
# Quantas falhas seguidas do provedor fazem o modelo ser dado como indisponível (ex.: modelo fora da conta)
LIMITE_DE_FALHAS_SEGUIDAS = 3
# Configuração do Interpretador usada na comparação (B3 = com RAG)
CONFIGURACAO = "B3"


class FalhaDoProvedor(Exception):
    """O provedor não respondeu de verdade (a resposta seria o MOCK): a planilha não pode ser pontuada."""


class ClienteSemDisfarce:
    """Fica entre o Interpretador e o cliente de IA: mede tempo, tokens e custo e recusa respostas do MOCK.

    O cliente de IA normal cai para o MOCK quando o provedor falha (bom para a demo, ruim para medir). Aqui, uma
    resposta do MOCK vira FalhaDoProvedor, para nenhum número da comparação sair de resposta simulada.
    """

    def __init__(self, cliente: LLMClient):
        """cliente: o cliente de IA em modo "llm"."""
        self.cliente = cliente
        self.segundos = 0.0
        self.tokens_entrada = 0
        self.tokens_saida = 0

    def gerar(self, tarefa, prompt, sistema="", modelo=None, temperatura=0.0):
        """Repassa a chamada, mede o tempo e os tokens e recusa a resposta do MOCK."""
        inicio = time.perf_counter()
        resposta = self.cliente.gerar(tarefa, prompt, sistema, modelo, temperatura)
        self.segundos += time.perf_counter() - inicio
        if resposta.modo != "llm":
            raise FalhaDoProvedor(resposta.motivo_fallback or "resposta não veio do provedor")
        self.tokens_entrada += resposta.tokens_entrada or 0
        self.tokens_saida += resposta.tokens_saida or 0
        return resposta


# ---------------- A amostra e os modelos ----------------

def carregar_prova() -> dict:
    """As planilhas da prova, pelo id: {0: {"cabecalhos": [...], "esperado": {...}}, ...}."""
    planilhas = {}
    with open(CAMINHO_DA_PROVA, encoding="utf-8") as arquivo:
        for linha in arquivo:
            planilha = json.loads(linha)
            planilhas[planilha["id"]] = planilha
    return planilhas


def sortear_amostra(prova: dict) -> list[int]:
    """Os ids das 30 planilhas da comparação, sorteados com semente fixa (sempre os mesmos), em ordem."""
    sorteio = random.Random(SEMENTE_DO_SORTEIO)
    ids = sorted(prova)
    escolhidos = sorteio.sample(ids, TAMANHO_DA_AMOSTRA)
    escolhidos.sort()
    return escolhidos


def gravar_amostra(ids: list[int]) -> None:
    """Grava a amostra (ela entra no congelamento da avaliação, ADR-58)."""
    registro = {"sobre": "Planilhas da prova usadas na comparação de modelos (sorteio com semente fixa).",
                "semente": SEMENTE_DO_SORTEIO, "ids": ids}
    CAMINHO_DA_AMOSTRA.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                  newline="\n")


def carregar_amostra() -> list[int]:
    """Os ids da amostra gravada."""
    return json.loads(CAMINHO_DA_AMOSTRA.read_text(encoding="utf-8"))["ids"]


def modelos_para_testar() -> list[dict]:
    """Os modelos com decisão "testar" na triagem, do mais barato para o mais caro (o teto corta os últimos)."""
    dados = json.loads(CAMINHO_DOS_CANDIDATOS.read_text(encoding="utf-8"))
    selecionados = []
    for modelo in dados["modelos"]:
        if modelo["decisao"] == "testar":
            selecionados.append(modelo)
    selecionados.sort(key=_preco_para_ordenar)
    return selecionados


def _preco_para_ordenar(modelo: dict) -> tuple:
    """A chave de ordenação: preço de saída (o que mais pesa) e depois o de entrada."""
    return (modelo["saida"], modelo["entrada"])


# ---------------- Uma planilha e um modelo ----------------

def perfil_da_planilha(planilha: dict) -> FileProfile:
    """A planilha da prova no formato que o Interpretador recebe: só os nomes das colunas, sem dados."""
    colunas = []
    for posicao, cabecalho in enumerate(planilha["cabecalhos"], start=1):
        colunas.append(ColunaPerfil(posicao=posicao, nome=cabecalho, tipo_provavel="NAO_INFORMADO", vazias=0,
                                    amostras=[]))
    return FileProfile(processamento_id=f"prova-{planilha['id']}", empresa_id="PROVA", nome_arquivo="prova.csv",
                       formato="csv", codificacao="utf-8", separador=";", linha_do_cabecalho=1, n_linhas=0,
                       n_colunas=len(colunas), colunas=colunas, hash_sha256="0" * 64, tamanho_bytes=0,
                       tipo_carga=TipoCarga.INICIAL, data_referencia=date(2026, 9, 1),
                       status=EstadoProcessamento.RECEBIDO)


def itens_da_proposta(plano) -> list[dict]:
    """As respostas do modelo no formato das métricas: [{"coluna", "status", "campo"}, ...]."""
    itens = []
    for item in plano.itens:
        itens.append({"coluna": item.coluna, "status": item.status.value, "campo": item.campo})
    return itens


def _contar_observacoes(plano, trecho: str) -> int:
    """Quantas observações da proposta contêm o trecho (ex.: "fora do contrato")."""
    quantidade = 0
    for observacao in plano.observacoes:
        if trecho in observacao:
            quantidade += 1
    return quantidade


def medir_modelo(modelo: dict, planilhas: list[dict], campos: list, teto_restante: float, busca=None) -> dict:
    """Roda o modelo nas planilhas e devolve as medidas. Para no teto; desiste se o provedor falhar seguidamente."""
    cliente = LLMClient(modo="llm", limite_chamadas=4 * len(planilhas), teto_de_gasto_usd=teto_restante)
    medidor = ClienteSemDisfarce(cliente)
    exemplos_pontuados = []
    previstos = []
    fora_do_contrato = 0
    dicionario_assumiu = 0
    falhas = []
    falhas_seguidas = 0
    situacao = "completo"
    for planilha in planilhas:
        # Atingiu o teto: o modelo fica parcial (o cliente não gasta mais)
        if cliente.gasto_usd >= teto_restante:
            situacao = "parcial: teto de gasto atingido"
            break
        try:
            plano = interpretador.interpretar(perfil_da_planilha(planilha), campos, 1, medidor,
                                              configuracao=CONFIGURACAO, modelo=modelo["modelo"], busca=busca)
        except FalhaDoProvedor as erro:
            falhas.append({"planilha": planilha["id"], "motivo": str(erro)[:300]})
            falhas_seguidas += 1
            # Várias falhas seguidas: o modelo não está disponível (ex.: fora da conta, nome errado)
            if falhas_seguidas >= LIMITE_DE_FALHAS_SEGUIDAS:
                situacao = "indisponível: o provedor falhou seguidamente"
                break
            continue
        falhas_seguidas = 0
        exemplos_pontuados.append(planilha)
        previstos.append(itens_da_proposta(plano))
        fora_do_contrato += _contar_observacoes(plano, "fora do contrato")
        dicionario_assumiu += _contar_observacoes(plano, "A IA falhou duas vezes")
    return _resumo_do_modelo(modelo, situacao, exemplos_pontuados, previstos, medidor, cliente, fora_do_contrato,
                             dicionario_assumiu, falhas)


def _resumo_do_modelo(modelo, situacao, exemplos, previstos, medidor, cliente, fora_do_contrato, dicionario_assumiu,
                      falhas) -> dict:
    """Junta as medidas de um modelo."""
    resumo = {"provedor": modelo["provedor"], "modelo": modelo["modelo"], "situacao": situacao,
              "planilhas_pontuadas": len(exemplos), "falhas_do_provedor": falhas,
              "respostas_fora_do_contrato": fora_do_contrato, "vezes_que_o_dicionario_assumiu": dicionario_assumiu,
              "custo_usd": round(cliente.gasto_usd, 4), "tokens_entrada": medidor.tokens_entrada,
              "tokens_saida": medidor.tokens_saida}
    # Sem planilha pontuada, não há métrica (nunca um número inventado)
    if not exemplos:
        return resumo
    resumo.update(resumir(contar(exemplos, previstos)))
    resumo["ic95_acuracia_por_campo"] = intervalo_bootstrap(exemplos, previstos)
    resumo["segundos_por_planilha"] = round(medidor.segundos / len(exemplos), 2)
    resumo["custo_por_planilha_usd"] = round(cliente.gasto_usd / len(exemplos), 5)
    return resumo


def medir_b0(planilhas: list[dict]) -> dict:
    """O dicionário sem IA (B0) nas mesmas planilhas: a régua, de graça."""
    mapeador = BaselineMapper()
    previstos = []
    inicio = time.perf_counter()
    for planilha in planilhas:
        previstos.append(mapeador.mapear(planilha["cabecalhos"]))
    segundos = time.perf_counter() - inicio
    resumo = {"provedor": "—", "modelo": "B0 (dicionário, sem IA)", "situacao": "completo",
              "planilhas_pontuadas": len(planilhas), "custo_usd": 0.0}
    resumo.update(resumir(contar(planilhas, previstos)))
    resumo["ic95_acuracia_por_campo"] = intervalo_bootstrap(planilhas, previstos)
    resumo["segundos_por_planilha"] = round(segundos / len(planilhas), 4)
    return resumo


# ---------------- A comparação inteira ----------------

def carregar_resultado() -> dict:
    """O resultado já gravado (para continuar de onde parou) ou um resultado vazio."""
    if CAMINHO_DO_RESULTADO.exists():
        return json.loads(CAMINHO_DO_RESULTADO.read_text(encoding="utf-8"))
    return {"modelos": {}}


def gravar_resultado(resultado: dict) -> None:
    """Grava o resultado (depois de cada modelo, para não perder nada se parar no meio)."""
    CAMINHO_DO_RESULTADO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_DO_RESULTADO.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                    newline="\n")


def verificar_configuracao(modelos: list[dict]) -> None:
    """Para antes de gastar se faltar a chave de algum provedor usado."""
    for modelo in modelos:
        provedor = provedores_de_ia.provedor_do_modelo(modelo["modelo"])
        if provedor == "openai" and not config.CHAVE_OPENAI:
            raise provedores_de_ia.ConfiguracaoDoProvedor("Falta OPENAI_API_KEY no .env (necessária para "
                                                          f"{modelo['modelo']}).")
        if provedor == "anthropic" and not config.CHAVE_ANTHROPIC:
            raise provedores_de_ia.ConfiguracaoDoProvedor("Falta ANTHROPIC_API_KEY no .env (necessária para "
                                                          f"{modelo['modelo']}).")


def comparar(teto_usd: float, busca=None, refazer: bool = False) -> dict:
    """Roda a comparação: B0 e cada modelo selecionado nas planilhas da amostra, respeitando o teto."""
    modelos = modelos_para_testar()
    verificar_configuracao(modelos)
    prova = carregar_prova()
    planilhas = []
    for identificador in carregar_amostra():
        planilhas.append(prova[identificador])
    campos = carregar_layout()
    resultado = carregar_resultado()
    if refazer:
        resultado = {"modelos": {}}
    # O gasto acumulado só sobe: inclui o que rodadas anteriores já gastaram, mesmo de modelos refeitos
    if "gasto_acumulado_usd" not in resultado:
        resultado["gasto_acumulado_usd"] = 0.0
    resultado["teto_usd"] = teto_usd
    resultado["configuracao"] = CONFIGURACAO
    resultado["planilhas"] = len(planilhas)
    resultado["b0"] = medir_b0(planilhas)
    for modelo in modelos:
        ja_medido = resultado["modelos"].get(modelo["modelo"])
        # Já completo numa rodada anterior: não gasta de novo
        if ja_medido is not None and ja_medido["situacao"] == "completo":
            continue
        restante = teto_usd - resultado["gasto_acumulado_usd"]
        if restante <= 0:
            resultado["modelos"][modelo["modelo"]] = {"provedor": modelo["provedor"], "modelo": modelo["modelo"],
                                                      "situacao": "não medido: teto de gasto atingido"}
            continue
        medida = medir_modelo(modelo, planilhas, campos, restante, busca=busca)
        resultado["modelos"][modelo["modelo"]] = medida
        resultado["gasto_acumulado_usd"] = round(resultado["gasto_acumulado_usd"] + medida["custo_usd"], 4)
        # Grava depois de cada modelo: se a comparação parar, nada do que foi pago se perde
        gravar_resultado(resultado)
    gravar_resultado(resultado)
    return resultado
