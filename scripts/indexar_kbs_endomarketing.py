"""Monta (ou refaz) a coleção "kbs_endomarketing" do índice do RAG com as KBs publicadas e vigentes (ADR-125).

Para que serve: a tela Benefícios troca no índice só a KB publicada, retirada ou revisada. Este script refaz a coleção
inteira: na primeira vez (no servidor que ainda não a tem) e se o índice ficar para trás (ex.: o modelo de embeddings
não estava disponível na hora de publicar). As outras coleções (layout, catálogo e mapeamentos aprovados) não mudam.

Como rodar (da pasta integra-folha, com o servidor da porta 8000 PARADO: o ChromaDB não aceita dois processos na
mesma pasta do índice):
    set MODE=mock
    .venv\\Scripts\\python.exe scripts\\indexar_kbs_endomarketing.py
Não usa IA paga: os vetores vêm do modelo de embeddings que roda na própria máquina.
"""
import sys
from pathlib import Path

# Deixa o Python achar as pastas do projeto quando o script roda direto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag import kbs_endomarketing as indice_das_kbs  # noqa: E402
from services import banco  # noqa: E402


def principal() -> int:
    """Abre o banco de dados do .env, refaz a coleção e mostra quantos trechos entraram. Devolve o total."""
    conexao = banco.conectar()
    # try/finally: a conexão fecha mesmo se o índice falhar
    try:
        quantidade = indice_das_kbs.indexar(conexao)
    finally:
        conexao.close()
    print(f"Coleção {indice_das_kbs.COLECAO_KBS}: {quantidade} trechos das KBs publicadas e vigentes.")
    return quantidade


if __name__ == "__main__":
    principal()
