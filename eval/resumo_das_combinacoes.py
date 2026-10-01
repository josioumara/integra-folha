"""EXP-019: o resumo das combinações do Endomarketing (as tabelas e as comparações do experimento).

Para que serve: lê as linhas das duas etapas (eval/combinacoes_do_endomarketing.py grava cada combinação no CSV) e
monta o que vai para o EXP-019 e para o relatório:
- a tabela situação → motivo → quantas combinações → por tipo → por canal → um exemplo;
- as empresas em que nenhuma combinação gera o rascunho, e o porquê;
- a qualidade do que foi GERADO (o WhatsApp que cortou benefícios, o bloco removido, o aviso do destaque);
- a etapa 2 (IA real) lado a lado com a 1 (MOCK): onde a IA real diverge;
- o detector do Bedrock Guardrails, a consistência entre duas rodadas, o custo e o tempo (p50 e p95).
Nada aqui chama a IA nem o banco: são contas sobre as linhas.
"""
import math
import statistics

from agents import endomarketing
from eval.combinacoes_do_endomarketing import (CASO_FORA_DO_CATALOGO, CASO_NORMAL, CONJUNTO_TODOS,
                                               EXPLICACAO_DO_MOTIVO, MOTIVO_EMPRESA_SEM_CATALOGO, agrupar,
                                               comparavel, filtrar)


# ---------------- A tabela por situação ----------------

def _exemplo(linha: dict) -> str:
    """Uma combinação contada numa frase, para a coluna "exemplo" das tabelas.

    Exemplo: "EMP008 · comunicado · E-mail · nenhum benefício · destaque vazio → Escolha pelo menos um benefício..."
    """
    # Os benefícios escolhidos: nenhum, os nomes, ou "todos os N" (a lista inteira não cabe numa célula)
    beneficios = "nenhum benefício"
    # Com benefícios marcados, os nomes deles
    if linha["beneficios"]:
        beneficios = ", ".join(linha["beneficios"])
    # Todos juntos: só a quantidade
    if linha["conjunto"] == CONJUNTO_TODOS:
        beneficios = f"todos os {len(linha['beneficios'])} benefícios"
    # A empresa, o tipo, o canal (pelo nome da tela), a escolha, o destaque e o que a tela mostrou
    return (f"{linha['empresa_id']} · {linha['tipo']} · {endomarketing.CANAIS[linha['canal']]['nome']} · "
            f"{beneficios} · destaque {linha['caso_do_destaque']} → {linha['mensagem']}")


def _contagem(linhas: list[dict], coluna: str, valores) -> dict:
    """Quantas linhas têm cada valor da coluna, na ordem dos valores. Ex.: {"email": 3, "mural": 0, "whatsapp": 1}."""
    contagem = {}
    # Todos os valores começam em zero, para a tabela mostrar também o que não aconteceu
    for valor in valores:
        contagem[valor] = 0
    # Soma cada linha no valor dela
    for linha in linhas:
        contagem[linha[coluna]] += 1
    return contagem


def _contagem_livre(linhas: list[dict], coluna: str) -> dict:
    """Quantas linhas têm cada valor da coluna, só os que aparecem. Ex.: {"GERADO": 10, "RECUSADO": 2}."""
    contagem = {}
    for linha in linhas:
        # O valor que aparece pela primeira vez começa em zero
        contagem[linha[coluna]] = contagem.get(linha[coluna], 0) + 1
    return contagem


def _ordem_da_tabela(linha_da_tabela: dict) -> tuple:
    """A ordem da tabela: mais combinações primeiro; no empate, pela situação e pelo motivo."""
    # O sinal de menos põe o maior número na frente (a ordem normal é do menor para o maior)
    return (-linha_da_tabela["combinacoes"], linha_da_tabela["situacao"], linha_da_tabela["motivo"])


def tabela_de_situacoes(linhas: list[dict]) -> list[dict]:
    """A tabela situação → motivo → quantas combinações → por tipo → por canal → um exemplo, da maior para a menor.

    Recebe: as linhas de uma etapa (a rodada 1; as repetições ficam de fora). Devolve: [{situacao, motivo, explicacao,
    combinacoes, por_tipo, por_canal, exemplo}].
    """
    # Uma linha por par de situação e motivo
    tabela = []
    # Um grupo por par de situação e motivo (ex.: BARRADO_NA_ENTRADA por empresa_sem_catalogo)
    for (situacao, motivo), grupo in agrupar(linhas, ("situacao", "motivo")).items():
        # Quantas, em cada tipo e em cada canal, com a explicação do motivo e o primeiro caso como exemplo
        tabela.append({"situacao": situacao, "motivo": motivo, "explicacao": EXPLICACAO_DO_MOTIVO[motivo],
                       "combinacoes": len(grupo), "por_tipo": _contagem(grupo, "tipo", endomarketing.TIPOS),
                       "por_canal": _contagem(grupo, "canal", endomarketing.CANAIS), "exemplo": _exemplo(grupo[0])})
    # Da situação mais comum para a mais rara (e, no empate, na ordem do nome)
    tabela.sort(key=_ordem_da_tabela)
    return tabela


def empresas_que_nao_geram(linhas: list[dict]) -> list[dict]:
    """As empresas em que NENHUMA combinação gerou o rascunho, com os motivos e o porquê.

    Devolve: [{empresa_id, empresa, combinacoes, motivos: {motivo: quantas}, porque}].
    """
    # Uma linha por empresa que não gera nada
    resultado = []
    # As combinações de cada empresa
    for (empresa_id, nome), grupo in agrupar(linhas, ("empresa_id", "empresa")).items():
        # Basta uma combinação gerada para a empresa sair da lista
        if filtrar(grupo, situacao=endomarketing.GERADO):
            continue
        # Quantas combinações pararam em cada motivo
        motivos = _contagem_livre(grupo, "motivo")
        # O porquê: o motivo que barra a escolha de benefícios (o ataque é recusado antes, em qualquer empresa)
        porque = "Nenhuma combinação gerou o rascunho: ver os motivos."
        if MOTIVO_EMPRESA_SEM_CATALOGO in motivos:
            porque = EXPLICACAO_DO_MOTIVO[MOTIVO_EMPRESA_SEM_CATALOGO]
        resultado.append({"empresa_id": empresa_id, "empresa": nome, "combinacoes": len(grupo), "motivos": motivos,
                          "porque": porque})
    return resultado


# ---------------- O que o GERADO trouxe ----------------

def qualidade_do_gerado(linhas: list[dict]) -> dict:
    """O que os rascunhos GERADOS trouxeram: onde "gerou", mas faltou algo que o especialista pediu.

    Devolve: {gerados, sem_bloco_de_nenhum_escolhido, com_escolhido_sem_bloco, cortados_pelo_canal, com_bloco_removido,
    com_titulo_trocado, ia_nao_encontrou, prometem_juros_zero, destaque_avisado_por_caso: {caso: [avisados, total]}}.
    """
    # Só os rascunhos que saíram
    geradas = filtrar(linhas, situacao=endomarketing.GERADO)
    # Os contadores começam em zero
    qualidade = {"gerados": len(geradas), "sem_bloco_de_nenhum_escolhido": 0, "com_escolhido_sem_bloco": 0,
                 "cortados_pelo_canal": 0, "com_bloco_removido": 0, "com_titulo_trocado": 0, "ia_nao_encontrou": 0,
                 "prometem_juros_zero": 0, "destaque_avisado_por_caso": {}}
    # Cada rascunho soma nas marcas que ele tem
    for linha in geradas:
        # O rascunho saiu, mas não fala de nenhum benefício escolhido (só do atendimento)
        if linha["blocos_sobre_os_escolhidos"] == 0:
            qualidade["sem_bloco_de_nenhum_escolhido"] += 1
        # Algum benefício escolhido ficou sem bloco (ex.: cortado pelo limite do WhatsApp)
        if linha["escolhidos_sem_bloco"]:
            qualidade["com_escolhido_sem_bloco"] += 1
        # O canal cortou o texto (o WhatsApp fica nos 3 primeiros blocos)
        if linha["cortado_pelo_canal"]:
            qualidade["cortados_pelo_canal"] += 1
        # A conferência tirou pelo menos um bloco (fonte, número, link ou termo proibido)
        if linha["blocos_removidos"]:
            qualidade["com_bloco_removido"] += 1
        # O título da IA foi trocado pelo padrão
        if linha["titulo_trocado"]:
            qualidade["com_titulo_trocado"] += 1
        # A IA disse que não achou algo no catálogo
        if linha["ia_nao_encontrou"]:
            qualidade["ia_nao_encontrou"] += 1
        # A promessa do ataque passou para o texto final
        if linha["promete_juros_zero"]:
            qualidade["prometem_juros_zero"] += 1
        # O aviso de destaque fora da escolha, por caso do destaque: [avisados, total]
        contagem_do_caso = qualidade["destaque_avisado_por_caso"].setdefault(linha["caso_do_destaque"], [0, 0])
        contagem_do_caso[1] += 1
        # Avisado: soma no primeiro número
        if linha["destaque_avisado"]:
            contagem_do_caso[0] += 1
    return qualidade


def _escolheu_a_conta_salario(beneficios: list[str]) -> bool:
    """True se algum benefício escolhido é a conta salário (o assunto do destaque normal)."""
    for beneficio in beneficios:
        # Comparado sem acento e em minúsculas ("Conta Salário" também vale)
        if "conta salario" in comparavel(beneficio):
            return True
    return False


def aviso_do_destaque(linhas: list[dict]) -> dict:
    """A tela avisou quando o destaque pede o que os benefícios escolhidos não têm? Só nos rascunhos GERADOS.

    O aviso certo: no destaque fora do catálogo, sempre (a empresa não tem o benefício); no normal (a conta salário sem
    tarifa), só quando a conta salário não está entre os escolhidos. Conta como aviso o da busca (a observação "não
    trazem informação") e, com a IA real, também o da IA ("A IA não encontrou no catálogo").
    Devolve: {caso: {devia_avisar, avisou, nao_devia_avisar, avisou_sem_precisar}}.
    Exemplo: 540 rascunhos com o destaque fora do catálogo e 156 avisos → {"devia_avisar": 540, "avisou": 156, ...}.
    """
    por_caso = {}
    # Os dois casos em que o aviso se mede: o pedido normal e o benefício que a empresa não tem
    for caso in (CASO_NORMAL, CASO_FORA_DO_CATALOGO):
        por_caso[caso] = {"devia_avisar": 0, "avisou": 0, "nao_devia_avisar": 0, "avisou_sem_precisar": 0}
    # Só os gerados: nos outros, a tela mostra a recusa, e não o aviso
    for linha in filtrar(linhas, situacao=endomarketing.GERADO):
        caso = linha["caso_do_destaque"]
        # Os outros casos (vazio e ataques) ficam de fora
        if caso not in por_caso:
            continue
        # O aviso que a tela mostra: o da busca ou o da IA
        avisou = linha["destaque_avisado"] or linha["ia_nao_encontrou"]
        # O normal só devia avisar sem a conta salário; o fora do catálogo, sempre
        devia_avisar = caso == CASO_FORA_DO_CATALOGO or not _escolheu_a_conta_salario(linha["beneficios"])
        if devia_avisar:
            por_caso[caso]["devia_avisar"] += 1
            # Avisou quando devia: o acerto
            if avisou:
                por_caso[caso]["avisou"] += 1
        else:
            por_caso[caso]["nao_devia_avisar"] += 1
            # Avisou sem precisar: o alarme falso
            if avisou:
                por_caso[caso]["avisou_sem_precisar"] += 1
    return por_caso


# ---------------- A IA real: o custo, o tempo, o detector e a comparação com o MOCK ----------------

def _percentil(valores: list[float], fracao: float) -> float | None:
    """O percentil pelo método do "posto mais próximo": p50 é a mediana; no p95, 95% dos valores ficam até ele.

    Exemplo: ([1, 2, 3, 4], 0.5) → 2; ([1, 2, 3, 4], 0.95) → 4. Sem valores: None.
    """
    # Sem valores, não há percentil
    if not valores:
        return None
    # Do menor para o maior
    ordenados = sorted(valores)
    # O posto (contando do 1) é a fração da quantidade, arredondada para cima
    posto = math.ceil(fracao * len(ordenados))
    # Nunca antes do primeiro
    if posto < 1:
        posto = 1
    # A lista começa no 0: o posto 1 é a posição 0
    return ordenados[posto - 1]


def custo_e_tempo(linhas: list[dict]) -> dict:
    """O custo e o tempo das combinações que chamaram a IA: o total, a média por chamada e os percentis do tempo.

    Devolve: {chamadas_da_ia, custo_total_usd, custo_medio_usd, tokens_entrada_medio, tokens_saida_medio, segundos_p50,
    segundos_p95, segundos_maximo}.
    """
    # O custo de todas as linhas (a checagem do detector também custa, mesmo sem chamar a IA do material)
    custo_total = 0.0
    for linha in linhas:
        if linha["custo_usd"] is not None:
            custo_total += linha["custo_usd"]
    # O tempo e os tokens, só das combinações em que a IA escreveu
    chamaram = filtrar(linhas, ia_chamada=True)
    # Os tempos e os tokens de cada chamada
    segundos = []
    tokens_entrada = []
    tokens_saida = []
    for linha in chamaram:
        segundos.append(linha["segundos"])
        # Os tokens só existem quando foram medidos (a IA real)
        if linha["tokens_entrada"] is not None:
            tokens_entrada.append(linha["tokens_entrada"])
        if linha["tokens_saida"] is not None:
            tokens_saida.append(linha["tokens_saida"])
    # Os percentis do tempo já entram; as médias, logo abaixo
    resumo = {"chamadas_da_ia": len(chamaram), "custo_total_usd": round(custo_total, 4), "custo_medio_usd": None,
              "tokens_entrada_medio": None, "tokens_saida_medio": None, "segundos_p50": _percentil(segundos, 0.50),
              "segundos_p95": _percentil(segundos, 0.95), "segundos_maximo": None}
    # As médias e o máximo só quando há o que medir
    if chamaram:
        resumo["custo_medio_usd"] = round(custo_total / len(chamaram), 5)
        resumo["segundos_maximo"] = max(segundos)
    if tokens_entrada:
        resumo["tokens_entrada_medio"] = round(statistics.mean(tokens_entrada))
    if tokens_saida:
        resumo["tokens_saida_medio"] = round(statistics.mean(tokens_saida))
    return resumo


def checagens_do_detector(linhas: list[dict]) -> dict:
    """O que o detector do Bedrock Guardrails disse, por caso do destaque: {caso: {resultado: quantas}}."""
    # {caso: {resultado: quantas}}
    por_caso = {}
    for linha in linhas:
        # Sem checagem: o MOCK, o destaque vazio ou o que a lista de frases já barrou
        if not linha["checagem_do_detector"]:
            continue
        # O resultado (normal, suspeito, estourou ou erro) somado no caso do destaque
        do_caso = por_caso.setdefault(linha["caso_do_destaque"], {})
        do_caso[linha["checagem_do_detector"]] = do_caso.get(linha["checagem_do_detector"], 0) + 1
    return por_caso


def _divergencia(mock: dict, real: dict) -> dict:
    """Uma combinação em que a IA real mudou a situação ou o motivo do MOCK, com as observações da IA real."""
    # A combinação, as duas situações lado a lado e o que a IA real observou
    return {"combinacao": real["combinacao"], "empresa_id": real["empresa_id"], "tipo": real["tipo"],
            "canal": real["canal"], "conjunto": real["conjunto"], "caso_do_destaque": real["caso_do_destaque"],
            "mock": f"{mock['situacao']} ({mock['motivo']})", "ia_real": f"{real['situacao']} ({real['motivo']})",
            "observacoes": real["observacoes"]}


def comparar_com_o_mock(linhas_da_etapa_1: list[dict], linhas_da_etapa_2: list[dict]) -> dict:
    """A etapa 2 lado a lado com a 1: a mesma combinação no MOCK e na IA real.

    Devolve: {pares: {"MOCK → IA real": quantas}, divergencias: [{combinacao, ..., mock, ia_real, observacoes}],
    blocos_medios: {mock, ia_real}, tamanho_medio: {mock, ia_real}} (as médias só dos GERADOS nas duas).
    """
    # As linhas do MOCK pelo número da combinação, para achar o par de cada linha da IA real
    da_etapa_1 = {}
    for linha in linhas_da_etapa_1:
        da_etapa_1[linha["combinacao"]] = linha
    # Quantas combinações em cada par de situações (ex.: "GERADO → FALHA")
    pares = {}
    # As combinações em que a situação ou o motivo mudaram
    divergencias = []
    # Os tamanhos dos rascunhos gerados nas duas etapas (em blocos e em letras)
    blocos_no_mock = []
    blocos_na_ia = []
    tamanho_no_mock = []
    tamanho_na_ia = []
    # Só a primeira rodada: as repetições medem a consistência, não a divergência
    for real in filtrar(linhas_da_etapa_2, rodada=1):
        mock = da_etapa_1[real["combinacao"]]
        # O par de situações (ex.: "GERADO → FALHA")
        par = f"{mock['situacao']} → {real['situacao']}"
        pares[par] = pares.get(par, 0) + 1
        # Diverge quando a situação ou o motivo mudam
        if (mock["situacao"], mock["motivo"]) != (real["situacao"], real["motivo"]):
            divergencias.append(_divergencia(mock, real))
        # O tamanho dos rascunhos, quando os dois geraram
        if mock["situacao"] == endomarketing.GERADO and real["situacao"] == endomarketing.GERADO:
            blocos_no_mock.append(mock["blocos"])
            blocos_na_ia.append(real["blocos"])
            tamanho_no_mock.append(mock["tamanho_do_texto"])
            tamanho_na_ia.append(real["tamanho_do_texto"])
    # As médias ficam vazias até haver um par gerado nas duas etapas
    comparacao = {"pares": pares, "divergencias": divergencias, "blocos_medios": None, "tamanho_medio": None}
    # As médias, quando houve pelo menos um par gerado nas duas
    if blocos_no_mock:
        comparacao["blocos_medios"] = {"mock": round(statistics.mean(blocos_no_mock), 2),
                                       "ia_real": round(statistics.mean(blocos_na_ia), 2)}
        comparacao["tamanho_medio"] = {"mock": round(statistics.mean(tamanho_no_mock)),
                                       "ia_real": round(statistics.mean(tamanho_na_ia))}
    return comparacao


def consistencia(linhas_da_etapa_2: list[dict]) -> dict:
    """As combinações que rodaram duas vezes com a IA real: quantas deram a mesma situação e o mesmo texto.

    Devolve: {pares, mesma_situacao, mesmo_numero_de_blocos, mesmo_texto}.
    """
    # A primeira rodada de cada combinação, pelo número
    primeiras = {}
    for linha in filtrar(linhas_da_etapa_2, rodada=1):
        primeiras[linha["combinacao"]] = linha
    # Os contadores da consistência
    resultado = {"pares": 0, "mesma_situacao": 0, "mesmo_numero_de_blocos": 0, "mesmo_texto": 0}
    # Cada repetição comparada com a primeira rodada da mesma combinação
    for segunda in filtrar(linhas_da_etapa_2, rodada=2):
        primeira = primeiras.get(segunda["combinacao"])
        # A primeira rodada pode ter ficado de fora (o teto chegou antes)
        if primeira is None:
            continue
        resultado["pares"] += 1
        # A mesma situação, o mesmo número de blocos e o mesmo texto, letra por letra
        if primeira["situacao"] == segunda["situacao"]:
            resultado["mesma_situacao"] += 1
        if primeira["blocos"] == segunda["blocos"]:
            resultado["mesmo_numero_de_blocos"] += 1
        if primeira["texto"] == segunda["texto"]:
            resultado["mesmo_texto"] += 1
    return resultado


# ---------------- O resumo das duas etapas ----------------

def _resumo_da_etapa_1(linhas_da_etapa_1: list[dict]) -> dict:
    """A etapa 1 (MOCK): quantas, por situação, a tabela, as empresas sem nada, a qualidade e o aviso do destaque."""
    # A grade aprovada, sem o caso extra (o ataque disfarçado)
    aprovadas = filtrar(linhas_da_etapa_1, na_grade_aprovada=True)
    # O que vai para o EXP e para o relatório
    return {"combinacoes": len(linhas_da_etapa_1), "na_grade_aprovada": len(aprovadas),
            "caso_extra": len(linhas_da_etapa_1) - len(aprovadas),
            "por_situacao": _contagem_livre(linhas_da_etapa_1, "situacao"),
            "por_situacao_na_grade_aprovada": _contagem_livre(aprovadas, "situacao"),
            "tabela": tabela_de_situacoes(linhas_da_etapa_1),
            "empresas_que_nao_geram": empresas_que_nao_geram(linhas_da_etapa_1),
            "qualidade_do_gerado": qualidade_do_gerado(linhas_da_etapa_1),
            "aviso_do_destaque": aviso_do_destaque(linhas_da_etapa_1)}


def _resumo_da_etapa_2(linhas_da_etapa_1: list[dict], linhas_da_etapa_2: list[dict]) -> dict:
    """A etapa 2 (IA real): a mesma tabela da etapa 1, a comparação com o MOCK, o detector, a consistência e o custo."""
    # As tabelas usam a primeira rodada; as repetições entram só na consistência e no custo
    rodada_1 = filtrar(linhas_da_etapa_2, rodada=1)
    # O que vai para o EXP e para o relatório
    return {"combinacoes": len(linhas_da_etapa_2), "rodada_1": len(rodada_1),
            "por_situacao": _contagem_livre(rodada_1, "situacao"),
            "tabela": tabela_de_situacoes(rodada_1),
            "qualidade_do_gerado": qualidade_do_gerado(rodada_1),
            "aviso_do_destaque": aviso_do_destaque(rodada_1),
            "comparacao_com_o_mock": comparar_com_o_mock(linhas_da_etapa_1, linhas_da_etapa_2),
            "detector": checagens_do_detector(rodada_1),
            "consistencia": consistencia(linhas_da_etapa_2),
            "custo_e_tempo": custo_e_tempo(linhas_da_etapa_2)}


def resumir(linhas_da_etapa_1: list[dict], linhas_da_etapa_2: list[dict]) -> dict:
    """O resumo das duas etapas: as tabelas, as empresas sem nada, a comparação, o detector, o custo e o tempo."""
    # As duas etapas, cada uma com o seu resumo
    return {"etapa_1": _resumo_da_etapa_1(linhas_da_etapa_1),
            "etapa_2": _resumo_da_etapa_2(linhas_da_etapa_1, linhas_da_etapa_2)}
