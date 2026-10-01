"""Testes do menu Sistema (a engrenagem) do Portal Interno: as 3 telas à vista, na ordem, em todas as telas do banco.

Lê o HTML das páginas, sem os comentários e sem as caixas <template> (o que o navegador desenha), sem navegador:
    - o menu tem "Parâmetros do layout", "Acompanhamento dos agentes" e "Teto de custo com agentes", nessa ordem; as
      Premissas financeiras continuam ocultas (ADR-148);
    - na tela do Teto, o item dela leva aria-current="page", e só ele.
O roteiro de clique menu_do_portal_interno confere o mesmo no Chrome (abrir, as setas e cada item levando à sua tela).
"""
import re

import pytest

from api.principal import PASTA_DO_FRONT

# Um comentário do HTML inteiro (<!-- ... -->). O "?" pega o menor pedaço; re.DOTALL deixa o "." passar de linha
PADRAO_DO_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
# Uma caixa <template ...>...</template> inteira (o navegador guarda o que está dentro sem desenhar)
PADRAO_DA_CAIXA = re.compile(r"<template\b[^>]*>.*?</template>", re.DOTALL)
# A lista do menu Sistema inteira (<ul ... data-itens-configuracao ...> ... </ul>)
PADRAO_DA_LISTA_DO_MENU = re.compile(r"<ul\b[^>]*data-itens-configuracao[^>]*>(.*?)</ul>", re.DOTALL)
# Um item do menu: o endereço, o que vem depois dele dentro da tag (ex.: aria-current) e o texto
PADRAO_DO_ITEM = re.compile(r'<a href="([^"]+)" class="menu-configuracao-item"([^>]*)>([^<]+)</a>')

# Os itens à vista do menu Sistema, na ordem, e a tela de cada um
ITENS_DO_SISTEMA = [
    ("Parâmetros do layout", "banco_parametros.html"),
    ("Acompanhamento dos agentes", "banco_agentes.html"),
    ("Teto de custo com agentes", "banco_teto_da_ia.html"),
]


def html_a_vista(nome_da_pagina: str) -> str:
    """O HTML que o navegador desenha: sem os comentários e sem as caixas <template>."""
    # Lê o arquivo da página, do jeito que o servidor entrega
    html = (PASTA_DO_FRONT / nome_da_pagina).read_text(encoding="utf-8")
    # Tira os comentários e depois as caixas, que não aparecem na tela
    return PADRAO_DA_CAIXA.sub("", PADRAO_DO_COMENTARIO.sub("", html))


def telas_do_banco_com_o_menu() -> list[str]:
    """As páginas do banco que têm o menu Sistema, em ordem alfabética."""
    nomes = []
    # Cada página do banco; entra a que tem o menu da engrenagem
    for pagina in sorted(PASTA_DO_FRONT.glob("banco_*.html")):
        if "data-menu-configuracao" in pagina.read_text(encoding="utf-8"):
            nomes.append(pagina.name)
    return nomes


def itens_do_menu(nome_da_pagina: str) -> list[tuple[str, str, str]]:
    """Os itens à vista do menu Sistema de uma página: (texto, endereço, o resto da tag), na ordem."""
    # A lista do menu, no HTML à vista
    lista = PADRAO_DA_LISTA_DO_MENU.search(html_a_vista(nome_da_pagina))
    assert lista is not None, nome_da_pagina
    itens = []
    # Cada item da lista, na ordem da página
    for achado in PADRAO_DO_ITEM.finditer(lista.group(1)):
        itens.append((achado.group(3), achado.group(1), achado.group(2)))
    return itens


@pytest.mark.parametrize("nome_da_pagina", telas_do_banco_com_o_menu())
def test_o_menu_sistema_tem_as_3_telas_na_ordem(nome_da_pagina):
    """Em toda tela do banco, o menu Sistema mostra as 3 telas, na ordem, sem as Premissas financeiras."""
    # Só o texto e o endereço de cada item
    encontrados = []
    for texto, endereco, _resto_da_tag in itens_do_menu(nome_da_pagina):
        encontrados.append((texto, endereco))
    assert encontrados == ITENS_DO_SISTEMA


def test_na_tela_do_teto_so_o_item_dela_fica_marcado():
    """Na tela do Teto, o item "Teto de custo com agentes" leva aria-current="page", e nenhum outro."""
    # Os itens marcados como a tela atual
    marcados = []
    for texto, _endereco, resto_da_tag in itens_do_menu("banco_teto_da_ia.html"):
        if 'aria-current="page"' in resto_da_tag:
            marcados.append(texto)
    assert marcados == ["Teto de custo com agentes"]


@pytest.mark.parametrize("nome_da_pagina", ["banco_inicio.html", "banco_parametros.html", "banco_agentes.html"])
def test_fora_da_tela_do_teto_o_item_dele_nao_fica_marcado(nome_da_pagina):
    """Nas outras telas, o item do Teto aparece sem a marca de tela atual."""
    # O resto da tag do item do Teto, na página
    for texto, _endereco, resto_da_tag in itens_do_menu(nome_da_pagina):
        if texto == "Teto de custo com agentes":
            assert "aria-current" not in resto_da_tag
