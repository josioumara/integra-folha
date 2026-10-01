"""Formatação de números no padrão brasileiro, num lugar só (usada pelas telas e pelo Validador)."""
from decimal import Decimal


def em_reais(valor: Decimal) -> str:
    """Dinheiro no padrão brasileiro: 1234567.89 vira "R$ 1.234.567,89"."""
    # Formato americano primeiro (1,234,567.89)
    texto_americano = f"{valor:,.2f}"
    # Troca vírgula e ponto de lugar, usando "#" como troca temporária
    texto_brasileiro = texto_americano.replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto_brasileiro}"
