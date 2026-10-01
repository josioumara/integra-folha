"""Os dois índices do RAG e as funções de busca que os agentes usam (ADR-08, ADR-09, ADR-10).

RAG = a IA consulta uma base de conhecimento antes de responder, e cita a fonte. Aqui ficam as duas bases:
- conhecimento_layout: layout do banco + regras de validação + mapeamentos já homologados.
  Usada pelo Interpretador e pelo Assistente de Correção, pela função search_rules().
- catalogo_beneficios: o catálogo de produtos e benefícios de cada empresa.
  Usada pelo Endomarketing, pela função buscar_beneficios(), SEMPRE filtrada pela empresa do usuário logado.
- mapeamentos_aprovados: os pares coluna → campo aprovados pelo banco (rag/aprendizado.py, ADR-70).
  A search_rules() só consulta este índice quando a aplicação liga o aprendizado; avaliações e testes não ligam.

"Sem evidência" é uma resposta válida: se nem o trecho mais parecido está perto o bastante da pergunta,
a busca devolve uma lista vazia, e o agente deve dizer que não encontrou, em vez de inventar.
"""
import os
from datetime import date

import chromadb
from chromadb.config import Settings

from rag.embeddings import vetorizar
from rag.trechos import Trecho
from services import config

# Onde os índices ficam guardados (fora do Git; refeitos por scripts/build_index.py). A variável PASTA_INDICES troca
# o lugar: o servidor de teste de uma cópia isolada do repositório (worktree) usa assim os índices da pasta principal,
# sem copiar nada (um caminho completo vale como está; um relativo parte da raiz do projeto)
PASTA_INDICES = config.RAIZ / os.getenv("PASTA_INDICES", "storage/indices")
# Nome de cada índice ("coleção", no ChromaDB)
COLECAO_LAYOUT = "conhecimento_layout"
COLECAO_CATALOGO = "catalogo_beneficios"
COLECAO_APROVADOS = "mapeamentos_aprovados"

# O interruptor do aprendizado (ADR-70). Começa DESLIGADO: só a API liga, ao abrir. Assim, os
# scripts de avaliação e os testes medem sempre o mesmo conhecimento congelado, sem os pares aprovados.
_consultar_mapeamentos_aprovados = False

# Quantos trechos devolver (k) e a distância máxima aceita como evidência (0 = idêntico; 2 = oposto).
# Medidos nas consultas de teste (scripts/avaliar_rag.py -> data/avaliacao/resultados/rag.json):
# - k: o menor que acha o trecho certo em 100% das perguntas com resposta (layout 4, catálogo 2).
# - Catálogo: resposta certa até 0,68 e pergunta sem resposta a partir de 0,92 -> corte em 0,80.
# - Layout: as duas faixas se encostam (0,587 x 0,588), então a distância NÃO decide "sem resposta";
#   o corte folgado só descarta o que é claramente outro assunto. Quem diz "não sei" é o Interpretador
#   (NAO_MAPEADO), medido nas Fases 4 e 14 (ADR-42).
K_LAYOUT, K_CATALOGO = 4, 2
DISTANCIA_MAXIMA_LAYOUT = 0.70
DISTANCIA_MAXIMA_CATALOGO = 0.80


def ligar_mapeamentos_aprovados() -> None:
    """Liga o aprendizado: a busca passa a consultar os mapeamentos aprovados, e cada aprovação atualiza o índice.

    Os testes desligam pela variável APRENDIZADO_DO_RAG=desligado (tests/conftest.py): assim, abrir a API num
    teste não faz uma homologação de teste mexer no índice de verdade.
    """
    global _consultar_mapeamentos_aprovados
    # Nos testes, o pedido para ligar é ignorado
    if os.environ.get("APRENDIZADO_DO_RAG") == "desligado":
        return
    _consultar_mapeamentos_aprovados = True


def desligar_mapeamentos_aprovados() -> None:
    """Desliga o aprendizado (os testes usam para voltar ao conhecimento congelado)."""
    global _consultar_mapeamentos_aprovados
    _consultar_mapeamentos_aprovados = False


def mapeamentos_aprovados_ligados() -> bool:
    """True se a aplicação ligou o aprendizado."""
    return _consultar_mapeamentos_aprovados


def _abrir_banco_de_indices(pasta=None):
    """Abre o banco do ChromaDB guardado em disco (sem mandar estatísticas de uso para fora)."""
    return chromadb.PersistentClient(path=str(pasta or PASTA_INDICES), settings=Settings(anonymized_telemetry=False))


def gravar_colecao(nome: str, trechos: list[Trecho], pasta=None) -> int:
    """Recria o índice do zero com os trechos, para ele ficar sempre igual às fontes vigentes.

    Os vetores são calculados ANTES de mexer no índice: se o cálculo falhar (ex.: o modelo de embeddings
    não baixou), o índice antigo continua intacto e nenhum índice vazio fica para trás (ADR-63).
    """
    # Separa o que o ChromaDB precisa: identificadores, textos, textos de busca e etiquetas
    identificadores, textos, textos_de_busca, etiquetas = [], [], [], []
    for trecho in trechos:
        identificadores.append(trecho.id)
        textos.append(trecho.texto)
        textos_de_busca.append(trecho.texto_busca)
        etiquetas.append(trecho.metadados)
    # O vetor vem do texto de BUSCA; calculado primeiro, antes de apagar qualquer coisa
    vetores = []
    if textos_de_busca:
        vetores = vetorizar(textos_de_busca)
    banco = _abrir_banco_de_indices(pasta)
    # Se o índice já existe, apaga para recriar
    nomes_existentes = []
    for colecao_existente in banco.list_collections():
        nomes_existentes.append(colecao_existente.name)
    if nome in nomes_existentes:
        banco.delete_collection(nome)
    # "cosine": a distância mede o ângulo entre os vetores (quanto os significados apontam para o mesmo lado)
    colecao = banco.create_collection(nome, metadata={"hnsw:space": "cosine"})
    # Guarda os trechos: o texto guardado é o que o agente lê (índice sem trechos fica criado e vazio)
    if trechos:
        colecao.add(ids=identificadores, documents=textos, embeddings=vetores, metadatas=etiquetas)
    return len(trechos)


class IndiceAusente(Exception):
    """O índice pedido ainda não foi montado neste ambiente (falta rodar scripts/build_index.py)."""


def _distancia_do_trecho(trecho: dict) -> float:
    """A distância do trecho até a pergunta (usada para ordenar: menor = mais parecido)."""
    return trecho["distancia"]


def _buscar(nome: str, texto: str, k: int, filtro: dict | None, distancia_maxima: float, pasta=None) -> list[dict]:
    """Os k trechos mais parecidos com o texto, dentro do filtro, que estejam perto o bastante.

    Sem o índice montado, levanta IndiceAusente: quem chama decide como seguir sem ele.
    """
    try:
        colecao = _abrir_banco_de_indices(pasta).get_collection(nome)
    except chromadb.errors.NotFoundError as erro:
        # O ChromaDB diz que a coleção não existe: o índice nunca foi montado aqui
        raise IndiceAusente(f"O índice {nome!r} ainda não foi montado: rode scripts/build_index.py.") from erro
    # Pergunta ao índice, com o vetor do texto
    resultado = colecao.query(query_embeddings=vetorizar([texto]), n_results=k, where=filtro)
    # O ChromaDB devolve listas paralelas (uma por pergunta; aqui só há uma pergunta, a posição 0)
    documentos = resultado["documents"][0]
    distancias = resultado["distances"][0]
    etiquetas = resultado["metadatas"][0]
    trechos_encontrados = []
    for documento, distancia, etiqueta in zip(documentos, distancias, etiquetas):
        # Longe demais da pergunta: não é evidência
        if round(distancia, 3) > distancia_maxima:
            continue
        # O trecho com o texto, a distância e todas as etiquetas (fonte, campo, empresa...)
        trecho = {"texto": documento, "distancia": round(distancia, 3)}
        trecho.update(etiqueta)
        trechos_encontrados.append(trecho)
    return trechos_encontrados


def _buscar_aprovados(consulta: str, k: int, distancia_maxima: float, pasta=None) -> list[dict]:
    """Os mapeamentos aprovados parecidos com a consulta. Sem esse índice montado, nenhum (a busca segue sem ele)."""
    try:
        return _buscar(COLECAO_APROVADOS, consulta, k, None, distancia_maxima, pasta)
    except IndiceAusente:
        # Nenhuma aprovação ainda: só o conhecimento do layout
        return []


def search_rules(consulta: str, k: int = K_LAYOUT, distancia_maxima: float = DISTANCIA_MAXIMA_LAYOUT,
                 pasta=None) -> list[dict]:
    """Busca campos, regras e mapeamentos parecidos com a consulta. É conhecimento do banco, sem dado pessoal.

    Diversidade: no máximo um trecho por campo (o mais parecido). Cinco sinônimos do mesmo campo não
    dizem nada novo ao agente e empurrariam para fora uma regra importante.
    """
    # Pede 4 vezes mais candidatos, porque vários podem ser do mesmo campo
    candidatos = _buscar(COLECAO_LAYOUT, consulta, k * 4, None, distancia_maxima, pasta)
    # Com o aprendizado ligado, junta os mapeamentos aprovados e reordena do mais parecido para o menos
    if _consultar_mapeamentos_aprovados:
        candidatos = candidatos + _buscar_aprovados(consulta, k * 4, distancia_maxima, pasta)
        candidatos.sort(key=_distancia_do_trecho)
    escolhidos = []
    ja_vistos = set()
    # Os candidatos já vêm do mais parecido para o menos parecido
    for trecho in candidatos:
        # A chave é o campo; regra não tem campo, então a chave é a própria fonte
        chave = trecho["campo"] or trecho["fonte"]
        if chave not in ja_vistos:
            ja_vistos.add(chave)
            escolhidos.append(trecho)
    # Devolve só os k primeiros
    return escolhidos[:k]


def buscar_beneficios(empresa_id: str, pergunta: str, dia: date | None = None, k: int = K_CATALOGO,
                      distancia_maxima: float = DISTANCIA_MAXIMA_CATALOGO, pasta=None) -> list[dict]:
    """Busca no catálogo SÓ da empresa informada e SÓ nos documentos vigentes no dia (ADR-10).

    O empresa_id vem do usuário logado, nunca do texto da pergunta: pedir "o pacote da Horizonte"
    estando logado como Aurora continua buscando só na Aurora.
    """
    # Sem empresa, a busca é recusada (nunca busca "em todas")
    if not empresa_id:
        raise ValueError("A busca no catálogo exige a empresa do usuário logado.")
    # O dia como número AAAAMMDD, para comparar com a vigência guardada
    dia_como_numero = int((dia or date.today()).strftime("%Y%m%d"))
    # Filtro obrigatório: esta empresa E vigência começando antes do dia E terminando depois
    filtro = {"$and": [{"empresa_id": empresa_id},
                       {"vigencia_inicio": {"$lte": dia_como_numero}},
                       {"vigencia_fim": {"$gte": dia_como_numero}}]}
    return _buscar(COLECAO_CATALOGO, pergunta, k, filtro, distancia_maxima, pasta)


def indice_disponivel(nome: str = COLECAO_LAYOUT, pasta=None) -> bool:
    """O índice já foi montado (scripts/build_index.py) e tem trechos? Sem ele, o Interpretador usa a B2.

    Um índice que existe mas está vazio conta como "não disponível": buscar nele não traria nada.
    """
    try:
        for colecao in _abrir_banco_de_indices(pasta).list_collections():
            if colecao.name == nome:
                # Existe: só vale se tiver pelo menos um trecho
                return _abrir_banco_de_indices(pasta).get_collection(nome).count() > 0
        return False
    except Exception:
        # Qualquer problema para abrir o banco de índices conta como "não disponível"
        return False
