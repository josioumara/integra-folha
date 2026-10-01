"""Monta os três índices do RAG a partir das fontes VIGENTES (ADR-08, ADR-09, ADR-70).

Fontes: o layout ativo e o catálogo (do banco da aplicação, com versões), as regras de validação
(data/contratos/regras_v1.json) e o histórico de mapeamentos homologados (só vocabulário de treino).
O terceiro índice, o dos mapeamentos aprovados pelo banco, vem da tabela historico_mapeamentos do banco da
aplicação (rag/aprendizado.py); a avaliação congelada não o consulta.
Os índices ficam em storage/indices/ (fora do Git) e são refeitos do zero a cada execução.

Para rodar: python scripts/build_index.py
"""
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag import aprendizado, indice_do_layout  # noqa: E402
from rag.busca import COLECAO_APROVADOS, COLECAO_CATALOGO, COLECAO_LAYOUT, gravar_colecao  # noqa: E402
from rag.trechos import trechos_catalogo  # noqa: E402
from services import banco, catalogo, homologacao, parametros  # noqa: E402


def main(caminho_banco=None, pasta=None) -> dict:
    """Refaz os três índices. Devolve quantos trechos entraram em cada um.

    caminho_banco e pasta podem ser informados nos testes, para não mexer no banco e nos índices locais
    (caminho_banco vale no SQLite; com BANCO=postgres, o banco é o do .env).
    """
    # Abre o banco da aplicação pela porta única (SQLite ou PostgreSQL, conforme o .env; ADR-67)
    conexao = banco.conectar(caminho_banco)
    # Lê do banco o layout ativo e a versão mais recente de cada documento do catálogo
    versao, campos = parametros.layout_ativo(conexao)
    documentos = catalogo.documentos_mais_recentes(conexao)
    # Os pares aprovados pelo banco (o histórico gravado a cada aprovação)
    pares_aprovados = homologacao.historico(conexao)
    conexao.close()
    # Índice do conhecimento do layout: campos + regras + mapeamentos (o mesmo que a tela Parâmetros refaz sozinha)
    quantidade_layout = indice_do_layout.refazer(versao, campos, pasta)
    # Índice do catálogo de benefícios
    quantidade_catalogo = gravar_colecao(COLECAO_CATALOGO, trechos_catalogo(documentos), pasta)
    # Índice dos mapeamentos aprovados (a memória que aprende)
    quantidade_aprovados = aprendizado.reconstruir_indice(pares_aprovados, campos, pasta)
    return {COLECAO_LAYOUT: quantidade_layout, COLECAO_CATALOGO: quantidade_catalogo,
            COLECAO_APROVADOS: quantidade_aprovados}


if __name__ == "__main__":
    for nome, quantidade in main().items():
        print(f"{nome}: {quantidade} trechos")
