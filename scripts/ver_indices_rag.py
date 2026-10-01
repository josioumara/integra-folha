"""Mostra o que está guardado no ChromaDB, o banco vetorial do RAG (docs/banco_de_dados.md).

O ChromaDB guarda cada trecho de conhecimento em três partes: o texto que o agente lê, as etiquetas (empresa,
fonte, vigência...) e um vetor de números que representa o significado do texto. Por dentro, é uma pasta de
arquivos binários (storage/indices), que não dá para abrir e ler: por isso este script.

Para cada coleção (índice), mostra quantos trechos há e alguns exemplos. Com --buscar, faz uma busca de exemplo e
mostra a distância de cada resultado (0 = significado igual; quanto maior, mais diferente). Só lê: não muda nada.

Para rodar:
  python scripts/ver_indices_rag.py
  python scripts/ver_indices_rag.py --exemplos 5
  python scripts/ver_indices_rag.py --buscar "salário bruto"
  python scripts/ver_indices_rag.py --buscar "seguro de vida" --empresa EMP002
"""
import argparse
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.busca import COLECAO_CATALOGO, COLECAO_LAYOUT, _abrir_banco_de_indices, buscar_beneficios, search_rules  # noqa: E402


def ler_opcoes() -> argparse.Namespace:
    """Quantos exemplos mostrar e, se quiser, uma busca de exemplo."""
    leitor = argparse.ArgumentParser(description="Mostra o conteúdo dos índices do RAG (ChromaDB).")
    leitor.add_argument("--exemplos", type=int, default=3, help="quantos trechos de exemplo por coleção")
    leitor.add_argument("--buscar", default="", help="um texto para buscar (mostra os trechos e as distâncias)")
    leitor.add_argument("--empresa", default="", help="com --buscar: busca no catálogo desta empresa (ex.: EMP001)")
    return leitor.parse_args()


def mostrar_colecoes(quantos_exemplos: int) -> None:
    """Cada coleção: o número de trechos e alguns exemplos com as etiquetas."""
    banco = _abrir_banco_de_indices()
    for colecao in banco.list_collections():
        # Abre a coleção pelo nome (a lista traz só a descrição dela)
        aberta = banco.get_collection(colecao.name)
        print(f"\n=== Coleção {colecao.name}: {aberta.count()} trechos")
        amostra = aberta.get(limit=quantos_exemplos, include=["documents", "metadatas"])
        for texto, etiquetas in zip(amostra["documents"], amostra["metadatas"]):
            primeira_linha = texto.split("\n", 1)[0]
            print(f"- {primeira_linha}")
            print(f"  etiquetas: {etiquetas}")


def mostrar_busca(texto: str, empresa: str) -> None:
    """Uma busca de exemplo: no catálogo da empresa (se informada) ou no conhecimento do layout."""
    if empresa:
        print(f"\n=== Busca no catálogo da {empresa}: {texto!r}")
        trechos = buscar_beneficios(empresa, texto, distancia_maxima=2)
    else:
        print(f"\n=== Busca no conhecimento do layout: {texto!r}")
        trechos = search_rules(texto, distancia_maxima=2)
    for trecho in trechos:
        print(f"- distância {trecho['distancia']:.3f} | {trecho['fonte']}")


if __name__ == "__main__":
    opcoes = ler_opcoes()
    print(f"Índices em storage/indices (coleções esperadas: {COLECAO_LAYOUT}, {COLECAO_CATALOGO})")
    mostrar_colecoes(opcoes.exemplos)
    if opcoes.buscar:
        mostrar_busca(opcoes.buscar, opcoes.empresa)
