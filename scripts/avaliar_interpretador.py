"""Roda uma configuração do Interpretador na prova (300 cabeçalhos de teste) e grava o resultado (ADR-37).

Por enquanto só o B0 (sem IA) pode rodar; B1 a B5 precisam do provedor de IA (Fases 4 e 14).

Para rodar: python scripts/avaliar_interpretador.py B0
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from baselines.baseline_mapper import BaselineMapper  # noqa: E402
from eval.congelamento import exigir_prova_congelada  # noqa: E402
from eval.metricas import acuracia_de_cada_campo, contar, intervalo_bootstrap, resumir  # noqa: E402

# A prova e onde os resultados são gravados
PROVA = RAIZ / "data" / "avaliacao" / "cabecalhos_teste.jsonl"
PASTA_RESULTADOS = RAIZ / "data" / "avaliacao" / "resultados"


def carregar_prova() -> list[dict]:
    """Os 300 cabeçalhos da prova (um JSON por linha do arquivo)."""
    exemplos = []
    with open(PROVA, encoding="utf-8") as arquivo:
        for linha in arquivo:
            exemplos.append(json.loads(linha))
    return exemplos


def main(configuracao: str) -> dict:
    """Mede a configuração na prova e grava o resultado em data/avaliacao/resultados/<configuração>.json."""
    # Só o B0 roda sem o provedor de IA
    if configuracao != "B0":
        sys.exit(f"{configuracao} depende do provedor de LLM (ainda não escolhido). Por enquanto, só B0.")
    # A prova e as métricas têm de estar como foram congeladas (ADR-58)
    exigir_prova_congelada()
    exemplos = carregar_prova()
    mapeador = BaselineMapper()
    # Mede o tempo de mapear todas as planilhas
    inicio = time.perf_counter()
    previstos = []
    for exemplo in exemplos:
        previstos.append(mapeador.mapear(exemplo["cabecalhos"]))
    segundos = time.perf_counter() - inicio

    # Monta o resultado: descrição, métricas, intervalos de confiança, tempo e custo
    resultado = {
        "configuracao": "B0",
        "descricao": f"Dicionário de sinônimos do treino + RapidFuzz ({mapeador.comparador}, limite "
                     f"{mapeador.limite}, calibrados na validação), sem LLM",
        "data": datetime.now(timezone.utc).date().isoformat(),
        "n_exemplos": len(exemplos),
    }
    resultado.update(resumir(contar(exemplos, previstos)))
    resultado["ic95_acerto_geral"] = intervalo_bootstrap(exemplos, previstos, "acerto_geral")
    resultado["ic95_acuracia_por_campo"] = intervalo_bootstrap(exemplos, previstos)
    # A acurácia de cada campo do layout, do mais difícil para o mais fácil
    resultado["acuracia_de_cada_campo"] = acuracia_de_cada_campo(exemplos, previstos)
    resultado["latencia_media_por_arquivo_ms"] = round(1000 * segundos / len(exemplos), 2)
    # Sem IA, sem custo de API
    resultado["custo_por_arquivo"] = 0.0
    # Grava o resultado
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2) + "\n"
    (PASTA_RESULTADOS / f"{configuracao}.json").write_text(texto, encoding="utf-8", newline="\n")
    return resultado


if __name__ == "__main__":
    # A configuração vem da linha de comando; sem informar, B0
    configuracao_pedida = sys.argv[1] if len(sys.argv) > 1 else "B0"
    resultado = main(configuracao_pedida)
    intervalo = resultado["ic95_acuracia_por_campo"]
    print(f"{resultado['configuracao']}: acerto geral {resultado['acerto_geral']:.1%} | "
          f"acurácia por campo {resultado['acuracia_por_campo']:.1%} "
          f"(IC 95% {intervalo[0]:.1%} a {intervalo[1]:.1%}) | "
          f"abstenção: recall {resultado['abstencao_recall']:.1%}, precisão {resultado['abstencao_precisao']:.1%} | "
          f"{resultado['latencia_media_por_arquivo_ms']} ms por arquivo")
