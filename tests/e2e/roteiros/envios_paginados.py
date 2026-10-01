"""Roteiro: a lista de envios em Acompanhar, paginada no servidor (ADR-86).

O que ele confere:
- com 7 envios, a tela mostra os 5 mais recentes e "Mostrando 5 de 7 envios";
- "Mostrar mais envios" busca os 2 que faltam, e o botão some.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Envios paginados: 5 por vez, buscados no servidor"
# Quantos envios a empresa tem no roteiro
QUANTIDADE_DE_ENVIOS = 7


def preparar() -> dict:
    """A Aurora com 7 envios, cada um com um arquivo pequeno diferente (sem passar pela IA)."""
    from datetime import date

    from services import auth, processamentos
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    for numero in range(QUANTIDADE_DE_ENVIOS):
        # Arquivos diferentes: o mesmo arquivo de novo seria o mesmo envio
        conteudo = ("Nome;Cargo\nPessoa " + str(numero) + ";Analista\n").encode("utf-8")
        processamentos.receber_arquivo(conexao, conteudo, "lista_" + str(numero) + ".csv", "EMP001",
                                       date(2026, 9, 1), LOGIN_DA_EMPRESA)
    conexao.close()
    return {}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na lista de envios de Acompanhar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    aba.wait_for_function("() => document.querySelector('[data-contador-envios]').innerText.includes('de 7 envios')",
                          timeout=20000)
    conferir("mostra 5 de 7 envios", aba.inner_text("[data-contador-envios]") == "Mostrando 5 de 7 envios"
             and aba.locator("[data-lista-envios] [data-envio]").count() == 5)
    conferir("o botão 'Mostrar mais envios' aparece", aba.locator("[data-mostrar-mais-envios]").is_visible())
    aba.click("[data-mostrar-mais-envios]")
    aba.wait_for_function("() => document.querySelectorAll('[data-lista-envios] [data-envio]').length === 7", timeout=15000)
    conferir("depois do clique: 7 de 7, sem o botão",
             aba.inner_text("[data-contador-envios]") == "Mostrando 7 de 7 envios"
             and aba.locator("[data-mostrar-mais-envios]").is_hidden())
    aba.close()
