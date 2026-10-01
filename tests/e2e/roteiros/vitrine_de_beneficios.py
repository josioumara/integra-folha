"""Roteiro: a vitrine "Benefícios do seu time" com as KBs publicadas da Aurora (categoria e as três partes; ADR-125).

O que ele confere:
- os 6 benefícios do catálogo viram cartões; só os filtros das categorias que o catálogo usa aparecem;
- "Ver detalhes" abre a janela com "Como funciona", "Quem pode usar" e "Como contratar" e a fonte.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Vitrine de benefícios: categorias, filtros e as três partes na janela de detalhes"


def preparar() -> dict:
    """Só os usuários de teste: o catálogo da Aurora entra sozinho no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na aba Benefícios do seu time."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/beneficios.html")
    aba.wait_for_function("() => document.querySelector('[data-grade-beneficios] [data-beneficio=\"Primeiro investimento\"]')",
                          timeout=20000)
    cartoes = aba.locator("[data-grade-beneficios] .cartao-beneficio")
    conferir("6 benefícios do catálogo na vitrine (" + str(cartoes.count()) + ")", cartoes.count() == 6)
    filtros_visiveis = aba.locator("[data-categoria-filtro]:not([hidden])")
    conferir("4 filtros: Todos e as 3 categorias do catálogo (" + str(filtros_visiveis.count()) + ")",
             filtros_visiveis.count() == 4 and aba.locator("[data-categoria-filtro='protecao']").is_hidden())
    # Filtro "Crédito": só consignado e cartão
    aba.click("[data-categoria-filtro='credito']")
    visiveis = aba.locator("[data-grade-beneficios] .cartao-beneficio:not([hidden])")
    titulos = sorted(visiveis.locator(".beneficio-titulo").all_inner_texts())
    conferir("filtro Crédito mostra consignado e cartão: " + ", ".join(titulos),
             titulos == ["Cartão de crédito com cashback", "Crédito consignado"])
    aba.click("[data-categoria-filtro='todas']")
    # A janela de detalhes com as três partes
    cartao = aba.locator("[data-grade-beneficios] [data-beneficio='Salário antecipado']")
    cartao.locator(".botao-ver-detalhes").click()
    aba.locator("#janela-beneficio[open]").wait_for(timeout=10000)
    detalhes = aba.inner_text("#janela-beneficio-detalhes")
    conferir("janela com Como funciona, Quem pode usar e Como contratar",
             "Como funciona" in detalhes and "Quem pode usar" in detalhes and "Como contratar" in detalhes)
    # A fonte é a KB do benefício (ADR-125): o título dela e a versão publicada
    conferir("janela diz de onde vem o texto", "Salário antecipado" in detalhes and "versão 1" in detalhes)
    aba.close()
