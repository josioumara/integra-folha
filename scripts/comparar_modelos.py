"""Compara os modelos de IA selecionados na triagem, com dinheiro de verdade (ADR-11, ADR-65).

Cada modelo interpreta as mesmas 30 planilhas da prova congelada (configuração B3); o B0 entra como régua.
Grava data/avaliacao/resultados/comparacao_modelos.json depois de cada modelo; rodar de novo continua de onde
parou (os modelos completos não são refeitos nem cobrados de novo).

Precisa de: OPENAI_API_KEY e ANTHROPIC_API_KEY no .env e os índices do RAG (scripts/build_index.py).
Sem chave, para antes de gastar qualquer centavo.

Para rodar:
  python scripts/comparar_modelos.py            (teto de US$ 25 para a comparação inteira)
  python scripts/comparar_modelos.py --teto 10  (outro teto)
  python scripts/comparar_modelos.py --refazer  (esquece os resultados anteriores e mede tudo de novo)
"""
import argparse
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.comparacao_de_modelos import comparar  # noqa: E402
from eval.congelamento import exigir_prova_congelada  # noqa: E402
from rag.busca import indice_disponivel  # noqa: E402
from services import config  # noqa: E402

# O teto da comparação inteira, em dólares
TETO_PADRAO_USD = 25.0


def ler_opcoes() -> argparse.Namespace:
    """As opções da linha de comando: o teto e se é para refazer tudo."""
    leitor = argparse.ArgumentParser(description="Compara os modelos de IA selecionados na triagem.")
    leitor.add_argument("--teto", type=float, default=TETO_PADRAO_USD, help="teto de gasto em dólares")
    leitor.add_argument("--refazer", action="store_true", help="mede tudo de novo, esquecendo o resultado anterior")
    return leitor.parse_args()


def main() -> dict:
    """Confere a prova e o índice, roda a comparação e devolve o resultado."""
    opcoes = ler_opcoes()
    # A prova, a amostra e as métricas têm de estar como foram congeladas (ADR-58)
    exigir_prova_congelada()
    # O B3 usa o RAG: sem o índice, a comparação mediria outra configuração
    if not indice_disponivel():
        sys.exit("Monte os índices antes: python scripts/build_index.py")
    # A comparação congelada mede nas condições do EXP-008, sem o formato garantido (ADR-107): o medidor dela não
    # conhece o esquema. Para medir com o formato garantido, use scripts/medir_pelo_bedrock.py
    config.INTERPRETADOR_FORMATO_GARANTIDO = False
    return comparar(opcoes.teto, refazer=opcoes.refazer)


if __name__ == "__main__":
    resultado = main()
    print(f"Gasto acumulado: US$ {resultado['gasto_acumulado_usd']:.2f} de US$ {resultado['teto_usd']:.2f}")
    b0 = resultado["b0"]
    print(f"  B0 (sem IA): acurácia por campo {b0['acuracia_por_campo']:.1%}")
    for nome_do_modelo, medida in resultado["modelos"].items():
        if "acuracia_por_campo" in medida:
            print(f"  {nome_do_modelo}: acurácia por campo {medida['acuracia_por_campo']:.1%} | abstenção "
                  f"{medida['abstencao_recall']:.1%} | US$ {medida['custo_usd']:.2f} | "
                  f"{medida['segundos_por_planilha']} s por planilha | {medida['situacao']}")
        else:
            print(f"  {nome_do_modelo}: {medida['situacao']}")
