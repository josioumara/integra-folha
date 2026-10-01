"""Registra a última comparação de modelos como um experimento novo do histórico (ADR-66).

Medir e registrar são dois passos: o script de medição grava o resultado bruto; depois de ler os números, a pessoa
registra o experimento com a pergunta, o que foi testado, a leitura e a decisão. O documento docs/experimentos.md é
regenerado em seguida.

Para rodar (exemplo):
  python scripts/registrar_experimento.py --titulo "Interpretador v2: menos perguntas à toa" ^
      --pergunta "O prompt v2 reduz as perguntas desnecessárias sem perder o recall?" ^
      --o-que-testamos "Prompt v2 do Interpretador nos modelos escolhidos" ^
      --leitura "..." --decisao "..."
"""
import argparse
import json
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.historico_de_experimentos import registrar, resultado_do_interpretador  # noqa: E402
from scripts import gerar_historico_de_experimentos  # noqa: E402

# O resultado bruto da comparação de modelos
CAMINHO_DA_COMPARACAO = RAIZ / "data" / "avaliacao" / "resultados" / "comparacao_modelos.json"


def ler_opcoes() -> argparse.Namespace:
    """Os textos do registro, informados na linha de comando."""
    leitor = argparse.ArgumentParser(description="Registra a última comparação de modelos no histórico.")
    leitor.add_argument("--titulo", required=True, help="nome curto do experimento")
    leitor.add_argument("--pergunta", required=True, help="o que o experimento quer saber")
    leitor.add_argument("--o-que-testamos", required=True, dest="o_que_testamos", help="o que mudou ou foi comparado")
    leitor.add_argument("--leitura", required=True, help="o que os números mostram")
    leitor.add_argument("--decisao", default="", help="a decisão tomada com o resultado")
    leitor.add_argument("--commit", default="", help="o commit do código medido")
    leitor.add_argument("--comparacao", default=str(CAMINHO_DA_COMPARACAO.relative_to(RAIZ)),
                        help="o arquivo da comparação, relativo à raiz (ex.: o do plano B pelo Bedrock)")
    return leitor.parse_args()


def resultados_da_comparacao(comparacao: dict) -> list[dict]:
    """O B0 e cada modelo medido, no formato do histórico (modelos sem métrica ficam de fora)."""
    resultados = [resultado_do_interpretador("B0", "dicionário (sem IA)", comparacao["b0"])]
    for nome_do_modelo, medida in comparacao["modelos"].items():
        # Modelo que não chegou a ser pontuado (ex.: teto atingido) não entra com número inventado
        if "acuracia_por_campo" not in medida:
            continue
        resultados.append(resultado_do_interpretador(comparacao["configuracao"], nome_do_modelo, medida))
    return resultados


def gasto_da_comparacao(comparacao: dict) -> float:
    """Quanto a comparação gastou. A das APIs diretas guarda em "gasto_acumulado_usd"; a do Bedrock, em "gasto_usd"."""
    if "gasto_acumulado_usd" in comparacao:
        return comparacao["gasto_acumulado_usd"]
    return comparacao["gasto_usd"]


def main() -> Path:
    """Registra o experimento, regenera o documento e devolve o caminho do registro."""
    opcoes = ler_opcoes()
    comparacao = json.loads((RAIZ / opcoes.comparacao).read_text(encoding="utf-8"))
    caminho = registrar({
        "titulo": opcoes.titulo, "tipo": "interpretador", "pergunta": opcoes.pergunta,
        "o_que_testamos": opcoes.o_que_testamos,
        "amostra": f"{comparacao['planilhas']} planilhas sorteadas da prova congelada (semente fixa)",
        "modo": "IA real", "resultados": resultados_da_comparacao(comparacao), "leitura": opcoes.leitura,
        "decisao": opcoes.decisao, "custo_usd": gasto_da_comparacao(comparacao),
        "fonte": opcoes.comparacao.replace("\\", "/"), "commit": opcoes.commit})
    gerar_historico_de_experimentos.main()
    return caminho


if __name__ == "__main__":
    print(f"Experimento registrado em {main()} e docs/experimentos.md atualizado.")
