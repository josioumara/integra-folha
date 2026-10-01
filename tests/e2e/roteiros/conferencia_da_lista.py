"""Roteiro: a leitura de um Word em texto corrido e a conferência da lista (ADR-73, decisão 6).

O que ele confere:
- a leitura resumida numa frase, antes das colunas; o contador das perguntas da IA junto das colunas;
- "No seu documento" mostra como a empresa chamou cada dado e em quantas pessoas ele apareceu;
- ao aceitar, a conferência abre sozinha, com contadores e o filtro "só quem tem pendência";
- o CPF que falta e a pergunta da IA viram um item só, que é uma conversa com a IA (a pendência se resolve
  conversando);
- contado o CPF na conversa, a IA corrige, a pendência e a pergunta somem; sem o filtro, as 4 pessoas aparecem;
- nenhuma tabela rola para o lado: a lista tem só colunas curtas, e
  "Ver todos os dados" abre a ficha da pessoa, com o "i" de ajuda em cada campo.
"""
from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Conferência da lista: resumo da leitura, pergunta da IA presa à pessoa, CPF corrigido pela conversa"
# Um CPF válido e inventado, para a Luíza (o Word diz "o CPF dela eu mando depois")
CPF_DA_LUIZA = "52601815906"


def preparar() -> dict:
    """Os usuários de teste e o Word de exemplo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {"word": criar_word_de_exemplo()}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na tela de envio: a leitura, o aceite e a conferência."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["word"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    # A leitura das colunas fica na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    # 1. A leitura numa frase, antes das colunas
    resumo = aba.locator("[data-real-resumo-leitura]")
    conferir("resumo da leitura em uma frase", resumo.is_visible() and "Texto corrido" in resumo.inner_text())
    conferir("a regra 'os agentes não inventam dado' aparece junto do resumo",
             "Os agentes não inventam dado" in resumo.inner_text())
    ordem = aba.evaluate("""() => {
        const resumo = document.querySelector('[data-real-resumo-leitura]');
        const colunas = document.querySelector('[data-real-bloco-colunas]');
        const detalhes = document.querySelector('[data-real-bloco-detalhes]');
        return [resumo.compareDocumentPosition(colunas) & 4, colunas.compareDocumentPosition(detalhes) & 4];
    }""")
    conferir("ordem na tela: resumo → colunas → detalhes", ordem == [4, 4])
    aviso = aba.locator("[data-real-aviso-perguntas]")
    conferir("contador das perguntas junto das colunas", aviso.is_visible() and "1 pergunta" in aviso.inner_text())
    colunas = aba.inner_text("[data-real-corpo-colunas]")
    conferir("colunas mostram como a empresa chamou cada dado e em quantas pessoas",
             "CPF" in colunas and "de 4 pessoa(s)" in colunas)
    # 2. Aceitar: a conferência abre sozinha, com contadores e o filtro
    aba.click("[data-real-aceitar]")
    aba.locator("[data-real-bloco-conferencia][open]").wait_for(timeout=60000)
    aba.locator("[data-real-contadores-conferencia] .contador-conferencia").first.wait_for(timeout=30000)
    contadores = aba.inner_text("[data-real-contadores-conferencia]")
    conferir("contadores com as perguntas dos agentes e as pendências",
             "1 pergunta dos agentes" in contadores and "pessoa com pendência" in contadores
             and "0 para confirmar" in contadores and "para revisar" in contadores)
    conferir("filtro 'só quem tem pendência' ligado", aba.is_checked("[data-real-so-pendencias]"))
    item = aba.locator(".pendencia-real").first
    conferir("o CPF que falta e a pergunta da IA num item só, que é a conversa com a IA",
             item.count() == 1 and item.locator(".conversa-ia-pendencia").count() == 1
             and aba.locator(".pendencia-real").count() == 1)
    conferir("o item pergunta num balão do agente", "✦ Agente de validação" in item.locator("[data-pergunta-da-pendencia]").inner_text())
    # 3. O CPF contado na conversa: a IA corrige, e a pendência e a pergunta somem
    item.locator("[data-caixa-da-conversa]").fill("O CPF certo é " + CPF_DA_LUIZA)
    item.locator("button[type=submit]").click()
    aba.wait_for_function("() => document.querySelectorAll('.pendencia-real').length === 0", timeout=30000)
    contadores_depois = aba.inner_text("[data-real-contadores-conferencia]")
    conferir("depois de corrigir: 0 com pendência e 0 perguntas",
             "0 pessoas com pendência" in contadores_depois and "0 perguntas dos agentes" in contadores_depois)
    conferir("com o filtro ligado, a mensagem de tudo resolvido",
             "Nenhuma pessoa com pendência" in aba.inner_text("[data-real-corpo-conferencia]"))
    # 4. Filtro desligado: a lista inteira aparece
    aba.uncheck("[data-real-so-pendencias]")
    aba.wait_for_function("() => document.querySelectorAll('[data-real-corpo-conferencia] > tr').length >= 4",
                          timeout=15000)
    pessoas = aba.locator("[data-real-corpo-conferencia] > tr:not(.linha-pendencias-real):not(.linha-correcao-real)")
    conferir("sem o filtro, as 4 pessoas aparecem (" + str(pessoas.count()) + ")", pessoas.count() == 4)
    # 5. Nenhuma tabela rola para o lado: a largura do conteúdo cabe na caixa (1 pixel de folga para arredondamento)
    rolagens = aba.evaluate("""() => {
        const caixas = document.querySelectorAll('[data-real-bloco-colunas] .tabela-rolavel, .conferencia-real .tabela-rolavel');
        return Array.from(caixas).map(caixa => caixa.scrollWidth - caixa.clientWidth);
    }""")
    conferir("nenhuma tabela rola para o lado (sobras: " + str(rolagens) + ")",
             len(rolagens) == 2 and max(rolagens) <= 1)
    # 6. "Ver todos os dados" abre a ficha da primeira pessoa, com os campos em grade e o "i" de ajuda
    primeira_pessoa = pessoas.first
    primeira_pessoa.locator("text=Ver todos os dados").click()
    ficha = aba.locator(".linha-ficha-real")
    # Quantos campos a lista do envio tem (o Word de exemplo traz só alguns): a ficha mostra todos eles
    campos_da_lista = aba.evaluate("() => estado_da_conferencia.lista.campos.length")
    conferir("a ficha abre com os " + str(campos_da_lista) + " campos da lista", ficha.count() == 1
             and ficha.locator(".item-ficha-real").count() == campos_da_lista and campos_da_lista >= 3)
    ficha.locator(".botao-ajuda-campo").first.click()
    conferir("o i de ajuda da ficha abre o balão", aba.locator("[data-balao-ajuda]").is_visible())
    # Fecha o balão com um clique fora e fecha a ficha no mesmo botão
    aba.locator("[data-real-contadores-conferencia]").click()
    primeira_pessoa.locator("text=Esconder os dados").click()
    conferir("clicar de novo fecha a ficha", aba.locator(".linha-ficha-real").count() == 0)
    aba.close()
