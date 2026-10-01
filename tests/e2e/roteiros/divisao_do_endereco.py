"""Roteiro: a coluna com o endereço inteiro já chega dividida pela IA e é refeita com o comentário (ADR-76, ADR-104).

O que ele confere:
- a planilha mostra um exemplo por coluna, inteiro (são os dados da própria empresa);
- a coluna "Endereço" chega "Dividida pela IA", com a prévia; cada parte vem logo abaixo, ligada ao campo;
- o botão "Refazer a divisão desta coluna" só liga depois do comentário;
- com o comentário "é o endereço do trabalho", a IA refaz SÓ essa coluna (as partes vão para o endereço comercial);
- o aceite com as partes dá certo.
"""
from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Divisão pela IA: coluna já dividida, prévia, comentário, refazer e aceite"


def preparar() -> dict:
    """Os usuários de teste e a planilha com o endereço inteiro numa coluna."""
    from services import auth
    from tests.e2e.apoio import criar_planilha_com_endereco, criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {"planilha": criar_planilha_com_endereco()}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na tela de envio, com a planilha."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["planilha"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    # As colunas ficam na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    corpo = aba.locator("[data-real-corpo-colunas]")
    # 1. Exemplos: o nome e o cargo aparecem inteiros (são os dados da própria empresa)
    nome = corpo.locator("tr", has=aba.locator("td:first-child", has_text="Nome")).first.inner_text()
    cargo = corpo.locator("tr", has=aba.locator("td:first-child", has_text="Cargo")).first.inner_text()
    conferir("o nome aparece inteiro", "Maria Souza" in nome)
    conferir("o cargo aparece inteiro", "Analista" in cargo)
    # 2. A coluna chega dividida pela IA, com a prévia, e a rua ligada ao endereço de casa
    linha_do_endereco = corpo.locator("tr", has=aba.locator("td:first-child", has_text="Endereço")).first
    conferir("'Endereço' chega 'Dividida pelo Agente Interpretador'",
             "Dividida pelo Agente Interpretador" in linha_do_endereco.inner_text())
    previa = aba.locator("[data-conferencia-da-divisao] .tabela-previa-divisao").inner_text()
    conferir("a prévia mostra a célula e as partes", "Rua das Flores" in previa and "SP" in previa)
    linha_da_rua = corpo.locator("tr", has=aba.locator("td:first-child", has_text="Endereço · rua")).first
    conferir("'Endereço · rua' ligada à rua de casa",
             linha_da_rua.locator("select").input_value() == "logradouro_residencial")
    # 3. O botão só liga com o comentário
    botao = aba.locator("[data-refazer-divisao]")
    conferir("sem comentário, o botão fica desligado", botao.is_disabled())
    aba.fill("[data-comentario-da-divisao]", "é o endereço do trabalho, não o de casa")
    conferir("com o comentário, o botão liga", botao.is_enabled())
    # 4. Refazer: só esta coluna muda (as partes vão para o endereço do trabalho)
    botao.click()
    aba.wait_for_function(
        "() => Array.from(document.querySelectorAll('[data-real-corpo-colunas] select'))"
        ".some(function (escolha) { return escolha.value === 'logradouro_comercial'; })", timeout=30000)
    conferir("a IA refez a divisão com o comentário", True)
    linha_do_nome = corpo.locator("tr", has=aba.locator("td:first-child", has_text="Nome")).first
    conferir("as outras colunas continuam como estavam",
             linha_do_nome.locator("select").input_value() == "nome_completo")
    # 5. O aceite com as partes
    aba.click("[data-real-aceitar]")
    aba.wait_for_function("() => !document.querySelector('[data-real-aceitar]') || "
                          "document.querySelector('[data-real-aceitar]').hidden", timeout=60000)
    conferir("o aceite com as partes deu certo", True)
    aba.close()
