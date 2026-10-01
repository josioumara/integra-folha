"""Congela a prova e as métricas antes de medir (ADR-58): grava data/avaliacao/congelamento.json.

Rode UMA vez antes de medir, e de novo só quando a prova mudar de propósito, dizendo o motivo.
O motivo e a data ficam gravados junto da foto (e no Git), para qualquer pessoa ver quando e por que
a prova mudou.

Para rodar: python scripts/congelar_avaliacao.py "prova inicial"
"""
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.congelamento import congelar  # noqa: E402

if __name__ == "__main__":
    # O motivo é obrigatório: vem da linha de comando
    if len(sys.argv) < 2:
        sys.exit('Informe o motivo. Exemplo: python scripts/congelar_avaliacao.py "prova inicial"')
    registro = congelar(sys.argv[1])
    print(f"Congelados {len(registro['arquivos'])} arquivos em {registro['data']}: {registro['motivo']}")
