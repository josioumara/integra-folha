"""Divisão de uma coluna em vários campos do layout: o endereço inteiro numa célula só (ADR-76) e outras (ADR-104).

Para que serve: muitas empresas mandam o endereço numa coluna só ("Rua das Flores, 123, apto 4 - Centro,
São Paulo - SP, 01234-567"), mas o banco quer rua, número, complemento, bairro, cidade, UF e CEP separados. Escolher
UM campo da lista perderia o resto. Aqui a coluna é dividida em partes, POR REGRA (sem IA e sem custo), e cada parte
vira uma coluna nova, já ligada ao seu campo.

Como a regra lê um endereço, em ordem:
1. o CEP (8 dígitos, com ou sem traço) em qualquer lugar;
2. a UF (sigla de estado) no fim;
3. o resto é cortado nas vírgulas, nos " - " e nas barras. A rua é o pedaço que começa com um tipo de via (Rua,
   Av., Travessa...), em qualquer posição; sem nenhum, o primeiro pedaço (se ela terminar num número, "Rua A 123", o
   número sai dela). Um pedaço só com número ("123", "nº 123", "s/n") é o número; um que começa com apto, bloco, casa,
   sala, lote... é o complemento; um que começa com "Bairro" é o bairro. Esses três valem em qualquer posição;
4. dos pedaços que sobram, o último é a cidade e o anterior, o bairro (a ordem de costume). Só com um pedaço sobrando
   e SEM UF, não dá para saber se é bairro ou cidade: ele não vai para campo nenhum (nada por suposição) e a tela
   mostra o que sobrou.

O que não coube em nenhuma parte aparece na prévia ("não reconheci: ...") e, se o campo for obrigatório, vira pendência
depois do aceite, como qualquer dado que falta.

Três ferramentas (ADR-104: a IA escolhe a ferramenta e o campo de cada parte; a regra executa em todas as linhas):
- "endereco": a regra acima;
- "cidade_uf": "Salvador/BA" → cidade e UF;
- "separador": qualquer outra coluna com vários dados separados por um sinal ("001 / 1234 / 56789-0" → banco,
  agência e conta). Corta no separador e dá a cada pedaço o nome da sua posição.
"""
import re
from dataclasses import dataclass, field

# As siglas dos estados (a UF só é reconhecida se for uma delas)
SIGLAS_DOS_ESTADOS = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
                      "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}
# CEP: 5 dígitos, traço (ou ponto, ou nada) e 3 dígitos, sem ser pedaço de um número maior
PADRAO_DO_CEP = re.compile(r"(?<!\d)(\d{2})\.?(\d{3})-?(\d{3})(?!\d)")
# A palavra "CEP" que às vezes vem antes do número ("CEP: 01234-567")
PADRAO_DA_PALAVRA_CEP = re.compile(r"\bcep\b\s*:?", re.IGNORECASE)
# A UF no fim do texto, depois de espaço, vírgula, traço ou barra ("São Paulo - SP", "Salvador/BA")
PADRAO_DA_UF_NO_FIM = re.compile(r"(?:^|[\s,/-])([A-Za-z]{2})\s*[.,;-]*\s*$")
# Onde o endereço é cortado em pedaços: vírgula, ponto e vírgula, barra e traço com espaços em volta
PADRAO_DOS_CORTES = re.compile(r"\s*[,;/]\s*|\s+-\s+")
# "s/n" (sem número): vira "SN" antes dos cortes, senão a barra o partiria em dois
PADRAO_DO_SEM_NUMERO = re.compile(r"(?<![a-z])s\s*/\s*n(?![a-z])", re.IGNORECASE)
# Um pedaço que é só o número da casa: "123", "123A", "nº 123", "n. 45", "número 7", "SN" (sem número)
PADRAO_DO_NUMERO = re.compile(r"^(?:n[º°o.]?\s*|n[úu]mero\s*)?(\d+[a-zA-Z]?|sn)$", re.IGNORECASE)
# A rua que termina no número ("Rua das Flores 123", "Av. Brasil nº 45")
PADRAO_DA_RUA_COM_NUMERO = re.compile(r"^(.*[^\d\s])\s+(?:n[º°o.]?\s*)?(\d+[a-zA-Z]?)$", re.IGNORECASE)
# As palavras que abrem um complemento
PALAVRAS_DE_COMPLEMENTO = {"apto", "apt", "ap", "apartamento", "bloco", "bl", "casa", "sala", "sl", "conj",
                           "conjunto", "cj", "andar", "fundos", "lote", "lt", "quadra", "qd", "loja", "lj", "torre"}

# As palavras que abrem o nome de uma via: o pedaço que começa com uma delas é a rua, em qualquer posição
TIPOS_DE_VIA = {"rua", "r", "avenida", "av", "travessa", "tv", "trav", "alameda", "al", "estrada", "est", "rodovia",
                "rod", "praça", "praca", "pça", "largo", "viela", "beco", "via", "servidão", "servidao", "ladeira"}
# A palavra que diz que o pedaço é o bairro ("Bairro Centro")
PALAVRAS_DE_BAIRRO = {"bairro"}

# Os nomes das partes como a empresa lê na tela (e no nome das colunas novas)
NOMES_DAS_PARTES = {"logradouro": "rua", "numero": "número", "complemento": "complemento", "bairro": "bairro",
                    "municipio": "cidade", "uf": "UF", "cep": "CEP"}

# Para onde uma coluna pode ser dividida: o nome que a empresa escolhe e o campo do layout de cada parte.
# Só aparecem os destinos cujos campos existem no layout vigente (ver destinos_disponiveis)
DESTINOS_DA_DIVISAO = [
    {"nome": "Endereço residencial", "partes": {
        "logradouro": "logradouro_residencial", "numero": "numero_residencial",
        "complemento": "complemento_residencial", "bairro": "bairro_residencial",
        "municipio": "municipio_residencial", "uf": "uf_residencial", "cep": "cep_residencial"}},
    {"nome": "Endereço comercial", "partes": {
        "logradouro": "logradouro_comercial", "numero": "numero_comercial",
        "complemento": "complemento_comercial", "bairro": "bairro_comercial",
        "municipio": "municipio_comercial", "uf": "uf_comercial", "cep": "cep_comercial"}},
    {"nome": "Cidade e UF de nascimento", "partes": {
        "municipio": "municipio_naturalidade", "uf": "uf_naturalidade"}},
]


@dataclass
class EnderecoDividido:
    """As partes que a regra achou num valor e o que não coube em nenhuma."""

    partes: dict[str, str] = field(default_factory=dict)   # {"logradouro": "Rua das Flores", "numero": "123", ...}
    sobrou: list[str] = field(default_factory=list)         # os pedaços que a regra não soube onde pôr


def _tirar_cep(texto: str, resultado: EnderecoDividido) -> str:
    """Acha o CEP, guarda como 01234-567 e devolve o texto sem ele (e sem a palavra "CEP")."""
    encontrado = PADRAO_DO_CEP.search(texto)
    if encontrado is None:
        return texto
    resultado.partes["cep"] = encontrado.group(1) + encontrado.group(2) + "-" + encontrado.group(3)
    sem_cep = texto[:encontrado.start()] + texto[encontrado.end():]
    return PADRAO_DA_PALAVRA_CEP.sub("", sem_cep)


def _tirar_uf(texto: str, resultado: EnderecoDividido) -> str:
    """Acha a UF no fim do texto (só se for sigla de estado) e devolve o texto sem ela."""
    texto = texto.strip(" ,;-/")
    encontrado = PADRAO_DA_UF_NO_FIM.search(texto)
    if encontrado is None or encontrado.group(1).upper() not in SIGLAS_DOS_ESTADOS:
        return texto
    resultado.partes["uf"] = encontrado.group(1).upper()
    return texto[:encontrado.start(1)].strip(" ,;-/")


def _primeira_palavra(pedaco: str) -> str:
    """A primeira palavra do pedaço, em minúsculas e sem ponto ou dois-pontos ("Av." → "av")."""
    return pedaco.split()[0].lower().strip(".:")


def _e_complemento(pedaco: str) -> bool:
    """True se o pedaço começa com uma palavra de complemento ("apto 4", "Bloco B", "casa 2")."""
    return _primeira_palavra(pedaco) in PALAVRAS_DE_COMPLEMENTO


def _posicao_da_rua(pedacos: list[str]) -> int:
    """A posição do pedaço que é a rua: o primeiro que começa com um tipo de via (Rua, Av., Travessa...).

    Assim a ordem dentro da célula não importa: "Centro, Rua A, 10, Recife - PE" também acha a rua. Sem nenhum tipo
    de via, vale o costume de o endereço começar pela rua: o primeiro pedaço.
    """
    for posicao, pedaco in enumerate(pedacos):
        if _primeira_palavra(pedaco) in TIPOS_DE_VIA:
            return posicao
    return 0


def _guardar_complemento(resultado: EnderecoDividido, pedaco: str) -> None:
    """Junta o pedaço ao complemento ("apto 4" e "bloco B" viram "apto 4, bloco B")."""
    if "complemento" in resultado.partes:
        resultado.partes["complemento"] = resultado.partes["complemento"] + ", " + pedaco
    else:
        resultado.partes["complemento"] = pedaco


def _separar_rua_e_numero(pedaco: str, resultado: EnderecoDividido) -> None:
    """O primeiro pedaço é a rua; se ele termina num número ("Rua A 123"), o número sai dela."""
    encontrado = PADRAO_DA_RUA_COM_NUMERO.match(pedaco)
    if encontrado is not None:
        resultado.partes["logradouro"] = encontrado.group(1).strip()
        resultado.partes["numero"] = encontrado.group(2)
    else:
        resultado.partes["logradouro"] = pedaco


def _bairro_e_cidade(livres: list[str], resultado: EnderecoDividido) -> None:
    """Os pedaços que sobraram: o último é a cidade e o anterior, o bairro. Um só, sem UF: não dá para saber."""
    if not livres:
        return
    # O bairro já veio com o rótulo ("Bairro Centro"): o último pedaço é a cidade, e o resto sobra
    if "bairro" in resultado.partes:
        resultado.partes["municipio"] = livres[-1]
        for pedaco in livres[:-1]:
            resultado.sobrou.append(pedaco)
        return
    if len(livres) == 1 and "uf" not in resultado.partes:
        # "Centro" ou "Salvador"? Sem a UF, não dá para saber: não vai para campo nenhum
        resultado.sobrou.append(livres[0])
        return
    resultado.partes["municipio"] = livres[-1]
    if len(livres) >= 2:
        resultado.partes["bairro"] = livres[-2]
    # O que veio antes do bairro não tem lugar
    for pedaco in livres[:-2]:
        resultado.sobrou.append(pedaco)


def dividir_endereco(valor: str) -> EnderecoDividido:
    """Divide um endereço inteiro nas partes do layout, por regra.

    Ex.: "Rua das Flores, 123, apto 4 - Centro, São Paulo - SP, 01234-567" → rua "Rua das Flores", número "123",
    complemento "apto 4", bairro "Centro", cidade "São Paulo", UF "SP", CEP "01234-567".
    """
    resultado = EnderecoDividido()
    texto = _tirar_cep(valor.strip(), resultado)
    texto = _tirar_uf(texto, resultado)
    texto = PADRAO_DO_SEM_NUMERO.sub("SN", texto)
    pedacos = []
    for pedaco in PADRAO_DOS_CORTES.split(texto):
        if pedaco.strip():
            pedacos.append(pedaco.strip())
    if not pedacos:
        return resultado
    # A rua: o pedaço que começa com um tipo de via, em qualquer posição (sem nenhum, o primeiro pedaço)
    posicao_da_rua = _posicao_da_rua(pedacos)
    _separar_rua_e_numero(pedacos[posicao_da_rua], resultado)
    livres = []
    for posicao, pedaco in enumerate(pedacos):
        if posicao == posicao_da_rua:
            continue
        numero = PADRAO_DO_NUMERO.match(pedaco)
        if "numero" not in resultado.partes and numero is not None:
            # Só o número ("nº 7" → "7"); sem número fica "S/N"
            if numero.group(1).lower() == "sn":
                resultado.partes["numero"] = "S/N"
            else:
                resultado.partes["numero"] = numero.group(1)
        elif _e_complemento(pedaco):
            _guardar_complemento(resultado, pedaco)
        elif _primeira_palavra(pedaco) in PALAVRAS_DE_BAIRRO and len(pedaco.split()) > 1:
            # "Bairro Centro": o bairro vem com o rótulo, em qualquer posição
            resultado.partes["bairro"] = pedaco.split(None, 1)[1].strip(" :")
        else:
            livres.append(pedaco)
    _bairro_e_cidade(livres, resultado)
    return resultado


def dividir_cidade_e_uf(valor: str) -> EnderecoDividido:
    """Divide "Salvador/BA", "São Paulo - SP" ou "Recife, PE" em cidade e UF. Sem UF, tudo é a cidade.

    Ex.: "Salvador/BA" → cidade "Salvador", UF "BA".
    """
    resultado = EnderecoDividido()
    cidade = _tirar_uf(valor.strip(), resultado)
    if cidade:
        resultado.partes["municipio"] = cidade
    return resultado


def dividir(valor: str, destino: dict) -> EnderecoDividido:
    """Divide o valor conforme o destino: endereço inteiro ou só cidade e UF (destino sem rua)."""
    if "logradouro" in destino["partes"]:
        return dividir_endereco(valor)
    return dividir_cidade_e_uf(valor)


def dividir_por_separador(valor: str, separador: str, nomes_das_partes: list[str]) -> EnderecoDividido:
    """Corta o valor no separador e dá a cada pedaço o nome da sua posição.

    Recebe: valor; separador (ex.: "/"); nomes_das_partes — na ordem (ex.: ["banco", "agência", "conta"]).
    Devolve: as partes achadas. Com mais pedaços do que nomes, os de sobra vão para "sobrou" (nada por suposição).
    Ex.: ("001 / 1234 / 56789-0", "/", ["banco", "agência", "conta"]) → banco "001", agência "1234", conta "56789-0".
    """
    resultado = EnderecoDividido()
    pedacos = []
    for pedaco in valor.split(separador):
        # Pedaço vazio (dois separadores seguidos) não conta
        if pedaco.strip():
            pedacos.append(pedaco.strip())
    for posicao, pedaco in enumerate(pedacos):
        if posicao < len(nomes_das_partes):
            resultado.partes[nomes_das_partes[posicao]] = pedaco
        else:
            resultado.sobrou.append(pedaco)
    return resultado


def dividir_com_a_ferramenta(valor: str, ferramenta: str, separador: str, nomes_das_partes: list[str]) -> EnderecoDividido:
    """Divide um valor com a ferramenta escolhida ("endereco", "cidade_uf" ou "separador").

    Ex.: ("Salvador/BA", "cidade_uf", "", ["municipio", "uf"]) → cidade "Salvador", UF "BA".
    Levanta ValueError se a ferramenta não existe ou se o separador veio vazio.
    """
    if ferramenta == "endereco":
        return dividir_endereco(valor)
    if ferramenta == "cidade_uf":
        return dividir_cidade_e_uf(valor)
    if ferramenta == "separador":
        if not separador:
            raise ValueError("A divisão por separador precisa do separador (ex.: \"/\").")
        return dividir_por_separador(valor, separador, nomes_das_partes)
    raise ValueError(f"Não existe a ferramenta de divisão {ferramenta!r}.")


def nome_da_parte(ferramenta: str, parte: str) -> str:
    """Como a parte aparece para a empresa: "logradouro" vira "rua"; na divisão por separador, o nome é o da posição."""
    if ferramenta in ("endereco", "cidade_uf"):
        return NOMES_DAS_PARTES[parte]
    return parte


def destinos_disponiveis(campos) -> list[dict]:
    """Os destinos de divisão cujos campos existem todos no layout vigente.

    Recebe: campos — os do layout. Devolve: [{"nome", "partes": {parte: campo}}].
    """
    nomes_dos_campos = set()
    for campo in campos:
        nomes_dos_campos.add(campo.campo)
    disponiveis = []
    for destino in DESTINOS_DA_DIVISAO:
        todos_existem = True
        for campo in destino["partes"].values():
            if campo not in nomes_dos_campos:
                todos_existem = False
        if todos_existem:
            disponiveis.append(destino)
    return disponiveis


def destino_pelo_nome(campos, nome: str) -> dict:
    """O destino escolhido pela empresa. Levanta ValueError se não existe no layout vigente."""
    for destino in destinos_disponiveis(campos):
        if destino["nome"] == nome:
            return destino
    raise ValueError(f"Não há como dividir em \"{nome}\" no layout atual.")
