"""As tabelas do EXP da fidelidade e da relevância do Endomarketing (o RAGAS) e a calibração do juiz.

Para que serve: lê o que eval/ragas_do_endomarketing.py mediu (um CSV por bloco e um por material) e monta o resumo:
- a fidelidade de cada material (as afirmações somadas) e a média, com o intervalo de confiança por bootstrap
  (sorteando materiais: as afirmações do mesmo material andam juntas);
- quantas afirmações sem sustentação na fonte citada estão em outro trecho (a fonte foi citada errado) e quantas não
  estão em trecho nenhum (inventadas), com exemplos;
- a relevância, e as duas métricas por tipo, canal, caso do destaque, tamanho da escolha e empresa;
- o custo do juiz;
- a concordância: o kappa de Cohen entre o juiz e outro avaliador nos 50 blocos da planilha (quando o outro é um juiz
  de IA, é a concordância entre dois juízes, e não uma calibração humana); e a conferência de 10 casos pelo agente que
  mede (uma IA conferindo o juiz).

O kappa de Cohen, em linguagem simples: dois avaliadores que chutassem concordariam às vezes, por sorte. O kappa
desconta essa sorte: 1 é a concordância perfeita; 0, a mesma de quem chuta; abaixo de 0, pior que o chute. O kappa
ponderado dá meio ponto a quem erra por uma casa ("em parte" no lugar de "fiel"), porque a régua tem ordem.
Analogia: dois professores corrigindo as mesmas 50 provas. Se quase todo mundo tira 10, concordar é fácil; o kappa
mede se eles concordam MAIS do que concordariam dando notas ao acaso, com as mesmas proporções de cada nota.
"""
import math
import random

from eval import ragas_do_endomarketing as ragas

# Quantas vezes o bootstrap sorteia a amostra de novo, e a semente (o intervalo sai igual em toda medição)
SORTEIOS_DO_BOOTSTRAP = 2000
SEMENTE_DO_BOOTSTRAP = 7
# Quantos exemplos de afirmação sem sustentação entram no resumo
EXEMPLOS_DE_AFIRMACOES = 12
# As colunas pelas quais as tabelas agrupam os materiais
AGRUPAMENTOS = ("tipo", "canal", "caso_do_destaque", "conjunto", "empresa_id")
# A leitura do kappa (Landis e Koch, 1977): o valor mínimo de cada faixa e o nome dela
FAIXAS_DO_KAPPA = ((0.81, "quase perfeita"), (0.61, "substancial"), (0.41, "moderada"), (0.21, "razoável"),
                   (0.0, "leve"))
# Uma diferença menor que isto entre a fidelidade do RAGAS e a contagem das afirmações é só arredondamento
TOLERANCIA_DA_CONTAGEM = 1e-6


def media(valores: list[float]):
    """A média dos valores, ou None se a lista está vazia."""
    if not valores:
        return None
    return sum(valores) / len(valores)


def _arredondar(valor, casas: int = 4):
    """O valor arredondado, ou None (o JSON do resumo guarda "não medido" como null)."""
    if valor is None:
        return None
    return round(valor, casas)


def _faixa_de_95(sorteados: list[float]) -> list[float]:
    """Os percentis 2,5% e 97,5% dos valores sorteados: o intervalo de confiança de 95%."""
    sorteados.sort()
    return [round(sorteados[int(0.025 * len(sorteados))], 4), round(sorteados[int(0.975 * len(sorteados)) - 1], 4)]


def intervalo_da_media(valores: list[float], semente: int = SEMENTE_DO_BOOTSTRAP):
    """O intervalo de confiança de 95% da média, sorteando os valores com reposição (bootstrap).

    Cada valor é um material: sortear materiais mantém juntas as afirmações do mesmo material.
    Exemplo: [1.0, 1.0, 0.5, 1.0] → cerca de [0.625, 1.0]. Lista vazia → None.
    """
    if not valores:
        return None
    sorteio = random.Random(semente)
    medias = []
    for _ in range(SORTEIOS_DO_BOOTSTRAP):
        soma = 0.0
        # Uma amostra do mesmo tamanho, sorteada com reposição
        for _ in range(len(valores)):
            soma += sorteio.choice(valores)
        medias.append(soma / len(valores))
    return _faixa_de_95(medias)


def materiais_medidos(materiais: list[dict]) -> list[dict]:
    """Só os materiais medidos por inteiro (todos os blocos e a relevância)."""
    medidos = []
    for material in materiais:
        if material["situacao"] == ragas.MATERIAL_MEDIDO:
            medidos.append(material)
    return medidos


def _valores(materiais: list[dict], coluna: str) -> list[float]:
    """Os valores medidos de uma coluna (sem os None)."""
    valores = []
    for material in materiais:
        if material[coluna] is not None:
            valores.append(material[coluna])
    return valores


def _somar(materiais: list[dict], coluna: str) -> int:
    """A soma de uma coluna de contagem."""
    soma = 0
    for material in materiais:
        soma += material[coluna]
    return soma


def resumo_de_um_grupo(materiais: list[dict]) -> dict:
    """As métricas de um grupo de materiais medidos: as médias por material e as afirmações somadas (dos blocos de
    conteúdo; o título conta à parte, em titulos_com_inventada)."""
    afirmacoes = _somar(materiais, "afirmacoes")
    sustentadas = _somar(materiais, "sustentadas_pela_fonte")
    fidelidade_somada = None
    # A fidelidade "somada": todas as afirmações do grupo juntas (um material longo pesa mais)
    if afirmacoes:
        fidelidade_somada = sustentadas / afirmacoes
    return {"materiais": len(materiais),
            "fidelidade_media": _arredondar(media(_valores(materiais, "fidelidade_do_material"))),
            "fidelidade_somada": _arredondar(fidelidade_somada),
            "fidelidade_ao_catalogo_media": _arredondar(media(_valores(materiais, "fidelidade_ao_catalogo"))),
            "relevancia_media": _arredondar(media(_valores(materiais, "relevancia"))),
            "afirmacoes": afirmacoes, "sustentadas_pela_fonte": sustentadas,
            "citadas_errado": _somar(materiais, "sustentadas_em_outro_trecho"),
            "inventadas": _somar(materiais, "inventadas"),
            "materiais_com_inventada": _materiais_com(materiais, "inventadas"),
            "titulos_com_inventada": _materiais_com(materiais, "titulo_inventadas")}


def _materiais_com(materiais: list[dict], coluna: str) -> int:
    """Quantos materiais têm pelo menos 1 na coluna de contagem."""
    quantos = 0
    for material in materiais:
        if material[coluna]:
            quantos += 1
    return quantos


def tabela_por(materiais: list[dict], coluna: str) -> dict:
    """As métricas por valor da coluna (ex.: por tipo: {"faq": {...}, "comunicado": {...}}), em ordem alfabética."""
    grupos = {}
    for material in materiais:
        valor = material[coluna]
        # O primeiro material de um valor abre o grupo dele
        if valor not in grupos:
            grupos[valor] = []
        grupos[valor].append(material)
    tabela = {}
    for valor in sorted(grupos):
        tabela[valor] = resumo_de_um_grupo(grupos[valor])
    return tabela


def contagem_dos_blocos(blocos: list[dict]) -> dict:
    """Quantos blocos de conteúdo o juiz achou fiéis, em parte e não fiéis, e a situação de todos os blocos."""
    rotulos = {}
    for rotulo in ragas.ROTULOS:
        rotulos[rotulo] = 0
    situacoes = {}
    titulos_nao_fieis = 0
    for bloco in blocos:
        situacoes[bloco["situacao"]] = situacoes.get(bloco["situacao"], 0) + 1
        # O título conta à parte (não cita fonte)
        if bloco["e_titulo"]:
            if bloco["rotulo_do_juiz"] and bloco["rotulo_do_juiz"] != ragas.ROTULO_FIEL:
                titulos_nao_fieis += 1
            continue
        if bloco["rotulo_do_juiz"]:
            rotulos[bloco["rotulo_do_juiz"]] += 1
    return {"blocos_de_conteudo_por_rotulo": rotulos, "blocos_por_situacao": situacoes,
            "titulos_com_afirmacao_sem_sustentacao": titulos_nao_fieis}


def exemplos_sem_sustentacao(blocos: list[dict], quantos: int = EXEMPLOS_DE_AFIRMACOES) -> list[dict]:
    """As primeiras afirmações sem sustentação na fonte citada, com o que o juiz achou no resto do catálogo."""
    exemplos = []
    for bloco in blocos:
        for detalhe in bloco["detalhes"]:
            # Só as que a fonte citada não sustenta
            if detalhe["veredito"] == 1:
                continue
            onde = "sem 2º veredito"
            if detalhe.get("veredito_no_catalogo") == 1:
                onde = "citada errado (outro trecho sustenta)"
            elif detalhe.get("veredito_no_catalogo") == 0:
                onde = "inventada (nenhum trecho sustenta)"
            if bloco["e_titulo"]:
                onde = "no título (nenhum trecho sustenta)"
            exemplos.append({"bloco_id": bloco["bloco_id"], "afirmacao": detalhe["afirmacao"], "onde": onde,
                             "motivo_do_juiz": detalhe.get("motivo_no_catalogo", detalhe["motivo"])})
            if len(exemplos) >= quantos:
                return exemplos
    return exemplos


def divergencias_da_contagem(blocos: list[dict]) -> int:
    """Quantos blocos têm a fidelidade do RAGAS diferente da contagem das afirmações (deve ser 0: é uma conferência)."""
    divergentes = 0
    for bloco in blocos:
        if bloco["situacao"] != ragas.BLOCO_MEDIDO:
            continue
        contagem = bloco["sustentadas_pela_fonte"] / bloco["afirmacoes"]
        if bloco["fidelidade"] is None or abs(bloco["fidelidade"] - contagem) > TOLERANCIA_DA_CONTAGEM:
            divergentes += 1
    return divergentes


# ============================== A calibração do juiz ==============================

def _peso(indice_de_a: int, indice_de_b: int, ponderado: bool) -> float:
    """O quanto um par de rótulos conta como concordância: 1 se iguais; no ponderado, meio ponto a uma casa de
    distância (os pesos lineares: 1 − distância ÷ 2)."""
    if not ponderado:
        if indice_de_a == indice_de_b:
            return 1.0
        return 0.0
    distancia = abs(indice_de_a - indice_de_b)
    return 1.0 - distancia / (len(ragas.ROTULOS) - 1)


def kappa_de_cohen(pares: list[tuple[str, str]], ponderado: bool = False):
    """O kappa de Cohen entre dois avaliadores (A e B), com os rótulos de ragas.ROTULOS.

    Recebe: pares [(rótulo de A, rótulo de B)] (ex.: A = o juiz, B = a pessoa); ponderado (True = os pesos lineares da
    régua com ordem).
    Devolve: o kappa (1 = concordância perfeita; 0 = a do acaso), ou None se não dá para calcular (nenhum par, ou os
    dois usaram um rótulo só: o acaso já explicaria tudo).
    Conta: kappa = (observada − esperada) ÷ (1 − esperada), onde "esperada" é a concordância que o acaso daria com as
    mesmas proporções de cada rótulo nos dois avaliadores.
    Exemplo: [("fiel", "fiel"), ("não fiel", "não fiel")] → 1.0.
    """
    if not pares:
        return None
    total = len(pares)
    # A posição de cada rótulo na régua (0 = não fiel, 1 = em parte, 2 = fiel)
    posicao = {}
    for indice, rotulo in enumerate(ragas.ROTULOS):
        posicao[rotulo] = indice
    # A proporção de cada rótulo em cada avaliador, e a concordância observada
    proporcao_de_a = [0.0] * len(ragas.ROTULOS)
    proporcao_de_b = [0.0] * len(ragas.ROTULOS)
    observada = 0.0
    for rotulo_de_a, rotulo_de_b in pares:
        proporcao_de_a[posicao[rotulo_de_a]] += 1 / total
        proporcao_de_b[posicao[rotulo_de_b]] += 1 / total
        observada += _peso(posicao[rotulo_de_a], posicao[rotulo_de_b], ponderado) / total
    # A concordância que o acaso daria: cada combinação de rótulos, com as proporções de cada avaliador
    esperada = 0.0
    for indice_de_a in range(len(ragas.ROTULOS)):
        for indice_de_b in range(len(ragas.ROTULOS)):
            peso = _peso(indice_de_a, indice_de_b, ponderado)
            esperada += peso * proporcao_de_a[indice_de_a] * proporcao_de_b[indice_de_b]
    # Esperada = 1: o acaso já explica tudo, e a conta dividiria por zero
    if esperada >= 1.0 - 1e-12:
        return None
    return (observada - esperada) / (1 - esperada)


def intervalo_do_kappa(pares: list[tuple[str, str]], ponderado: bool = False, semente: int = SEMENTE_DO_BOOTSTRAP):
    """O intervalo de confiança de 95% do kappa, sorteando os pares com reposição (bootstrap). None se não dá."""
    if not pares:
        return None
    sorteio = random.Random(semente)
    valores = []
    for _ in range(SORTEIOS_DO_BOOTSTRAP):
        amostra = []
        for _ in range(len(pares)):
            amostra.append(sorteio.choice(pares))
        valor = kappa_de_cohen(amostra, ponderado)
        # Uma amostra com um rótulo só não tem kappa: fica de fora
        if valor is not None:
            valores.append(valor)
    if not valores:
        return None
    return _faixa_de_95(valores)


def leitura_do_kappa(valor) -> str:
    """O nome da faixa do kappa (Landis e Koch). Ex.: 0.7 → "substancial"; −0.1 → "pior que o acaso"."""
    if valor is None:
        return "não dá para calcular"
    for minimo, nome in FAIXAS_DO_KAPPA:
        if valor >= minimo:
            return nome
    return "pior que o acaso"


def matriz_de_confusao(pares: list[tuple[str, str]]) -> dict:
    """Quantos pares em cada combinação: {rótulo de A: {rótulo de B: quantos}}."""
    matriz = {}
    for rotulo_de_a in ragas.ROTULOS:
        matriz[rotulo_de_a] = {}
        for rotulo_de_b in ragas.ROTULOS:
            matriz[rotulo_de_a][rotulo_de_b] = 0
    for rotulo_de_a, rotulo_de_b in pares:
        matriz[rotulo_de_a][rotulo_de_b] += 1
    return matriz


def estatisticas_dos_pares(pares: list[tuple[str, str]]) -> dict:
    """A concordância simples, o kappa (simples e ponderado, com o intervalo), a leitura e a matriz de uma lista de
    pares [(rótulo de A, rótulo de B)]."""
    iguais = 0
    for rotulo_de_a, rotulo_de_b in pares:
        if rotulo_de_a == rotulo_de_b:
            iguais += 1
    concordancia = None
    if pares:
        concordancia = iguais / len(pares)
    kappa = kappa_de_cohen(pares)
    kappa_ponderado = kappa_de_cohen(pares, ponderado=True)
    return {"pares": len(pares), "concordancia_simples": _arredondar(concordancia), "kappa": _arredondar(kappa),
            "kappa_ic95": intervalo_do_kappa(pares), "kappa_ponderado": _arredondar(kappa_ponderado),
            "kappa_ponderado_ic95": intervalo_do_kappa(pares, ponderado=True), "leitura": leitura_do_kappa(kappa),
            "leitura_do_ponderado": leitura_do_kappa(kappa_ponderado), "matriz": matriz_de_confusao(pares)}


def _rotulos_do_juiz(blocos: list[dict], pelo_catalogo: bool) -> dict:
    """O rótulo do juiz em cada bloco: {bloco_id: rótulo} (vazio nos blocos que ele não rotulou).

    pelo_catalogo: False = pela fonte citada (a mesma régua da planilha); True = pela fidelidade ao catálogo inteiro
    (a análise secundária: a 1ª conferência do juiz nega afirmações que estão no trecho citado, e a 2ª as aceita).
    """
    rotulos = {}
    for bloco in blocos:
        rotulos[bloco["bloco_id"]] = bloco["rotulo_do_juiz"]
        # Na análise secundária, o rótulo sai da fidelidade ao catálogo (só nos blocos que o juiz rotulou)
        if pelo_catalogo and bloco["rotulo_do_juiz"]:
            rotulos[bloco["bloco_id"]] = ragas.rotulo_da_fidelidade(bloco["fidelidade_ao_catalogo"])
    return rotulos


def calibracao(blocos: list[dict], rotulos: dict, pelo_catalogo: bool = False) -> dict:
    """A concordância entre o juiz (A) e outro avaliador (B, ex.: outro juiz de IA) nos blocos que B rotulou.

    Recebe: blocos (as linhas do CSV dos blocos); rotulos ({bloco_id: {"rotulo", "comentario"}}, de ler_rotulos);
    pelo_catalogo (ver _rotulos_do_juiz).
    Devolve: as estatísticas dos pares (a matriz é juiz × outro), a taxa de fiéis do outro, as discordâncias e os
    blocos que o juiz não rotulou (erro, teto ou sem afirmação), que ficam de fora do kappa.
    """
    rotulo_do_juiz = _rotulos_do_juiz(blocos, pelo_catalogo)
    pares = []
    sem_rotulo_do_juiz = []
    discordancias = []
    for bloco_id in sorted(rotulos):
        outro = rotulos[bloco_id]
        juiz = rotulo_do_juiz.get(bloco_id, "")
        if not juiz:
            sem_rotulo_do_juiz.append(bloco_id)
            continue
        pares.append((juiz, outro["rotulo"]))
        if juiz != outro["rotulo"]:
            discordancias.append({"bloco_id": bloco_id, "juiz": juiz, "outro": outro["rotulo"],
                                  "comentario": outro["comentario"]})
    resultado = {"blocos_rotulados": len(rotulos), "fieis_pelo_outro": taxa_de_fieis(rotulos)}
    resultado.update(estatisticas_dos_pares(pares))
    resultado["discordancias"] = discordancias
    resultado["sem_rotulo_do_juiz"] = sem_rotulo_do_juiz
    return resultado


def intervalo_de_wilson(acertos: int, total: int, z: float = 1.96) -> list[float]:
    """O intervalo de confiança de 95% de uma proporção com poucos casos (o de Wilson: não passa de 0 nem de 1).

    Exemplo: 41 de 50 → cerca de [0.692, 0.902].
    """
    proporcao = acertos / total
    centro = (proporcao + z * z / (2 * total)) / (1 + z * z / total)
    margem = z * math.sqrt(proporcao * (1 - proporcao) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(centro - margem, 4), round(centro + margem, 4)]


def taxa_de_fieis(rotulos: dict) -> dict:
    """Quantos blocos um avaliador achou fiéis: {fieis, total, taxa, ic95_wilson} (None na taxa se não há rótulos)."""
    fieis = 0
    for rotulo in rotulos.values():
        if rotulo["rotulo"] == ragas.ROTULO_FIEL:
            fieis += 1
    if not rotulos:
        return {"fieis": 0, "total": 0, "taxa": None, "ic95_wilson": None}
    return {"fieis": fieis, "total": len(rotulos), "taxa": _arredondar(fieis / len(rotulos)),
            "ic95_wilson": intervalo_de_wilson(fieis, len(rotulos))}


def conferencia_do_agente_resumida(conferencia: list[dict]) -> dict:
    """O resumo da conferência do agente que mede (uma IA conferindo o juiz caso a caso; não é uma calibração humana).

    Recebe: [{bloco_id, rotulo_do_juiz, rotulo_do_agente, concorda (True/False), nota}]. Devolve: {casos, concorda,
    discorda: [{bloco_id, nota}]}.
    """
    discorda = []
    for caso in conferencia:
        if not caso["concorda"]:
            discorda.append({"bloco_id": caso["bloco_id"], "nota": caso["nota"]})
    return {"casos": len(conferencia), "concorda": len(conferencia) - len(discorda), "discorda": discorda}


# ============================== O resumo do EXP ==============================

# O que o resumo diz enquanto faltam os rótulos
PENDENTE = "pendente: a planilha ainda não tem rótulos"


def _custo(materiais: list[dict]) -> dict:
    """O custo do juiz nos materiais (o dos blocos e o da relevância de cada um)."""
    total = 0.0
    for material in materiais:
        total += material["custo_usd"]
    por_material = None
    if materiais:
        por_material = total / len(materiais)
    return {"total_usd": round(total, 4), "por_material_usd": _arredondar(por_material, 5)}


def _concordancias(blocos: list[dict], rotulos_dos_50: dict | None) -> dict:
    """Os 50 rótulos da planilha × o juiz, pela fonte citada e pelo catálogo (quando os rótulos vêm de outro juiz de IA,
    é a concordância entre dois juízes, e não uma calibração humana)."""
    concordancias = {"concordancia_com_os_rotulos_dos_50": PENDENTE,
                     "concordancia_com_os_rotulos_dos_50_pelo_catalogo": PENDENTE}
    if rotulos_dos_50:
        concordancias["concordancia_com_os_rotulos_dos_50"] = calibracao(blocos, rotulos_dos_50)
        concordancias["concordancia_com_os_rotulos_dos_50_pelo_catalogo"] = calibracao(blocos, rotulos_dos_50,
                                                                                       pelo_catalogo=True)
    return concordancias


def resumir(amostras: list[dict], blocos: list[dict], materiais: list[dict], rotulos_dos_50: dict | None = None,
            conferencia: list[dict] | None = None) -> dict:
    """O resumo do EXP: as médias com o intervalo, as tabelas por grupo, os blocos, os exemplos e as concordâncias.

    Recebe: amostras (a etapa 1); blocos e materiais (a etapa 2); rotulos_dos_50 (a planilha dos 50, se já tem
    rótulos); conferencia (a do agente que mede, se já foi feita).
    """
    medidos = materiais_medidos(materiais)
    fora_do_catalogo = []
    for amostra in amostras:
        if not amostra["catalogo_confere"]:
            fora_do_catalogo.append({"combinacao": amostra["combinacao"], "porque": amostra["por_que_nao_confere"]})
    fidelidades = _valores(medidos, "fidelidade_do_material")
    relevancias = _valores(medidos, "relevancia")
    resumo = {"materiais_do_exp_019": len(amostras), "materiais_com_catalogo_diferente": fora_do_catalogo,
              "materiais_julgados": len(materiais), "materiais_medidos": len(medidos),
              "geral": resumo_de_um_grupo(medidos),
              "fidelidade_media_ic95": intervalo_da_media(fidelidades),
              "fidelidade_ao_catalogo_media_ic95": intervalo_da_media(_valores(medidos, "fidelidade_ao_catalogo")),
              "relevancia_media_ic95": intervalo_da_media(relevancias),
              "materiais_totalmente_fieis": _contar_iguais_a_um(fidelidades),
              "materiais_evasivos": _materiais_com(medidos, "evasivo"),
              "blocos": contagem_dos_blocos(blocos),
              "divergencias_entre_o_ragas_e_a_contagem": divergencias_da_contagem(blocos),
              "exemplos_sem_sustentacao": exemplos_sem_sustentacao(blocos), "custo_do_juiz": _custo(materiais)}
    # As tabelas por grupo
    for coluna in AGRUPAMENTOS:
        resumo[f"por_{coluna}"] = tabela_por(medidos, coluna)
    # As concordâncias e a conferência do agente, quando já existem
    resumo.update(_concordancias(blocos, rotulos_dos_50))
    resumo["conferencia_do_agente"] = "pendente"
    if conferencia:
        resumo["conferencia_do_agente"] = conferencia_do_agente_resumida(conferencia)
    return resumo


def _contar_iguais_a_um(valores: list[float]) -> int:
    """Quantos valores são 1 (os materiais em que toda afirmação está na fonte citada)."""
    quantos = 0
    for valor in valores:
        if math.isclose(valor, 1.0):
            quantos += 1
    return quantos
