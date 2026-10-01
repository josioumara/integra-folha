"""Roteiro: descartar a leitura na tela Cadastrar.

O que ele confere:
- "Descartar esta leitura" abre a janela que pergunta e explica o que acontece (a mesma da tela Acompanhar);
- "Continuar com este envio" desiste: a leitura continua na tela;
- "Sim, descartar" descarta: a tela volta limpa para a escolha do arquivo, com o aviso de que a leitura foi
  descartada e ficou registrada;
- em Acompanhar, o envio aparece como "Descartado", com quem descartou e quando.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Descarte na tela Cadastrar: a janela explica, a tela volta limpa e o envio fica registrado"


def preparar() -> dict:
    """Os usuários de teste e o Word de exemplo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {"word": criar_word_de_exemplo()}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: enviar, pedir o descarte, desistir, descartar de verdade e ver o registro em Acompanhar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["word"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    # 1. A janela pergunta e explica
    aba.locator("[data-real-descartar]").click()
    janela = aba.locator("dialog[open]", has_text="Descartar esta leitura?")
    janela.wait_for(timeout=15000)
    explicacao = janela.inner_text()
    conferir("a janela explica o que acontece, com a quantidade de funcionários",
             "Nada foi enviado ao banco" in explicacao and "4 funcionário(s)" in explicacao
             and "Descartado" in explicacao)
    # 2. Desistir: a leitura continua na tela
    janela.locator("text=Continuar com este envio").click()
    conferir("'Continuar' desiste e a leitura continua na tela",
             aba.locator("dialog[open]").count() == 0 and aba.locator("#resultado-real").is_visible())
    # 3. Descartar de verdade: a tela volta limpa, com o aviso
    aba.locator("[data-real-descartar]").click()
    janela.wait_for(timeout=15000)
    janela.locator("text=Sim, descartar").click()
    aba.wait_for_url("**descartado=1**", timeout=15000)
    aba.locator("[data-aviso-descartado]:not([hidden])").wait_for(timeout=15000)
    conferir("a tela volta limpa para a escolha do arquivo, com o aviso",
             aba.locator("#etapa-envio").is_visible() and not aba.locator("#resultado-real").is_visible())
    # 4. Em Acompanhar, o envio fica registrado como descartado, com quem e quando
    aba.goto(endereco + "/acompanhar.html")
    nota = aba.locator(".nota-do-descarte").first
    nota.wait_for(timeout=20000)
    conferir("em Acompanhar, o envio aparece com quem descartou",
             "Descartado por " + LOGIN_DA_EMPRESA in nota.inner_text())
    aba.close()
