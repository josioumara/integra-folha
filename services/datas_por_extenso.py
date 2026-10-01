"""Datas escritas com palavras, em português e inglês (ADR-76, passo 4).

Para que serve: num documento Word em texto corrido (e às vezes numa planilha), a data pode vir toda escrita:
"quatorze de setembro de mil novecentos e noventa e um", "primeiro de maio de dois mil e vinte", "dia 3 de março de
dois mil e vinte e quatro", "September fourteenth, nineteen ninety-one". Este arquivo:
1. converte esse texto numa data (data_escrita), para o normalizador;
2. acha esses trechos dentro de um texto maior (trechos_de_data_escrita), para o detector de dados
   (services/detector_de_dados.py) reconhecer a data inteira como um dado só.

Como funciona: o nome do mês é a âncora. O que vem antes dele é o dia (em número ou em palavras) e o que vem depois
(depois de "de", "of" ou vírgula) é o ano (em número ou em palavras). Os números por extenso são somados palavra por
palavra ("mil novecentos e noventa e um" = 1000 + 900 + 90 + 1). Sem ano, não é uma data completa: fica de fora.
"""
import re
import unicodedata
from datetime import date

# Os nomes dos meses, completos e abreviados, em português e inglês (sem acento e em minúsculas)
MES_PELO_NOME_COMPLETO = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8,
    "set": 9, "sep": 9, "sept": 9, "out": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}
# As abreviações (e "may"): também são palavras comuns, então não servem de âncora para achar a data num texto
MESES_ABREVIADOS = {"jan", "fev", "feb", "mar", "abr", "apr", "mai", "may", "jun", "jul", "ago", "aug", "set", "sep",
                    "sept", "out", "oct", "nov", "dez", "dec"}
# O valor de cada palavra de número (português e inglês). "mil", "hundred" e "thousand" multiplicam (ver _somar)
VALOR_DA_PALAVRA = {
    # Português
    "zero": 0, "um": 1, "uma": 1, "primeiro": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14,
    "catorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16, "dezessete": 17, "dezassete": 17, "dezoito": 18,
    "dezenove": 19, "dezanove": 19, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
    "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100, "duzentos": 200, "trezentos": 300,
    "quatrocentos": 400, "quinhentos": 500, "seiscentos": 600, "setecentos": 700, "oitocentos": 800,
    "novecentos": 900,
    # Inglês (cardinais)
    "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    # Inglês (ordinais, usados no dia: "the fourteenth")
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
}
# As palavras que multiplicam o que veio antes
MULTIPLICADORES = {"mil": 1000, "thousand": 1000, "hundred": 100}
# Palavras de ligação que aparecem no meio dos números ("noventa e um", "two thousand and twenty")
LIGACOES_DOS_NUMEROS = {"e", "and"}
# O que pode vir antes do dia e entre as partes ("dia 14 de", "the 14th of", ", ")
PALAVRAS_DE_ENCAIXE = {"dia", "the", "de", "do", "of", "ano"}
# As palavras e números de um texto, com a posição de cada um (para achar o trecho da data no texto)
PADRAO_DAS_PALAVRAS = re.compile(r"\d+(?:º|°|o|st|nd|rd|th)?|[^\W\d_]+", re.IGNORECASE)
# Número de dia com ordinal colado: "1º", "14th", "3rd"
PADRAO_DIA_COM_ORDINAL = re.compile(r"(\d{1,2})(?:º|°|o|st|nd|rd|th)?", re.IGNORECASE)
# Quantas palavras, no máximo, o dia e o ano podem ter ("vinte e cinco" = 3; "mil novecentos e noventa e um" = 6)
MAXIMO_DE_PALAVRAS_DO_DIA = 4
MAXIMO_DE_PALAVRAS_DO_ANO = 8


def _sem_acento(palavra: str) -> str:
    """A palavra em minúsculas e sem acento ("Março" → "marco", "três" → "tres")."""
    return unicodedata.normalize("NFKD", palavra).encode("ascii", "ignore").decode().lower()


def _somar(palavras: list[str]) -> int | None:
    """O número escrito por extenso, somando palavra por palavra. None se alguma palavra não for de número.

    Ex.: ["mil", "novecentos", "e", "noventa", "e", "um"] → 1991; ["vinte", "e", "cinco"] → 25;
    ["two", "thousand", "and", "twenty"] → 2020.
    """
    total = 0
    atual = 0
    achou_numero = False
    for palavra in palavras:
        if palavra in LIGACOES_DOS_NUMEROS:
            continue
        if palavra in MULTIPLICADORES:
            # "mil" sozinho vale 1000; "dois mil" vale 2000
            if atual == 0:
                atual = 1
            atual = atual * MULTIPLICADORES[palavra]
            if MULTIPLICADORES[palavra] == 1000:
                total = total + atual
                atual = 0
            achou_numero = True
            continue
        if palavra not in VALOR_DA_PALAVRA:
            return None
        atual = atual + VALOR_DA_PALAVRA[palavra]
        achou_numero = True
    if not achou_numero:
        return None
    return total + atual


def _ano_ingles_em_dois_pedacos(palavras: list[str]) -> int | None:
    """O ano inglês dito em dois pedaços ("nineteen ninety one" = 19 e 91 → 1991; "twenty twenty four" → 2024)."""
    if not palavras:
        return None
    # Com "hundred" ou "thousand", o ano não é dito em dois pedaços
    for palavra in palavras:
        if palavra in MULTIPLICADORES:
            return None
    # O primeiro pedaço: uma palavra ("nineteen", "twenty") ou dezena + unidade ("twenty one" → 21)
    tamanho_do_primeiro = 1
    if len(palavras) > 2 and VALOR_DA_PALAVRA.get(palavras[0], 0) >= 20 and VALOR_DA_PALAVRA.get(palavras[1], 99) < 10:
        tamanho_do_primeiro = 2
    seculo = _somar(palavras[:tamanho_do_primeiro])
    resto = _somar(palavras[tamanho_do_primeiro:])
    if seculo is None or resto is None or not 10 <= seculo <= 29 or resto > 99:
        return None
    return seculo * 100 + resto


def _numero(palavras: list[str]) -> int | None:
    """Um número dito com palavras ou com algarismos (com ordinal colado: "14th", "1º")."""
    if len(palavras) == 1:
        com_ordinal = PADRAO_DIA_COM_ORDINAL.fullmatch(palavras[0])
        if com_ordinal:
            return int(com_ordinal.group(1))
        if palavras[0].isdigit():
            return int(palavras[0])
    return _somar(palavras)


def _ano(palavras: list[str]) -> int | None:
    """O ano: em algarismos (2 ou 4), por extenso em português, ou em inglês (em dois pedaços ou com "thousand")."""
    if len(palavras) == 1 and palavras[0].isdigit():
        if len(palavras[0]) == 4:
            return int(palavras[0])
        return None
    ano = _somar(palavras)
    if ano is not None and 1900 <= ano <= 2100:
        return ano
    return _ano_ingles_em_dois_pedacos(palavras)


def _limpar_encaixes(palavras: list[str]) -> list[str]:
    """Tira as palavras de encaixe das pontas ("dia", "the", "de", "of")."""
    while palavras and palavras[0] in PALAVRAS_DE_ENCAIXE:
        palavras = palavras[1:]
    while palavras and palavras[-1] in PALAVRAS_DE_ENCAIXE:
        palavras = palavras[:-1]
    return palavras


def _montar(ano: int | None, mes: int, dia: int | None) -> date | None:
    """A data, se as três partes existem e formam uma data de verdade (31 de fevereiro não)."""
    if ano is None or dia is None or not 1 <= dia <= 31:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _data_das_palavras(palavras: list[str]) -> date | None:
    """A data de uma lista de palavras já sem acento, com o nome do mês no meio.

    Dia antes do mês ("quatorze de setembro de 1991", "the 14th of September 1991") ou mês antes do dia
    ("September fourteenth, nineteen ninety one").
    """
    for posicao, palavra in enumerate(palavras):
        if palavra not in MES_PELO_NOME_COMPLETO:
            continue
        mes = MES_PELO_NOME_COMPLETO[palavra]
        antes = _limpar_encaixes(palavras[:posicao])
        depois = _limpar_encaixes(palavras[posicao + 1:])
        # Dia antes do mês: o resto depois do mês é o ano
        if antes:
            return _montar(_ano(depois), mes, _numero(antes))
        # Mês antes do dia (inglês): o dia é a primeira ou as duas primeiras palavras; o resto é o ano
        for tamanho_do_dia in (1, 2):
            dia = _numero(depois[:tamanho_do_dia])
            data = _montar(_ano(_limpar_encaixes(depois[tamanho_do_dia:])), mes, dia)
            if data is not None:
                return data
        return None
    return None


def _palavras_do_texto(texto: str) -> list[str]:
    """As palavras e números do texto, sem acento, com os hífens de número separados ("ninety-one" → "ninety one")."""
    palavras = []
    for encontrado in PADRAO_DAS_PALAVRAS.finditer(texto.replace("-", " ")):
        palavras.append(_sem_acento(encontrado.group()))
    return palavras


def data_escrita(texto: str) -> date | None:
    """Converte uma data escrita com palavras (o texto inteiro é a data). None se não for uma data completa.

    Ex.: "quatorze de setembro de mil novecentos e noventa e um" → 1991-09-14;
    "primeiro de maio de dois mil e vinte" → 2020-05-01; "September fourteenth, nineteen ninety-one" → 1991-09-14.
    """
    palavras = _palavras_do_texto(texto)
    if not palavras:
        return None
    data = _data_das_palavras(palavras)
    if data is not None:
        return data
    # Com algo em volta que não é data ("segunda-feira, quatorze de setembro de 2026, às 10h"): vale se houver
    # exatamente uma data escrita no texto
    trechos = trechos_de_data_escrita(texto)
    if len(trechos) != 1:
        return None
    inicio, fim = trechos[0]
    return _data_das_palavras(_palavras_do_texto(texto[inicio:fim]))


def trechos_de_data_escrita(texto: str) -> list[tuple[int, int]]:
    """Onde estão, dentro de um texto maior, as datas escritas com o mês por extenso: [(início, fim)].

    Usado pelo detector de dados, que marca a data inteira como um dado só. A âncora é o nome completo do mês;
    em volta dele, o maior pedaço que ainda forma uma data completa.
    Ex.: "Nasceu em quatorze de setembro de mil novecentos e noventa e um, em Recife." → o trecho de "quatorze" até "um".
    """
    encontradas = list(PADRAO_DAS_PALAVRAS.finditer(texto.replace("-", " ")))
    palavras = []
    for encontrada in encontradas:
        palavras.append(_sem_acento(encontrada.group()))
    trechos = []
    for posicao, palavra in enumerate(palavras):
        # Só o nome completo do mês é âncora aqui ("set", "mar", "out", "may" são palavras comuns no meio do texto)
        if palavra not in MES_PELO_NOME_COMPLETO or palavra in MESES_ABREVIADOS:
            continue
        melhor = None
        for inicio in range(max(0, posicao - MAXIMO_DE_PALAVRAS_DO_DIA - 1), posicao + 1):
            for fim in range(posicao + 1, min(len(palavras), posicao + MAXIMO_DE_PALAVRAS_DO_ANO + 2) + 1):
                # O trecho não começa nem termina numa palavra de ligação ("... noventa e um e entrou": o "e" do fim
                # é do resto da frase)
                if palavras[inicio] in LIGACOES_DOS_NUMEROS or palavras[fim - 1] in LIGACOES_DOS_NUMEROS:
                    continue
                if _data_das_palavras(palavras[inicio:fim]) is None:
                    continue
                # Fica o pedaço mais longo que ainda é uma data (o ano inteiro, "mil novecentos e noventa e um")
                if melhor is None or fim - inicio > melhor[1] - melhor[0]:
                    melhor = (inicio, fim)
        if melhor is not None:
            trechos.append((encontradas[melhor[0]].start(), encontradas[melhor[1] - 1].end()))
    return trechos
