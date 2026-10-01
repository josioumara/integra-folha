"""Embeddings locais: transformam um texto numa lista de 384 números que representa o SIGNIFICADO (ADR-42).

Textos com sentido parecido ("salário base" e "remuneração mensal") ficam com números parecidos, mesmo
sem letras em comum. É assim que a busca do RAG acha o trecho certo. O modelo roda localmente (sem
chave, sem custo e sem mandar dado para fora) e fica guardado em storage/modelos/ (fora do Git),
baixado uma vez só.
"""
import os
from functools import lru_cache

from services import config

# No Windows sem "modo desenvolvedor", o cache do modelo não usa atalhos (symlinks): funciona igual,
# só mostraria um aviso. Esta linha desliga o aviso.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# O modelo escolhido: multilíngue (bom em português) e leve (cerca de 220 MB)
NOME_MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Onde o modelo fica guardado depois do primeiro download. A variável PASTA_MODELOS troca o lugar: o servidor de teste
# de uma cópia isolada do repositório (worktree) usa assim o modelo da pasta principal, sem baixar de novo
PASTA_MODELOS = config.RAIZ / os.getenv("PASTA_MODELOS", "storage/modelos")


@lru_cache(maxsize=1)
def _carregar_modelo():
    """Carrega o modelo uma vez só (o lru_cache guarda o resultado para as próximas chamadas)."""
    # Importado só aqui dentro: carregar a biblioteca e o modelo leva alguns segundos
    from fastembed import TextEmbedding
    return TextEmbedding(NOME_MODELO, cache_dir=str(PASTA_MODELOS))


def vetorizar(textos: list[str]) -> list[list[float]]:
    """Transforma cada texto em uma lista de 384 números (o "vetor" do significado)."""
    # Tudo em minúsculas, no índice e na pergunta: este modelo é sensível a maiúsculas a ponto de
    # "Salario Mensal Bruto" e "salario mensal bruto" parecerem assuntos diferentes (ADR-42)
    textos_em_minusculas = []
    for texto in textos:
        textos_em_minusculas.append(texto.lower())
    # O modelo devolve um vetor por texto; cada vetor vira uma lista comum de números
    vetores = []
    for vetor in _carregar_modelo().embed(textos_em_minusculas):
        vetores.append(vetor.tolist())
    return vetores
