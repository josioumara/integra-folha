"""Roteiro: "Preencher para todos" (ADR-83). O campo que o arquivo não traz, informado uma vez.

A pendência se resolve conversando com a IA. O que ele confere:
- o envio sem a coluna do CNPJ do empregador mostra o cartão "Arquivo inteiro", com a conversa; a empresa escreve
  na caixa o valor para todos (sem resposta rápida);
- um valor que não serve (ex.: "123") é explicado na conversa, e nada muda;
- o CNPJ certo faz o cartão sumir.
Desde o ADR-138, a conversa do cartão abre no painel do lado: o roteiro abre o cartão e usa o painel.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = "Preencher para todos: o CNPJ que o arquivo não traz, informado uma vez na conversa com a IA"


def preparar() -> dict:
    """Aurora com a coluna do CNPJ do empregador ignorada no aceite (como um Word que não fala do CNPJ)."""
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro, mapeamentos
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import ENVIOS, _escolhas_do_gabarito, _gabarito, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    gabarito = _gabarito("aurora_carga_inicial")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, gabarito["arquivo"],
                                      busca=busca_falsa)
    # A coluna do CNPJ do empregador fica de fora no aceite
    escolhas = _escolhas_do_gabarito(gabarito)
    for coluna, campo in gabarito["mapeamento"].items():
        if campo == "cnpj_empregador":
            escolhas[coluna] = mapeamentos.IGNORAR
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], escolhas,
                                busca=busca_falsa)
    conexao.close()
    return {}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques em Acompanhar: valor errado, depois o certo."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    cartao_da_lista = aba.locator("[data-pendencia]", has_text="Arquivo inteiro").first
    cartao_da_lista.wait_for(timeout=20000)
    # A conversa do cartão, no painel do lado (ADR-138)
    cartao = abrir_a_conversa(aba, cartao_da_lista)
    conferir("cartão do arquivo inteiro, com a conversa", cartao.locator(".conversa-ia-pendencia").count() == 1)
    conferir("sem a resposta rápida 'O valor para todos é'",
             cartao.locator("[data-sugestao-da-conversa]", has_text="O valor para todos").count() == 0)
    caixa = cartao.locator("[data-caixa-da-conversa]")
    # Valor que não serve: a conversa explica, e nada muda
    caixa.fill("O valor para todos é: 123")
    cartao.locator("button[type=submit]").click()
    cartao.locator(".balao-voce").first.wait_for(timeout=20000)
    aba.wait_for_function("() => !document.querySelector('[data-contador-processando]')", timeout=20000)
    resposta = cartao.locator(".fala-ia").last.inner_text()
    conferir("valor que não serve é explicado na conversa (" + resposta[:60] + ")",
             cartao.locator(".mudanca-da-ia").count() == 0)
    # O CNPJ certo: o cartão fica verde, com o que mudou no chat, e sai das abertas
    cartao.locator("[data-caixa-da-conversa]").fill("O valor para todos é: 10.433.218/0001-93")
    cartao.locator("button[type=submit]").click()
    resolvido = aba.locator("[data-resolvido-a-vista]", has_text="Arquivo inteiro")
    resolvido.wait_for(timeout=30000)
    cartao.locator(".mudanca-da-ia").last.wait_for(timeout=30000)
    conferir("depois de preencher, o cartão fica verde com o 'Pronto: ...' e sai das abertas",
             "Pronto:" in cartao.locator(".mudanca-da-ia").last.inner_text()
             and aba.locator("[data-pendencia]:not([data-resolvido-a-vista])", has_text="Arquivo inteiro").count() == 0)
    aba.close()
