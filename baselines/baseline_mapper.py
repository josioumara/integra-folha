"""Baseline B0: mapeia colunas SEM IA, só com um dicionário de sinônimos e comparação de textos (ADR-05).

"Baseline" é a régua: a solução mais simples possível. Se a IA não for claramente melhor que isto, ela
não se justifica. O dicionário usa só o vocabulário de TREINO (o de teste fica guardado para a prova).

Como o B0 decide o campo de uma coluna:
1. se o nome (sem acento, maiúsculas e pontuação) é igual a um sinônimo conhecido -> esse campo;
2. senão, procura o sinônimo mais parecido (biblioteca RapidFuzz); se a nota passar do limite -> esse
   campo (o comparador e o limite foram escolhidos por scripts/calibrar_b0.py, sem olhar a prova);
3. senão -> NAO_MAPEADO. O B0 não sabe reconhecer ambiguidade: é uma das coisas que a IA precisa
   fazer melhor.
"""
import csv
import json
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz, process

# Pasta raiz do projeto (integra-folha/)
RAIZ = Path(__file__).resolve().parent.parent
# Arquivo com o comparador e o limite escolhidos pela calibração
CAMINHO_CALIBRACAO = RAIZ / "data" / "avaliacao" / "calibracao_b0.json"
# Valores de fábrica, usados só se a calibração ainda não tiver rodado
PADRAO = {"comparador": "ratio", "limite": 85}
# Os jeitos de comparar textos que a calibração testa (todos dão nota de 0 a 100):
# ratio = o texto inteiro; token_sort_ratio = as mesmas palavras em outra ordem;
# token_set_ratio = palavras em comum; WRatio = combinação dos anteriores, olhando também pedaços do texto
COMPARADORES = {"ratio": fuzz.ratio, "token_sort_ratio": fuzz.token_sort_ratio,
                "token_set_ratio": fuzz.token_set_ratio, "WRatio": fuzz.WRatio}


def normalizar(texto: str) -> str:
    """Deixa o texto comparável: sem acento, minúsculo, pontuação vira espaço (ex.: "Dt. Admissão" -> "dt admissao")."""
    # Separa as letras dos acentos e descarta os acentos
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    # Troca todo caractere que não é letra nem número por espaço
    so_letras_e_numeros = ""
    for caractere in sem_acento.lower():
        if caractere.isalnum():
            so_letras_e_numeros += caractere
        else:
            so_letras_e_numeros += " "
    # Um espaço só entre as palavras
    return " ".join(so_letras_e_numeros.split())


def ler_termos(caminho: Path) -> list[tuple[str, str]]:
    """Lê um arquivo de vocabulário (colunas campo e termo) como uma lista de pares (termo, campo)."""
    pares = []
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            pares.append((linha["termo"], linha["campo"]))
    return pares


def configuracao_calibrada() -> dict:
    """O comparador e o limite escolhidos pela calibração; sem calibração, os valores de fábrica."""
    if CAMINHO_CALIBRACAO.exists():
        escolhida = json.loads(CAMINHO_CALIBRACAO.read_text(encoding="utf-8"))["escolhida"]
        return {"comparador": escolhida["comparador"], "limite": escolhida["limite"]}
    # Cópia dos valores de fábrica (para ninguém alterar o original sem querer)
    return dict(PADRAO)


class BaselineMapper:
    """O mapeador sem IA. Cada instância carrega o dicionário uma vez e mapeia quantas colunas quiser."""

    def __init__(self, termos: list[tuple[str, str]] | None = None, comparador: str | None = None,
                 limite: float | None = None):
        """termos: pares (termo, campo); sem informar, usa o vocabulário de treino.
        comparador e limite: sem informar, usa o que a calibração escolheu.
        """
        # Comparador e limite: o informado, ou o da calibração
        configuracao = configuracao_calibrada()
        self.comparador = comparador or configuracao["comparador"]
        self.limite = limite if limite is not None else configuracao["limite"]
        # Sem termos informados, usa o vocabulário de treino
        if termos is None:
            termos = ler_termos(RAIZ / "data" / "vocabulario" / "treino.csv")
        # O dicionário: termo normalizado -> campo
        self.sinonimos: dict[str, str] = {}
        for termo, campo in termos:
            self.sinonimos[normalizar(termo)] = campo
            # O próprio nome técnico do campo também vale como sinônimo
            self.sinonimos[normalizar(campo)] = campo
        # A lista de termos conhecidos, para a comparação aproximada
        self._termos_conhecidos = list(self.sinonimos)

    def mapear_coluna(self, coluna: str) -> dict:
        """O campo de UMA coluna, com a situação (PROPOSTO ou NAO_MAPEADO) e a nota de semelhança."""
        chave = normalizar(coluna)
        # 1. Nome igual a um sinônimo: certeza (nota 100)
        if chave in self.sinonimos:
            return {"coluna": coluna, "campo": self.sinonimos[chave], "status": "PROPOSTO", "nota": 100.0}
        # 2. O termo conhecido mais parecido, com o comparador escolhido
        mais_parecido = process.extractOne(chave, self._termos_conhecidos, scorer=COMPARADORES[self.comparador])
        # mais_parecido é (termo, nota, posição), ou None se não houver termos
        if mais_parecido and mais_parecido[1] >= self.limite:
            termo, nota = mais_parecido[0], mais_parecido[1]
            return {"coluna": coluna, "campo": self.sinonimos[termo], "status": "PROPOSTO", "nota": round(nota, 1)}
        # 3. Nada parecido o bastante: não mapeia
        nota = round(mais_parecido[1], 1) if mais_parecido else 0.0
        return {"coluna": coluna, "campo": None, "status": "NAO_MAPEADO", "nota": nota}

    def mapear(self, colunas: list[str]) -> list[dict]:
        """O campo de cada coluna, na mesma ordem."""
        resultados = []
        for coluna in colunas:
            resultados.append(self.mapear_coluna(coluna))
        return resultados
