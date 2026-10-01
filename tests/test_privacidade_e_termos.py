"""Testes das páginas "Privacidade e LGPD" e "Termos de uso" e dos links que levam a elas.

As duas páginas abrem SEM login (api/principal.py, ENDERECOS_PUBLICOS): são só texto, sem dado nenhum, para a pessoa
ler antes de entrar. No rodapé das telas da empresa, "Central de ajuda" e "Fale com seu especialista" ficam ocultos
(ADR-148), e "Privacidade e LGPD" e "Termos de uso" abrem as páginas. No Início do banco, "Manual do especialista" e
"Suporte interno" ficam ocultos, e "Política de sigilo e LGPD" abre a privacidade. O painel do login também leva às
duas páginas.
Usa o TestClient do FastAPI (um navegador de mentira, sem ligar servidor) e lê o HTML das telas, sem navegador.
O banco é o temporário dos testes (tests/conftest.py).
"""
import re

import pytest
from fastapi.testclient import TestClient

from api.principal import ENDERECOS_PUBLICOS, PASTA_DO_FRONT, aplicacao
from models.contratos import Perfil
from services import auth

# Senha dos usuários deste arquivo (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"

# As duas páginas de texto e o título que cada uma mostra
PAGINAS_DE_TEXTO = {"privacidade.html": "Privacidade e LGPD", "termos_de_uso.html": "Termos de uso"}

# As telas da empresa com o rodapé de links
TELAS_COM_O_RODAPE_DA_EMPRESA = ["home.html", "acompanhar.html", "beneficios.html", "endomarketing.html"]

# Um comentário do HTML inteiro (<!-- ... -->). O "?" pega o menor pedaço; re.DOTALL deixa o "." passar de linha
PADRAO_DO_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
# Um bloco <template> inteiro: o que ele guarda não aparece na tela
PADRAO_DO_TEMPLATE = re.compile(r"<template\b.*?</template>", re.DOTALL)
# O bloco de links do rodapé (o que fica dentro do <nav class="rodape-links">)
PADRAO_DOS_LINKS_DO_RODAPE = re.compile(r'<nav class="rodape-links"[^>]*>(.*?)</nav>', re.DOTALL)
# Um link: o endereço e o texto (ex.: <a href="privacidade.html">Privacidade e LGPD</a>)
PADRAO_DO_LINK = re.compile(r'<a href="([^"]*)"[^>]*>([^<]*)</a>')
# O endereço de cada script da página (ex.: <script src="js/voltar.js"></script>)
PADRAO_DO_SCRIPT = re.compile(r'<script src="([^"]+)"')


@pytest.fixture(scope="module", autouse=True)
def usuarios_de_teste():
    """Cadastra um usuário de cada perfil no banco temporário dos testes, uma vez para este arquivo."""
    # Abre o banco temporário dos testes
    conexao = auth.conectar()
    # O RH de uma empresa e o especialista do banco
    auth.cadastrar_usuario(conexao, "textos.empresa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "textos.banco", SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()


def navegador_logado(login: str) -> TestClient:
    """Um navegador de mentira já logado com o usuário informado (sem seguir os desvios do porteiro)."""
    # Navegador novo, sem cookies; follow_redirects=False para o teste enxergar os desvios do porteiro
    navegador = TestClient(aplicacao, follow_redirects=False)
    # Entra; o login precisa ter dado certo para o teste seguir
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200
    return navegador


def html_sem_comentarios(nome_da_tela: str) -> str:
    """O HTML da tela sem os comentários (que não aparecem na tela)."""
    # Lê o arquivo do jeito que o servidor entrega
    texto = (PASTA_DO_FRONT / nome_da_tela).read_text(encoding="utf-8")
    return PADRAO_DO_COMENTARIO.sub("", texto)


def links_do_rodape(nome_da_tela: str) -> str:
    """O HTML de dentro do bloco de links do rodapé da tela (sem os comentários)."""
    # O bloco de links; toda tela com rodapé de links tem um
    achado = PADRAO_DOS_LINKS_DO_RODAPE.search(html_sem_comentarios(nome_da_tela))
    assert achado is not None, nome_da_tela
    return achado.group(1)


# ---------------- As páginas abrem sem login ----------------

@pytest.mark.parametrize("pagina", sorted(PAGINAS_DE_TEXTO))
def test_a_pagina_de_texto_abre_sem_login(pagina):
    """Quem ainda não entrou lê a página: o porteiro não manda para o login."""
    # Navegador sem login nenhum
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.get("/" + pagina)
    assert resposta.status_code == 200
    # É a página certa: o título dela aparece
    assert "<h1>" + PAGINAS_DE_TEXTO[pagina] + "</h1>" in resposta.text


@pytest.mark.parametrize("login", ["textos.empresa", "textos.banco"])
def test_as_paginas_de_texto_abrem_para_os_dois_perfis(login):
    """Logado, qualquer perfil lê as duas páginas: elas não são de um portal só."""
    navegador = navegador_logado(login)
    for pagina in PAGINAS_DE_TEXTO:
        assert navegador.get("/" + pagina).status_code == 200, pagina


def test_as_paginas_de_texto_estao_na_lista_publica_do_porteiro():
    """As duas páginas estão na lista de liberação do porteiro, pelo endereço exato."""
    for pagina in PAGINAS_DE_TEXTO:
        assert "/" + pagina in ENDERECOS_PUBLICOS


def test_uma_variacao_do_endereco_continua_pedindo_login():
    """A lista de liberação vale só para o endereço exato: uma variação (que o Windows abriria) pede login."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.get("/PRIVACIDADE.HTML")
    # Sem login, o porteiro manda para a tela de login
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login.html"


# ---------------- O que as páginas mostram ----------------

@pytest.mark.parametrize("pagina", sorted(PAGINAS_DE_TEXTO))
def test_a_pagina_de_texto_nao_cita_o_banco_parceiro(pagina):
    """Como a tela de login, uma página aberta sem login não cita o nome do banco parceiro."""
    assert "santander" not in html_sem_comentarios(pagina).lower()


@pytest.mark.parametrize("pagina", sorted(PAGINAS_DE_TEXTO))
def test_a_pagina_de_texto_so_carrega_scripts_sem_dado(pagina):
    """A página só carrega o "Voltar" e a data da versão: nenhum script que peça dado de empresa ou de pessoa."""
    assert PADRAO_DO_SCRIPT.findall(html_sem_comentarios(pagina)) == ["js/voltar.js", "js/data_da_versao.js"]


@pytest.mark.parametrize("pagina", sorted(PAGINAS_DE_TEXTO))
def test_o_voltar_sem_tela_anterior_leva_ao_login(pagina):
    """O "Voltar" aponta para o login: é para lá que vai quem abriu o endereço direto (js/voltar.js)."""
    assert '<a href="login.html" class="link-simples" data-voltar>Voltar</a>' in html_sem_comentarios(pagina)


def test_uma_pagina_de_texto_leva_a_outra():
    """A privacidade aponta para os termos, e os termos, para a privacidade."""
    assert 'href="termos_de_uso.html"' in html_sem_comentarios("privacidade.html")
    assert 'href="privacidade.html"' in html_sem_comentarios("termos_de_uso.html")


# ---------------- O rodapé das telas da empresa ----------------

@pytest.mark.parametrize("tela", TELAS_COM_O_RODAPE_DA_EMPRESA)
def test_o_rodape_da_empresa_mostra_so_privacidade_e_termos(tela):
    """Na tela, o rodapé mostra só os dois links, e cada um abre a sua página."""
    # O que aparece: o bloco de links sem o que está guardado nos <template>
    visivel = PADRAO_DO_TEMPLATE.sub("", links_do_rodape(tela))
    assert PADRAO_DO_LINK.findall(visivel) == [("privacidade.html", "Privacidade e LGPD"),
                                               ("termos_de_uso.html", "Termos de uso")]


@pytest.mark.parametrize("tela", TELAS_COM_O_RODAPE_DA_EMPRESA)
def test_o_rodape_da_empresa_guarda_os_dois_links_ocultos(tela):
    """"Central de ajuda" e "Fale com seu especialista" ficam guardados, ocultos (ADR-148), e não apagados."""
    # O que está guardado nos <template> do rodapé
    ocultos = PADRAO_DO_TEMPLATE.findall(links_do_rodape(tela))
    assert len(ocultos) == 2
    # Os dois com a marca de oculto nesta versão, cada um com o seu link
    assert 'data-oculto-nesta-versao="central-de-ajuda"' in ocultos[0] and "Central de ajuda" in ocultos[0]
    assert ('data-oculto-nesta-versao="fale-com-seu-especialista"' in ocultos[1]
            and "Fale com seu especialista" in ocultos[1])


# ---------------- A tela de login e o rodapé do Início do banco ----------------

def test_o_login_leva_as_duas_paginas_de_texto():
    """No rodapé do painel do login, logo abaixo do aviso de projeto, os links das duas páginas (que abrem sem login)."""
    links = PADRAO_DO_LINK.findall(html_sem_comentarios("login.html"))
    assert ("privacidade.html", "Privacidade e LGPD") in links
    assert ("termos_de_uso.html", "Termos de uso") in links


def test_o_rodape_do_inicio_do_banco_mostra_so_a_politica_de_sigilo():
    """No Início do banco, o rodapé mostra só "Política de sigilo e LGPD", que abre a página de privacidade."""
    # O que aparece: o bloco de links sem o que está guardado nos <template>
    visivel = PADRAO_DO_TEMPLATE.sub("", links_do_rodape("banco_inicio.html"))
    assert PADRAO_DO_LINK.findall(visivel) == [("privacidade.html", "Política de sigilo e LGPD")]


def test_o_rodape_do_inicio_do_banco_guarda_os_dois_links_ocultos():
    """"Manual do especialista" e "Suporte interno" ficam guardados, ocultos (ADR-148), e não apagados."""
    ocultos = PADRAO_DO_TEMPLATE.findall(links_do_rodape("banco_inicio.html"))
    assert len(ocultos) == 2
    assert 'data-oculto-nesta-versao="manual-do-especialista"' in ocultos[0] and "Manual do especialista" in ocultos[0]
    assert 'data-oculto-nesta-versao="suporte-interno"' in ocultos[1] and "Suporte interno" in ocultos[1]
