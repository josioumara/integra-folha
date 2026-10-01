"""Índice de busca das KBs de endomarketing (a coleção "kbs_endomarketing" do RAG, ADR-125).

RAG ("geração com busca") é dar ao agente, antes de ele escrever, os trechos mais parecidos com o pedido. Este
arquivo corta cada KB PUBLICADA em trechos (um por seção "##"), guarda no índice e busca neles.

Isolamento entre empresas: a busca de uma empresa só olha as KBs GERAIS, as do SANTANDER e as DELA. O código da
empresa vem de quem chama (o especialista escolhe a empresa na tela), nunca do texto do pedido.

A coleção é nova: não mexe nas coleções que já existem (layout, catálogo e mapeamentos aprovados).
"""
from datetime import date

from rag import busca
from rag.trechos import Trecho
from services import kbs_endomarketing

# O nome da coleção no índice
COLECAO_KBS = "kbs_endomarketing"
# Quantos trechos uma busca traz, e a distância máxima aceita (a mesma régua do catálogo de benefícios)
TRECHOS_POR_BUSCA = 4
DISTANCIA_MAXIMA = busca.DISTANCIA_MAXIMA_CATALOGO


def _data_como_numero(data_em_texto: str) -> int:
    """A data "AAAA-MM-DD" como número AAAAMMDD, para o índice comparar vigências (ex.: 20261231)."""
    return int(data_em_texto.replace("-", ""))


def trechos_das_kbs(kbs: list[dict]) -> list[Trecho]:
    """Um trecho por seção de cada KB, com o dono, o tipo e a vigência nas etiquetas.

    Recebe: as KBs publicadas (como devolve kbs_endomarketing.kbs_publicadas, com "corpo").
    Devolve: os trechos. Todo trecho começa pela fonte (título, versão e seção), para o agente citar de onde veio.
    """
    trechos = []
    for kb in kbs:
        for secao in kbs_endomarketing.secoes_da_kb(kb["corpo"]):
            # A fonte: o título da KB, a versão e a seção
            fonte = f"{kb['titulo']} v{kb['versao']} › {secao['titulo']}"
            identificador = f"{kb['kb_id']}:v{kb['versao']}:{secao['titulo']}"
            metadados = {"dono": kb["dono"], "kb_id": kb["kb_id"], "tipo": kb["tipo"], "versao": kb["versao"],
                         "secao": secao["titulo"], "fonte": fonte,
                         "vigencia_inicio": _data_como_numero(kb["vigencia_inicio"]),
                         "vigencia_fim": _data_como_numero(kb["vigencia_fim"])}
            trechos.append(Trecho(identificador, f"{fonte}\n{secao['texto']}", metadados))
    return trechos


def indexar(conexao, pasta=None) -> int:
    """Refaz a coleção com as KBs publicadas e vigentes hoje. Devolve quantos trechos entraram."""
    publicadas = kbs_endomarketing.kbs_publicadas(conexao)
    return busca.gravar_colecao(COLECAO_KBS, trechos_das_kbs(publicadas), pasta)


def atualizar_uma_kb(conexao, kb_id: str, pasta=None) -> int:
    """Troca no índice só os trechos de UMA KB (depois de publicar, retirar ou revisar), sem refazer as outras.

    Refazer tudo leva dezenas de segundos (são centenas de trechos); trocar uma KB leva menos de um segundo.
    Tira os trechos antigos da KB e, se ela tem versão publicada e vigente, põe os novos. Devolve quantos trechos da
    KB ficaram no índice. Sem a coleção montada, levanta busca.IndiceAusente: montar tudo dentro de um clique da tela
    deixaria a pessoa esperando; a coleção é montada uma vez por scripts/indexar_kbs_endomarketing.py.
    """
    banco_de_indices = busca._abrir_banco_de_indices(pasta)
    nomes = []
    for colecao_existente in banco_de_indices.list_collections():
        nomes.append(colecao_existente.name)
    # Coleção ainda não montada: quem chama avisa que o índice ficou para o script
    if COLECAO_KBS not in nomes:
        raise busca.IndiceAusente(f"A coleção {COLECAO_KBS!r} ainda não foi montada: rode "
                                  "scripts/indexar_kbs_endomarketing.py.")
    colecao = banco_de_indices.get_collection(COLECAO_KBS)
    # Tira os trechos antigos desta KB (de qualquer versão)
    colecao.delete(where={"kb_id": kb_id})
    trechos = trechos_das_kbs(kbs_da_mesma_kb(conexao, kb_id))
    if trechos:
        identificadores, textos, textos_de_busca, etiquetas = [], [], [], []
        for trecho in trechos:
            identificadores.append(trecho.id)
            textos.append(trecho.texto)
            textos_de_busca.append(trecho.texto_busca)
            etiquetas.append(trecho.metadados)
        colecao.add(ids=identificadores, documents=textos, embeddings=busca.vetorizar(textos_de_busca),
                    metadatas=etiquetas)
    return len(trechos)


def kbs_da_mesma_kb(conexao, kb_id: str) -> list[dict]:
    """A versão publicada e vigente de uma KB, numa lista (vazia se ela não está publicada ou venceu)."""
    escolhidas = []
    for kb in kbs_endomarketing.kbs_publicadas(conexao):
        if kb["kb_id"] == kb_id:
            escolhidas.append(kb)
    return escolhidas


def buscar_kbs(empresa_id: str, pergunta: str, dia: date | None = None, k: int = TRECHOS_POR_BUSCA,
               pasta=None) -> list[dict]:
    """Busca nas KBs GERAIS, do SANTANDER e SÓ da empresa informada, vigentes no dia.

    Recebe: empresa_id (obrigatório; nunca vem do texto da pergunta); pergunta; dia (sem informar, hoje); k.
    Devolve: os trechos encontrados ({texto, distancia, metadados...}, como a busca do catálogo).
    Sem o índice montado, levanta busca.IndiceAusente.
    """
    # Sem empresa, a busca é recusada (nunca busca "em todas")
    if not empresa_id:
        raise ValueError("A busca nas KBs exige a empresa.")
    dia_como_numero = int((dia or date.today()).strftime("%Y%m%d"))
    # Filtro obrigatório: os donos permitidos E a vigência valendo no dia
    donos_permitidos = [kbs_endomarketing.DONO_GERAL, kbs_endomarketing.DONO_SANTANDER, empresa_id]
    filtro = {"$and": [{"dono": {"$in": donos_permitidos}},
                       {"vigencia_inicio": {"$lte": dia_como_numero}},
                       {"vigencia_fim": {"$gte": dia_como_numero}}]}
    return busca._buscar(COLECAO_KBS, pergunta, k, filtro, DISTANCIA_MAXIMA, pasta)
