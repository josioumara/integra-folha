"""Normalizador: converte o arquivo para o layout do banco, sem LLM (ADR-12).

O TIPO de cada campo de destino decide a conversão, sempre de um catálogo fechado (a allowlist).
Regra de ouro: **nada é corrigido por suposição**. Quando não dá para converter com certeza, o valor
fica vazio no registro e vai para `nao_convertidos` (ou para `pendencias_de_coluna`, quando a dúvida é
da coluna inteira), e a empresa decide na correção. As decisões dela voltam aqui em `decisoes`.

Exemplos:
- "R$ 5.200,50" e "5200.5" → 5200.50 (Decimal, nunca float);
- "01/09/2026" → 2026-09-01 quando alguma data do ARQUIVO tem dia > 12 (um sistema de RH exporta todas
  as datas do mesmo jeito); se nenhuma data do arquivo desempata, a coluna fica pendente;
- CPF que o Excel guardou como número e perdeu o zero → recomposto só se o dígito verificador confirmar.
"""
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from models.contratos import CampoLayout, EstadoProcessamento, MappingPlan, StatusMapeamento, TipoCampo
from services import auditoria, datas_por_extenso, parametros, processamentos
from services.documentos import cnpj_valido, cpf_valido
from services.ingestao import Leitura
# O que a IA achou num campo opcional sem ter certeza do campo fica guardado sem rótulo (ADR-143, Parte 1)
from services import informacoes_sem_rotulo

# Pasta raiz do projeto (para achar data/contratos/dominios_v1.json)
RAIZ = Path(__file__).resolve().parent.parent
# Dinheiro sempre com duas casas
CENTAVOS = Decimal("0.01")

# Allowlist: as únicas operações que o Normalizador sabe fazer, por tipo de campo
OPERACOES_POR_TIPO = {
    TipoCampo.TEXTO: ["tirar_espacos"],
    TipoCampo.MATRICULA: ["tirar_espacos", "completar_zeros_com_aprovacao"],
    TipoCampo.CPF: ["somente_digitos", "recompor_zeros_se_dv_confere"],
    TipoCampo.CNPJ: ["somente_digitos", "recompor_zeros_se_dv_confere"],
    TipoCampo.CEP: ["somente_digitos"],
    TipoCampo.UF: ["maiusculas", "nome_do_estado_para_sigla"],
    TipoCampo.TELEFONE: ["somente_digitos"],
    TipoCampo.EMAIL: ["tirar_espacos", "minusculas"],
    TipoCampo.DECIMAL_MONETARIO: ["converter_decimal"],
    TipoCampo.DATA: ["converter_data"],
    TipoCampo.DOMINIO: ["sinonimo_do_dominio"],
}
# Todas as operações permitidas, juntas (qualquer outra é recusada)
ALLOWLIST = set()
for operacoes_do_tipo in OPERACOES_POR_TIPO.values():
    ALLOWLIST.update(operacoes_do_tipo)

# Nome do estado (sem acento, minúsculo) -> sigla
ESTADOS = {"acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
           "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
           "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
           "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
           "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
           "sergipe": "SE", "tocantins": "TO"}

# Números bem formados: com milhar e decimal no padrão brasileiro (1.234,56) ou no americano (1,234.56)
NUMERO_COM_VIRGULA_DECIMAL = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d{1,2})?")
NUMERO_COM_PONTO_DECIMAL = re.compile(r"-?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?")
# Termina com centavos depois da vírgula ("3.150,00") ou do ponto ("3150.00")
CENTAVOS_NA_VIRGULA = re.compile(r",\d{1,2}$")
CENTAVOS_NO_PONTO = re.compile(r"\.\d{1,2}$")
# Só dígitos, pontos e vírgulas (com pelo menos um dígito), com sinal de menos opcional
PARECE_NUMERO = re.compile(r"-?[\d.,]*\d[\d.,]*")
# Data com barras, pontos ou hífens: 01/09/2026, 1.9.2026, 01-09-2026 (as duas primeiras partes em grupos)
DATA_COM_BARRAS = re.compile(r"(\d{1,2})(?:\s*[/.-]\s*|\s+)(\d{1,2})(?:\s*[/.-]\s*|\s+)(\d{4})")
# A mesma data com o ano em dois dígitos: 06/05/24 (ADR-72; o século é decidido em _ano_com_quatro_digitos)
DATA_COM_ANO_CURTO = re.compile(r"(\d{1,2})(?:\s*[/.-]\s*|\s+)(\d{1,2})(?:\s*[/.-]\s*|\s+)(\d{2})")
# Dia + mês escrito + ano, em português ou inglês (ADR-72, com o inglês e mais separadores):
# "14 de setembro de 1991", "03 jun 2024", "8 de jul. de 2024", "1º de maio de 2020", "14-Sep-2024", "14/set/24"
DATA_DIA_E_MES_ESCRITO = re.compile(
    r"(\d{1,2})(?:º|°|o|st|nd|rd|th)?\s*(?:de\s+|[-/.\s])\s*([a-zç]+)\.?\s*(?:de\s+|[-/.,\s])\s*(\d{4}|\d{2})")
# Mês escrito + dia + ano (o jeito americano): "Sep 14, 1991", "September 14 1991", "May 3rd, 2020"
DATA_MES_ESCRITO_PRIMEIRO = re.compile(r"([a-zç]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")
# O número de cada mês pelas 3 primeiras letras do nome, sem acento, em português e em inglês
# ("mar" de março ou March, "set" de setembro, "sep" de September). Os nomes não se confundem entre as línguas
MES_PELO_NOME = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9,
                 "out": 10, "nov": 11, "dez": 12,
                 "feb": 2, "apr": 4, "may": 5, "aug": 8, "sep": 9, "oct": 10, "dec": 12}
# Ano primeiro, com traço, barra ou ponto: 2026-09-01 (o padrão internacional), 2026/09/01, 2026.9.1.
# Sempre ano, mês e dia (ninguém escreve ano, dia e mês)
DATA_ANO_PRIMEIRO = re.compile(r"(\d{4})(?:\s*[/.-]\s*|\s+)(\d{1,2})(?:\s*[/.-]\s*|\s+)(\d{1,2})")
# Data compacta, sem separador: 20260901 (ano primeiro) ou 01092026 (dia e mês primeiro)
DATA_COMPACTA = re.compile(r"\d{8}")
# A hora que às vezes vem depois da data: sai antes de converter. Ex.: "01/09/2026 08:30", "01/09/2026 às 10h",
# "2026-09-01T08:30:00Z", "2026-09-01T08:30:00-03:00", "9/1/2026 8:30 PM", "14 de setembro de 2026, 14h30"
HORA_DEPOIS_DA_DATA = re.compile(
    r"(.*\d)(?:,?\s+(?:(?:às|as|at)\s+)?|T)"
    r"(?:\d{1,2}[:h]\d{2}(?::\d{2})?(?:\.\d+)?(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*(?:h|hs|horas)|\d{1,2}\s*[ap]\.?m\.?)"
    r"(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?",
    re.IGNORECASE)
# O que às vezes vem antes da data e não é data: dia da semana, "dia", "em" ("segunda-feira, 14/09/2026",
# "Mon, Sep 14 2026", "dia 14/09/2026")
PREFIXO_DA_DATA = re.compile(
    r"(?:(?:segunda|terça|terca|quarta|quinta|sexta)(?:-feira)?|sábado|sabado|domingo|seg|ter|qua|qui|sex|sáb|sab|dom"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun"
    r"|dia|em|on)\.?,?\s+",
    re.IGNORECASE)
# Só mês e ano, sem o dia ("09/2026", "set/2026", "setembro de 2026"): não é uma data completa
MES_E_ANO_SEM_DIA = re.compile(r"(?:\d{1,2}|[a-zç]+\.?)\s*(?:de\s+|[/.\-\s])\s*\d{4}", re.IGNORECASE)
# Data como número de série do Excel (dias desde 30/12/1899): 46266 (ou 46266.5, com a hora na fração)
DATA_DO_EXCEL = re.compile(r"\d{5}(?:[.,]\d+)?")
INICIO_DAS_DATAS_DO_EXCEL = date(1899, 12, 30)


class NaoConvertido(ValueError):
    """O valor não pode ser convertido com certeza. A mensagem vira o motivo da pendência."""


@dataclass
class Normalizacao:
    """O resultado da padronização de um arquivo."""

    registros: list[dict]                       # um por funcionário: campo -> valor canônico (texto)
    plano: list[dict]                           # TransformationPlan: coluna, campo, tipo, operações
    log: list[dict]                             # TransformationLog: o que mudou em cada coluna
    nao_convertidos: list[dict] = field(default_factory=list)       # valores que ficaram para a empresa decidir
    pendencias_de_coluna: list[dict] = field(default_factory=list)  # dúvidas da coluna inteira (formato de data, zeros)
    conferencia: dict = field(default_factory=dict)                 # nada some e nada aparece (ver _conferir)


def _chave_de_comparacao(texto: str) -> str:
    """Sem acento, minúsculas, pontuação vira espaço: "Pró-labore" e "pro labore" ficam iguais."""
    # Separa as letras dos acentos e joga os acentos fora
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    # Tudo o que não é letra ou número vira espaço; espaços repetidos viram um só
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento).split())


# ---------------- Conversões (funções puras) ----------------

def convencao_decimal(valores: list[str]) -> str | None:
    """Separador decimal da coluna: "virgula", "ponto" ou None (só inteiros, ou nada decide)."""
    com_virgula = 0
    com_ponto = 0
    for valor in valores:
        numero = valor.replace("R$", "").replace(" ", "")
        if CENTAVOS_NA_VIRGULA.search(numero):
            com_virgula += 1
        elif CENTAVOS_NO_PONTO.search(numero) and "," not in numero:
            com_ponto += 1
    # Coluna misturada: cada valor decide sozinho, e o incerto vira pendência
    if com_virgula and com_ponto:
        return None
    if com_virgula:
        return "virgula"
    if com_ponto:
        return "ponto"
    return None


def converter_decimal(valor: str, convencao: str | None) -> Decimal:
    """Converte dinheiro escrito de qualquer jeito para Decimal com duas casas."""
    numero = valor.replace("R$", "").replace(" ", "").strip()
    if not PARECE_NUMERO.fullmatch(numero):
        raise NaoConvertido("valor não numérico")
    # A vírgula é o decimal (pela coluna ou, sem convenção, pelo próprio valor): "1.234,56"
    if convencao == "virgula" or (convencao is None and CENTAVOS_NA_VIRGULA.search(numero)):
        if not NUMERO_COM_VIRGULA_DECIMAL.fullmatch(numero):
            raise NaoConvertido("número mal formado")
        # Tira o ponto de milhar e troca a vírgula por ponto
        numero = numero.replace(".", "").replace(",", ".")
    # O ponto é o decimal: "1,234.56"
    elif convencao == "ponto" or (convencao is None and CENTAVOS_NO_PONTO.search(numero) and "," not in numero):
        if not NUMERO_COM_PONTO_DECIMAL.fullmatch(numero):
            raise NaoConvertido("número mal formado")
        # Tira a vírgula de milhar
        numero = numero.replace(",", "")
    # Tem vírgula, mas nada diz se ela é decimal ou milhar
    elif "," in numero:
        raise NaoConvertido("separador decimal incerto")
    # 1.234 ou 1.234.567: o ponto é de milhar
    elif numero.count(".") > 1 or re.search(r"\.\d{3}$", numero):
        if not NUMERO_COM_VIRGULA_DECIMAL.fullmatch(numero):
            raise NaoConvertido("número mal formado")
        numero = numero.replace(".", "")
    try:
        resultado = Decimal(numero)
    except InvalidOperation as erro:
        raise NaoConvertido("valor não numérico") from erro
    # Mais de duas casas não é dinheiro: não arredondamos por suposição
    if resultado != resultado.quantize(CENTAVOS):
        raise NaoConvertido("mais de duas casas decimais")
    return resultado.quantize(CENTAVOS)


def _sem_a_hora(texto: str) -> str:
    """A data sem o que não é data: a hora depois e o dia da semana antes.

    Ex.: "01/09/2026 08:30" → "01/09/2026"; "segunda-feira, 14/09/2026" → "14/09/2026"; "dia 3/5/2026" → "3/5/2026".
    """
    # O prefixo pode se repetir ("segunda-feira, dia 14/09/2026")
    sem_prefixo = PREFIXO_DA_DATA.match(texto)
    while sem_prefixo:
        texto = texto[sem_prefixo.end():]
        sem_prefixo = PREFIXO_DA_DATA.match(texto)
    com_hora = HORA_DEPOIS_DA_DATA.fullmatch(texto)
    if com_hora:
        return com_hora.group(1)
    return texto


def _ano_primeiro_compacto(texto: str) -> bool:
    """True se a data compacta começa pelo ano ("20260901"): 4 primeiros dígitos entre 1900 e 2100 e mês válido."""
    return 1900 <= int(texto[:4]) <= 2100 and 1 <= int(texto[4:6]) <= 12


def _partes_que_podem_trocar(valor: str) -> tuple[int, int] | None:
    """As duas primeiras partes de uma data que pode ser dia/mês ou mês/dia, ou None se a data não tem essa dúvida.

    Têm a dúvida: "01/09/2026", "01.09.2026", "06/05/24", "01092026". Não têm: ano primeiro ("2026-09-01"), mês
    escrito ("14 de setembro de 1991") e o número de série do Excel.
    """
    texto = _sem_a_hora(valor.strip())
    for molde in (DATA_COM_BARRAS, DATA_COM_ANO_CURTO):
        partes = molde.fullmatch(texto)
        if partes:
            return int(partes.group(1)), int(partes.group(2))
    if DATA_COMPACTA.fullmatch(texto) and not _ano_primeiro_compacto(texto):
        return int(texto[:2]), int(texto[2:4])
    return None


def ordem_das_datas(valores: list[str]) -> str | None:
    """"DMY" (dia primeiro) ou "MDY" (mês primeiro) quando alguma data decide (parte > 12); None quando
    nenhuma decide ou quando as datas se contradizem."""
    tem_dia_primeiro = False
    tem_mes_primeiro = False
    for valor in valores:
        partes = _partes_que_podem_trocar(valor)
        if partes:
            # Só o dia passa de 12: se a primeira parte passa, ela é o dia
            if partes[0] > 12:
                tem_dia_primeiro = True
            if partes[1] > 12:
                tem_mes_primeiro = True
    if tem_dia_primeiro and not tem_mes_primeiro:
        return "DMY"
    if tem_mes_primeiro and not tem_dia_primeiro:
        return "MDY"
    return None


def _montar_data(ano: int, mes: int, dia: int) -> date:
    """A data, ou NaoConvertido se ela não existe (ex.: 31/02)."""
    try:
        return date(ano, mes, dia)
    except ValueError as erro:
        raise NaoConvertido("data inexistente") from erro


def _ano_com_quatro_digitos(ano_curto: int) -> int:
    """"24" vira 2024 e "79" vira 1979: até o ano atual é deste século; acima, do século passado.

    Ex.: em 2026, 24 → 2024, 26 → 2026, 27 → 1927, 79 → 1979.
    """
    ano_atual_curto = date.today().year % 100
    if ano_curto <= ano_atual_curto:
        return 2000 + ano_curto
    return 1900 + ano_curto


def _numero_do_mes(nome: str) -> int | None:
    """O número do mês pelo nome, em português ou inglês ("março" → 3, "Sept" → 9); None se não for mês."""
    # O mês pelas 3 primeiras letras, sem acento ("março" → "mar")
    return MES_PELO_NOME.get(nome.lower()[:3].replace("ç", "c"))


def _ano_da_data(ano_escrito: str) -> int:
    """O ano com 4 dígitos ("24" → 2024; "1991" fica 1991)."""
    if len(ano_escrito) == 2:
        return _ano_com_quatro_digitos(int(ano_escrito))
    return int(ano_escrito)


def _data_com_mes_escrito(texto: str) -> date | None:
    """Data com o mês escrito, em português ou inglês; qualquer outro texto devolve None.

    O mês escrito não deixa dúvida de ordem. Ex.: "14 de setembro de 1991", "03 jun 2024", "14-Sep-2024",
    "1º de maio de 2020", "Sep 14, 1991" (mês primeiro, o jeito americano).
    """
    minusculas = texto.lower()
    dia_primeiro = DATA_DIA_E_MES_ESCRITO.fullmatch(minusculas)
    if dia_primeiro:
        mes = _numero_do_mes(dia_primeiro.group(2))
        if mes is None:
            return None
        return _montar_data(_ano_da_data(dia_primeiro.group(3)), mes, int(dia_primeiro.group(1)))
    mes_primeiro = DATA_MES_ESCRITO_PRIMEIRO.fullmatch(minusculas)
    if mes_primeiro:
        mes = _numero_do_mes(mes_primeiro.group(1))
        if mes is None:
            return None
        return _montar_data(int(mes_primeiro.group(3)), mes, int(mes_primeiro.group(2)))
    return None


def converter_data(valor: str, ordem: str | None) -> date:
    """Converte uma data. ordem: "DMY", "MDY" ou None (só converte se o próprio valor desempatar).

    Formatos aceitos (a lista completa, com exemplos, está no ADR-76, passo 4):
    - números: dia/mês/ano e mês/dia/ano, com barra, ponto, traço ou espaço, ano com 2 ou 4 dígitos (14/09/2026,
      9/14/2026, 14.09.26, 14 09 2026); ano primeiro (2026-09-14, 2026/09/14); compacta (20260914, 14092026);
      número de série do Excel (46266, 46266.5);
    - mês escrito, em português ou inglês: "14 de setembro de 2026", "14 set 2026", "14/set/26", "14-Sep-2026",
      "1º de maio de 2020", "Sep 14, 2026", "May 3rd, 2020", "the 14th of September 2026";
    - tudo por extenso: "quatorze de setembro de mil novecentos e noventa e um", "primeiro de maio de dois mil e
      vinte", "September fourteenth, nineteen ninety-one";
    - com o que não é data em volta: dia da semana antes ("segunda-feira, 14/09/2026", "Mon, Sep 14 2026") e hora
      depois ("14/09/2026 08:30", "às 10h", "2026-09-14T08:30:00Z", "8:30 PM").
    Só mês e ano ("09/2026") não é data completa: vira pendência dizendo que falta o dia.
    """
    # A hora depois da data não importa para o cadastro ("01/09/2026 08:30" → "01/09/2026")
    texto = _sem_a_hora(valor.strip())
    # Mês escrito ("14 de setembro de 1991", "Sep 14, 1991"): o nome do mês não deixa dúvida de ordem
    por_extenso = _data_com_mes_escrito(texto)
    if por_extenso is not None:
        return por_extenso
    # Tudo escrito com palavras ("quatorze de setembro de mil novecentos e noventa e um")
    escrita = datas_por_extenso.data_escrita(texto)
    if escrita is not None:
        return escrita
    # Ano em dois dígitos ("06/05/24"): vira o mesmo formato com quatro dígitos e segue a regra de sempre
    ano_curto = DATA_COM_ANO_CURTO.fullmatch(texto)
    if ano_curto:
        ano = _ano_com_quatro_digitos(int(ano_curto.group(3)))
        texto = f"{ano_curto.group(1)}/{ano_curto.group(2)}/{ano}"
    # Ano primeiro: 2026-09-01, 2026/09/01 (sempre ano, mês e dia)
    ano_primeiro = DATA_ANO_PRIMEIRO.fullmatch(texto)
    if ano_primeiro:
        return _montar_data(int(ano_primeiro.group(1)), int(ano_primeiro.group(2)), int(ano_primeiro.group(3)))
    # Número de série do Excel
    if DATA_DO_EXCEL.fullmatch(texto):
        # Só os dias inteiros (a fração é a hora)
        return INICIO_DAS_DATAS_DO_EXCEL + timedelta(days=int(texto[:5]))
    # Compacta: 20260901 é ano, mês e dia; 01092026 vira 01/09/2026 e segue a regra de dia e mês
    if DATA_COMPACTA.fullmatch(texto):
        if _ano_primeiro_compacto(texto):
            return _montar_data(int(texto[:4]), int(texto[4:6]), int(texto[6:8]))
        texto = f"{texto[:2]}/{texto[2:4]}/{texto[4:]}"
    # 01/09/2026 e parecidos
    partes = DATA_COM_BARRAS.fullmatch(texto)
    if partes:
        primeira, segunda, ano = int(partes.group(1)), int(partes.group(2)), int(partes.group(3))
        if ordem is None:
            # Sem ordem definida: só dá para converter se uma das partes passar de 12
            if primeira > 12:
                return _montar_data(ano, segunda, primeira)
            if segunda > 12:
                return _montar_data(ano, primeira, segunda)
            raise NaoConvertido("data ambígua (dia e mês podem estar trocados)")
        # Dia primeiro (DD/MM/AAAA)
        if ordem == "DMY":
            return _montar_data(ano, segunda, primeira)
        # Mês primeiro (MM/DD/AAAA)
        return _montar_data(ano, primeira, segunda)
    # Mês e ano, sem o dia: não dá para inventar o dia
    if MES_E_ANO_SEM_DIA.fullmatch(texto):
        raise NaoConvertido("a data não tem o dia (só o mês e o ano)")
    raise NaoConvertido("formato de data desconhecido")


def converter_documento(valor: str, tamanho: int, valido, veio_como_numero: bool) -> tuple[str, bool]:
    """CPF (11) ou CNPJ (14) só com dígitos. Devolve (valor, zeros_recompostos).

    Se o Excel guardou o documento como número e os zeros à esquerda sumiram, eles só são recolocados
    quando o dígito verificador confirma: assim não é suposição.
    """
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == tamanho:
        return digitos, False
    if veio_como_numero and 0 < len(digitos) < tamanho:
        com_zeros = digitos.zfill(tamanho)
        if valido(com_zeros):
            return com_zeros, True
    raise NaoConvertido(f"deveria ter {tamanho} dígitos")


def _sem_sufixo_de_genero(chave: str) -> str:
    """Tira o sufixo de gênero do fim, já na chave de comparação (a pontuação virou espaço).

    Ex.: "solteiro a" (de "Solteiro(a)", "solteiro/a" ou "SOLTEIRO (A)") → "solteiro"; "casado o" → "casado".
    Sem sufixo, volta como veio.
    """
    for sufixo in (" a", " o"):
        if chave.endswith(sufixo):
            return chave[:-len(sufixo)]
    return chave


def _forma_masculina(chave: str) -> str | None:
    """A forma que só troca o "a" final da última palavra por "o". Ex.: "casada" → "casado"; "viuva" → "viuvo".

    Devolve None quando a chave não termina em "a" (nada a trocar).
    """
    if not chave.endswith("a"):
        return None
    return chave[:-1] + "o"


def _item_da_lista(chave: str, valores_aceitos: list[str]) -> str | None:
    """O item da lista cuja chave de comparação é igual à chave, ou None."""
    for aceito in valores_aceitos:
        if _chave_de_comparacao(aceito) == chave:
            return aceito
    return None


def converter_dominio(valor: str, campo: str, dominios: dict) -> str:
    """Valor de lista fechada (ex.: sexo, estado civil): aceita a forma oficial, um sinônimo conhecido ou a variação
    de gênero de um item da lista.

    Variação de gênero: "Solteiro(a)", "solteiro/a", "SOLTEIRO (A)" e "Solteira" viram
    "Solteiro"; "Casada" vira "Casado". Nada é assumido: só casa com um item que JÁ está na lista do parâmetro.
    """
    regra = dominios.get(campo)
    # Campo sem lista fechada: só tira os espaços
    if regra is None:
        return valor.strip()
    chave = _chave_de_comparacao(valor)
    # O próprio valor aceito, escrito com outra caixa ou acento
    aceito = _item_da_lista(chave, regra["valores"])
    if aceito:
        return aceito
    # Um sinônimo conhecido ("feminino" -> "F")
    if chave in regra["sinonimos"]:
        return regra["sinonimos"][chave]
    # A variação de gênero: sem o sufixo "(a)", "(o)", "/a", "/o"; depois, a forma que troca o "a" final por "o"
    sem_sufixo = _sem_sufixo_de_genero(chave)
    aceito = _item_da_lista(sem_sufixo, regra["valores"])
    if aceito:
        return aceito
    masculina = _forma_masculina(sem_sufixo)
    if masculina:
        aceito = _item_da_lista(masculina, regra["valores"])
        if aceito:
            return aceito
    raise NaoConvertido(f"fora da lista aceita ({', '.join(regra['valores'])})")


# O palpite por semelhança só vale acima desta nota (0 a 1) e com esta folga sobre o 2º colocado
SEMELHANCA_MINIMA_DO_PALPITE = 0.85
FOLGA_MINIMA_DO_PALPITE = 0.1


def _semelhanca(primeiro: str, segundo: str) -> float:
    """Quanto dois textos se parecem, de 0 a 1 (difflib: a biblioteca padrão do Python que compara sequências).

    Ex.: ("casdo", "casado") → 0,91; ("salario", "clt") → 0,2.
    """
    import difflib
    return difflib.SequenceMatcher(None, primeiro, segundo).ratio()


def palpite_na_lista(valor: str | None, campo: str, dominios: dict) -> str | None:
    """Um palpite SEGURO do item da lista fechada que o valor lido quis dizer, ou None (na dúvida, sem palpite).

    Para que serve (pendências por conversa): num valor fora da lista, o agente pode sugerir "Acredito que o
    certo é 'Solteiro'. Posso usar?". Quem decide continua sendo a pessoa; o palpite só aparece quando é seguro:
      1. o valor vira um item da lista pelas mesmas regras da padronização (acento, caixa, sinônimo, gênero); ou
      2. um único item se parece muito com ele (nota >= SEMELHANCA_MINIMA_DO_PALPITE) e com folga clara sobre o 2º.
    Ex.: ("Casdo", "estado_civil") → "Casado"; ("Salário", "tipo_renda") → None; ("x", "cargo") → None (sem lista).
    """
    regra = dominios.get(campo)
    if regra is None or not valor:
        return None
    # 1. As regras da padronização (o valor pode ter sido lido antes delas existirem)
    try:
        return converter_dominio(valor, campo, dominios)
    except NaoConvertido:
        pass
    # 2. A semelhança com cada item da lista, sem o sufixo de gênero
    chave = _sem_sufixo_de_genero(_chave_de_comparacao(valor))
    notas = []
    for aceito in regra["valores"]:
        notas.append((_semelhanca(chave, _chave_de_comparacao(aceito)), aceito))
    notas.sort(reverse=True)
    melhor_nota, melhor_item = notas[0]
    segunda_nota = notas[1][0] if len(notas) > 1 else 0.0
    if melhor_nota >= SEMELHANCA_MINIMA_DO_PALPITE and melhor_nota - segunda_nota >= FOLGA_MINIMA_DO_PALPITE:
        return melhor_item
    return None


def carregar_dominios() -> dict:
    """As listas fechadas do layout (data/contratos/dominios_v1.json), com os sinônimos já na chave de comparação."""
    dados = json.loads((RAIZ / "data" / "contratos" / "dominios_v1.json").read_text(encoding="utf-8"))
    dominios = {}
    for campo, regra in dados.items():
        # Chaves que começam com "_" são comentários do arquivo
        if campo.startswith("_"):
            continue
        sinonimos = {}
        for sinonimo, valor_oficial in regra["sinonimos"].items():
            sinonimos[_chave_de_comparacao(sinonimo)] = valor_oficial
        dominios[campo] = {"valores": regra["valores"], "sinonimos": sinonimos}
    return dominios


# ---------------- Plano de transformação (allowlist) ----------------

def plano_de_transformacao(mapeamento: MappingPlan, campos: list[CampoLayout]) -> list[dict]:
    """Deriva as operações do tipo de cada campo de destino. Só colunas mapeadas e aprovadas entram."""
    tipo_do_campo = {}
    for campo in campos:
        tipo_do_campo[campo.campo] = campo.tipo
    plano = []
    for item in mapeamento.itens:
        if item.status == StatusMapeamento.AMBIGUO:
            raise ValueError(f"A coluna {item.coluna!r} ainda está AMBIGUO: o mapeamento não foi aprovado.")
        # Coluna ignorada (NAO_MAPEADO) não entra no plano
        if item.status == StatusMapeamento.PROPOSTO:
            tipo = tipo_do_campo[item.campo]
            plano.append({"coluna": item.coluna, "campo": item.campo, "tipo": tipo.value,
                          "operacoes": list(OPERACOES_POR_TIPO[tipo])})
    validar_plano(plano, mapeamento, campos)
    return plano


def validar_plano(plano: list[dict], mapeamento: MappingPlan, campos: list[CampoLayout]) -> None:
    """Confere o plano antes de executar: só colunas aprovadas, tipo do layout vigente e operações da allowlist."""
    pares_aprovados = set()
    for item in mapeamento.itens:
        if item.status == StatusMapeamento.PROPOSTO:
            pares_aprovados.add((item.coluna, item.campo))
    tipo_do_campo = {}
    for campo in campos:
        tipo_do_campo[campo.campo] = campo.tipo.value
    for passo in plano:
        if (passo["coluna"], passo["campo"]) not in pares_aprovados:
            raise ValueError(f"Operação sobre coluna fora do mapeamento aprovado: {passo['coluna']!r}.")
        if tipo_do_campo.get(passo["campo"]) != passo["tipo"]:
            raise ValueError(f"Tipo do campo {passo['campo']} diferente do layout vigente.")
        fora_da_lista = set(passo["operacoes"]) - ALLOWLIST
        if fora_da_lista:
            raise ValueError(f"Operação fora da lista permitida: {', '.join(sorted(fora_da_lista))}.")


# ---------------- Conferência de uma coluna trocada pela empresa ----------------

# Quantos exemplos de valor que não serve a conferência devolve (a tela mostra poucos)
EXEMPLOS_QUE_NAO_SERVEM = 3


def _parece_texto(valor: str) -> bool:
    """True se o valor tem pelo menos uma letra. "Maria" → True; "529.982.247-25" → False; "05/03/2026" → False."""
    for caractere in valor:
        if caractere.isalpha():
            return True
    return False


def _digito_confere(documento: str, tipo: TipoCampo) -> bool:
    """True se o dígito verificador do CPF ou do CNPJ confere (os outros tipos não têm dígito: sempre True)."""
    if tipo == TipoCampo.CPF:
        return cpf_valido(documento)
    if tipo == TipoCampo.CNPJ:
        return cnpj_valido(documento)
    return True


def conferir_valores_para_o_campo(valores: list[str], campo: CampoLayout, conferir_digito: bool = False) -> dict:
    """Confere, sem gravar nada, se os valores de uma coluna servem para o campo que a empresa escolheu.

    É a mesma conversão da padronização, feita antes do aceite, para a tela avisar na hora (ex.: a empresa pôs a
    coluna do CPF no campo da data de admissão). Campo de texto aceita qualquer coisa; nele, a conferência só
    estranha valor sem nenhuma letra (um número ou uma data no lugar do nome).
    Recebe: valores — os da coluna (vazios são ignorados); campo — o do layout; conferir_digito — True para conferir
    também o dígito verificador do CPF e do CNPJ (a coluna indicada na conversa como o CPF, ADR-124).
    Devolve: {"preenchidos": N, "nao_servem": N, "exemplos": [{"valor": ..., "motivo": ...}]}.
    Ex.: ["05/03/2026", "abc"] para uma DATA → {"preenchidos": 2, "nao_servem": 1, "exemplos": [{"valor": "abc", ...}]}.
    """
    # Só os valores preenchidos
    preenchidos = []
    for valor in valores:
        if valor.strip():
            preenchidos.append(valor)
    nao_servem = []
    if campo.tipo == TipoCampo.TEXTO:
        # Texto: estranha só valor sem letra nenhuma
        for valor in preenchidos:
            if not _parece_texto(valor):
                nao_servem.append({"valor": valor, "motivo": "não parece um texto (não tem nenhuma letra)"})
    else:
        # Os outros tipos: a conversão da padronização, com o contexto da coluna inteira (separador decimal etc.)
        resultado_descartavel = Normalizacao(registros=[], plano=[], log=[])
        entrada_do_log = {"alterados": 0, "nao_convertidos": 0}
        contexto = _contexto_da_coluna(campo.tipo, preenchidos, "", {}, False, resultado_descartavel, entrada_do_log)
        # Data sem desempate dia/mês: aqui só interessa se É uma data (o formato a empresa decide depois)
        if contexto.get("ordem") == "PENDENTE":
            contexto["ordem"] = "DMY"
        dominios = carregar_dominios()
        for valor in preenchidos:
            # try/except: o valor que não converte é justamente o que a conferência procura
            try:
                convertido = _converter(valor, campo.tipo, campo.campo, contexto, dominios, entrada_do_log)
            except NaoConvertido as motivo:
                nao_servem.append({"valor": valor, "motivo": str(motivo)})
                continue
            # O dígito verificador do CPF e do CNPJ, quando pedido (a padronização aceita o número com o dígito
            # errado: quem aponta é o Validador; aqui a conferência precisa saber antes)
            if conferir_digito and not _digito_confere(convertido, campo.tipo):
                nao_servem.append({"valor": valor, "motivo": "o dígito verificador não confere"})
    return {"preenchidos": len(preenchidos), "nao_servem": len(nao_servem),
            "exemplos": nao_servem[:EXEMPLOS_QUE_NAO_SERVEM]}


# ---------------- Execução ----------------

def normalizar(leitura: Leitura, mapeamento: MappingPlan, campos: list[CampoLayout],
               decisoes: dict[str, str] | None = None) -> Normalizacao:
    """Converte todas as linhas. decisoes: coluna -> "DMY" | "MDY" (datas) ou "zeros:N" (matrícula).

    A coluna em que a IA ficou em dúvida só entre campos opcionais, e que ficou de fora, é guardada sem rótulo em cada
    registro (services/informacoes_sem_rotulo.py; ADR-143, Parte 1): ela nunca vira o valor de um campo.
    """
    decisoes = decisoes or {}
    plano = plano_de_transformacao(mapeamento, campos)
    dominios = carregar_dominios()
    # O número de cada linha no arquivo, como a empresa vê no Excel
    if leitura.numeros_linha:
        numeros_das_linhas = leitura.numeros_linha
    else:
        primeira_linha_de_dados = leitura.linha_do_cabecalho + 1
        numeros_das_linhas = list(range(primeira_linha_de_dados, primeira_linha_de_dados + len(leitura.linhas)))
    # Um registro por linha, com todos os campos do layout começando vazios
    registros = []
    for numero_da_linha in numeros_das_linhas:
        registro = {"_linha": numero_da_linha}
        for campo in campos:
            registro[campo.campo] = None
        registros.append(registro)
    resultado = Normalizacao(registros=registros, plano=plano, log=[])

    # Convenção de data do ARQUIVO: todas as colunas de data, juntas, desempatam dia/mês × mês/dia
    datas_do_arquivo = []
    for passo in plano:
        if passo["tipo"] == TipoCampo.DATA.value:
            posicao_da_coluna = leitura.cabecalhos.index(passo["coluna"])
            for linha in leitura.linhas:
                datas_do_arquivo.append(linha[posicao_da_coluna])
    ordem_do_arquivo = ordem_das_datas(datas_do_arquivo)
    # Um campo pode vir de várias colunas (no Word em texto corrido, uma por rótulo): a decisão de formato dada numa
    # delas vale para as outras, e a dúvida de formato aparece uma vez só por campo
    decisoes = _decisoes_para_as_colunas_do_mesmo_campo(plano, decisoes)
    campos_com_duvida_de_formato = set()

    for passo in plano:
        posicao_da_coluna = leitura.cabecalhos.index(passo["coluna"])
        campo, tipo = passo["campo"], TipoCampo(passo["tipo"])
        valores = []
        for linha in leitura.linhas:
            valores.append(linha[posicao_da_coluna])
        # A coluna tinha células gravadas como número no Excel? (zeros à esquerda podem ter sumido)
        veio_como_numero = leitura.celulas_numericas.get(posicao_da_coluna, 0) > 0
        preenchidos = 0
        for valor in valores:
            if valor.strip():
                preenchidos += 1
        # O registro do que acontece nesta coluna (vai para o log)
        entrada_do_log = {"coluna": passo["coluna"], "campo": campo, "operacoes": passo["operacoes"],
                          "preenchidos": preenchidos, "alterados": 0, "nao_convertidos": 0}
        pendencias_antes = len(resultado.pendencias_de_coluna)
        contexto = _contexto_da_coluna(tipo, valores, passo["coluna"], decisoes, veio_como_numero, resultado,
                                       entrada_do_log, ordem_do_arquivo)
        # A dúvida de formato deste campo já foi pedida noutra coluna dele: não pede de novo
        if len(resultado.pendencias_de_coluna) > pendencias_antes:
            if campo in campos_com_duvida_de_formato:
                resultado.pendencias_de_coluna.pop()
            else:
                # A dúvida leva o campo da coluna: com duas colunas em dúvida (ex.: nascimento e admissão), cada uma é
                # uma pendência diferente (sem o campo, as duas tinham a mesma regra e nenhuma linha, e a resposta num
                # cartão decidia a outra coluna)
                resultado.pendencias_de_coluna[-1]["campo"] = campo
            campos_com_duvida_de_formato.add(campo)

        for registro, valor in zip(registros, valores):
            # Vazio continua vazio; se o campo é obrigatório, o Validador aponta
            if not valor.strip():
                continue
            try:
                novo_valor = _converter(valor, tipo, campo, contexto, dominios, entrada_do_log)
            except NaoConvertido as motivo:
                # Não deu para converter com certeza: o campo fica vazio e a empresa decide
                entrada_do_log["nao_convertidos"] += 1
                resultado.nao_convertidos.append({"linha": registro["_linha"], "coluna": passo["coluna"],
                                                  "campo": campo, "valor": valor, "motivo": str(motivo)})
                continue
            registro[campo] = novo_valor
            if novo_valor != valor:
                entrada_do_log["alterados"] += 1
        resultado.log.append(entrada_do_log)

    # A coluna em dúvida só entre campos opcionais, que ficou de fora, vai sem rótulo para a pessoa (ADR-143, Parte 1)
    informacoes_sem_rotulo.guardar_nos_registros(leitura, mapeamento, campos, registros)
    resultado.conferencia = _conferir(leitura, resultado)
    return resultado


def _decisoes_para_as_colunas_do_mesmo_campo(plano: list[dict], decisoes: dict[str, str]) -> dict[str, str]:
    """As decisões de formato, estendidas às outras colunas do mesmo campo.

    Ex.: as colunas "entrou" e "começou" vão para data_admissao; a empresa decidiu "DMY" em "entrou" → "começou"
    também fica "DMY". Coluna com decisão própria mantém a dela.
    """
    decisao_do_campo = {}
    for passo in plano:
        if passo["coluna"] in decisoes and passo["campo"] not in decisao_do_campo:
            decisao_do_campo[passo["campo"]] = decisoes[passo["coluna"]]
    decisoes_estendidas = dict(decisoes)
    for passo in plano:
        if passo["coluna"] not in decisoes_estendidas and passo["campo"] in decisao_do_campo:
            decisoes_estendidas[passo["coluna"]] = decisao_do_campo[passo["campo"]]
    return decisoes_estendidas


def _tem_data_com_barras(valores: list[str]) -> bool:
    """True se algum valor da coluna é uma data como 01/09/2026 (a que pode ter dia e mês trocados)."""
    for valor in valores:
        if _partes_que_podem_trocar(valor):
            return True
    return False


def _contexto_da_coluna(tipo, valores, coluna, decisoes, veio_como_numero, resultado, entrada_do_log,
                        ordem_do_arquivo=None) -> dict:
    """Decisões que valem para a coluna inteira (convenção decimal, ordem das datas, zeros)."""
    contexto = {"veio_como_numero": veio_como_numero}
    if tipo == TipoCampo.DECIMAL_MONETARIO:
        contexto["convencao"] = convencao_decimal(valores)
        entrada_do_log["decisao"] = f"separador decimal: {contexto['convencao'] or 'sem casas decimais'}"
    elif tipo == TipoCampo.DATA:
        # Quem decide a ordem, nesta prioridade: a empresa, a própria coluna, as outras datas do arquivo
        ordem_pela_coluna = ordem_das_datas(valores)
        ordem = decisoes.get(coluna) or ordem_pela_coluna or ordem_do_arquivo
        if coluna in decisoes:
            origem = " (confirmado pela empresa)"
        elif ordem_pela_coluna is None and ordem:
            origem = " (definido pelas outras datas do arquivo)"
        else:
            origem = ""
        tem_barras = _tem_data_com_barras(valores)
        if tem_barras and ordem is None:
            # Nada desempata: a coluna inteira fica pendente, sem supor
            resultado.pendencias_de_coluna.append({
                "coluna": coluna, "tipo": "DATA_AMBIGUA",
                "mensagem": "Nenhuma data da coluna mostra se o formato é dia/mês ou mês/dia. Confirme o formato."})
            entrada_do_log["decisao"] = "datas pendentes de confirmação do formato"
            contexto["ordem"] = "PENDENTE"
        else:
            contexto["ordem"] = ordem
            if tem_barras:
                formato = "DD/MM/AAAA" if ordem == "DMY" else "MM/DD/AAAA"
                entrada_do_log["decisao"] = f"datas lidas como {formato}{origem}"
    elif tipo == TipoCampo.MATRICULA:
        # A empresa informa com quantos dígitos a matrícula fica: "zeros:5"
        decisao = decisoes.get(coluna, "")
        if decisao.startswith("zeros:"):
            contexto["zeros"] = int(decisao.split(":")[1])
        else:
            contexto["zeros"] = None
        if veio_como_numero and contexto["zeros"] is None:
            resultado.pendencias_de_coluna.append({
                "coluna": coluna, "tipo": "ZEROS_A_ESQUERDA",
                "mensagem": "A matrícula foi gravada como número no Excel: zeros à esquerda podem ter se perdido. "
                            "Informe com quantos dígitos ela deve ficar."})
    return contexto


def _converter(valor: str, tipo: TipoCampo, campo: str, contexto: dict, dominios: dict, entrada_do_log: dict) -> str:
    """Converte UM valor conforme o tipo do campo. Levanta NaoConvertido quando não há certeza."""
    texto = valor.strip()
    if tipo == TipoCampo.TEXTO:
        return texto
    if tipo == TipoCampo.MATRICULA:
        # Completa os zeros só com a decisão da empresa
        if contexto.get("zeros") and texto.isdigit():
            return texto.zfill(contexto["zeros"])
        return texto
    if tipo in (TipoCampo.CPF, TipoCampo.CNPJ):
        if tipo == TipoCampo.CPF:
            tamanho, conferir_digito = 11, cpf_valido
        else:
            tamanho, conferir_digito = 14, cnpj_valido
        documento, zeros_recompostos = converter_documento(texto, tamanho, conferir_digito, contexto["veio_como_numero"])
        if zeros_recompostos:
            entrada_do_log["zeros_recompostos"] = entrada_do_log.get("zeros_recompostos", 0) + 1
        return documento
    if tipo in (TipoCampo.CEP, TipoCampo.TELEFONE):
        digitos = re.sub(r"\D", "", texto)
        if not digitos:
            raise NaoConvertido("sem dígitos")
        # Telefone com o código do Brasil na frente ("+55 71 99205-7734"): o 55 sai, fica DDD + número (ADR-73)
        if tipo == TipoCampo.TELEFONE and digitos.startswith("55") and len(digitos) in (12, 13):
            digitos = digitos[2:]
        return digitos
    if tipo == TipoCampo.UF:
        # Duas letras: já é a sigla; senão, procura pelo nome do estado
        if len(texto) == 2:
            sigla = texto.upper()
        else:
            sigla = ESTADOS.get(_chave_de_comparacao(texto))
        if not sigla:
            raise NaoConvertido("UF desconhecida")
        return sigla
    if tipo == TipoCampo.EMAIL:
        return texto.lower()
    if tipo == TipoCampo.DECIMAL_MONETARIO:
        return str(converter_decimal(texto, contexto["convencao"]))
    if tipo == TipoCampo.DATA:
        if contexto["ordem"] == "PENDENTE":
            # Data com barras espera a decisão da empresa; as outras (ex.: 2026-09-01) não têm dúvida
            if _partes_que_podem_trocar(texto):
                raise NaoConvertido("aguardando a confirmação do formato de data da coluna")
            return converter_data(texto, None).isoformat()
        return converter_data(texto, contexto["ordem"]).isoformat()
    if tipo == TipoCampo.DOMINIO:
        return converter_dominio(texto, campo, dominios)
    raise NaoConvertido(f"tipo sem conversão: {tipo.value}")


def _conferir(leitura: Leitura, resultado: Normalizacao) -> dict:
    """Nada some e nada aparece: mesmas linhas, mesmos vazios, soma dos valores convertidos.

    Um campo pode vir de mais de uma coluna (no Word em texto corrido, cada jeito de a empresa chamar o dado é uma
    coluna, e cada pessoa tem o valor numa só delas). Por isso a conta é por campo: na origem, o campo está vazio numa
    linha quando TODAS as colunas dele estão vazias nela.
    """
    # As posições das colunas de cada campo do plano: {campo: [posição, ...]}
    posicoes_por_campo = {}
    for passo in resultado.plano:
        posicoes_por_campo.setdefault(passo["campo"], []).append(leitura.cabecalhos.index(passo["coluna"]))
    # Campos vazios no arquivo, linha por linha
    vazios_na_origem = 0
    for linha in leitura.linhas:
        for posicoes in posicoes_por_campo.values():
            campo_vazio_na_linha = True
            for posicao_da_coluna in posicoes:
                if linha[posicao_da_coluna].strip():
                    campo_vazio_na_linha = False
            if campo_vazio_na_linha:
                vazios_na_origem += 1
    # Campos vazios no resultado, nos mesmos campos
    vazios_no_destino = 0
    for registro in resultado.registros:
        for campo in posicoes_por_campo:
            if registro[campo] is None:
                vazios_no_destino += 1
    # Soma das rendas convertidas (serve para conferir com o total que a empresa conhece)
    soma_das_rendas = Decimal("0")
    for registro in resultado.registros:
        if registro.get("valor_renda"):
            soma_das_rendas += Decimal(registro["valor_renda"])
    return {"linhas_lidas": len(leitura.linhas), "registros": len(resultado.registros),
            "linhas_conferem": len(leitura.linhas) == len(resultado.registros),
            "vazios_na_origem": vazios_na_origem,
            "vazios_no_destino": vazios_no_destino,
            # Vazio a mais no destino só pode ser valor que não foi convertido
            "vazios_conferem": vazios_no_destino == vazios_na_origem + len(resultado.nao_convertidos),
            "soma_valor_renda": str(soma_das_rendas)}


# ---------------- Persistência ----------------

def _preparar(conexao) -> None:
    """Cria a tabela das padronizações, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS normalizacoes (
               processamento_id TEXT PRIMARY KEY,
               resultado        TEXT NOT NULL,
               decisoes         TEXT NOT NULL,
               criado_em        TEXT NOT NULL
           )"""
    )


def executar(conexao, processamento_id: str, empresa_id: str, decisoes: dict[str, str] | None = None) -> Normalizacao:
    """Normaliza o processamento com o mapeamento APROVADO e guarda o resultado."""
    from services import mapeamentos
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    mapeamento_existente = mapeamentos.obter(conexao, processamento_id)
    if mapeamento_existente is None or mapeamento_existente[1] != "APROVADO":
        raise ValueError("O mapeamento precisa estar aprovado antes da padronização.")
    plano_aprovado = mapeamento_existente[0]
    _, campos = parametros.layout_ativo(conexao)
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    resultado = normalizar(leitura, plano_aprovado, campos, decisoes)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Grava ou substitui a padronização deste processamento ("ON CONFLICT": a mesma forma no SQLite e no PostgreSQL)
    conexao.execute("INSERT INTO normalizacoes (processamento_id, resultado, decisoes, criado_em) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (processamento_id) DO UPDATE SET resultado = excluded.resultado, "
                    "decisoes = excluded.decisoes, criado_em = excluded.criado_em",
                    (processamento_id, json.dumps(asdict(resultado), ensure_ascii=False),
                     json.dumps(decisoes or {}, ensure_ascii=False), agora))
    conexao.commit()
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.NORMALIZADO)
    # Só contagens na auditoria: nada pessoal no painel
    auditoria.registrar(conexao, processamento_id, empresa_id, "Normalização", "NORMALIZADO", {
        "registros": len(resultado.registros), "nao_convertidos": len(resultado.nao_convertidos),
        "pendencias_de_coluna": len(resultado.pendencias_de_coluna),
        "linhas_conferem": resultado.conferencia["linhas_conferem"],
        "vazios_conferem": resultado.conferencia["vazios_conferem"]})
    return resultado


def obter(conexao, processamento_id: str) -> Normalizacao | None:
    """A padronização guardada do processamento, ou None se ainda não foi feita."""
    _preparar(conexao)
    linha = conexao.execute("SELECT resultado FROM normalizacoes WHERE processamento_id = ?",
                            (processamento_id,)).fetchone()
    if linha is None:
        return None
    return Normalizacao(**json.loads(linha[0]))


def decisoes_salvas(conexao, processamento_id: str) -> dict[str, str]:
    """Decisões de coluna já tomadas pela empresa (formato de data, dígitos da matrícula)."""
    _preparar(conexao)
    linha = conexao.execute("SELECT decisoes FROM normalizacoes WHERE processamento_id = ?",
                            (processamento_id,)).fetchone()
    if linha is None:
        return {}
    return json.loads(linha[0])


def descartar(conexao, processamento_id: str) -> None:
    """Apaga a padronização do processamento (ex.: o mapeamento mudou e ela deixou de valer).

    Não faz commit: quem chama decide quando gravar, junto com as outras mudanças.
    """
    _preparar(conexao)
    conexao.execute("DELETE FROM normalizacoes WHERE processamento_id = ?", (processamento_id,))


def converter_valor(valor: str, campo: CampoLayout) -> str:
    """Padroniza UM valor digitado pela empresa na correção, com as mesmas regras do arquivo.

    Data digitada no Portal segue o padrão brasileiro (DD/MM/AAAA). Levanta NaoConvertido com o motivo.
    """
    contexto = {"veio_como_numero": False, "convencao": None, "ordem": "DMY", "zeros": None}
    return _converter(str(valor), campo.tipo, campo.campo, contexto, carregar_dominios(), {})
