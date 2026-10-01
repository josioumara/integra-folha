"""Gera os conjuntos de cabeçalhos para treinar e avaliar o Interpretador (ADR-37).

Cada exemplo imita o cabeçalho de uma planilha de RH: uma lista de colunas e, para cada coluna, a
resposta certa (o campo do layout, AMBIGUO ou NAO_MAPEADO). Variações realistas: abreviações e erros
de digitação, ordem trocada, colunas extras que não existem no layout e colunas ambíguas.

Regra de ouro: o TREINO usa só o vocabulário de treino; a PROVA (teste) usa só o de teste. As listas
de colunas ambíguas e extras também são divididas, para nada da prova aparecer no treino.

Sai:
- data/avaliacao/cabecalhos_treino.jsonl       (1.500 exemplos: few-shot, Fine-Tuning)
- data/avaliacao/cabecalhos_teste.jsonl        (300 exemplos: a prova do B0 ao B5)
- data/synthetic/historico_mapeamentos.csv     (mapeamentos "já homologados", base do RAG; só treino)

Para rodar: python scripts/gerar_cabecalhos.py
"""
import csv
import json
import random
from pathlib import Path

from scripts.dividir_vocabulario import CAMPOS_ACRESCENTADOS_DEPOIS, ordem_do_sorteio

# Pastas do projeto: a raiz, o vocabulário de entrada e a avaliação de saída
RAIZ = Path(__file__).resolve().parent.parent
PASTA_VOCAB = RAIZ / "data" / "vocabulario"
PASTA_AVALIACAO = RAIZ / "data" / "avaliacao"
# Semente do sorteio (a mesma semente gera sempre os mesmos cabeçalhos)
SEED = 2026
# Quantos exemplos de treino e de teste
N_TREINO, N_TESTE = 1500, 300

# Colunas que NÃO dá para mapear com segurança (esperado: AMBIGUO), divididas entre treino e teste
AMBIGUAS = {"treino": ["Vencimentos", "Valor", "Data", "Total", "Código"],
            "teste": ["Proventos", "Montante", "Dt.", "Soma", "Cód."]}
# Colunas que não existem no layout (esperado: NAO_MAPEADO), também divididas
EXTRAS = {"treino": ["Obs. RH", "Centro de Resultado", "Turno", "Ramal", "Foto", "Crachá"],
          "teste": ["Observação Interna", "Escala", "Sindicato", "Tamanho Uniforme", "Vaga Garagem"]}


def ler_vocabulario(nome: str) -> dict[str, list[str]]:
    """Lê data/vocabulario/<nome>.csv e devolve campo -> nomes de coluna que significam aquele campo."""
    termos = {}
    with open(PASTA_VOCAB / f"{nome}.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            termos.setdefault(linha["campo"], []).append(linha["termo"])
    return termos


def erro_de_digitacao(termo: str, sorteio: random.Random) -> str:
    """Troca de lugar duas letras vizinhas ou apaga uma letra, como no mundo real."""
    # As posições do texto que são letras (espaços e pontos não entram)
    posicoes_de_letras = []
    for posicao, caractere in enumerate(termo):
        if caractere.isalpha():
            posicoes_de_letras.append(posicao)
    # Palavra curta demais: fica como está
    if len(posicoes_de_letras) < 4:
        return termo
    # Sorteia uma letra do meio (nunca a primeira nem a última)
    posicao = sorteio.choice(posicoes_de_letras[1:-1])
    if sorteio.random() < 0.5:
        # Metade das vezes: troca esta letra com a seguinte ("Nome" -> "Noem")
        return termo[:posicao] + termo[posicao + 1] + termo[posicao] + termo[posicao + 2:]
    # Na outra metade: apaga a letra ("Nome" -> "Nme")
    return termo[:posicao] + termo[posicao + 1:]


def variar(termo: str, sorteio: random.Random) -> str:
    """Às vezes deixa o nome em maiúsculas, com espaços sobrando ou com erro de digitação."""
    sorteado = sorteio.random()
    # 15% das vezes: tudo em maiúsculas
    if sorteado < 0.15:
        return termo.upper()
    # 10%: espaços sobrando antes e depois
    if sorteado < 0.25:
        return f" {termo}  "
    # 10%: erro de digitação
    if sorteado < 0.35:
        return erro_de_digitacao(termo, sorteio)
    # No resto, o nome fica como está
    return termo


def campos_da_prova(vocab: dict) -> list[str]:
    """Os campos que os cabeçalhos sorteiam: os da primeira divisão, em ordem alfabética.

    Os campos acrescentados depois (ex.: cnpj_grupo, ADR-77) ficam fora: se entrassem, o sorteio mudaria todos os
    cabeçalhos, e a prova de hoje deixaria de ser comparável com as medições já feitas (EXP-008).
    """
    campos = []
    for campo in sorted(vocab):
        if campo not in CAMPOS_ACRESCENTADOS_DEPOIS:
            campos.append(campo)
    return campos


def gerar_exemplo(indice: int, vocab: dict, ambiguas: list, extras: list, sorteio: random.Random) -> dict:
    """Um cabeçalho de planilha: 8 a 20 campos do layout, até 2 colunas ambíguas e até 3 extras."""
    # Sorteia quais campos do layout a planilha traz
    campos = sorteio.sample(campos_da_prova(vocab), k=sorteio.randint(8, 20))
    colunas, esperado = [], {}
    for campo in campos:
        # Para cada campo, um dos nomes que ele costuma ter, às vezes com variação
        coluna = variar(sorteio.choice(vocab[campo]), sorteio)
        # Se dois campos derem o mesmo nome de coluna, fica só o primeiro
        if coluna.strip() not in esperado:
            colunas.append(coluna)
            esperado[coluna.strip()] = campo
    # Colunas ambíguas: a resposta certa é pedir confirmação
    for coluna in sorteio.sample(ambiguas, k=sorteio.randint(0, 2)):
        colunas.append(coluna)
        esperado[coluna] = "AMBIGUO"
    # Colunas que não existem no layout: a resposta certa é não mapear
    for coluna in sorteio.sample(extras, k=sorteio.randint(0, 3)):
        colunas.append(coluna)
        esperado[coluna] = "NAO_MAPEADO"
    # Embaralha a ordem das colunas, como nas planilhas reais
    sorteio.shuffle(colunas)
    return {"id": indice, "cabecalhos": colunas, "esperado": esperado}


def gravar_jsonl(caminho: Path, exemplos: list[dict]) -> None:
    """Grava um exemplo por linha, em JSON (formato JSONL)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as arquivo:
        for exemplo in exemplos:
            arquivo.write(json.dumps(exemplo, ensure_ascii=False) + "\n")


def main() -> None:
    """Gera o treino, a prova e o histórico de mapeamentos."""
    sorteio = random.Random(SEED)
    treino, teste = ler_vocabulario("treino"), ler_vocabulario("teste")
    # Primeiro todos os exemplos de treino, depois os de teste (a ordem importa para o sorteio)
    exemplos_treino = []
    for numero in range(N_TREINO):
        exemplos_treino.append(gerar_exemplo(numero, treino, AMBIGUAS["treino"], EXTRAS["treino"], sorteio))
    exemplos_teste = []
    for numero in range(N_TESTE):
        exemplos_teste.append(gerar_exemplo(numero, teste, AMBIGUAS["teste"], EXTRAS["teste"], sorteio))
    gravar_jsonl(PASTA_AVALIACAO / "cabecalhos_treino.jsonl", exemplos_treino)
    gravar_jsonl(PASTA_AVALIACAO / "cabecalhos_teste.jsonl", exemplos_teste)

    # Histórico de mapeamentos "já homologados" (memória do RAG): um por termo de TREINO,
    # distribuídos entre 12 empresas fictícias do passado (HIST-01 a HIST-12)
    historico = []
    # Os campos acrescentados depois vão no fim: os mapeamentos antigos mantêm a empresa fictícia de antes
    for campo in ordem_do_sorteio(treino):
        for termo in treino[campo]:
            numero_da_empresa = len(historico) % 12 + 1
            historico.append({"coluna_origem": termo, "campo": campo,
                              "empresa_origem": f"HIST-{numero_da_empresa:02d}", "versao_layout": 1})
    with open(RAIZ / "data" / "synthetic" / "historico_mapeamentos.csv", "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(historico[0]), lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(historico)

    # Quantas colunas a prova tem no total
    colunas_na_prova = 0
    for exemplo in exemplos_teste:
        colunas_na_prova += len(exemplo["cabecalhos"])
    print(f"{len(exemplos_treino)} exemplos de treino | {len(exemplos_teste)} de teste ({colunas_na_prova} colunas) | "
          f"{len(historico)} mapeamentos no histórico")


if __name__ == "__main__":
    main()
