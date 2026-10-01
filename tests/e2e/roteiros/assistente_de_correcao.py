"""Roteiro: a conversa com a IA na conferência da tela Cadastrar (no lugar do antigo "Perguntar à IA").

O que ele confere (com a IA simulada, sem custo):
- a pendência da Luíza (o Word diz "o CPF dela eu mando depois") é uma conversa: a pergunta num balão do agente e a
  caixa "Responda ao agente...";
- uma pergunta vira um balão "você" e ganha a explicação da regra, e nada muda;
- contado o CPF certo, a IA já corrige: a pendência some e vira "Resolvido agora", com o Desfazer;
- o Desfazer traz a pendência de volta.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Conversa com a IA no Cadastrar: pergunta, a IA corrige na hora, Resolvido agora e Desfazer"
# Um CPF válido e inventado, para a Luíza
CPF_DA_LUIZA = "526.018.159-06"


def preparar() -> dict:
    """Os usuários de teste e o Word de exemplo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {"word": criar_word_de_exemplo()}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: enviar o Word, aceitar as colunas e conversar com a IA sobre a pendência da Luíza."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["word"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba.click("[data-real-aceitar]")
    aba.locator("[data-real-bloco-conferencia][open]").wait_for(timeout=60000)
    item = aba.locator(".pendencia-real").first
    item.wait_for(timeout=30000)
    # 1. A conversa já está aberta: a pergunta num balão do agente e a caixa
    conversa = item.locator(".conversa-ia-pendencia")
    conferir("a pergunta vem num balão do agente, e a caixa 'Responda ao agente...' está à vista",
             "✦ Agente de validação" in conversa.locator("[data-pergunta-da-pendencia]").inner_text()
             and conversa.locator("[data-caixa-da-conversa]").is_visible())
    # 2. Uma pergunta: a explicação, e nada muda
    conversa.locator("[data-caixa-da-conversa]").fill("Por que isso é um erro?")
    conversa.locator("button[type=submit]").click()
    conversa.locator(".balao-voce").first.wait_for(timeout=30000)
    aba.wait_for_function("() => !document.querySelector('[data-contador-processando]')", timeout=30000)
    conferir("a pergunta vira um balão 'você' e ganha uma resposta da IA, sem mudar nada",
             conversa.locator(".fala-ia").count() == 2 and conversa.locator(".mudanca-da-ia").count() == 0
             and aba.locator(".pendencia-real").count() >= 1)
    # 3. O CPF certo: a IA corrige na hora; a pendência some e vira "Resolvido agora"
    conversa.locator("[data-caixa-da-conversa]").fill("O certo é " + CPF_DA_LUIZA)
    conversa.locator("button[type=submit]").click()
    aviso = aba.locator("[data-real-resolvidos-agora] [data-aviso-resolvido]")
    aviso.first.wait_for(timeout=30000)
    aba.wait_for_function("() => document.querySelectorAll('.pendencia-real').length === 0", timeout=30000)
    conferir("a IA corrigiu: a pendência some e o aviso 'Resolvido agora' mostra o CPF novo",
             "Resolvido agora" in aviso.first.inner_text()
             and CPF_DA_LUIZA.replace(".", "").replace("-", "")
             in aviso.first.inner_text().replace(".", "").replace("-", ""))
    # 4. Desfazer: a pendência volta
    aviso.first.locator("[data-desfazer-mudanca]").click()
    aba.locator(".pendencia-real").first.wait_for(timeout=30000)
    conferir("o Desfazer traz a pendência de volta e tira o aviso",
             aba.locator("[data-real-resolvidos-agora] [data-aviso-resolvido]").count() == 0)
    aba.close()
