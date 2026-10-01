"""Mede o fluxo da empresa de ponta a ponta nos 9 arquivos de envio, em modo MOCK (ADR-59).

Grava o resultado em data/avaliacao/resultados/fluxo.json (mostrado no Painel Técnico).
Roda num banco, numa pasta de arquivos e num ponto de salvamento TEMPORÁRIOS: o banco local, com os seus
usuários e envios, nunca é tocado.

Para rodar: python scripts/avaliar_fluxo.py   (antes: python scripts/gerar_dados.py)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Antes de qualquer import do projeto: tudo temporário e sempre MOCK (a configuração é lida no import)
PASTA_TEMPORARIA = Path(tempfile.mkdtemp(prefix="avaliacao_fluxo_"))
os.environ["CAMINHO_BANCO"] = str(PASTA_TEMPORARIA / "avaliacao.db")
# Sempre num SQLite temporário, mesmo que o .env diga BANCO=postgres: a avaliação nunca toca no banco de uso
os.environ["BANCO"] = "sqlite"
os.environ["PASTA_UPLOADS"] = str(PASTA_TEMPORARIA / "uploads")
os.environ["PASTA_HOMOLOGADOS"] = str(PASTA_TEMPORARIA / "homologados")
os.environ["CAMINHO_CHECKPOINTS"] = str(PASTA_TEMPORARIA / "checkpoints.db")
os.environ["MODE"] = "mock"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.avaliacao_do_fluxo import PASTA_DOS_ENVIOS, avaliar  # noqa: E402
from eval.congelamento import exigir_prova_congelada  # noqa: E402

# Onde o resultado é gravado
SAIDA = RAIZ / "data" / "avaliacao" / "resultados" / "fluxo.json"


def main() -> dict:
    """Roda a avaliação num banco temporário e grava o resultado."""
    # Os gabaritos têm de estar como foram congelados (ADR-58)
    exigir_prova_congelada()
    # Os arquivos de envio não vão para o Git: precisam ser gerados antes
    if not PASTA_DOS_ENVIOS.exists():
        sys.exit("Gere os arquivos de envio antes: python scripts/gerar_dados.py")
    conexao = sqlite3.connect(PASTA_TEMPORARIA / "avaliacao.db", check_same_thread=False)
    resultado = avaliar(conexao)
    conexao.close()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return resultado


if __name__ == "__main__":
    resumo = main()["resumo"]
    print(f"Arquivos: {resumo['arquivos']} | concluídos: {resumo['concluidos']} | erros injetados achados: "
          f"{resumo['erros_achados']} de {resumo['erros_injetados']} | fora do gabarito: "
          f"{resumo['achados_fora_do_gabarito']} | sem edição manual: {resumo['homologados_sem_edicao_manual']} | "
          f"intervenções por arquivo: {resumo['intervencoes_por_arquivo']} | etapas refeitas na retomada: "
          f"{resumo['etapas_refeitas_na_retomada']}")
