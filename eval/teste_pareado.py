"""Contas para comparar DOIS jeitos de fazer a mesma tarefa, nos MESMOS itens (o teste pareado).

Para que serve: dizer se a diferença de acerto entre dois jeitos (sem IA × com IA, ou um modelo × outro) é de verdade
ou pode ser sorte da amostra. "Pareado" quer dizer que os dois jeitos resolveram exatamente os mesmos itens (a mesma
coluna, a mesma célula de uma pessoa): então só interessam os itens em que eles discordam.

Analogia: dois alunos fazem a mesma prova. As questões que os dois acertaram (ou os dois erraram) não dizem quem é
melhor; só as questões em que um acertou e o outro errou dizem. Se o aluno A ganha 30 dessas e o B ganha 2, a diferença
é de verdade; se ficar 17 a 15, pode ser sorte.

As contas:
- mcnemar_exato: o teste de McNemar exato. Olha só os itens discordantes e pergunta: se os dois jeitos fossem iguais,
  qual a chance de a divisão ficar tão desequilibrada quanto a que vimos? Essa chance é o "valor-p": abaixo de 0,05,
  a diferença é considerada de verdade (com 95% de confiança);
- bootstrap_pareado: o intervalo de confiança da diferença de acerto. Sorteia os GRUPOS (ex.: os arquivos ou as
  planilhas) com reposição, milhares de vezes, e vê quanto a diferença varia. Os itens do mesmo grupo andam juntos,
  porque se parecem entre si (as colunas da mesma planilha têm o mesmo jeito de escrever);
- correcao_de_holm: quando se fazem vários testes ao mesmo tempo (ex.: 7 tipos de arquivo, ou 6 pares de modelos),
  a chance de um deles dar "diferença" por sorte cresce. A correção de Holm aumenta os valores-p na medida certa;
- acuracia_por_dolar: quanto acerto cada dólar compra (o acerto dividido pelo custo).

Não depende de nada do sistema: recebe números e listas, e devolve números. Usado por eval/ganho_por_tipo.py e pela
comparação de modelos.
"""
import random
from math import comb

# Quantas vezes o bootstrap sorteia os grupos (o mesmo número das outras réguas do projeto)
SORTEIOS_DO_BOOTSTRAP = 2000


def mcnemar_exato(so_o_primeiro_acertou: int, so_o_segundo_acertou: int) -> float:
    """O valor-p do teste de McNemar exato (bilateral), a partir dos itens em que os dois jeitos discordam.

    Recebe: quantos itens só o primeiro jeito acertou e quantos só o segundo acertou.
    Devolve: o valor-p, de 0 a 1. Sem nenhum item discordante, 1,0 (não há diferença a testar).
    Como funciona: se os dois jeitos fossem iguais, cada item discordante iria para um lado ou para o outro como uma
    moeda (50% cada). O valor-p é a chance de a moeda dar uma divisão tão desequilibrada quanto a vista, para qualquer
    um dos lados. Ex.: 30 × 2 → 0,0000002 (a diferença é de verdade); 17 × 15 → 0,86 (pode ser sorte).
    """
    discordantes = so_o_primeiro_acertou + so_o_segundo_acertou
    # Sem discordância, os dois jeitos empataram em tudo
    if discordantes == 0:
        return 1.0
    # O lado menor da divisão
    menor = min(so_o_primeiro_acertou, so_o_segundo_acertou)
    # A chance de a moeda dar "menor" ou menos para um lado (a cauda da distribuição binomial com 50%)
    chance_de_uma_cauda = 0.0
    for quantidade in range(menor + 1):
        chance_de_uma_cauda += comb(discordantes, quantidade) * 0.5 ** discordantes
    # Bilateral: tão desequilibrado para qualquer um dos lados (nunca passa de 1)
    return min(1.0, 2 * chance_de_uma_cauda)


def contar_discordantes(pares: list[tuple[bool, bool]]) -> dict:
    """Conta os itens de cada tipo: os dois acertaram, só o primeiro, só o segundo, nenhum.

    Recebe: uma lista de (o primeiro acertou?, o segundo acertou?), um par por item.
    Ex.: [(True, True), (False, True), (False, True)] → {"os_dois": 1, "so_o_primeiro": 0, "so_o_segundo": 2,
    "nenhum": 0}.
    """
    contagem = {"os_dois": 0, "so_o_primeiro": 0, "so_o_segundo": 0, "nenhum": 0}
    for primeiro_acertou, segundo_acertou in pares:
        if primeiro_acertou and segundo_acertou:
            contagem["os_dois"] += 1
        elif primeiro_acertou:
            contagem["so_o_primeiro"] += 1
        elif segundo_acertou:
            contagem["so_o_segundo"] += 1
        else:
            contagem["nenhum"] += 1
    return contagem


def _diferenca_de_acerto(grupos: list[list[tuple[bool, bool]]]) -> float:
    """O acerto do segundo jeito menos o do primeiro, somando todos os itens dos grupos (de −1 a 1)."""
    itens = 0
    acertos_do_primeiro = 0
    acertos_do_segundo = 0
    for grupo in grupos:
        for primeiro_acertou, segundo_acertou in grupo:
            itens += 1
            acertos_do_primeiro += int(primeiro_acertou)
            acertos_do_segundo += int(segundo_acertou)
    # Sem itens, não há diferença
    if itens == 0:
        return 0.0
    return (acertos_do_segundo - acertos_do_primeiro) / itens


def bootstrap_pareado(grupos: list[list[tuple[bool, bool]]], semente: int = 7,
                      sorteios: int = SORTEIOS_DO_BOOTSTRAP) -> dict:
    """A diferença de acerto (segundo − primeiro) e o intervalo de confiança de 95%, sorteando os grupos.

    Recebe: os grupos (ex.: um por arquivo), cada um com os pares (o primeiro acertou?, o segundo acertou?) dos itens
    dele; a semente (o mesmo sorteio sempre) e quantos sorteios.
    Devolve: {"diferenca", "ic_95_baixo", "ic_95_alto", "grupos", "itens"}.
    Ex.: 5 arquivos, em que o com IA acerta 20 pontos a mais em todos → diferença 0,20 e intervalo estreito em volta.
    Com poucos grupos (5 arquivos), o intervalo é grosso: ele diz que a diferença pode variar de arquivo para arquivo.
    """
    quantidade_de_itens = 0
    for grupo in grupos:
        quantidade_de_itens += len(grupo)
    resultado = {"diferenca": _diferenca_de_acerto(grupos), "ic_95_baixo": 0.0, "ic_95_alto": 0.0,
                 "grupos": len(grupos), "itens": quantidade_de_itens}
    # Sem grupos, não há o que sortear
    if not grupos:
        return resultado
    sorteio = random.Random(semente)
    diferencas = []
    for _ in range(sorteios):
        # Um "novo conjunto" do mesmo tamanho, com os grupos sorteados com reposição
        sorteados = []
        for _posicao in range(len(grupos)):
            sorteados.append(sorteio.choice(grupos))
        diferencas.append(_diferenca_de_acerto(sorteados))
    diferencas.sort()
    # As pontas de 2,5% de cada lado ficam de fora
    resultado["ic_95_baixo"] = diferencas[int(0.025 * sorteios)]
    resultado["ic_95_alto"] = diferencas[int(0.975 * sorteios) - 1]
    return resultado


def correcao_de_holm(valores_p: dict[str, float]) -> dict[str, float]:
    """Os valores-p ajustados pela correção de Holm, para vários testes feitos ao mesmo tempo.

    Recebe: {nome do teste: valor-p}. Devolve: {nome do teste: valor-p ajustado}, que se compara com 0,05 como sempre.
    Como funciona: ordena do menor para o maior; o menor é multiplicado pelo número de testes, o segundo pelo número
    menos 1, e assim por diante; um ajustado nunca fica menor que o anterior e nunca passa de 1.
    Ex.: {"T1": 0.01, "T2": 0.04, "T3": 0.30} → {"T1": 0.03, "T2": 0.08, "T3": 0.30}.
    """
    # Os testes do menor valor-p para o maior
    ordenados = sorted(valores_p.items(), key=_valor_p_do_par)
    quantidade = len(ordenados)
    ajustados = {}
    maior_ate_aqui = 0.0
    for posicao, (nome, valor_p) in enumerate(ordenados):
        # O multiplicador cai de um em um: o número de testes que ainda restam
        ajustado = min(1.0, valor_p * (quantidade - posicao))
        # Nunca menor que o do teste anterior (a ordem se mantém)
        maior_ate_aqui = max(maior_ate_aqui, ajustado)
        ajustados[nome] = maior_ate_aqui
    return ajustados


def _valor_p_do_par(par: tuple[str, float]) -> float:
    """O valor-p de um par (nome, valor-p): serve para ordenar os testes."""
    return par[1]


def acuracia_por_dolar(acerto: float, custo_usd: float) -> float | None:
    """Quanto acerto cada dólar compra: o acerto (de 0 a 1) dividido pelo custo. None se o custo for zero.

    Ex.: 82,9% por US$ 1,51 → 0,549 (54,9 pontos por dólar).
    """
    # Sem custo, a divisão não tem sentido (sem IA, a régua é outra: o acerto sozinho)
    if not custo_usd:
        return None
    return acerto / custo_usd
