"""Roteiro: a tela de envio "Cadastrar funcionários" com um Word em texto corrido (ADR-72, ADR-75).

O que ele confere:
- o cronômetro aparece ao enviar e para quando a leitura chega;
- "No seu documento": uma linha por rótulo, cada uma com exemplo (inteiro: os dados da própria empresa);
- trocar o campo vira "Ajustado por você"; um tipo que não bate avisa que vira pendência; voltar desfaz;
- "Ajude o agente a acertar" fica oculto nesta versão (o bloco continua na página, escondido); os detalhes da
  leitura sem "Pessoa N";
- descartar pela janela que explica: a tela volta limpa para a escolha do arquivo;
- um Word antigo (.doc) é recusado com o caminho para converter.
"""
import re

from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Janela de cadastro: cronômetro, rótulos com exemplo, ajuste com conferência do tipo, releitura oculta"


def preparar() -> dict:
    """Os usuários de teste, o Word de exemplo e um arquivo .doc (Word antigo, que a tela recusa)."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo, pasta_do_roteiro
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    # O Word antigo: o conteúdo não importa, a tela recusa pela extensão
    antigo = pasta_do_roteiro() / "lista_antiga.doc"
    antigo.write_bytes(b"conteudo qualquer")
    return {"word": criar_word_de_exemplo(), "word_antigo": str(antigo)}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na tela de envio."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    # 1. Cronômetro: aparece com o envio e para quando a leitura chega
    aba.set_input_files("#campo-arquivo", dados["word"])
    aba.locator("#cronometro-ia:not([hidden])").wait_for(timeout=10000)
    conferir("cronômetro aparece ao enviar", re.fullmatch(r"\d+:\d\d", aba.inner_text("#cronometro-ia")) is not None)
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    tempo_final = aba.inner_text("#cronometro-ia")
    aba.wait_for_timeout(2200)
    conferir("cronômetro para quando a leitura chega", aba.inner_text("#cronometro-ia") == tempo_final)
    # As colunas ficam na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    # 2. Uma linha por rótulo do documento, com exemplo
    corpo = aba.locator("[data-real-corpo-colunas]")
    linhas = corpo.locator("tr")
    conferir("título da coluna: No seu documento",
             aba.inner_text("[data-real-titulo-coluna-arquivo]") == "No seu documento")
    conferir("cada linha tem um exemplo do valor (" + str(linhas.count()) + " linhas)",
             corpo.locator(".exemplo-da-coluna").count() == linhas.count())
    linha_do_cpf = corpo.locator("tr", has=aba.locator("td:first-child", has_text="CPF")).first
    conferir("exemplo do CPF inteiro, como está no arquivo", "***" not in linha_do_cpf.inner_text()
             and "982" in linha_do_cpf.inner_text())
    # 3. Trocar o campo: um tipo que não bate avisa; voltar desfaz
    selo_do_cpf = linha_do_cpf.locator(".selo")
    selo_original = selo_do_cpf.inner_text()
    linha_do_cpf.locator("select").select_option("data_admissao")
    linha_do_cpf.locator(".alerta-do-tipo").wait_for(timeout=15000)
    conferir("CPF no campo de data: o selo pede para conferir o tipo", "confira" in selo_do_cpf.inner_text())
    alerta = linha_do_cpf.locator(".alerta-do-tipo").inner_text()
    conferir("o alerta explica e diz que vira pendência", "não servem" in alerta and "pendência" in alerta)
    linha_do_cpf.locator("select").select_option("cpf")
    aba.wait_for_timeout(500)
    conferir("voltar ao campo da IA desfaz",
             selo_do_cpf.inner_text() == selo_original and linha_do_cpf.locator(".alerta-do-tipo").count() == 0)
    # Um texto em outro campo de texto: "Ajustado por você", sem alerta
    linha_do_cargo = corpo.locator("tr", has_text="analista").first
    linha_do_cargo.locator("select").select_option("nome_unidade")
    aba.wait_for_timeout(1500)
    conferir("cargo em outro campo de texto: 'Ajustado por você', sem alerta",
             linha_do_cargo.locator(".selo").inner_text() == "Ajustado por você"
             and linha_do_cargo.locator(".alerta-do-tipo").count() == 0)
    linha_do_cargo.locator("select").select_option("cargo")
    # 4. "Ajude o agente a acertar" oculto nesta versão: o bloco continua na página (o código fica), mas nunca aparece,
    #    mesmo na etapa em que o script o liga
    bloco_da_releitura = aba.locator("[data-real-bloco-ajude]")
    conferir("'Ajude o agente a acertar' continua na página, com a marca de oculto",
             bloco_da_releitura.count() == 1
             and bloco_da_releitura.get_attribute("data-oculto-nesta-versao") == "ajude-o-agente")
    conferir("'Ajude o agente a acertar' não aparece na aba 'Como o agente leu'", bloco_da_releitura.is_hidden())
    # 5. Detalhes da leitura sem "Pessoa N"
    detalhes = aba.inner_text("[data-real-lista-detalhes]")
    conferir("detalhes da leitura sem 'Pessoa N'", re.search(r"Pessoa \d", detalhes) is None)
    # 6. Descartar: a janela diz que nada foi ao banco e o que se perde; confirmando, a tela volta limpa
    aba.click("[data-real-descartar]")
    janela = aba.locator("dialog[open]", has_text="Descartar esta leitura?")
    janela.wait_for(timeout=15000)
    explicacao = janela.inner_text()
    conferir("a janela diz que nada foi ao banco e o que se perde",
             "Nada foi enviado ao banco" in explicacao and "funcionário(s)" in explicacao)
    janela.locator("text=Sim, descartar").click()
    aba.wait_for_url("**descartado=1**", timeout=30000)
    conferir("descartada, a tela volta limpa para a escolha do arquivo", aba.locator("#etapa-envio").is_visible())
    # 7. O Word antigo (.doc) é recusado com o caminho para converter
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["word_antigo"])
    aba.wait_for_function("() => document.querySelector('#painel-ia').innerText.includes('Salvar como')", timeout=30000)
    conferir("Word antigo (.doc) recusado com o caminho para converter", True)
    aba.close()
