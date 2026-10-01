"""Roteiro: o CNPJ do grupo (ADR-77). A empresa confirma uma vez; o banco vê e cadastra filiais.

O que ele confere:
- dois funcionários com o mesmo CNPJ fora do cadastro viram dois cartões "É de uma empresa do seu grupo?";
- "Sim, é do nosso grupo" (a resposta rápida da conversa com a IA) em um só tira os dois;
- no Portal Interno, a ficha da Aurora mostra o CNPJ registrado pela empresa, aceita uma filial, recusa um CNPJ
  com os dígitos errados e tira a filial com dois cliques.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = "CNPJ do grupo: a empresa confirma uma vez; o banco vê, cadastra e tira filiais"
# Uma filial válida da Aurora (mesma raiz 10433218, estabelecimento 0002)
FILIAL_DA_AURORA = "10433218000274"


def preparar() -> dict:
    """Aurora com a carga inicial enviada e as colunas aceitas; dois funcionários com o CNPJ de outra empresa.

    Devolve: {"cnpj_do_grupo": o CNPJ usado}.
    """
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import acompanhamento, auth, cadastro, correcoes
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_cnpjs_das_empresas import cnpj_de_outra_raiz
    from tests.test_correcao import ENVIOS, _escolhas_do_gabarito, _gabarito, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # O envio da Aurora, com as colunas aceitas
    gabarito = _gabarito("aurora_carga_inicial")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, gabarito["arquivo"],
                                      busca=busca_falsa)
    leitura = cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                          _escolhas_do_gabarito(gabarito), busca=busca_falsa)
    # Dois funcionários com o CNPJ de uma "empresa do grupo"
    grupo = cnpj_de_outra_raiz(5)
    registros = correcoes.dados_atuais(conexao, leitura["processamento_id"]).registros
    for registro in registros[:2]:
        acompanhamento.corrigir_pendencia(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                          registro["_linha"], "cnpj_empregador", grupo, "Empregado pelo grupo")
    conexao.close()
    return {"cnpj_do_grupo": grupo}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: primeiro a empresa (Acompanhar), depois o banco (Empresas)."""
    grupo = dados["cnpj_do_grupo"]
    # 1. A empresa: dois cartões "é do grupo?"; confirmar um tira os dois
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    # Os cartões da lista perguntam; a resposta fica na conversa, que abre no painel do lado (ADR-138)
    cartoes = aba.locator("[data-lista-pendencias] [data-pendencia]", has_text="seu grupo")
    cartoes.first.wait_for(timeout=20000)
    conferir("dois cartões perguntam se o CNPJ é do grupo (" + str(cartoes.count()) + ")", cartoes.count() == 2)
    botao = abrir_a_conversa(aba, cartoes.first).locator("button:has-text('Sim, é do nosso grupo')")
    conferir("a conversa do cartão tem 'Sim, é do nosso grupo'", botao.count() == 1)
    botao.click()
    # O cartão confirmado fica verde à vista, sem as respostas rápidas: contam só os botões
    # à vista
    aba.wait_for_function(
        "() => ![...document.querySelectorAll('button')].some(botao => botao.offsetParent !== null"
        " && botao.innerText.includes('Sim, é do nosso grupo'))",
        timeout=20000)
    abertos = aba.locator("[data-lista-pendencias] [data-pendencia]:not([data-resolvido-a-vista])", has_text="seu grupo")
    # A lista é refeita depois da resposta: espera o outro cartão sair
    abertos.first.wait_for(state="detached", timeout=20000)
    conferir("depois de confirmar um, nenhum cartão pergunta de novo", abertos.count() == 0)
    aba.close()
    # 2. O banco: o CNPJ confirmado aparece na ficha; filial entra; CNPJ errado é recusado; tirar com 2 cliques
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_empresas.html?empresa=EMP001")
    # Desde o ADR-112, a ficha abre na aba "Visão geral": os CNPJs ficam na aba "Dados", que precisa ser aberta
    aba.locator("[data-aba-ficha='dados']").click(timeout=20000)
    aba.locator("[data-bloco-cnpjs]:not([hidden])").wait_for(timeout=20000)
    linha = aba.locator("[data-corpo-cnpjs] tr[data-cnpj='" + grupo + "']")
    conferir("CNPJ confirmado pela empresa aparece na ficha",
             "A empresa, ao confirmar num envio" in linha.inner_text() and "Empresa do grupo" in linha.inner_text())
    conferir("rótulo 'Endereço da sede' na aba Dados", "Endereço da sede" in aba.inner_text("[data-campos-empresa]"))
    # CNPJ com os dígitos errados
    aba.fill("[data-cnpj-novo]", "11.111.111/1111-11")
    aba.click("[data-formulario-cnpj] button[type='submit']")
    aba.locator("[data-erro-cnpj]:not([hidden])").wait_for(timeout=10000)
    conferir("CNPJ errado recusado com o motivo", "dígitos" in aba.inner_text("[data-erro-cnpj]"))
    # Uma filial de verdade
    aba.fill("[data-cnpj-novo]", FILIAL_DA_AURORA)
    aba.select_option("[data-cnpj-tipo]", "FILIAL")
    aba.click("[data-formulario-cnpj] button[type='submit']")
    aba.locator("[data-corpo-cnpjs] tr[data-cnpj='" + FILIAL_DA_AURORA + "']").wait_for(timeout=10000)
    conferir("filial cadastrada pelo banco", "Banco" in aba.inner_text("tr[data-cnpj='" + FILIAL_DA_AURORA + "']"))
    # Tirar: o primeiro clique pede confirmação; o segundo tira
    botao = aba.locator("[data-tirar-cnpj='" + FILIAL_DA_AURORA + "']")
    botao.click()
    conferir("primeiro clique pede confirmação", "Clique de novo" in botao.inner_text())
    botao.click()
    aba.locator("tr[data-cnpj='" + FILIAL_DA_AURORA + "']").wait_for(state="detached", timeout=10000)
    conferir("filial tirada e o CNPJ do grupo continua", aba.locator("tr[data-cnpj='" + grupo + "']").count() == 1)
    aba.close()
