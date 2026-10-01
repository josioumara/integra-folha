"""Roteiro: o layout de Acompanhar e a grade que mostra o valor corrigido (ADR-138).

O que ele confere (com a IA simulada, sem custo):
- o bloco de cima: os 5 números numa linha só, menores (o 5º é o dos cadastrados ainda sem conta), e a lista das
  pendências embaixo, na largura inteira; o "Depois do cadastro" e os atalhos para ele não aparecem (continuam na
  página, ocultos); o "Pronto para enviar ao banco" fica abaixo do bloco;
- os cartões da lista são compactos (sem a caixa da conversa); o clique num cartão abre a conversa numa janela por cima
  da tela, e marca o cartão;
- o CPF certo, dito na conversa da janela: o "Pronto" e o Desfazer na janela, e a grade dos funcionários com o CPF
  novo, destacado, sem recarregar a página; o Desfazer volta o CPF de antes na grade, destacado também;
- o X fecha a janela, e o foco volta ao cartão; reaberta, a mensagem não enviada continua; o Esc e o clique fora da
  janela também fecham;
- no filtro "Resolvidas", o "Ver a conversa" abre a conversa guardada na janela, só de leitura;
- no celular: os números (2 a 2) e depois a lista; a conversa abre em tela cheia, e o "Voltar à lista" fecha.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.roteiros.pendencias_por_conversa import (CPF_CERTO, CPF_ERRADO, cartao_do_cpf_errado, preparar,
                                                        somente_digitos)

DESCRICAO = "Acompanhar: os 5 números numa linha, a conversa numa janela e a grade com o valor corrigido e destacado"

# A preparação (preparar, importada acima) é a do roteiro das pendências por conversa: dois envios da Aurora com CPFs
# de dígito errado

# A largura de um celular comum (em pixels), para a parte do celular
LARGURA_DO_CELULAR = 390
ALTURA_DO_CELULAR = 844
# A janela da conversa (o <dialog> do acompanhar.html)
JANELA_DA_CONVERSA = "[data-painel-da-conversa]"
# O JavaScript que diz se a janela da conversa está aberta como janela por cima da tela (":modal")
JANELA_POR_CIMA = "() => document.querySelector('[data-painel-da-conversa]').matches(':modal')"


def caixa_de(aba, seletor: str) -> dict:
    """A posição e o tamanho de um elemento na tela: {x, y, width, height}."""
    return aba.locator(seletor).first.bounding_box()


def conferir_o_bloco_de_cima(aba, conferir) -> None:
    """Os 5 números numa linha, a lista embaixo na largura inteira e o "Depois do cadastro" oculto."""
    colunas = aba.eval_on_selector(".grade-numeros", "elemento => getComputedStyle(elemento).gridTemplateColumns")
    conferir(f"os 5 números numa linha só (na tela: {colunas})", len(colunas.split()) == 5)
    alturas_dos_cartoes = []
    for cartao in aba.locator(".grade-numeros > .cartao-numero").all():
        alturas_dos_cartoes.append(round(cartao.bounding_box()["y"]))
    conferir(f"os 5 cartões lado a lado (alturas: {alturas_dos_cartoes})",
             len(alturas_dos_cartoes) == 5 and len(set(alturas_dos_cartoes)) == 1)
    valor_do_numero = aba.eval_on_selector(".grade-numeros .cartao-numero-valor",
                                           "elemento => parseFloat(getComputedStyle(elemento).fontSize)")
    conferir(f"os números menores que o padrão de 32 px (na tela: {valor_do_numero}px)", valor_do_numero < 32)
    quinto = aba.locator("[data-resumo-sem-conta-valor]")
    conferir(f"o 5º cartão: os cadastrados ainda sem conta, sem o número de exemplo (na tela: {quinto.inner_text()})",
             quinto.is_visible() and quinto.inner_text().strip() != "69"
             and "ainda sem conta" in aba.inner_text("[data-resumo-sem-conta-legenda]"))
    numeros = caixa_de(aba, ".grade-numeros")
    pendencias = caixa_de(aba, "#pendencias")
    conferir("a lista das pendências fica embaixo dos números, na mesma largura",
             pendencias["y"] >= numeros["y"] + numeros["height"] and abs(pendencias["x"] - numeros["x"]) < 5
             and abs(pendencias["width"] - numeros["width"]) < 5)
    conferir("o 'Depois do cadastro' não aparece (continua na página, com a marca de oculto)",
             aba.locator("#contas").count() == 1 and aba.locator("#contas").is_hidden()
             and aba.locator("[data-painel-do-lado]").get_attribute("data-oculto-nesta-versao") == "depois-do-cadastro")
    conferir("nenhum link à vista leva ao 'Depois do cadastro' (o 'Ir para' e o cartão das contas)",
             aba.locator("a[href='#contas']").count() == 0)
    ordem = aba.evaluate("() => { const bloco = document.querySelector('.bloco-acompanhar');"
                         " const prontos = document.getElementById('prontos');"
                         " return Boolean(bloco.compareDocumentPosition(prontos) & Node.DOCUMENT_POSITION_FOLLOWING); }")
    conferir("o 'Pronto para enviar ao banco' fica abaixo do bloco", ordem)
    conferir("sem cartão escolhido, a janela da conversa está fechada", aba.locator(JANELA_DA_CONVERSA).is_hidden())
    conferir("os cartões da lista são compactos (sem a caixa da conversa)",
             aba.locator("[data-lista-pendencias] [data-caixa-da-conversa]").count() == 0
             and aba.locator("[data-lista-pendencias] [data-previa-da-pergunta]").count() >= 1)


def linha_da_grade(aba, nome: str):
    """A linha da grade dos funcionários com o nome da pessoa."""
    return aba.locator("[data-corpo-tabela] tr").filter(has_text=nome).first


def esperar_o_cpf_na_grade(aba, nome: str, cpf: str) -> None:
    """Espera a grade mostrar o CPF na linha da pessoa (a grade se refaz sozinha depois da mudança)."""
    aba.wait_for_function(
        "([nome, digitos]) => Array.from(document.querySelectorAll('[data-corpo-tabela] tr'))"
        ".some(linha => linha.innerText.includes(nome) && linha.innerText.replace(/\\D/g, '').includes(digitos))",
        arg=[nome, somente_digitos(cpf)], timeout=30000)


def conferir_a_conversa_na_janela_e_a_grade(aba, dados: dict, conferir) -> None:
    """Abre o cartão, corrige o CPF na janela, confere a grade e desfaz; o X, o Esc e o clique fora fecham."""
    nome = dados["primeiro"]["nomes"][0]
    cartao = cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first
    cartao.wait_for(timeout=30000)
    linha_da_grade(aba, nome).wait_for(timeout=30000)
    cartao.click()
    janela = aba.locator(JANELA_DA_CONVERSA)
    janela.wait_for(timeout=10000)
    titulo = aba.inner_text("[data-titulo-da-conversa]")
    conferir(f"o clique abre a conversa numa janela por cima da tela (título: {titulo})",
             aba.evaluate(JANELA_POR_CIMA) and nome in titulo and '"CPF"' in titulo
             and janela.locator("[data-caixa-da-conversa]").is_visible())
    conferir("o cartão escolhido fica marcado na lista",
             "ajuste-escolhido" in (cartao.get_attribute("class") or ""))
    aba.screenshot(path="storage/painel/acompanhar_layout_conversa_na_janela.png")
    # O CPF certo, na caixa da janela
    janela.locator("[data-caixa-da-conversa]").fill("O certo é " + CPF_CERTO)
    janela.locator("button[type=submit]").click()
    janela.locator("[data-desfazer-mudanca]").wait_for(timeout=30000)
    conferir("resolvida, a conversa continua na janela, com o 'Pronto' e o Desfazer",
             "Pronto:" in janela.inner_text() and janela.locator("[data-caixa-da-conversa]").is_hidden())
    esperar_o_cpf_na_grade(aba, nome, CPF_CERTO)
    destaque = linha_da_grade(aba, nome).locator("[data-celula-que-mudou='cpf']")
    conferir("a grade mostra o CPF novo, destacado, sem recarregar a página",
             destaque.count() == 1 and somente_digitos(CPF_CERTO) in somente_digitos(destaque.inner_text()))
    # O Desfazer, na janela: a pendência volta aberta, e a grade volta o CPF de antes
    janela.locator("[data-desfazer-mudanca]").first.click()
    janela.locator("[data-caixa-da-conversa]").wait_for(timeout=30000)
    esperar_o_cpf_na_grade(aba, nome, CPF_ERRADO)
    destaque = linha_da_grade(aba, nome).locator("[data-celula-que-mudou='cpf']")
    conferir("o Desfazer: a conversa volta aberta na janela, e a grade volta o CPF de antes, destacado",
             "Desfeito" in janela.inner_text() and destaque.count() == 1
             and somente_digitos(CPF_ERRADO) in somente_digitos(destaque.inner_text()))
    # Uma mensagem escrita e não enviada, e o X fecha a janela
    janela.locator("[data-caixa-da-conversa]").fill("mensagem ainda não enviada")
    janela.locator("[data-fechar-conversa]").click()
    conferir("o X fecha a janela, e nenhum cartão fica marcado",
             janela.is_hidden() and aba.locator("[data-lista-pendencias] .ajuste-escolhido").count() == 0)
    foco_no_cartao = aba.evaluate("() => document.activeElement.hasAttribute('data-abrir-conversa')"
                                  " && document.activeElement.closest('[data-pendencia]').innerText.includes("
                                  + repr(nome) + ")")
    conferir("ao fechar, o foco volta ao 'Abrir a conversa' do cartão", foco_no_cartao)
    # Aberta de novo, a mensagem não enviada continua na caixa (o rascunho fica guardado pela chave)
    cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first.locator("[data-abrir-conversa]").click()
    conferir("reaberta, a conversa traz de volta a mensagem que não foi enviada",
             janela.locator("[data-caixa-da-conversa]").input_value() == "mensagem ainda não enviada")
    janela.locator("[data-caixa-da-conversa]").fill("")
    aba.keyboard.press("Escape")
    # O navegador fecha a janela e avisa ("close") um instante depois: é o aviso que tira a marca do cartão
    aba.wait_for_function("() => !document.querySelector('[data-painel-da-conversa]').open"
                          " && !document.querySelector('[data-lista-pendencias] .ajuste-escolhido')", timeout=5000)
    conferir("o Esc também fecha a janela, e nenhum cartão fica marcado", janela.is_hidden())
    # O clique fora da janela (no fundo escurecido) também fecha
    cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first.locator("[data-abrir-conversa]").click()
    janela.wait_for(timeout=10000)
    aba.mouse.click(5, 5)
    conferir("o clique fora da janela também fecha", janela.is_hidden())


def conferir_a_resolvida_na_janela(aba, dados: dict, conferir) -> None:
    """Resolve de novo, fecha, vai para "Resolvidas" e abre a conversa guardada na janela."""
    nome = dados["primeiro"]["nomes"][0]
    cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first.click()
    janela = aba.locator(JANELA_DA_CONVERSA)
    janela.locator("[data-caixa-da-conversa]").fill("O certo é " + CPF_CERTO)
    janela.locator("button[type=submit]").click()
    janela.locator("[data-desfazer-mudanca]").wait_for(timeout=30000)
    # Com a janela por cima, a tela de trás não recebe cliques: a pessoa fecha a conversa e troca o filtro
    janela.locator("[data-fechar-conversa]").click()
    aba.click("[data-filtro-pendencia='resolvidas']")
    resolvida = aba.locator("[data-lista-resolvidas] [data-resolvida]", has_text=nome).first
    resolvida.wait_for(timeout=30000)
    resolvida.locator("[data-ver-a-conversa]").click()
    janela.wait_for(timeout=10000)
    conferir("o 'Ver a conversa' da resolvida abre a conversa guardada na janela, só de leitura",
             "O certo é" in janela.inner_text() and janela.locator("[data-caixa-da-conversa]").count() == 0
             and "ajuste-escolhido" in (resolvida.get_attribute("class") or ""))
    janela.locator("[data-fechar-conversa]").click()


def conferir_o_celular(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """No celular: os números 2 a 2 e depois a lista; a conversa em tela cheia, com o "Voltar à lista"."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.set_viewport_size({"width": LARGURA_DO_CELULAR, "height": ALTURA_DO_CELULAR})
    aba.goto(endereco + "/acompanhar.html")
    nome = dados["segundo"]["nomes"][0]
    cartao = aba.locator("[data-lista-pendencias] [data-pendencia]", has_text=nome).first
    cartao.wait_for(timeout=30000)
    colunas = aba.eval_on_selector(".grade-numeros", "elemento => getComputedStyle(elemento).gridTemplateColumns")
    conferir(f"no celular, os números 2 a 2 (na tela: {colunas})", len(colunas.split()) == 2)
    numeros = caixa_de(aba, ".grade-numeros")
    pendencias = caixa_de(aba, "#pendencias")
    conferir("no celular: os números, depois a lista", numeros["y"] < pendencias["y"])
    largura_da_pagina = aba.evaluate("() => document.documentElement.scrollWidth")
    conferir(f"no celular, a página não rola para o lado (largura: {largura_da_pagina})",
             largura_da_pagina <= LARGURA_DO_CELULAR)
    aba.screenshot(path="storage/painel/acompanhar_layout_celular.png", full_page=True)
    cartao.scroll_into_view_if_needed()
    cartao.locator("[data-abrir-conversa]").click()
    janela = aba.locator(JANELA_DA_CONVERSA)
    janela.wait_for(timeout=10000)
    tamanho = janela.bounding_box()
    conferir(f"no celular, a conversa abre em tela cheia (na tela: {tamanho})",
             tamanho["x"] == 0 and tamanho["y"] == 0 and tamanho["width"] == LARGURA_DO_CELULAR
             and janela.locator("[data-voltar-a-lista]").is_visible())
    aba.screenshot(path="storage/painel/acompanhar_layout_celular_conversa.png")
    janela.locator("[data-voltar-a-lista]").click()
    conferir("o 'Voltar à lista' fecha a conversa", janela.is_hidden())
    aba.close()


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques no computador e no celular."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-lista-pendencias] [data-pendencia]").first.wait_for(timeout=30000)
    aba.wait_for_function("() => document.querySelector('[data-resumo-sem-conta-valor]').hasAttribute('data-dado-pronto')",
                          timeout=30000)
    conferir_o_bloco_de_cima(aba, conferir)
    aba.screenshot(path="storage/painel/acompanhar_layout_computador.png")
    conferir_a_conversa_na_janela_e_a_grade(aba, dados, conferir)
    conferir_a_resolvida_na_janela(aba, dados, conferir)
    aba.close()
    conferir_o_celular(navegador, endereco, dados, conferir, erros_da_pagina)
