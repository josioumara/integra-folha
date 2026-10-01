"""CPF e CNPJ: gerar números sintéticos (para os dados de teste) e conferir o dígito verificador.

Os dois últimos dígitos de um CPF ou de um CNPJ são o "dígito verificador": são calculados a partir dos
dígitos anteriores. Refazer essa conta e comparar pega a maioria dos erros de digitação. Os números
gerados aqui são sintéticos: não pertencem a pessoas ou empresas reais.

A conta (a mesma para CPF e CNPJ, só mudam os pesos):
1. multiplica cada dígito pelo seu peso e soma tudo;
2. pega o resto da divisão da soma por 11;
3. se o resto for 0 ou 1, o dígito é 0; senão, o dígito é 11 menos o resto.
"""
import random

# Pesos do primeiro dígito do CPF: 10, 9, 8, ..., 2 (um para cada um dos 9 primeiros dígitos)
PESOS_CPF_PRIMEIRO_DIGITO = [10, 9, 8, 7, 6, 5, 4, 3, 2]
# Pesos do segundo dígito do CPF: 11, 10, ..., 2 (os 9 dígitos mais o primeiro verificador)
PESOS_CPF_SEGUNDO_DIGITO = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
# Pesos do primeiro dígito do CNPJ (12 primeiros dígitos)
PESOS_CNPJ_PRIMEIRO_DIGITO = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
# Pesos do segundo dígito do CNPJ (12 dígitos mais o primeiro verificador)
PESOS_CNPJ_SEGUNDO_DIGITO = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def _calcular_digito(digitos: list[int], pesos: list[int]) -> int:
    """Calcula um dígito verificador com a conta do módulo 11 (explicada no topo do arquivo)."""
    # Multiplica cada dígito pelo peso da mesma posição e soma tudo
    soma = 0
    for digito, peso in zip(digitos, pesos):
        soma += digito * peso
    # Resto da divisão por 11
    resto = soma % 11
    # Resto 0 ou 1: o dígito é 0; senão, é 11 menos o resto
    if resto < 2:
        return 0
    return 11 - resto


def _digitos_verificadores_do_cpf(nove_primeiros: list[int]) -> list[int]:
    """Os dois dígitos verificadores de um CPF, a partir dos 9 primeiros dígitos."""
    # O primeiro usa só os 9 dígitos
    primeiro = _calcular_digito(nove_primeiros, PESOS_CPF_PRIMEIRO_DIGITO)
    # O segundo usa os 9 dígitos mais o primeiro verificador
    segundo = _calcular_digito(nove_primeiros + [primeiro], PESOS_CPF_SEGUNDO_DIGITO)
    return [primeiro, segundo]


def _somente_digitos(texto) -> list[int]:
    """Os dígitos de um texto, como números (ex.: "529.982.247-25" vira [5, 2, 9, ...])."""
    digitos = []
    for caractere in str(texto):
        if caractere.isdigit():
            digitos.append(int(caractere))
    return digitos


def gerar_cpf(sorteio: random.Random) -> str:
    """Sorteia um CPF sintético válido: 11 dígitos, sem pontuação (ex.: "52998224725")."""
    while True:
        # Sorteia os 9 primeiros dígitos
        nove_primeiros = []
        for _posicao in range(9):
            nove_primeiros.append(sorteio.randint(0, 9))
        # CPF com todos os dígitos iguais (111.111.111-11) é inválido: sorteia de novo
        if len(set(nove_primeiros)) == 1:
            continue
        # Junta os 9 dígitos com os 2 verificadores e transforma em texto
        todos_os_digitos = nove_primeiros + _digitos_verificadores_do_cpf(nove_primeiros)
        return "".join(str(digito) for digito in todos_os_digitos)


def cpf_valido(cpf: str) -> bool:
    """True se o CPF tem 11 dígitos e o dígito verificador confere. Aceita com ou sem pontuação."""
    # Pega só os dígitos ("529.982.247-25" e "52998224725" dão o mesmo resultado)
    digitos = _somente_digitos(cpf)
    # Precisa ter exatamente 11 dígitos
    if len(digitos) != 11:
        return False
    # Todos os dígitos iguais passam na conta, mas são CPFs inválidos por regra
    if len(set(digitos)) == 1:
        return False
    # Refaz a conta com os 9 primeiros e compara com os 2 últimos
    return digitos[9:] == _digitos_verificadores_do_cpf(digitos[:9])


def gerar_cnpj(sorteio: random.Random, filial: int = 1) -> str:
    """Sorteia um CNPJ sintético válido: 8 dígitos da empresa, 4 da filial e 2 verificadores."""
    # Sorteia os 8 dígitos da empresa (a "raiz" do CNPJ)
    doze_primeiros = []
    for _posicao in range(8):
        doze_primeiros.append(sorteio.randint(0, 9))
    # Acrescenta os 4 dígitos da filial (ex.: filial 1 vira 0001)
    for caractere in f"{filial:04d}":
        doze_primeiros.append(int(caractere))
    # Calcula os dois verificadores
    primeiro = _calcular_digito(doze_primeiros, PESOS_CNPJ_PRIMEIRO_DIGITO)
    segundo = _calcular_digito(doze_primeiros + [primeiro], PESOS_CNPJ_SEGUNDO_DIGITO)
    # Junta tudo e transforma em texto
    todos_os_digitos = doze_primeiros + [primeiro, segundo]
    return "".join(str(digito) for digito in todos_os_digitos)


def cnpj_valido(cnpj: str) -> bool:
    """True se o CNPJ tem 14 dígitos e o dígito verificador confere. Aceita com ou sem pontuação."""
    # Pega só os dígitos
    digitos = _somente_digitos(cnpj)
    # Precisa ter exatamente 14 dígitos
    if len(digitos) != 14:
        return False
    # Todos os dígitos iguais são inválidos por regra
    if len(set(digitos)) == 1:
        return False
    # Refaz a conta com os 12 primeiros
    primeiro = _calcular_digito(digitos[:12], PESOS_CNPJ_PRIMEIRO_DIGITO)
    segundo = _calcular_digito(digitos[:12] + [primeiro], PESOS_CNPJ_SEGUNDO_DIGITO)
    # Compara com os 2 últimos
    return digitos[12:] == [primeiro, segundo]
