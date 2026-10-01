"""Calibra o baseline B0 SEM olhar a prova (ADR-41).

O problema: o B0 tem dois "botões", o comparador de textos do RapidFuzz e o limite de semelhança. Se
eu escolher os botões pelo resultado na prova, a prova deixa de ser prova (é como estudar com o gabarito).

A solução: separo 20% dos termos de TREINO como "validação" (o B0 não os conhece), gero cabeçalhos com
eles e testo cada combinação de comparador × limite. A melhor pelo acerto geral é gravada em
data/avaliacao/calibracao_b0.json, e o B0 passa a usá-la. A prova só roda depois, uma vez.

Para rodar: python scripts/calibrar_b0.py
"""
import json
import random
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from baselines.baseline_mapper import CAMINHO_CALIBRACAO, COMPARADORES, BaselineMapper, ler_termos  # noqa: E402
from eval.metricas import contar, resumir  # noqa: E402
from scripts.gerar_cabecalhos import AMBIGUAS, EXTRAS, gerar_exemplo  # noqa: E402

# Semente do sorteio (a mesma semente dá sempre o mesmo resultado)
SEED = 11
# Parte dos termos de treino separada para a validação
FRACAO_VALIDACAO = 0.2
# Quantos cabeçalhos de validação são gerados
N_EXEMPLOS = 300
# Os limites de semelhança testados
LIMITES = [70, 75, 80, 85, 90, 95]


def dividir_treino(termos: list[tuple[str, str]], sorteio: random.Random):
    """Separa, por campo, cerca de 20% dos termos (no mínimo 1) para a validação.

    Devolve (ajuste, validacao): ajuste é a lista de pares (termo, campo) que o B0 conhece; validacao é
    campo -> termos que ele NÃO conhece. Campo com um termo só fica inteiro no ajuste.
    """
    # Agrupa os termos por campo
    termos_por_campo: dict[str, list[str]] = {}
    for termo, campo in termos:
        termos_por_campo.setdefault(campo, []).append(termo)
    ajuste, validacao = [], {}
    # Campos em ordem alfabética (a ordem importa para o sorteio dar sempre o mesmo resultado)
    for campo in sorted(termos_por_campo):
        termos_do_campo = sorted(termos_por_campo[campo])
        sorteio.shuffle(termos_do_campo)
        # Quantos vão para a validação (nenhum, se o campo só tem um termo)
        if len(termos_do_campo) >= 2:
            quantidade_na_validacao = max(1, round(len(termos_do_campo) * FRACAO_VALIDACAO))
        else:
            quantidade_na_validacao = 0
        if quantidade_na_validacao:
            validacao[campo] = termos_do_campo[:quantidade_na_validacao]
        for termo in termos_do_campo[quantidade_na_validacao:]:
            ajuste.append((termo, campo))
    return ajuste, validacao


def main() -> dict:
    """Testa todas as combinações na validação e grava a melhor."""
    sorteio = random.Random(SEED)
    ajuste, validacao = dividir_treino(ler_termos(RAIZ / "data" / "vocabulario" / "treino.csv"), sorteio)
    # Gera os cabeçalhos de validação só com termos que o B0 não conhece
    exemplos = []
    for numero in range(N_EXEMPLOS):
        exemplos.append(gerar_exemplo(numero, validacao, AMBIGUAS["treino"], EXTRAS["treino"], sorteio))

    # Mede cada combinação de comparador × limite
    resultados = []
    for comparador in COMPARADORES:
        for limite in LIMITES:
            mapeador = BaselineMapper(termos=ajuste, comparador=comparador, limite=limite)
            previstos = []
            for exemplo in exemplos:
                previstos.append(mapeador.mapear(exemplo["cabecalhos"]))
            resultado = {"comparador": comparador, "limite": limite}
            resultado.update(resumir(contar(exemplos, previstos)))
            resultados.append(resultado)
    # A melhor pelo acerto geral; no empate, o limite mais alto (o mais cauteloso)
    escolhida = None
    for resultado in resultados:
        if escolhida is None or (resultado["acerto_geral"], resultado["limite"]) > (escolhida["acerto_geral"],
                                                                                    escolhida["limite"]):
            escolhida = resultado

    # Quantos termos ficaram na validação
    termos_na_validacao = 0
    for termos_do_campo in validacao.values():
        termos_na_validacao += len(termos_do_campo)
    saida = {"seed": SEED, "termos_ajuste": len(ajuste), "termos_validacao": termos_na_validacao,
             "exemplos_validacao": N_EXEMPLOS, "escolhida": escolhida, "todas": resultados}
    CAMINHO_CALIBRACAO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_CALIBRACAO.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return saida


if __name__ == "__main__":
    calibracao = main()
    for resultado in calibracao["todas"]:
        print(f"{resultado['comparador']:>16} {resultado['limite']:>3}: acerto geral {resultado['acerto_geral']:.1%} | "
              f"campos {resultado['acuracia_por_campo']:.1%} | abstenção recall {resultado['abstencao_recall']:.1%}")
    escolhida = calibracao["escolhida"]
    print(f"\nEscolhida: {escolhida['comparador']} com limite {escolhida['limite']} "
          f"(acerto geral {escolhida['acerto_geral']:.1%} na validação)")
