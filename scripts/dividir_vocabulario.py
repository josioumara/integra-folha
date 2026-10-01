"""Divide o vocabulário de sinônimos em treino e teste, ANTES de qualquer geração de dados (ADR-37).

Por que isso importa: se a mesma palavra aparecer no treino e no teste, a avaliação mede memória, não
inteligência. Os termos de teste nunca podem ser vistos no treino (nem pelo dicionário do baseline B0,
nem pelos exemplos do prompt, nem pelo Fine-Tuning).

Para rodar: python scripts/dividir_vocabulario.py
Gera data/vocabulario/treino.csv e data/vocabulario/teste.csv. A semente fixa do sorteio garante que a
divisão seja sempre a mesma.
"""
import csv
import random
from pathlib import Path

# Pasta do vocabulário
PASTA = Path(__file__).resolve().parent.parent / "data" / "vocabulario"
# Semente do sorteio: a mesma semente dá sempre o mesmo resultado
SEED = 42
# Cerca de 30% dos termos de cada campo vão para o teste
FRACAO_TESTE = 0.3
# Campos que entraram no layout DEPOIS da primeira divisão. Eles são sorteados no fim, depois dos outros: assim o
# sorteio dos campos antigos continua o mesmo, e o vocabulário de teste já congelado das medições não muda
# (cnpj_grupo: ADR-77)
CAMPOS_ACRESCENTADOS_DEPOIS = ["cnpj_grupo"]


def ordem_do_sorteio(termos_por_campo: dict[str, list[str]]) -> list[str]:
    """Os campos na ordem do sorteio: os da primeira divisão em ordem alfabética; os acrescentados depois, no fim."""
    antigos = []
    novos = []
    for campo in sorted(termos_por_campo):
        if campo in CAMPOS_ACRESCENTADOS_DEPOIS:
            novos.append(campo)
        else:
            antigos.append(campo)
    return antigos + novos


def dividir(termos_por_campo: dict[str, list[str]], seed: int = SEED) -> tuple[list, list]:
    """Para cada campo, sorteia quais termos vão para o teste. Devolve (treino, teste) como pares (campo, termo).

    Todo campo fica com pelo menos um termo no treino e um no teste.
    """
    sorteio = random.Random(seed)
    treino, teste = [], []
    # Percorre os campos em ordem alfabética, com os acrescentados depois no fim (a ordem importa para o sorteio dar
    # sempre o mesmo resultado)
    for campo in ordem_do_sorteio(termos_por_campo):
        # Os termos do campo, em ordem alfabética, depois embaralhados pelo sorteio
        termos = sorted(termos_por_campo[campo])
        sorteio.shuffle(termos)
        # Quantos vão para o teste (pelo menos 1)
        quantidade_no_teste = max(1, round(len(termos) * FRACAO_TESTE))
        # Os primeiros vão para o teste; o resto, para o treino
        for termo in termos[:quantidade_no_teste]:
            teste.append((campo, termo))
        for termo in termos[quantidade_no_teste:]:
            treino.append((campo, termo))
    return treino, teste


def gravar(caminho: Path, linhas: list[tuple[str, str]]) -> None:
    """Grava os pares (campo, termo) num CSV, com quebra de linha no formato Linux (igual à do Git)."""
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, lineterminator="\n")
        escritor.writerow(["campo", "termo"])
        escritor.writerows(linhas)


def main() -> None:
    """Lê todos os sinônimos, divide e grava treino e teste."""
    # Junta os termos de cada campo: campo -> lista de termos
    termos_por_campo = {}
    with open(PASTA / "sinonimos.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            termos_por_campo.setdefault(linha["campo"], []).append(linha["termo"])

    treino, teste = dividir(termos_por_campo)
    gravar(PASTA / "treino.csv", treino)
    gravar(PASTA / "teste.csv", teste)
    print(f"{len(termos_por_campo)} campos | {len(treino)} termos de treino | {len(teste)} de teste")


if __name__ == "__main__":
    main()
