"""Métricas da avaliação do Interpretador (ADR-37).

- Acurácia por campo: das colunas que TÊM um campo certo, quantas foram mapeadas para ele.
- Abstenção: das colunas que deveriam virar pendência (AMBIGUO ou NAO_MAPEADO), quantas viraram
  ("recall"), e das pendências que o mapeador criou, quantas eram mesmo necessárias ("precisão").
- Acerto geral: toda coluna conta; abster-se quando devia também é acerto.
- IC 95% por bootstrap: sorteia as planilhas com reposição milhares de vezes e vê a faixa em que a
  acurácia cai em 95% dos sorteios. Mostra se uma diferença entre configurações é real ou sorte.
"""
import random

# As respostas que querem dizer "pedir ajuda" em vez de propor um campo
PENDENCIAS = {"AMBIGUO", "NAO_MAPEADO"}


def resposta(item: dict) -> str:
    """O que o mapeador respondeu para a coluna: o campo proposto, ou a situação de pendência."""
    if item["status"] == "PROPOSTO":
        return item["campo"]
    return item["status"]


def contar(exemplos: list[dict], previstos: list[list[dict]]) -> dict:
    """Conta acertos e abstenções em todos os exemplos (cada exemplo é uma planilha)."""
    contagem = {"campos": 0, "campos_certos": 0, "deveria_abster": 0, "absteve_certo": 0, "absteve": 0}
    for exemplo, itens in zip(exemplos, previstos):
        for item in itens:
            # A resposta certa e a resposta dada, para esta coluna
            esperado = exemplo["esperado"][item["coluna"].strip()]
            dado = resposta(item)
            # A coluna deveria virar pendência
            if esperado in PENDENCIAS:
                contagem["deveria_abster"] += 1
                if dado in PENDENCIAS:
                    contagem["absteve_certo"] += 1
            # A coluna tem um campo certo
            else:
                contagem["campos"] += 1
                if dado == esperado:
                    contagem["campos_certos"] += 1
            # Conta toda pendência que o mapeador criou (certa ou não)
            if dado in PENDENCIAS:
                contagem["absteve"] += 1
    return contagem


def _dividir(parte: int, total: int) -> float:
    """parte / total, ou 0 quando o total é zero (evita a divisão por zero)."""
    if total == 0:
        return 0.0
    return parte / total


def resumir(contagem: dict) -> dict:
    """Transforma as contagens em porcentagens (de 0 a 1)."""
    return {
        "acuracia_por_campo": _dividir(contagem["campos_certos"], contagem["campos"]),
        "abstencao_recall": _dividir(contagem["absteve_certo"], contagem["deveria_abster"]),
        "abstencao_precisao": _dividir(contagem["absteve_certo"], contagem["absteve"]),
        "acerto_geral": _dividir(contagem["campos_certos"] + contagem["absteve_certo"],
                                 contagem["campos"] + contagem["deveria_abster"]),
        "n_colunas_com_campo": contagem["campos"],
        "n_colunas_para_abster": contagem["deveria_abster"],
    }


def acuracia_de_cada_campo(exemplos: list[dict], previstos: list[list[dict]]) -> list[dict]:
    """A acurácia separada por campo do layout, do campo mais difícil para o mais fácil.

    Mostra ONDE o mapeador erra: um número geral de 50% pode esconder campos sempre certos (cpf) e
    campos quase sempre errados (um nome de coluna que muda muito de empresa para empresa).
    Exemplo de item devolvido: {"campo": "valor_renda", "colunas": 250, "acertos": 120, "acuracia": 0.48}
    """
    # Para cada campo certo: quantas colunas deveriam ir para ele e quantas foram
    colunas_por_campo = {}
    acertos_por_campo = {}
    for exemplo, itens in zip(exemplos, previstos):
        for item in itens:
            esperado = exemplo["esperado"][item["coluna"].strip()]
            # Colunas que deveriam virar pendência não têm campo certo: ficam na métrica de abstenção
            if esperado in PENDENCIAS:
                continue
            # Conta mais uma coluna deste campo (começa em zero na primeira vez)
            colunas_por_campo[esperado] = colunas_por_campo.get(esperado, 0) + 1
            if esperado not in acertos_por_campo:
                acertos_por_campo[esperado] = 0
            # Conta o acerto quando o mapeador propôs exatamente este campo
            if resposta(item) == esperado:
                acertos_por_campo[esperado] += 1
    # Monta uma linha por campo
    linhas = []
    for campo, colunas in colunas_por_campo.items():
        acertos = acertos_por_campo[campo]
        linhas.append({"campo": campo, "colunas": colunas, "acertos": acertos,
                       "acuracia": _dividir(acertos, colunas)})
    # Do pior para o melhor: os campos difíceis aparecem primeiro (empate: ordem alfabética)
    linhas.sort(key=_chave_do_pior_para_o_melhor)
    return linhas


def _chave_do_pior_para_o_melhor(linha: dict) -> tuple:
    """A chave de ordenação: primeiro a acurácia (menor antes), depois o nome do campo."""
    return (linha["acuracia"], linha["campo"])


def intervalo_bootstrap(exemplos: list[dict], previstos: list[list[dict]], metrica: str = "acuracia_por_campo",
                        repeticoes: int = 2000, seed: int = 7) -> tuple[float, float]:
    """A faixa de 95% da métrica (IC 95%), sorteando as PLANILHAS com reposição.

    Com reposição quer dizer que a mesma planilha pode sair mais de uma vez num sorteio.
    """
    # Sorteio com semente fixa: o mesmo resultado a cada execução
    sorteio = random.Random(seed)
    # Cada planilha junto com as respostas dadas para ela
    pares = list(zip(exemplos, previstos))
    valores = []
    for _repeticao in range(repeticoes):
        # Sorteia tantas planilhas quanto existem
        amostra = []
        for _posicao in pares:
            amostra.append(sorteio.choice(pares))
        # Separa de novo as planilhas e as respostas da amostra
        exemplos_da_amostra = []
        previstos_da_amostra = []
        for exemplo, previsto in amostra:
            exemplos_da_amostra.append(exemplo)
            previstos_da_amostra.append(previsto)
        # Calcula a métrica nesta amostra
        valores.append(resumir(contar(exemplos_da_amostra, previstos_da_amostra))[metrica])
    # Ordena e corta 2,5% de cada ponta: sobra a faixa de 95%
    valores.sort()
    return valores[int(0.025 * repeticoes)], valores[int(0.975 * repeticoes) - 1]
