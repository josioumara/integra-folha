"""Roteiro: o prazo de resposta de 1 dia útil na conversa da ficha da empresa (ADR-94).

A tela "Mensagens" saiu: a conversa de cada empresa fica na aba "Conversa" da ficha dela. O que ele confere:
- o resumo do prazo da carteira aparece acima da lista das empresas, com 1 atrasada;
- a conversa da Aurora (uma pergunta de 10 dias atrás, sem resposta) aparece com a situação "Atrasada";
- na Carteira, a bolinha da Aurora (a conversa aberta) avisa, na dica, que a resposta está atrasada.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Prazo das mensagens: pergunta sem resposta há 10 dias aparece como atrasada na ficha da empresa"


def preparar() -> dict:
    """Os usuários de teste e uma mensagem antiga da Aurora, sem resposta."""
    from datetime import datetime, timedelta, timezone

    from services import auth, mensagens
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # Cria as tabelas das conversas e grava a pergunta com a hora de 10 dias atrás
    mensagens.conversa_da_empresa(conexao, "EMP001")
    dez_dias_atras = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
    conexao.execute("INSERT INTO mensagens_de_ajuda (empresa_id, de, autor, contexto, texto, criado_em) "
                    "VALUES ('EMP001', 'empresa', 'teste.empresa', 'Início', 'Posso mandar a matrícula com letras?', ?)",
                    (dez_dias_atras,))
    conexao.commit()
    conexao.close()
    return {}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre a ficha da Aurora direto na aba Conversa e confere o prazo."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_empresas.html?empresa=EMP001&aba=conversa")
    # O resumo do prazo da carteira, acima da lista das empresas
    aba.locator("[data-prazo-respostas]:not([hidden])").wait_for(timeout=20000)
    resumo = aba.inner_text("[data-prazo-respostas]")
    conferir("o resumo do prazo aparece com 1 atrasada (" + resumo + ")", "1 atrasada" in resumo)
    # A conversa da Aurora: a aba Conversa aberta pelo endereço, com a situação "Atrasada". O resumo do prazo chega
    # antes das fichas das empresas, então espera a aba aparecer (ela só é escolhida quando as fichas chegam)
    conteudo_da_conversa = aba.locator("[data-conteudo-aba='conversa']")
    conteudo_da_conversa.wait_for(state="visible", timeout=20000)
    conferir("a aba Conversa abre direto pelo endereço (?aba=conversa)", conteudo_da_conversa.is_visible())
    aba.wait_for_function("() => document.querySelector('[data-conversa-situacao]').innerText.includes('Atrasada')",
                          timeout=10000)
    conferir("a conversa da Aurora tem a situação 'Atrasada'", "Atrasada" in aba.inner_text("[data-conversa-situacao]"))
    conferir("a pergunta aparece na conversa",
             "Posso mandar a matrícula com letras?" in aba.inner_text("[data-mensagens-banco]"))
    # A bolinha da Aurora na Carteira: a conversa aberta, esperando resposta, com o atraso na dica
    bolinha = aba.locator("[data-lista-empresas] [data-abrir-empresa='EMP001'] [data-sinal-conversa]")
    aba.wait_for_function("() => {"
                          "  const bolinha = document.querySelector(\"[data-lista-empresas] [data-abrir-empresa='EMP001'] "
                          "[data-sinal-conversa]\");"
                          "  return bolinha !== null && bolinha.title.includes('atrasada');"
                          "}", timeout=10000)
    conferir("a bolinha da Aurora na Carteira avisa, na dica, que a resposta está atrasada (" +
             (bolinha.get_attribute("title") or "") + ")",
             bolinha.get_attribute("data-sinal-conversa") == "sem-resposta" and "atrasada" in bolinha.get_attribute("title"))
    aba.close()
