"""Mede o Agente de Endomarketing: fidelidade, isolamento, recusa e o guardrail de saída (ADR-61).

Usa a busca REAL no catálogo (o índice de scripts/build_index.py) e grava o resultado em
data/avaliacao/resultados/endomarketing.json (mostrado no Painel Técnico). Também mede se uma distância
máxima da busca separaria "o catálogo tem o assunto" de "não tem", com destaques de desenvolvimento.
Roda num banco TEMPORÁRIO: o banco local não é tocado.

Para rodar: python scripts/avaliar_endomarketing.py   (antes: python scripts/build_index.py)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Antes de qualquer import do projeto: banco temporário (a configuração é lida no import)
PASTA_TEMPORARIA = Path(tempfile.mkdtemp(prefix="avaliacao_endomarketing_"))
os.environ["CAMINHO_BANCO"] = str(PASTA_TEMPORARIA / "avaliacao.db")
# Sempre num SQLite temporário, mesmo que o .env diga BANCO=postgres: a avaliação nunca toca no banco de uso
os.environ["BANCO"] = "sqlite"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.avaliacao_do_endomarketing import avaliar, carregar_casos, medir_distancias_de_destaque  # noqa: E402
from eval.congelamento import exigir_prova_congelada  # noqa: E402
from rag.busca import COLECAO_CATALOGO, indice_disponivel  # noqa: E402
from services import auth  # noqa: E402

# Onde o resultado é gravado
SAIDA = RAIZ / "data" / "avaliacao" / "resultados" / "endomarketing.json"


def main() -> dict:
    """Roda a avaliação com a busca real, num banco temporário, e grava o resultado."""
    # Os casos têm de estar como foram congelados (ADR-58)
    exigir_prova_congelada()
    # A medição é da busca real: sem o índice, não há o que medir
    if not indice_disponivel(COLECAO_CATALOGO):
        sys.exit("Monte os índices antes: python scripts/build_index.py")
    # O banco temporário já nasce com o catálogo inicial das 6 empresas
    conexao = auth.conectar(PASTA_TEMPORARIA / "avaliacao.db")
    resultado = avaliar(conexao)
    conexao.close()
    resultado["distancias_de_destaque"] = medir_distancias_de_destaque(carregar_casos())
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return resultado


if __name__ == "__main__":
    resultado = main()
    resumo = resultado["resumo"]
    distancias = resultado["distancias_de_destaque"]
    print(f"Materiais: {resumo['materiais_gerados']} de {resumo['materiais']} | fidelidade {resumo['fidelidade']:.0%} | "
          f"fontes de outra empresa: {resumo['fontes_de_outra_empresa']} | destaques fora do catálogo avisados: "
          f"{resumo['destaques_fora_do_catalogo']} | no catálogo achados: {resumo['destaques_no_catalogo']} | "
          f"adulterados barrados: {resumo['adulterados_barrados']} | originais mantidos: {resumo['originais_mantidos']}")
    print(f"Distância: quando tem, até {distancias['maior_quando_tem']}; quando não tem, a partir de "
          f"{distancias['menor_quando_nao_tem']} | existe limite que separa: {distancias['existe_limite_que_separa']}")
