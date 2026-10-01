"""Roteiro: a navegação do Portal Empresa (ADR-74).

O que ele confere:
- em todas as páginas: o botão "Cadastrar funcionários" no canto, sem a aba no menu, e o ícone de conversa;
- "Materiais de endomarketing": a empresa só baixa o que o Santander publicou (ADR-115): a página mostra o recado
  do Santander, a lista (ou o aviso de lista vazia), sem erro e sem nenhum botão de criar ou gerar material;
- o chat abre pelo ícone do cabeçalho;
- o botão abre a janela do envio (sem o cabeçalho do portal dentro); aceitar as colunas leva a Acompanhar;
- no segundo clique, a janela vem do zero; o mesmo arquivo de novo avisa e oferece ver o envio.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, abrir_janela_de_cadastro, entrar

DESCRICAO = "Navegação: botão em todas as páginas, materiais para divulgar, janela do envio, chat e arquivo repetido"
# As páginas do Portal Empresa
PAGINAS_DA_EMPRESA = ("home.html", "acompanhar.html", "beneficios.html", "endomarketing.html")
# A página de materiais terminou de carregar: aparece a lista, o aviso de lista vazia ou o aviso de erro
MATERIAIS_CARREGADOS = ("[data-lista-materiais] article, [data-sem-materiais]:not([hidden]), "
                        "[data-erro-materiais]:not([hidden])")


def preparar() -> dict:
    """Os usuários de teste e o Word de exemplo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {"word": criar_word_de_exemplo()}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques pelas páginas da empresa e pela janela do envio."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # 1. Em todas as páginas: o botão do canto, sem a aba no menu, com o ícone de conversa
    for nome in PAGINAS_DA_EMPRESA:
        aba.goto(endereco + "/" + nome)
        aba.locator(".botao-cadastrar-funcionarios").wait_for(timeout=15000)
        conferir(nome + ": botão no canto, sem a aba no menu, com o ícone de conversa",
                 "Cadastrar funcionários" in aba.inner_text(".assistente-flutuante")
                 and "Cadastrar funcionários" not in aba.inner_text(".abas-portal")
                 and aba.locator(".acoes-usuario .botao-conversa").count() == 1)
    # 2. Materiais para divulgar: só baixar o que o Santander publicou (ADR-115)
    aba.goto(endereco + "/endomarketing.html")
    aba.locator(MATERIAIS_CARREGADOS).first.wait_for(timeout=15000)
    conferir("materiais: o recado do Santander no alto, sem erro ao carregar",
             "não altere valores" in aba.inner_text("[data-recado-santander]")
             and aba.locator("[data-erro-materiais]").is_hidden())
    # Lista vazia: o aviso claro; com materiais: um cartão com "Copiar texto" e "Baixar texto"
    cartoes = aba.locator("[data-lista-materiais] article")
    if cartoes.count() == 0:
        conferir("materiais: sem publicação, o aviso de que o Santander ainda não publicou",
                 "ainda não publicou materiais" in aba.inner_text("[data-sem-materiais]"))
    else:
        conferir("materiais: cada cartão com 'Copiar texto' e 'Baixar texto'",
                 cartoes.first.locator("button", has_text="Copiar texto").count() == 1
                 and cartoes.first.locator("button", has_text="Baixar texto").count() == 1)
    # Nada de criar, gerar, aprovar ou descartar material na tela da empresa
    texto_da_pagina = aba.inner_text("main")
    conferir("materiais: nenhum botão de criar, gerar, aprovar ou descartar",
             aba.locator("[data-gerar-material], [data-aprovar-material], [data-descartar-material]").count() == 0
             and "Gerar rascunho" not in texto_da_pagina and "Criar material" not in texto_da_pagina)
    # 3. O chat abre pelo ícone do cabeçalho
    aba.goto(endereco + "/home.html")
    aba.click(".botao-conversa")
    conferir("chat abre pelo ícone do cabeçalho", aba.locator(".painel-conversa").is_visible())
    aba.keyboard.press("Escape")
    # 4. O botão abre a janela com a tela de envio; aceitar as colunas leva a Acompanhar
    quadro = abrir_janela_de_cadastro(aba)
    conferir("janela aberta, sem o cabeçalho do portal dentro",
             quadro.locator(".barra-topo").count() == 1 and not quadro.locator(".barra-topo").is_visible())
    quadro.locator("#campo-arquivo").set_input_files(dados["word"])
    quadro.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    quadro.locator("[data-real-aceitar]").click()
    aba.wait_for_url("**/acompanhar.html?envio=*", timeout=60000)
    aba.locator("[data-aviso-recebido]").wait_for(timeout=10000)
    conferir("aceitar leva a Acompanhar com o recado 'Colunas aceitas'",
             "aviso=colunas_aceitas" in aba.url and "Colunas aceitas" in aba.inner_text("[data-aviso-recebido-texto]"))
    # 5. Clicar de novo: a janela vem do zero
    quadro = abrir_janela_de_cadastro(aba)
    conferir("janela do zero no segundo clique",
             quadro.locator("#etapa-envio").is_visible() and quadro.locator("#resultado-real").is_hidden())
    # 6. O mesmo arquivo de novo: avisa e oferece ver o envio
    quadro.locator("#campo-arquivo").set_input_files(dados["word"])
    quadro.locator("#conversa-ia >> text=Ver em Acompanhar cadastros").wait_for(timeout=60000)
    conferir("mesmo arquivo: avisa que já foi enviado e não segue",
             "já foi enviado" in quadro.locator("#conversa-ia").inner_text()
             and quadro.locator("#resultado-real").is_hidden())
    quadro.locator("#conversa-ia >> text=Ver em Acompanhar cadastros").click()
    aba.wait_for_url("**aviso=ja_enviado", timeout=15000)
    conferir("o botão leva a Acompanhar com o recado de arquivo repetido",
             "já tinha sido enviado" in aba.inner_text("[data-aviso-recebido-texto]"))
    aba.close()
