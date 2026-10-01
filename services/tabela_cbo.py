"""A tabela oficial de profissões (CBO): conferir um código e achar a profissão pelo nome do cargo (ADR-129).

O que é a CBO: a Classificação Brasileira de Ocupações, a lista oficial de profissões do Ministério do Trabalho e
Emprego. Cada profissão tem um código de 6 dígitos (411010 = "Assistente administrativo", escrito "4110-10"), e os 4
primeiros dígitos são a "família" (4110). A tabela também traz os sinônimos: outros nomes da mesma profissão (ex.:
"Auxiliar de escritório" é um nome do 411005). Os arquivos ficam em data/cbo/ (scripts/calcular_faixas_cbo.py baixa).

O que este arquivo faz (sem IA e sem banco de dados; só lê os arquivos da CBO):
1. Confere o código que a empresa mandou: tira pontos, traços e espaços ("4110-10", "4110.10" e "411010" são o mesmo
   código) e diz se ele existe na tabela.
2. Acha a profissão pelo nome do cargo, com regras gerais que valem para qualquer nome:
   - maiúsculas, acentos, pontuação e a ordem das palavras não importam;
   - palavras de ligação ("de", "da", "e"...) e o nível na carreira ("júnior", "pleno", "sênior", "I", "II"...) não
     mudam a profissão;
   - o plural vira singular ("motoristas" → "motorista"), o feminino vira masculino, como a CBO escreve
     ("enfermeira" → "enfermeiro"), e as abreviações comuns viram a palavra inteira ("aux." → "auxiliar");
   - a profissão que a CBO marca como "em geral" ("Recepcionista, em geral") também atende pelo nome sem o "em geral";
   - o nome é comparado com os títulos E os sinônimos. Se só uma profissão combina, ela é a sugestão; se mais de uma
     combina igualmente bem, o cargo é "ambíguo" e não há sugestão; se nenhuma combina o bastante, "nenhuma".
   A sugestão nunca vale sozinha: a empresa confirma (nada do que o banco recebe é assumido).
3. Busca para a tela do banco: por código (o começo dele) ou por palavras do título.
"""
import csv
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Pasta raiz do projeto e a pasta dos arquivos da CBO
RAIZ = Path(__file__).resolve().parent.parent
PASTA_DA_CBO = RAIZ / "data" / "cbo"

# Palavras que ligam as outras e não dizem qual é a profissão
PALAVRAS_DE_LIGACAO = frozenset({"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "na", "no", "nas",
                                 "nos", "para", "com", "por"})
# O nível na carreira: "Analista júnior" e "Analista sênior" são a mesma profissão
PALAVRAS_DE_NIVEL = frozenset({"junior", "jr", "pleno", "pl", "senior", "sr", "trainee", "i", "ii", "iii", "iv", "v"})
# Abreviações comuns nos nomes de cargo e a palavra inteira de cada uma (depois de tirar acentos e pontos)
ABREVIACOES = {
    "aux": "auxiliar", "assist": "assistente", "asst": "assistente", "adm": "administrativo",
    "admin": "administrativo", "tec": "tecnico", "ger": "gerente", "sup": "supervisor", "superv": "supervisor",
    "coord": "coordenador", "op": "operador", "oper": "operador", "eng": "engenheiro", "prof": "professor",
    "esp": "especialista", "vend": "vendedor", "atend": "atendente", "dir": "diretor", "contab": "contabil",
    "mot": "motorista", "recep": "recepcionista", "enf": "enfermeiro", "manut": "manutencao",
}
# Quanto um nome precisa combinar com um título, quando não é igual: a parte das palavras em comum (0 a 1).
# 0,75 = pelo menos 3 de cada 4 palavras em comum (ex.: "operador empilhadeira eletrica" com "operador empilhadeira")
COMBINACAO_MINIMA = 0.75
# Quantas opções a mensagem do cargo ambíguo cita
OPCOES_NA_MENSAGEM = 3
# As três respostas possíveis da sugestão
SUGESTAO_UNICA, SUGESTAO_AMBIGUA, SUGESTAO_NENHUMA = "UNICA", "AMBIGUA", "NENHUMA"


@dataclass
class Sugestao:
    """A profissão que o nome do cargo sugere: uma (UNICA), várias empatadas (AMBIGUA) ou nenhuma (NENHUMA)."""

    situacao: str                     # UNICA, AMBIGUA ou NENHUMA
    codigo: str | None = None         # o código sugerido (só na UNICA)
    titulo: str | None = None         # o título oficial do código sugerido (só na UNICA)
    opcoes: list[tuple[str, str]] = field(default_factory=list)   # (código, título) das empatadas (só na AMBIGUA)


# ---------------- Os arquivos da CBO ----------------

def _ler_codigos_e_titulos(nome_do_arquivo: str) -> list[tuple[str, str]]:
    """As linhas (código, título) de um arquivo da CBO em data/cbo/; arquivo que não existe → lista vazia."""
    caminho = PASTA_DA_CBO / nome_do_arquivo
    if not caminho.exists():
        return []
    linhas = []
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            linhas.append((linha["codigo"], linha["titulo"]))
    return linhas


@lru_cache(maxsize=1)
def ocupacoes() -> dict[str, str]:
    """{código de 6 dígitos: título oficial} de todas as profissões (lido uma vez e guardado na memória)."""
    titulo_por_codigo = {}
    for codigo, titulo in _ler_codigos_e_titulos("cbo2002_ocupacoes.csv"):
        titulo_por_codigo[codigo] = titulo
    return titulo_por_codigo


@lru_cache(maxsize=1)
def familias() -> dict[str, str]:
    """{código de 4 dígitos: título da família}."""
    titulo_por_codigo = {}
    for codigo, titulo in _ler_codigos_e_titulos("cbo2002_familias.csv"):
        titulo_por_codigo[codigo] = titulo
    return titulo_por_codigo


@lru_cache(maxsize=1)
def sinonimos() -> list[tuple[str, str]]:
    """As linhas (código, outro nome da profissão). Um código pode ter vários sinônimos."""
    return _ler_codigos_e_titulos("cbo2002_sinonimos.csv")


# ---------------- 1. O código ----------------

def codigo_normalizado(texto) -> str | None:
    """O código CBO só com os 6 dígitos, ou None se o texto não tem cara de código.

    Ex.: "4110-10" → "411010"; " 4110.10 " → "411010"; "10105" → "010105" (a planilha tirou o zero da frente);
    411010.0 (número lido do Excel) → "411010"; "abc" → None; "4110" → None (é uma família, não uma profissão).
    """
    if texto is None:
        return None
    texto = str(texto).strip()
    # Número lido de planilha com casas decimais zeradas ("411010.0"): fica só a parte inteira
    if re.fullmatch(r"\d+[.,]0+", texto):
        texto = re.split(r"[.,]", texto)[0]
    # Fica só com os dígitos (tira traço, ponto, espaço e barra)
    digitos = re.sub(r"\D", "", texto)
    # Escrito com separador, tem de ser no desenho da CBO: 4 dígitos, o separador e 2 dígitos ("4110-1" não é código)
    if digitos != texto and not re.fullmatch(r"\d{4}[-./ ]\d{2}", texto):
        return None
    # Só dígitos e 5 deles: a planilha tirou o zero da frente (os códigos de 0101 a 0999 começam com zero)
    if len(digitos) == 5:
        digitos = "0" + digitos
    if len(digitos) != 6:
        return None
    return digitos


def codigo_formatado(codigo: str) -> str:
    """O código como a CBO escreve: "411010" → "4110-10"."""
    return f"{codigo[:4]}-{codigo[4:]}"


def existe(codigo: str | None) -> bool:
    """True se o código (6 dígitos) é uma profissão da tabela oficial."""
    return codigo is not None and codigo in ocupacoes()


def titulo(codigo: str) -> str | None:
    """O título oficial da profissão, ou None se o código não existe."""
    return ocupacoes().get(codigo)


# ---------------- 2. O nome do cargo ----------------

def texto_normalizado(texto: str) -> str:
    """O texto em minúsculas, sem acentos, sem pontuação e com um espaço só entre as palavras.

    Ex.: "  Aux. Administrativo  I " → "aux administrativo i". É também a "chave" do cargo na tabela cbo_dos_cargos.
    """
    # Separa cada letra do acento ("é" vira "e" + acento) e joga os acentos fora
    decomposto = unicodedata.normalize("NFKD", str(texto))
    sem_acento = ""
    for letra in decomposto:
        if not unicodedata.combining(letra):
            sem_acento += letra
    # Pontuação vira espaço (o "." de "Aux." e o "/" de "Aux./Assist.")
    so_letras_e_numeros = re.sub(r"[^a-z0-9]+", " ", sem_acento.lower())
    return " ".join(so_letras_e_numeros.split())


def _singular(palavra: str) -> str:
    """O singular da palavra (sem acento). Ex.: "motoristas" → "motorista"; "vendedores" → "vendedor";
    "operacoes" → "operacao"; "gerais" → "geral"."""
    if len(palavra) <= 3:
        return palavra
    if palavra.endswith("oes") or palavra.endswith("aes"):
        return palavra[:-3] + "ao"
    if palavra.endswith("ais"):
        return palavra[:-3] + "al"
    if palavra.endswith("eis"):
        return palavra[:-3] + "el"
    if palavra.endswith("res") or palavra.endswith("zes"):
        return palavra[:-2]
    if palavra.endswith("s"):
        return palavra[:-1]
    return palavra


def _forma_unica(palavra: str) -> str:
    """Uma forma só para o singular e o plural, o masculino e o feminino (a CBO escreve os títulos no masculino).

    Não precisa ser português perfeito: o nome do cargo e os títulos da CBO passam pela mesma regra, e o que importa é
    que os dois cheguem à mesma forma.
    Ex.: "faxineiras" → "faxineira" → "faxineiro"; "vendedora" → "vendedor"; "tecnica" → "tecnico";
    "motorista" → "motoristo" (nos dois lados, então combina do mesmo jeito).
    """
    palavra = _singular(palavra)
    if len(palavra) <= 3:
        return palavra
    # Feminino terminado em "ora" ("vendedora", "professora", "diretora"): o masculino é sem o "a"
    if palavra.endswith("ora"):
        return palavra[:-1]
    # Outro feminino terminado em "a" ("enfermeira", "tecnica", "secretaria"): o masculino troca o "a" por "o"
    if palavra.endswith("a"):
        return palavra[:-1] + "o"
    return palavra


def palavras_que_contam(texto: str) -> frozenset[str]:
    """As palavras que dizem qual é a profissão, na forma única (sem ligação, sem nível, sem plural, sem abreviação).

    Ex.: "Aux. Administrativos II" → {"auxiliar", "administrativo"}; "Motorista de Caminhão" → {"motorista", "caminhao"}.
    """
    palavras = set()
    for palavra in texto_normalizado(texto).split():
        # A abreviação vira a palavra inteira
        palavra = ABREVIACOES.get(palavra, palavra)
        # Ligação e nível na carreira não contam
        if palavra in PALAVRAS_DE_LIGACAO or palavra in PALAVRAS_DE_NIVEL:
            continue
        palavras.add(_forma_unica(palavra))
    return frozenset(palavras)


@dataclass
class _Indice:
    """Os títulos e sinônimos já preparados para a comparação (montado uma vez)."""

    codigos_por_palavras: dict[frozenset, set[str]]       # palavras exatas → códigos com esse nome
    nomes_por_palavra: dict[str, list[tuple[frozenset, str]]]   # uma palavra → (palavras do nome, código) que a têm


@lru_cache(maxsize=1)
def _indice() -> _Indice:
    """Prepara os títulos e os sinônimos para a comparação com o nome do cargo."""
    codigos_por_palavras = {}
    nomes_por_palavra = {}
    # Os títulos oficiais e os sinônimos entram do mesmo jeito
    todos_os_nomes = list(ocupacoes().items()) + sinonimos()
    for codigo, nome in todos_os_nomes:
        # O nome como está e, quando a CBO marca a profissão genérica com "em geral" ("Recepcionista, em geral"),
        # também sem o "em geral": quem escreve só "Recepcionista" fala dessa profissão genérica
        variantes = [nome]
        if "em geral" in texto_normalizado(nome):
            variantes.append(texto_normalizado(nome).replace("em geral", ""))
        for variante in variantes:
            palavras = palavras_que_contam(variante)
            if not palavras:
                continue
            codigos_por_palavras.setdefault(palavras, set()).add(codigo)
            for palavra in palavras:
                nomes_por_palavra.setdefault(palavra, []).append((palavras, codigo))
    return _Indice(codigos_por_palavras, nomes_por_palavra)


def _opcoes(codigos) -> list[tuple[str, str]]:
    """(código, título) de cada código, em ordem de código."""
    lista = []
    for codigo in sorted(codigos):
        lista.append((codigo, titulo(codigo)))
    return lista


def sugerir(cargo: str) -> Sugestao:
    """A profissão que o nome do cargo sugere, pela tabela oficial (títulos e sinônimos).

    Recebe: o cargo como a empresa escreveu. Devolve: a Sugestao (UNICA, AMBIGUA ou NENHUMA).
    Ex.: "Motoristas de caminhão" → UNICA 782510; "Analista" → NENHUMA (há dezenas de "Analista de ...").
    """
    palavras_do_cargo = palavras_que_contam(cargo or "")
    if not palavras_do_cargo:
        return Sugestao(SUGESTAO_NENHUMA)
    indice = _indice()
    # 1. Um título ou sinônimo com exatamente as mesmas palavras
    codigos_iguais = indice.codigos_por_palavras.get(palavras_do_cargo, set())
    if len(codigos_iguais) == 1:
        codigo = next(iter(codigos_iguais))
        return Sugestao(SUGESTAO_UNICA, codigo, titulo(codigo))
    if len(codigos_iguais) > 1:
        return Sugestao(SUGESTAO_AMBIGUA, opcoes=_opcoes(codigos_iguais))
    # 2. O nome mais parecido: a parte das palavras em comum (palavras em comum ÷ palavras dos dois juntos)
    melhor_combinacao = 0.0
    codigos_do_melhor = set()
    for palavra in palavras_do_cargo:
        for palavras_do_nome, codigo in indice.nomes_por_palavra.get(palavra, []):
            combinacao = len(palavras_do_cargo & palavras_do_nome) / len(palavras_do_cargo | palavras_do_nome)
            if combinacao > melhor_combinacao:
                # Um nome melhor: recomeça a lista dos melhores
                melhor_combinacao, codigos_do_melhor = combinacao, {codigo}
            elif combinacao == melhor_combinacao:
                # Empate com o melhor até agora
                codigos_do_melhor.add(codigo)
    if melhor_combinacao < COMBINACAO_MINIMA:
        return Sugestao(SUGESTAO_NENHUMA)
    if len(codigos_do_melhor) == 1:
        codigo = next(iter(codigos_do_melhor))
        return Sugestao(SUGESTAO_UNICA, codigo, titulo(codigo))
    return Sugestao(SUGESTAO_AMBIGUA, opcoes=_opcoes(codigos_do_melhor))


# ---------------- 3. A busca da tela do banco ----------------

def buscar(texto: str) -> list[dict]:
    """TODAS as profissões que batem com a busca, em ordem de código (a tela mostra de 50 em 50).

    Recebe: o texto digitado. Só dígitos (e traço, ponto, espaço) → o começo do código ("4110" acha 411005, 411010...);
    com letras → cada palavra digitada tem de ser o começo de uma palavra do título ou de um sinônimo ("motor cam"
    acha "Motorista de caminhão"). Vazio → todas as profissões da tabela.
    Devolve: [{"codigo", "titulo", "sinonimo"}]; "sinonimo" é o nome que bateu, quando não foi o título.
    """
    texto = (texto or "").strip()
    encontrados = {}
    # Busca por código: só dígitos e separadores
    if texto and re.fullmatch(r"[\d\s.\-]+", texto):
        comeco = re.sub(r"\D", "", texto)
        for codigo, titulo_oficial in ocupacoes().items():
            if codigo.startswith(comeco):
                encontrados[codigo] = {"codigo": codigo, "titulo": titulo_oficial, "sinonimo": None}
    else:
        palavras_digitadas = texto_normalizado(texto).split()
        # Os títulos primeiro (um título que bate não é trocado por um sinônimo do mesmo código)
        for codigo, titulo_oficial in ocupacoes().items():
            if _todas_comecam_palavras(palavras_digitadas, titulo_oficial):
                encontrados[codigo] = {"codigo": codigo, "titulo": titulo_oficial, "sinonimo": None}
        for codigo, sinonimo in sinonimos():
            if codigo not in encontrados and _todas_comecam_palavras(palavras_digitadas, sinonimo):
                encontrados[codigo] = {"codigo": codigo, "titulo": titulo(codigo), "sinonimo": sinonimo}
    resultado = []
    for codigo in sorted(encontrados):
        resultado.append(encontrados[codigo])
    return resultado


def _todas_comecam_palavras(palavras_digitadas: list[str], nome: str) -> bool:
    """True se cada palavra digitada é o começo de alguma palavra do nome ("motor" começa "motorista")."""
    palavras_do_nome = texto_normalizado(nome).split()
    for digitada in palavras_digitadas:
        achou = False
        for palavra in palavras_do_nome:
            if palavra.startswith(digitada):
                achou = True
                break
        if not achou:
            return False
    return True
