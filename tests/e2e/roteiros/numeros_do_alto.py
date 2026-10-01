"""Roteiro: os números do alto de Acompanhar cadastros se atualizam sozinhos.

O defeito: os 4 números do alto só eram buscados ao abrir a página e depois de uma correção. O descarte, o fechamento
da janela "Cadastrar funcionários" e a decisão do banco (em outra tela) deixavam os números parados.

O que ele confere:
- o 2º cartão mostra as PESSOAS em análise pelo banco (e não mais "envios em andamento");
- enviar os prontos ao banco: o 2º cartão passa a contar as pessoas enviadas;
- o banco aprova o envio numa outra aba: sem recarregar a página, os números mudam quando a pessoa volta para a aba
  (cadastrados sobe e "em análise" volta a zero);
- de tempos em tempos (30 segundos), os números mudam sozinhos, mesmo sem trocar de aba;
- fechar a janela "Cadastrar funcionários" refaz a tela (o atalho "Envios" conta o envio novo).
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, abrir_janela_de_cadastro, entrar

DESCRICAO = "Acompanhar: os números do alto se atualizam (banco aprova, volta à aba, relógio de 30 s, janela fechada)"


def preparar() -> dict:
    """A mesma preparação do roteiro acompanhar: carga inicial cadastrada e a inclusão pronta para o banco."""
    from tests.e2e.roteiros.acompanhar import preparar as preparar_acompanhar
    return preparar_acompanhar()


def numero_do_cartao(aba, seletor: str) -> int:
    """O número mostrado num cartão do alto, como inteiro. Ex.: "12" → 12."""
    return int(aba.inner_text(seletor).strip())


def aprovar_pelo_banco(aba_do_banco, processamento_id: str) -> int:
    """O especialista aprova o envio pela API, na aba dele. Devolve o código da resposta (200 = aprovado)."""
    return aba_do_banco.evaluate(
        "async (id) => (await fetch('/api/banco/envios/' + encodeURIComponent(id) + '/avaliar', {"
        "method: 'POST', headers: {'Content-Type': 'application/json'},"
        "body: JSON.stringify({aprovar: true, motivo: ''})})).status",
        processamento_id)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: envia ao banco, o banco aprova em outra aba, e os números mudam sem recarregar a página."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # O relógio de mentira do navegador: deixa "passar" 30 segundos sem esperar de verdade
    aba.clock.install()
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-prontos]").wait_for(state="visible", timeout=20000)
    aba.wait_for_load_state("networkidle")
    # 1. O 2º cartão: pessoas em análise pelo banco (nenhuma, antes do envio)
    legenda = aba.inner_text("[data-resumo-andamento-legenda]")
    conferir(f"o 2º cartão diz 'pessoas em análise pelo banco' (na tela: {legenda})",
             legenda == "pessoas em análise pelo banco")
    conferir("antes do envio, ninguém em análise", numero_do_cartao(aba, "[data-resumo-andamento-valor]") == 0)
    cadastrados_antes = numero_do_cartao(aba, "[data-resumo-aprovados]")
    # O envio pronto (para o banco aprovar depois)
    processamento_id = aba.evaluate("async () => (await (await fetch('/api/empresa/prontos_para_o_banco')).json())"
                                    "[0].processamento_id")
    # 2. Envia ao banco: a página volta com o recado, e o 2º cartão conta as pessoas enviadas
    aba.click("[data-abrir-conferencia-prontos]")
    aba.locator("#janela-conferir-envio[open] .linha-de-grupos").wait_for(timeout=20000)
    aba.check("[data-conferi-prontos]")
    aba.click("[data-enviar-prontos]")
    aba.wait_for_url("**acompanhar.html?enviado=*", timeout=30000)
    aba.wait_for_load_state("networkidle")
    enviados = int(aba.url.split("enviado=")[1].split("&")[0])
    em_analise = numero_do_cartao(aba, "[data-resumo-andamento-valor]")
    conferir(f"depois do envio, o 2º cartão conta as {enviados} pessoas enviadas (na tela: {em_analise})",
             enviados > 0 and em_analise == enviados)
    # 3. O banco aprova, numa outra aba (outra sessão): a tela da empresa continua aberta, sem recarregar
    aba_do_banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir("o banco aprova o envio", aprovar_pelo_banco(aba_do_banco, processamento_id) == 200)
    # A pessoa "volta para a aba": o navegador avisa com o evento visibilitychange
    aba.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    aba.wait_for_function("() => document.querySelector('[data-resumo-andamento-valor]').innerText.trim() === '0'",
                          timeout=15000)
    cadastrados_depois = numero_do_cartao(aba, "[data-resumo-aprovados]")
    conferir(f"ao voltar para a aba: cadastrados sobe de {cadastrados_antes} para {cadastrados_depois} e "
             "'em análise' volta a zero", cadastrados_depois == cadastrados_antes + enviados)
    # 4. O relógio de 30 segundos: o número do alto muda sem trocar de aba (troca o número na tela e deixa o tempo correr)
    aba.evaluate("() => { document.querySelector('[data-resumo-aprovados]').textContent = '-1'; }")
    aba.clock.run_for(31000)
    aba.wait_for_function("() => document.querySelector('[data-resumo-aprovados]').innerText.trim() !== '-1'",
                          timeout=15000)
    conferir("depois de 30 segundos, os números foram buscados de novo sozinhos",
             numero_do_cartao(aba, "[data-resumo-aprovados]") == cadastrados_depois)
    # 5. Fechar a janela "Cadastrar funcionários" refaz a tela: o atalho "Envios" conta o envio novo
    envios_antes = numero_do_cartao(aba, "[data-atalho-envios]")
    quadro = abrir_janela_de_cadastro(aba)
    quadro.locator("#campo-arquivo").set_input_files(dados["word"])
    quadro.locator("[data-real-aceitar]").wait_for(state="visible", timeout=60000)
    aba.locator(".janela-novo-envio .botao-fechar-janela").click()
    aba.wait_for_function("(antes) => Number(document.querySelector('[data-atalho-envios]').innerText) > antes",
                          arg=envios_antes, timeout=15000)
    conferir("ao fechar a janela do envio, o atalho 'Envios' conta o envio novo", True)
    aba_do_banco.close()
    aba.close()
