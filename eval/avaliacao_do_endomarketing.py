"""Avaliação do Agente de Endomarketing: fidelidade às fontes, recusa e isolamento (Fase 14, ADR-61).

Os casos ficam em data/avaliacao/endomarketing_casos.json. O que é medido:
- fidelidade: dos blocos que a IA escreveu, quantos passaram na conferência das fontes (fonte que veio
  da busca e todo número presente no trecho citado);
- isolamento: nenhum bloco cita fonte do catálogo de outra empresa;
- recusa quando falta informação: destaque que o catálogo da empresa não traz é avisado e nada é escrito
  sobre ele (três desses assuntos existem no catálogo de OUTRA empresa);
- achar o que existe: destaque que o catálogo traz aparece num bloco, citando a seção certa;
- sensibilidade do guardrail de saída: blocos adulterados de propósito (número trocado, fonte inventada,
  fonte de outra empresa) têm de ser TODOS barrados, e os blocos originais, TODOS mantidos.

Limite honesto: em MOCK, a IA "copia" os trechos do catálogo, então a fidelidade dela é alta por
construção. A adulteração mede o que não depende da IA: se a conferência barra um bloco errado.
O hit@k do catálogo é medido à parte, em scripts/avaliar_rag.py.
"""
import json
import re
from datetime import date
from pathlib import Path

from agents import endomarketing
from rag.busca import buscar_beneficios
from rag.trechos import trechos_catalogo
from services import catalogo

# Onde estão os casos
CAMINHO_DOS_CASOS = Path(__file__).resolve().parent.parent / "data" / "avaliacao" / "endomarketing_casos.json"
# Quem aparece como autor dos pedidos na auditoria
USUARIO_SIMULADO = "avaliacao.simulada"
# O número usado para adulterar um bloco (não aparece em nenhum catálogo)
NUMERO_ADULTERADO = "99999"
# Uma fonte que não existe em catálogo nenhum
FONTE_INVENTADA = "Catálogo inexistente v1 › Benefício inventado"


def carregar_casos() -> dict:
    """Os casos da avaliação."""
    return json.loads(CAMINHO_DOS_CASOS.read_text(encoding="utf-8"))


def trechos_por_empresa(conexao) -> dict:
    """Todos os trechos vigentes do catálogo, separados por empresa: empresa_id -> [{"fonte", "texto"}]."""
    separados = {}
    for trecho in trechos_catalogo(catalogo.documentos_vigentes(conexao)):
        empresa_id = trecho.metadados["empresa_id"]
        if empresa_id not in separados:
            separados[empresa_id] = []
        separados[empresa_id].append({"fonte": trecho.metadados["fonte"], "texto": trecho.texto})
    return separados


def _fontes(trechos: list[dict]) -> set:
    """Só as fontes de uma lista de trechos."""
    fontes = set()
    for trecho in trechos:
        fontes.add(trecho["fonte"])
    return fontes


def _blocos_removidos(resultado) -> int:
    """Quantos blocos a conferência removeu num pedido (cada remoção vira uma observação)."""
    removidos = 0
    for observacao in resultado.observacoes:
        if observacao.startswith("Bloco removido"):
            removidos += 1
    return removidos


def _blocos(resultado) -> list[dict]:
    """Os blocos aprovados pela conferência (vazio se o pedido não gerou material)."""
    if resultado.material is None:
        return []
    return resultado.material["blocos"]


def medir_materiais(conexao, casos: dict, trechos_da_empresa: dict, busca=None) -> list[dict]:
    """Gera todo tipo de material para toda empresa e mede fidelidade e isolamento de cada um."""
    linhas = []
    for empresa_id in casos["materiais"]["empresas"]:
        fontes_da_empresa = _fontes(trechos_da_empresa[empresa_id])
        for tipo in casos["materiais"]["tipos"]:
            resultado = endomarketing.gerar_material(conexao, empresa_id, tipo, USUARIO_SIMULADO, busca=busca)
            # Blocos com fonte fora do catálogo da empresa (tem de ser zero)
            fontes_de_fora = 0
            for bloco in _blocos(resultado):
                for fonte in bloco["fontes"]:
                    if fonte not in fontes_da_empresa:
                        fontes_de_fora += 1
            linhas.append({"empresa_id": empresa_id, "tipo": tipo, "situacao": resultado.situacao,
                           "blocos_aprovados": len(_blocos(resultado)),
                           "blocos_removidos": _blocos_removidos(resultado),
                           "fontes_de_outra_empresa": fontes_de_fora, "blocos": _blocos(resultado)})
    return linhas


def _falou_do_assunto(resultado, secao: str) -> bool:
    """True se algum bloco cita a seção do catálogo (ex.: "Seguro de vida em grupo")."""
    for bloco in _blocos(resultado):
        for fonte in bloco["fontes"]:
            if fonte.endswith(f"› {secao}"):
                return True
    return False


def _avisou_que_nao_tem(resultado, destaque: str) -> bool:
    """True se o pedido avisou que o catálogo não traz o destaque (pela busca ou pela IA)."""
    for observacao in resultado.observacoes:
        if destaque in observacao and ("não traz" in observacao or "não encontrou" in observacao):
            return True
    return False


def medir_destaques(conexao, casos: dict, trechos_da_empresa: dict, busca=None) -> list[dict]:
    """Os destaques fora do catálogo (o certo é avisar e não escrever) e no catálogo (o certo é achar)."""
    linhas = []
    for caso in casos["destaques_fora_do_catalogo"]:
        resultado = endomarketing.gerar_material(conexao, caso["empresa_id"], "comunicado", USUARIO_SIMULADO,
                                                 destaque=caso["destaque"], busca=busca)
        # O certo: avisar e não citar nenhuma fonte de fora da empresa (a seção existe em OUTRA empresa)
        fontes_da_empresa = _fontes(trechos_da_empresa[caso["empresa_id"]])
        citou_fora = False
        for bloco in _blocos(resultado):
            for fonte in bloco["fontes"]:
                if fonte not in fontes_da_empresa:
                    citou_fora = True
        avisou = _avisou_que_nao_tem(resultado, caso["destaque"])
        linhas.append({"id": caso["id"], "tipo": "fora_do_catalogo", "avisou": avisou, "citou_fora": citou_fora,
                       "acertou": avisou and not citou_fora})
    for caso in casos["destaques_no_catalogo"]:
        resultado = endomarketing.gerar_material(conexao, caso["empresa_id"], "comunicado", USUARIO_SIMULADO,
                                                 destaque=caso["destaque"], busca=busca)
        # O certo: nenhum aviso de "não traz" e um bloco citando a seção do assunto
        avisou = _avisou_que_nao_tem(resultado, caso["destaque"])
        achou = _falou_do_assunto(resultado, caso["secao"])
        linhas.append({"id": caso["id"], "tipo": "no_catalogo", "avisou": avisou, "achou": achou,
                       "acertou": achou and not avisou})
    return linhas


def fonte_de_outra_empresa(trechos_da_empresa: dict, empresa_id: str) -> str:
    """Uma fonte real do catálogo de outra empresa (a primeira empresa diferente, em ordem)."""
    for outra_empresa in sorted(trechos_da_empresa):
        if outra_empresa != empresa_id:
            return trechos_da_empresa[outra_empresa][0]["fonte"]
    raise ValueError("É preciso haver pelo menos duas empresas no catálogo.")


def _adulteracoes(bloco: dict, fonte_alheia: str) -> list[tuple[str, dict]]:
    """As versões adulteradas de um bloco: (tipo da adulteração, bloco adulterado)."""
    versoes = []
    # Número trocado: só em bloco que tem número
    if re.search(r"\d+", bloco["texto"]):
        texto_trocado = re.sub(r"\d+", NUMERO_ADULTERADO, bloco["texto"], count=1)
        versoes.append(("numero_trocado", {"texto": texto_trocado, "fontes": bloco["fontes"]}))
    # Fonte inventada e fonte de outra empresa, com o mesmo texto
    versoes.append(("fonte_inventada", {"texto": bloco["texto"], "fontes": [FONTE_INVENTADA]}))
    versoes.append(("fonte_de_outra_empresa", {"texto": bloco["texto"], "fontes": [fonte_alheia]}))
    return versoes


def _passa_na_conferencia(bloco: dict, trechos: list[dict]) -> bool:
    """True se o bloco sozinho passa na conferência de saída do Endomarketing."""
    material = endomarketing.MaterialGerado(titulo="(avaliação)", blocos=[bloco])
    aprovados, _observacoes = endomarketing.conferir_material(material, trechos)
    return len(aprovados) == 1


def medir_adulteracoes(materiais: list[dict], trechos_da_empresa: dict) -> dict:
    """Confere de novo cada bloco original (tem de passar) e as versões adulteradas (têm de ser barradas).

    A conferência usa todo o catálogo da empresa como fontes válidas: assim, a medida não depende da busca.
    """
    medidas = {"originais": 0, "originais_mantidos": 0}
    for material in materiais:
        trechos = trechos_da_empresa[material["empresa_id"]]
        fonte_alheia = fonte_de_outra_empresa(trechos_da_empresa, material["empresa_id"])
        for bloco in material["blocos"]:
            medidas["originais"] += 1
            if _passa_na_conferencia(bloco, trechos):
                medidas["originais_mantidos"] += 1
            for tipo, bloco_adulterado in _adulteracoes(bloco, fonte_alheia):
                # Cada tipo de adulteração tem o seu total e os seus barrados
                if tipo not in medidas:
                    medidas[tipo] = {"total": 0, "barrados": 0}
                medidas[tipo]["total"] += 1
                if not _passa_na_conferencia(bloco_adulterado, trechos):
                    medidas[tipo]["barrados"] += 1
    return medidas


def resumir(materiais: list[dict], destaques: list[dict], adulteracoes: dict) -> dict:
    """Os números do conjunto."""
    aprovados = 0
    removidos = 0
    fontes_de_fora = 0
    gerados = 0
    for material in materiais:
        aprovados += material["blocos_aprovados"]
        removidos += material["blocos_removidos"]
        fontes_de_fora += material["fontes_de_outra_empresa"]
        if material["situacao"] == endomarketing.GERADO:
            gerados += 1
    certos_fora = 0
    casos_fora = 0
    certos_no_catalogo = 0
    casos_no_catalogo = 0
    for destaque in destaques:
        if destaque["tipo"] == "fora_do_catalogo":
            casos_fora += 1
            if destaque["acertou"]:
                certos_fora += 1
        else:
            casos_no_catalogo += 1
            if destaque["acertou"]:
                certos_no_catalogo += 1
    # Todas as adulterações juntas
    adulterados = 0
    barrados = 0
    for tipo, medida in adulteracoes.items():
        if tipo in ("originais", "originais_mantidos"):
            continue
        adulterados += medida["total"]
        barrados += medida["barrados"]
    # Fidelidade: dos blocos que a IA escreveu, a fração que passou na conferência
    escritos = aprovados + removidos
    fidelidade = 0.0
    if escritos:
        fidelidade = round(aprovados / escritos, 3)
    return {
        "materiais": len(materiais), "materiais_gerados": gerados,
        "blocos_escritos": escritos, "blocos_aprovados": aprovados, "fidelidade": fidelidade,
        "fontes_de_outra_empresa": fontes_de_fora,
        "destaques_fora_do_catalogo": f"{certos_fora} de {casos_fora}",
        "destaques_no_catalogo": f"{certos_no_catalogo} de {casos_no_catalogo}",
        "adulterados_barrados": f"{barrados} de {adulterados}",
        "originais_mantidos": f"{adulteracoes['originais_mantidos']} de {adulteracoes['originais']}",
    }


def medir_distancias_de_destaque(casos: dict) -> dict:
    """Uma distância máxima separaria "o catálogo tem o assunto" de "não tem"? Só com o índice real.

    Usa os destaques de DESENVOLVIMENTO (outros assuntos, fora dos casos medidos) e devolve a faixa de
    distâncias de cada grupo. Se as faixas se cruzam, nenhuma distância máxima decide sozinha.
    """
    distancias = {"tem": [], "nao_tem": []}
    for caso in casos["desenvolvimento_da_distancia"]:
        # Sem limite de distância: queremos ver a distância do trecho mais parecido
        trechos = buscar_beneficios(caso["empresa_id"], caso["destaque"], dia=date.today(), k=1,
                                    distancia_maxima=2)
        # Em qual grupo a distância entra: o catálogo tem ou não tem o assunto
        if caso["catalogo_tem"]:
            grupo = "tem"
        else:
            grupo = "nao_tem"
        distancias[grupo].append(round(trechos[0]["distancia"], 3))
    maior_quando_tem = max(distancias["tem"])
    menor_quando_nao_tem = min(distancias["nao_tem"])
    return {"quando_tem": sorted(distancias["tem"]), "quando_nao_tem": sorted(distancias["nao_tem"]),
            "maior_quando_tem": maior_quando_tem, "menor_quando_nao_tem": menor_quando_nao_tem,
            # Só existe um limite que separa os grupos se TODO "tem" ficar abaixo de TODO "não tem"
            "existe_limite_que_separa": maior_quando_tem < menor_quando_nao_tem}


def avaliar(conexao, busca=None) -> dict:
    """Roda todos os casos. conexao: um banco com o catálogo (auth.conectar cria e preenche)."""
    casos = carregar_casos()
    trechos_da_empresa = trechos_por_empresa(conexao)
    materiais = medir_materiais(conexao, casos, trechos_da_empresa, busca=busca)
    destaques = medir_destaques(conexao, casos, trechos_da_empresa, busca=busca)
    adulteracoes = medir_adulteracoes(materiais, trechos_da_empresa)
    return {"modo": endomarketing.cliente_padrao().modo.upper(),
            "resumo": resumir(materiais, destaques, adulteracoes),
            "adulteracoes": adulteracoes, "destaques": destaques, "materiais": materiais}
