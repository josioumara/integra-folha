"""Testes das telas da empresa (Cadastrar e Acompanhar), lendo o HTML, o CSS e o JavaScript, sem navegador.

O que eles provam:
- Cadastrar: a frase das outras informações diz "entram quando nosso agente reconhece"; o resultado da leitura tem duas
  abas ("Funcionários", aberta, e "Como o agente leu"); o recado e os botões ficam fora das abas; o "Ajude o agente a
  acertar" fica oculto, com o código na página;
- Acompanhar: os 5 números numa linha (o 5º, os cadastrados ainda sem conta); o "Depois do cadastro" e os links para ele
  ocultos, com o código na página; a conversa do cartão numa janela (<dialog>); a busca por CPF e situação, com o filtro
  de unidade oculto; as ações do envio numa linha ("Descartar este envio" e "Conferir arquivo");
- a marca data-oculto-nesta-versao esconde sempre, mesmo quando um script tira o "hidden" (css/estilos.css).
Os roteiros de clique cadastrar_em_duas_abas, acompanhar_layout_e_grade e acompanhar_busca_e_envios conferem o mesmo no
Chrome.
"""
import re

from api.principal import PASTA_DO_FRONT
from tests.test_telas_ocultas import html_a_vista, html_da_pagina

# A frase das outras informações, no quadro de antes do envio (o texto que a tela mostra)
FRASE_DAS_OUTRAS_INFORMACOES = "As outras informações que vierem no arquivo entram quando nosso agente reconhece."


def sem_espacos_repetidos(texto: str) -> str:
    """O texto com cada sequência de espaços e quebras de linha trocada por um espaço só (o HTML quebra as linhas)."""
    return re.sub(r"\s+", " ", texto)


def texto_do_arquivo(caminho_no_front: str) -> str:
    """O conteúdo de um arquivo do front (ex.: "js/acompanhar.js")."""
    return (PASTA_DO_FRONT / caminho_no_front).read_text(encoding="utf-8")


def etiqueta_com(html: str, marca: str) -> str:
    """A etiqueta de abertura do elemento que tem a marca (ex.: 'data-real-bloco-ajude'), ou "" se não houver.

    A marca vem depois de um espaço (é um atributo) e não pode continuar com letra, número ou hífen (assim
    "data-real-bloco-ajude" não acha "data-real-bloco-ajude-algo").
    """
    encontrada = re.search(r"<[a-z]+\b[^>]*\s" + re.escape(marca) + r"(?![\w-])[^>]*>", html)
    if encontrada is None:
        return ""
    return sem_espacos_repetidos(encontrada.group(0))


# ---------------- Cadastrar ----------------

def test_a_frase_das_outras_informacoes():
    """O quadro de antes do envio diz que as outras informações entram quando o agente reconhece."""
    html = sem_espacos_repetidos(html_a_vista("cadastrar.html"))
    assert FRASE_DAS_OUTRAS_INFORMACOES in html
    assert "sem pergunta: elas não são obrigatórias" not in html


def test_o_resultado_tem_as_duas_abas():
    """As duas abas: "Funcionários" aberta e "Como o agente leu" fechada, cada uma com o seu conteúdo."""
    html = html_a_vista("cadastrar.html")
    aba_dos_funcionarios = etiqueta_com(html, 'data-aba-do-resultado="funcionarios"')
    aba_das_colunas = etiqueta_com(html, 'data-aba-do-resultado="colunas"')
    assert 'role="tab"' in aba_dos_funcionarios and 'aria-selected="true"' in aba_dos_funcionarios
    assert 'role="tab"' in aba_das_colunas and 'aria-selected="false"' in aba_das_colunas
    assert re.search(r'data-aba-do-resultado="funcionarios">Funcionários</button>', html) is not None
    assert re.search(r'data-aba-do-resultado="colunas">Como o agente leu</button>', html) is not None
    # O conteúdo da 1ª aba à vista; o da 2ª, escondido
    assert " hidden" not in etiqueta_com(html, 'data-painel-do-resultado="funcionarios"')
    assert " hidden" in etiqueta_com(html, 'data-painel-do-resultado="colunas"')


def test_as_colunas_e_a_conferencia_ficam_na_aba_como_o_agente_leu():
    """A tabela das colunas, os detalhes, os formatos e a conferência ficam na 2ª aba; o recado, o "Conferi a lista" e
    os botões ficam fora das abas (valem para as duas)."""
    html = html_a_vista("cadastrar.html")
    inicio_da_2a_aba = html.index('data-painel-do-resultado="colunas"')
    # Sem os comentários, o fim da 2ª aba é achado pelo "Conferi a lista", que vem logo depois dela
    fim_da_2a_aba = html.index("data-real-conferi ")
    trecho_da_2a_aba = html[inicio_da_2a_aba:fim_da_2a_aba]
    for marca in ["data-real-bloco-colunas", "data-real-bloco-detalhes", "data-real-bloco-formatos",
                  "data-real-bloco-conferencia", "data-real-resumo-leitura", "data-real-bloco-ajude"]:
        assert marca in trecho_da_2a_aba, marca
    # O recado das ações fica antes das abas; os botões, depois delas
    assert html.index("data-real-erro") < html.index("data-abas-do-resultado")
    assert html.index("data-real-aceitar") > fim_da_2a_aba


def test_o_ajude_o_agente_a_acertar_fica_oculto_com_o_codigo():
    """O bloco continua na página, com o "hidden" e a marca de oculto; o molde e o script da releitura ficam."""
    html = html_a_vista("cadastrar.html")
    bloco = etiqueta_com(html, "data-real-bloco-ajude")
    assert " hidden" in bloco and 'data-oculto-nesta-versao="ajude-o-agente"' in bloco
    assert 'id="modelo-pedido-de-releitura"' in html_da_pagina("cadastrar.html")
    assert "function montar_colunas_para_reler" in texto_do_arquivo("js/cadastrar_conferencia_real.js")


def test_a_grade_da_1a_aba_usa_a_linha_comum_das_pessoas_de_um_envio():
    """A 1ª aba e o "Conferir e enviar" de Acompanhar usam a MESMA linha (js/grade_do_parametro.js), sem cópia."""
    assert "function linha_de_pessoa_do_envio" in texto_do_arquivo("js/grade_do_parametro.js")
    assert "linha_de_pessoa_do_envio(" in texto_do_arquivo("js/cadastrar_abas.js")
    assert "linha_de_pessoa_do_envio(" in texto_do_arquivo("js/acompanhar.js")
    assert "function linha_do_envio_pronto" not in texto_do_arquivo("js/acompanhar.js")
    # A prévia vem da rota só de leitura
    assert "/previa" in texto_do_arquivo("js/cadastrar_abas.js")


# ---------------- Acompanhar ----------------

def test_os_cinco_numeros_numa_linha():
    """Os números numa linha só: 5 cartões, o 5º com os cadastrados ainda sem conta."""
    html = html_a_vista("acompanhar.html")
    inicio = html.index('<section class="grade-numeros grade-numeros-numa-linha"')
    fim = html.index("</section>", inicio)
    grade = html[inicio:fim]
    assert grade.count('class="cartao cartao-numero') == 5
    assert "data-resumo-sem-conta-valor" in grade and "data-resumo-sem-conta-legenda" in grade
    # A regra do CSS: 5 colunas no computador
    assert "grid-template-columns: repeat(5, minmax(0, 1fr));" in texto_do_arquivo("css/acompanhar_painel.css")


def test_o_depois_do_cadastro_fica_oculto_com_o_codigo():
    """O painel do lado continua na página, com o "hidden" e a marca; nenhum link à vista leva a ele."""
    html = html_a_vista("acompanhar.html")
    painel = etiqueta_com(html, "data-painel-do-lado")
    assert " hidden" in painel and 'data-oculto-nesta-versao="depois-do-cadastro"' in painel
    assert 'id="contas"' in html
    assert 'href="#contas"' not in html
    # Os dois links (o "Ir para" e o do cartão das contas) continuam na página, nas caixas
    assert html_da_pagina("acompanhar.html").count('<template data-oculto-nesta-versao="depois-do-cadastro">') == 2


def test_a_conversa_do_cartao_abre_numa_janela():
    """A conversa é um <dialog> (a janela pronta do navegador), fora do painel do lado."""
    html = html_a_vista("acompanhar.html")
    janela = etiqueta_com(html, "data-painel-da-conversa")
    assert janela.startswith("<dialog ") and 'id="conversa"' in janela
    assert "showModal()" in texto_do_arquivo("js/painel_da_conversa.js")
    assert "function preparar_a_janela_da_conversa" in texto_do_arquivo("js/painel_da_conversa.js")
    assert "preparar_a_janela_da_conversa();" in texto_do_arquivo("js/acompanhar.js")


def test_a_busca_de_funcionarios_e_por_cpf_e_situacao():
    """A caixa busca por CPF; a situação continua; o filtro de unidade fica oculto, com o código."""
    html = html_a_vista("acompanhar.html")
    busca = etiqueta_com(html, "data-busca")
    assert 'placeholder="Buscar por CPF"' in busca
    assert "data-filtro-situacao" in html
    unidade = etiqueta_com(html, "data-filtro-unidade")
    assert " hidden" in unidade and 'data-oculto-nesta-versao="filtro-de-unidade"' in unidade
    assert "Tente outro CPF" in html
    assert "function somente_os_numeros_do_texto" in texto_do_arquivo("js/acompanhar.js")


def test_as_acoes_do_envio_numa_linha():
    """No histórico: "Descartar este envio" (letra menor) e "Conferir arquivo" (discreto) na linha das ações."""
    acompanhar = texto_do_arquivo("js/acompanhar.js")
    assert 'criar("a", "link-conferir-arquivo", "Conferir arquivo")' in acompanhar
    assert 'criar("div", "acoes-do-envio", "")' in acompanhar
    assert '"botao-nome botao-descartar-envio", "Descartar este envio"' in acompanhar
    estilo = texto_do_arquivo("css/acompanhar_painel.css")
    assert ".botao-descartar-envio {\n  font-size: 12px;" in estilo
    assert ".link-conferir-arquivo {\n  margin-left: auto;" in estilo


# ---------------- A marca de oculto ----------------

def test_a_marca_de_oculto_esconde_sempre():
    """A regra geral: o que tem a marca data-oculto-nesta-versao nunca aparece, mesmo sem o "hidden"."""
    estilos = texto_do_arquivo("css/estilos.css")
    assert "[data-oculto-nesta-versao] {\n  display: none !important;\n}" in estilos
