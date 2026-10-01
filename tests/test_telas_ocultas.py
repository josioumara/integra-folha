"""Testes das telas ocultas nesta versão (ADR-148) e do nome "Sistema" no menu do banco, lendo o HTML das páginas,
sem navegador.

O que fica oculto continua no HTML, para voltar rápido numa evolução:
    - dentro de uma caixa <template data-oculto-nesta-versao="..."> (o navegador guarda o que está dentro sem desenhar
      nem rodar): o item "Premissas financeiras" do menu, as guias e o Simulador de Rentabilidade, o link e o script
      dele;
    - com "hidden": o cartão do falso não folha recuperado (o js/banco_planejamento.js continua escrevendo nele).
Estes testes tiram os comentários e as caixas do HTML e conferem que, no que sobra, nada das telas ocultas aparece; e
que as caixas continuam lá (o código fica). Os roteiros de clique (menu_do_portal_interno, painel_de_indicadores e
premissas_financeiras) conferem o mesmo no Chrome.
"""
import re

import pytest

from api.principal import PASTA_DO_FRONT

# Um comentário do HTML inteiro (<!-- ... -->). O "?" pega o menor pedaço; re.DOTALL deixa o "." passar de linha
PADRAO_DO_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
# Uma caixa <template ...>...</template> inteira (as caixas deste projeto não têm outra caixa dentro)
PADRAO_DA_CAIXA = re.compile(r"<template\b[^>]*>.*?</template>", re.DOTALL)


def html_da_pagina(nome_da_pagina: str) -> str:
    """O HTML de uma página do front, sem os comentários (que falam das telas ocultas, mas não aparecem)."""
    texto = (PASTA_DO_FRONT / nome_da_pagina).read_text(encoding="utf-8")
    return PADRAO_DO_COMENTARIO.sub("", texto)


def html_a_vista(nome_da_pagina: str) -> str:
    """O HTML que o navegador desenha: sem os comentários e sem as caixas <template>."""
    return PADRAO_DA_CAIXA.sub("", html_da_pagina(nome_da_pagina))


def telas_do_banco_com_o_menu() -> list[str]:
    """As páginas do banco que têm o menu da engrenagem, em ordem alfabética (a banco_beneficios.html é só um desvio)."""
    nomes = []
    for pagina in sorted(PASTA_DO_FRONT.glob("banco_*.html")):
        if "data-menu-configuracao" in pagina.read_text(encoding="utf-8"):
            nomes.append(pagina.name)
    return nomes


def test_todas_as_telas_do_banco_com_o_menu_entram_no_teste():
    """As 9 telas do banco com o menu (as 5 abas, as 2 do Sistema, o Teto da IA e a das Premissas, oculta)."""
    assert len(telas_do_banco_com_o_menu()) == 9


@pytest.mark.parametrize("nome_da_pagina", telas_do_banco_com_o_menu())
def test_o_botao_da_engrenagem_diz_sistema(nome_da_pagina):
    """O botão "Configuração" virou "Sistema", com o desenho da engrenagem (o leitor de tela lê o mesmo nome)."""
    html = html_a_vista(nome_da_pagina)
    assert 'aria-label="Sistema"' in html
    assert '<span class="botao-configuracao-texto">Sistema</span>' in html
    assert '<use href="#icone-configuracao"/>' in html and 'id="icone-configuracao"' in html
    assert 'aria-label="Configuração"' not in html and ">Configuração</span>" not in html


def test_o_nome_sistema_tambem_nos_titulos_das_telas_do_sistema():
    """O nome do menu mudou também nos títulos: o título e a aba do navegador dos
    Parâmetros do layout, e o sobretítulo do Acompanhamento dos agentes e do Teto de gasto da IA."""
    parametros = html_a_vista("banco_parametros.html")
    assert "<title>Sistema | Portal Interno</title>" in parametros
    assert re.search(r'<h1 class="titulo-pagina">\s*Sistema\s*<span', parametros) is not None
    assert '<span class="sobretitulo">Sistema</span>' in html_a_vista("banco_agentes.html")
    assert ">Sistema › Acompanhamento dos agentes</a>" in html_a_vista("banco_teto_da_ia.html")


@pytest.mark.parametrize("nome_da_pagina", telas_do_banco_com_o_menu())
def test_nenhum_link_a_vista_leva_as_telas_ocultas(nome_da_pagina):
    """Nenhum link à vista leva às Premissas financeiras nem ao Simulador; o item das Premissas continua na caixa."""
    html = html_a_vista(nome_da_pagina)
    assert 'href="banco_premissas.html"' not in html
    assert "aba=simulador" not in html
    # O item do menu continua no HTML, dentro da caixa (o código fica, ADR-148)
    assert '<template data-oculto-nesta-versao="premissas">' in html_da_pagina(nome_da_pagina)


def test_indicadores_sem_guias_sem_simulador_e_sem_o_cartao_do_falso_nao_folha():
    """Nos Indicadores, à vista: nem as guias, nem o simulador, nem o script dele; o cartão do falso não folha com
    "hidden". Dentro das caixas, o simulador continua inteiro."""
    html = html_a_vista("banco_indicadores.html")
    assert "data-aba-indicadores" not in html
    assert 'id="guia-simulador"' not in html and "data-simulador" not in html
    assert "simulador_de_rentabilidade.js" not in html
    assert "data-ir-para-simulador" not in html
    # O cartão do falso não folha: continua na página, com "hidden"
    cartao = re.search(r'<div class="cartao[^"]*"[^>]*data-oculto-nesta-versao="falso-nao-folha"[^>]*>', html)
    assert cartao is not None and " hidden " in cartao.group(0)
    # O que está nas caixas: as guias, o simulador inteiro e o script (o código fica, ADR-148)
    html_inteiro = html_da_pagina("banco_indicadores.html")
    assert html_inteiro.count('<template data-oculto-nesta-versao="simulador">') == 4
    assert 'id="guia-simulador"' in html_inteiro and "simulador_de_rentabilidade.js" in html_inteiro


def test_o_codigo_das_telas_ocultas_continua_no_projeto():
    """O código fica e sai numa evolução (ADR-148): a página e o script das Premissas e o script do Simulador."""
    for arquivo in ["banco_premissas.html", "js/banco_premissas.js", "js/simulador_de_rentabilidade.js"]:
        assert (PASTA_DO_FRONT / arquivo).exists(), arquivo
