"""Testes do nome de quem atende a empresa no banco: nas telas, é sempre o "especialista", nunca o "gerente".

Lê o que as telas podem mostrar, sem navegador: o HTML de cada página, sem os comentários, e os scripts do front (os
textos que eles escrevem na tela estão neles). A única exceção é o "gerente dedicado": um benefício do catálogo de cada
empresa (o atendimento do banco), e não o especialista.
"""
import re

import pytest

from api.principal import PASTA_DO_FRONT

# Um comentário do HTML inteiro (<!-- ... -->). O "?" pega o menor pedaço; re.DOTALL deixa o "." passar de linha
PADRAO_DO_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
# "gerente" ou "gerentes", em maiúscula ou minúscula, que não seja o benefício "gerente dedicado"
PADRAO_DO_GERENTE = re.compile(r"\bgerentes?\b(?! dedicad)", re.IGNORECASE)

# As páginas da empresa com o rodapé que guarda, oculto (ADR-148), o link para falar com o especialista
PAGINAS_COM_O_RODAPE_DA_EMPRESA = ["home.html", "acompanhar.html", "beneficios.html", "endomarketing.html"]


def paginas_e_scripts_do_front() -> list[str]:
    """Os HTML do front e os scripts de front/js, com o caminho a partir da pasta do front (ex.: "js/login.js")."""
    caminhos = []
    # Cada página do front
    for arquivo in sorted(PASTA_DO_FRONT.glob("*.html")):
        caminhos.append(arquivo.name)
    # Cada script do front
    for arquivo in sorted((PASTA_DO_FRONT / "js").glob("*.js")):
        caminhos.append("js/" + arquivo.name)
    return caminhos


def texto_que_a_tela_pode_mostrar(caminho: str) -> str:
    """O HTML sem os comentários (que não aparecem na tela), ou o script inteiro."""
    # Lê o arquivo, do jeito que o servidor entrega
    texto = (PASTA_DO_FRONT / caminho).read_text(encoding="utf-8")
    # Numa página, tira os comentários
    if caminho.endswith(".html"):
        return PADRAO_DO_COMENTARIO.sub("", texto)
    return texto


@pytest.mark.parametrize("caminho", paginas_e_scripts_do_front())
def test_nenhuma_tela_chama_o_especialista_de_gerente(caminho):
    """Nenhuma página nem script do front diz "gerente" (a não ser o benefício "gerente dedicado")."""
    # Cada "gerente" que sobrou no que a tela pode mostrar
    achados = PADRAO_DO_GERENTE.findall(texto_que_a_tela_pode_mostrar(caminho))
    assert achados == []


@pytest.mark.parametrize("pagina", PAGINAS_COM_O_RODAPE_DA_EMPRESA)
def test_o_rodape_da_empresa_guarda_o_especialista_oculto(pagina):
    """O link "Fale com seu especialista" do rodapé das telas da empresa fica oculto nesta versão (ADR-148), guardado
    num <template> (que não aparece na tela), e continua dizendo "especialista" para quando voltar."""
    assert ('<template data-oculto-nesta-versao="fale-com-seu-especialista"><a href="#">Fale com seu especialista</a>'
            '</template>') in texto_que_a_tela_pode_mostrar(pagina)


def test_o_login_diz_que_o_usuario_vem_do_especialista():
    """No login, o usuário é criado pelo especialista, e o primeiro acesso começa com ele."""
    # O que a tela de login mostra
    login = texto_que_a_tela_pode_mostrar("login.html")
    assert "Entre com o usuário criado pelo seu especialista." in login
    # O primeiro acesso e a senha esquecida levam ao especialista do banco da empresa (a quebra de linha do HTML vira
    # um espaço só, como na tela)
    login_em_uma_linha = " ".join(login.split())
    assert ('Primeiro acesso ou esqueceu a senha? <a href="#" class="link-simples">Fale com o especialista do banco '
            "que cuida do relacionamento com a sua empresa.</a>") in login_em_uma_linha
