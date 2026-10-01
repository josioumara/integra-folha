"""Roteiro: a conversa com a empresa na aba "Conversa" da ficha (a bolinha das conversas abertas, o "Marcar como
respondida" em cima do chat, "Responder"/"Enviar" e a aba no canto direito).

A tela "Mensagens" saiu do menu: a conversa de cada empresa fica na ficha dela. Uma conversa está ABERTA enquanto não
é marcada como respondida: sem resposta do especialista, ou respondida e ainda não marcada. O que ele confere, a
1366 × 768 (a tela mais comum de notebook):
- na Carteira, a Aurora e a Horizonte (as duas esperando resposta) têm a bolinha com 1; as outras, nenhuma; a bolinha
  do menu, ao lado de "Empresas", conta as 2 conversas abertas;
- a aba Conversa fica no canto direito das abas, depois de todas, com o ícone de conversa e a bolinha com 1;
- a conversa da Aurora mostra as 2 perguntas (com "Sobre: <tela>"), a situação "Sem resposta", o "Marcar como
  respondida" em cima do chat, à direita, e o botão "Responder" (a última mensagem é da empresa);
- uma atualização das conversas e do sinal não apaga o que o especialista está digitando;
- a resposta pronta só preenche a caixa; a resposta enviada aparece, a situação vira "Respondida", o botão vira
  "Enviar" e a conversa CONTINUA aberta (a bolinha fica, agora "respondida", e o menu continua com 2); a empresa lê a
  resposta pelo lado dela;
- "Marcar como respondida" fecha a conversa: o botão some, a bolinha da Aurora sai da Carteira e da aba, e o menu
  baixa para 1;
- a Horizonte, marcada como respondida sem resposta, fica "Resolvida", e a bolinha do menu some (nenhuma aberta);
- depois da atualização do servidor, nada volta; ao abrir de novo pelo endereço (?empresa=EMP001&aba=conversa), a
  conversa gravada continua lá, sem o "Marcar como respondida" (já marcada).
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = ("Conversa na ficha da empresa: a bolinha das conversas abertas (Carteira, aba e menu), Responder/Enviar, "
             "Marcar como respondida em cima do chat e a aba no canto direito")
# O texto da resposta do especialista
RESPOSTA_DO_BANCO = "Pode mandar com letras, sim: a matrícula é o código que a empresa já usa."

# O script que confere onde ficam a aba Conversa e o "Marcar como respondida" (as posições na tela, em pixels)
POSICOES_DA_CONVERSA = """() => {
  const abas = document.querySelectorAll("[data-aba-ficha]");
  const aba_conversa = document.querySelector("[data-aba-ficha='conversa']");
  const linha_das_abas = document.querySelector(".abas-ficha").getBoundingClientRect();
  const caixa_da_aba = aba_conversa.getBoundingClientRect();
  const botao = document.querySelector("[data-marcar-respondida]").getBoundingClientRect();
  const chat = document.querySelector("[data-mensagens-banco]").getBoundingClientRect();
  let aba_mais_a_direita_antes = 0;
  for (const aba of abas) {
    if (aba !== aba_conversa) {
      aba_mais_a_direita_antes = Math.max(aba_mais_a_direita_antes, aba.getBoundingClientRect().right);
    }
  }
  return {
    ultima_aba: abas[abas.length - 1].dataset.abaFicha,
    aba_no_canto_direito: Math.abs(linha_das_abas.right - caixa_da_aba.right) <= 4,
    aba_separada_das_outras: caixa_da_aba.left - aba_mais_a_direita_antes >= 24,
    aba_tem_icone: aba_conversa.querySelector("svg.icone") !== null,
    botao_em_cima_do_chat: botao.bottom <= chat.top,
    botao_a_direita: Math.abs(botao.right - chat.right) <= 4,
    botao_a_vista: botao.top >= 0 && botao.bottom <= window.innerHeight,
  };
}"""


def gravar_mensagem(conexao, empresa_id: str, contexto: str, texto: str) -> None:
    """Grava uma mensagem da empresa, com a hora de agora, direto na tabela das conversas."""
    from datetime import datetime, timezone
    # A hora de agora, no formato que o serviço grava
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conexao.execute("INSERT INTO mensagens_de_ajuda (empresa_id, de, autor, contexto, texto, criado_em) "
                    "VALUES (?, 'empresa', 'rh.da.empresa', ?, ?, ?)", (empresa_id, contexto, texto, agora))


def preparar() -> dict:
    """Os usuários de teste, duas perguntas da Aurora e uma da Horizonte, todas sem resposta."""
    from services import auth, mensagens
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # Cria as tabelas das conversas
    mensagens.conversa_da_empresa(conexao, "EMP001")
    # A Aurora pergunta duas vezes; a Horizonte, uma
    gravar_mensagem(conexao, "EMP001", "Cadastrar funcionários", "Posso mandar a matrícula com letras?")
    gravar_mensagem(conexao, "EMP001", "Acompanhar cadastros", "E o PIS, é obrigatório?")
    gravar_mensagem(conexao, "EMP002", "Início", "Quando o banco manda as contas abertas?")
    conexao.commit()
    conexao.close()
    return {}


def bolinha_da_empresa(aba, empresa_id: str):
    """A bolinha de uma empresa na Carteira (não existe quando a conversa dela está fechada)."""
    return aba.locator(f"[data-lista-empresas] [data-abrir-empresa='{empresa_id}'] [data-sinal-conversa]")


def bolinha_do_menu(aba):
    """A bolinha ao lado de "Empresas", no menu do alto."""
    return aba.locator(".abas-banco a.aba[href='banco_empresas.html'] [data-contador-mensagens]")


def esperar_o_menu(aba, texto: str) -> None:
    """Espera a bolinha do menu mostrar o número (sem recarregar a página: o sinal é buscado de novo sozinho)."""
    aba.wait_for_function("(texto) => document.querySelector('.abas-banco [data-contador-mensagens]').innerText.trim()"
                          " === texto", arg=texto, timeout=10000)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Responde e marca a Aurora, e marca a Horizonte sem responder, pela aba Conversa da ficha."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    # A tela mais comum de notebook: o botão e as bolinhas precisam estar à vista nela
    aba.set_viewport_size({"width": 1366, "height": 768})
    aba.goto(endereco + "/banco_empresas.html")
    # 1. As bolinhas na Carteira e no menu, quando o sinal das conversas abertas chega
    bolinha_da_empresa(aba, "EMP001").wait_for(timeout=20000)
    conferir("a Aurora tem a bolinha com 1, esperando resposta ('" + bolinha_da_empresa(aba, "EMP001").inner_text() + "')",
             bolinha_da_empresa(aba, "EMP001").inner_text() == "1"
             and bolinha_da_empresa(aba, "EMP001").get_attribute("data-sinal-conversa") == "sem-resposta")
    conferir("a Horizonte tem a bolinha com 1, esperando resposta",
             bolinha_da_empresa(aba, "EMP002").inner_text() == "1"
             and bolinha_da_empresa(aba, "EMP002").get_attribute("data-sinal-conversa") == "sem-resposta")
    conferir("as outras empresas não têm bolinha", aba.locator("[data-lista-empresas] [data-sinal-conversa]").count() == 2)
    conferir("a dica da bolinha da Aurora diz que ela espera a resposta",
             "esperando a sua resposta" in (bolinha_da_empresa(aba, "EMP001").get_attribute("title") or ""))
    conferir("a bolinha do menu, ao lado de 'Empresas', conta as 2 conversas abertas",
             bolinha_do_menu(aba).inner_text().strip() == "2" and bolinha_do_menu(aba).is_visible())
    # 2. A aba Conversa da Aurora: no canto direito, com o ícone e a bolinha
    aba.click("[data-abrir-empresa='EMP001']")
    aba.click("[data-aba-ficha='conversa']")
    aba.wait_for_function("() => document.querySelectorAll('[data-mensagens-banco] .bolha').length === 2", timeout=10000)
    mensagens_na_tela = aba.inner_text("[data-mensagens-banco]")
    conferir("as 2 perguntas da Aurora aparecem",
             "Posso mandar a matrícula com letras?" in mensagens_na_tela and "E o PIS, é obrigatório?" in mensagens_na_tela)
    conferir("cada pergunta diz de que tela veio ('Sobre: ...')",
             "Sobre: Cadastrar funcionários" in mensagens_na_tela and "Sobre: Acompanhar cadastros" in mensagens_na_tela)
    conferir("a situação é 'Sem resposta'", aba.inner_text("[data-conversa-situacao]").strip() == "Sem resposta")
    conferir("a aba Conversa mostra a bolinha com 1",
             aba.locator("[data-contador-conversa]").is_visible()
             and aba.inner_text("[data-contador-conversa]").strip() == "1")
    posicoes = aba.evaluate(POSICOES_DA_CONVERSA)
    conferir("a aba Conversa é a última, no canto direito das abas, separada das outras e com o ícone de conversa (" +
             str(posicoes) + ")",
             posicoes["ultima_aba"] == "conversa" and posicoes["aba_no_canto_direito"]
             and posicoes["aba_separada_das_outras"] and posicoes["aba_tem_icone"])
    conferir("o 'Marcar como respondida' aparece em cima do chat, no canto direito, à vista",
             aba.locator("[data-marcar-respondida]").is_visible() and posicoes["botao_em_cima_do_chat"]
             and posicoes["botao_a_direita"] and posicoes["botao_a_vista"])
    conferir("o botão de mandar diz 'Responder' (a última mensagem é da empresa)",
             aba.inner_text("[data-botao-de-mandar]").strip() == "Responder")
    aba.screenshot(path="storage/painel/conversa_na_ficha.png")
    # 3. A atualização das conversas e do sinal não apaga o que está sendo digitado
    aba.fill("[data-texto-banco]", "Rascunho que não pode sumir")
    aba.evaluate("() => carregar_conversas_do_servidor()")
    aba.evaluate("() => buscar_conversas_abertas()")
    aba.wait_for_timeout(1000)
    conferir("a atualização não apagou o texto da caixa",
             aba.input_value("[data-texto-banco]") == "Rascunho que não pode sumir")
    # 4. A resposta pronta só preenche a caixa; a resposta enviada aparece, e a conversa continua aberta
    aba.click("[data-resposta-pronta]")
    conferir("a resposta pronta só preenche a caixa", "Vou verificar" in aba.input_value("[data-texto-banco]"))
    conferir("a resposta pronta não foi enviada sozinha", aba.locator("[data-mensagens-banco] .bolha").count() == 2)
    aba.fill("[data-texto-banco]", RESPOSTA_DO_BANCO)
    aba.click("[data-botao-de-mandar]")
    aba.wait_for_function("() => document.querySelectorAll('[data-mensagens-banco] .bolha').length === 3", timeout=10000)
    conferir("a resposta aparece na conversa", RESPOSTA_DO_BANCO in aba.inner_text("[data-mensagens-banco]"))
    conferir("a caixa ficou vazia depois de responder", aba.input_value("[data-texto-banco]") == "")
    aba.wait_for_function("() => document.querySelector('[data-conversa-situacao]').innerText.includes('Respondida')",
                          timeout=10000)
    conferir("a situação virou 'Respondida'", "Respondida" in aba.inner_text("[data-conversa-situacao]"))
    conferir("o botão de mandar virou 'Enviar' (a última mensagem é do especialista)",
             aba.inner_text("[data-botao-de-mandar]").strip() == "Enviar")
    # A conversa respondida continua aberta até ser marcada: a bolinha fica, agora "respondida"
    aba.locator("[data-lista-empresas] [data-abrir-empresa='EMP001'] [data-sinal-conversa='respondida']").wait_for(
        timeout=10000)
    conferir("a bolinha da Aurora fica na Carteira (respondida, ainda não marcada)",
             bolinha_da_empresa(aba, "EMP001").count() == 1)
    conferir("a dica da bolinha diz que falta marcar como respondida",
             "falta marcar como respondida" in (bolinha_da_empresa(aba, "EMP001").get_attribute("title") or ""))
    conferir("a bolinha da aba Conversa continua", aba.locator("[data-contador-conversa]").is_visible())
    conferir("a bolinha do menu continua com 2", bolinha_do_menu(aba).inner_text().strip() == "2")
    conferir("o 'Marcar como respondida' continua à vista", aba.locator("[data-marcar-respondida]").is_visible())
    # A empresa lê a resposta pelo lado dela (a mesma conversa gravada no servidor)
    aba_da_empresa = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    conversa_da_empresa = aba_da_empresa.evaluate("async () => (await fetch('/api/empresa/conversa')).json()")
    ultima = conversa_da_empresa["mensagens"][-1]
    conferir("a empresa lê a resposta do banco", ultima["de"] == "banco" and ultima["texto"] == RESPOSTA_DO_BANCO)
    aba_da_empresa.close()
    # 5. "Marcar como respondida" fecha a conversa da Aurora
    aba.click("[data-marcar-respondida]")
    aba.wait_for_function("() => document.querySelector('[data-conversa-situacao]').innerText.includes('Resolvida')",
                          timeout=10000)
    conferir("a Aurora ficou 'Resolvida'", "Resolvida" in aba.inner_text("[data-conversa-situacao]"))
    conferir("o 'Marcar como respondida' sumiu (a conversa já foi marcada)",
             aba.locator("[data-marcar-respondida]").is_hidden())
    esperar_o_menu(aba, "1")
    conferir("a bolinha do menu baixou para 1 (sem recarregar a página)", bolinha_do_menu(aba).inner_text().strip() == "1")
    conferir("a bolinha da Aurora saiu da Carteira", bolinha_da_empresa(aba, "EMP001").count() == 0)
    conferir("a bolinha da aba Conversa sumiu", aba.locator("[data-contador-conversa]").is_hidden())
    # 6. A Horizonte: marcada como respondida sem resposta (a Carteira está congelada na Aurora: o "Trocar empresa"
    #    traz a lista de volta)
    aba.click("[data-trocar-empresa]")
    aba.click("[data-abrir-empresa='EMP002']")
    aba.wait_for_function("() => document.querySelector('[data-mensagens-banco]').innerText"
                          ".includes('Quando o banco manda as contas abertas?')", timeout=10000)
    conferir("trocar de empresa mantém a aba Conversa", aba.locator("[data-conteudo-aba='conversa']").is_visible())
    conferir("a bolinha da aba volta com 1 (a conversa aberta da Horizonte)",
             aba.locator("[data-contador-conversa]").is_visible()
             and aba.inner_text("[data-contador-conversa]").strip() == "1")
    conferir("a Horizonte também mostra 'Responder'", aba.inner_text("[data-botao-de-mandar]").strip() == "Responder")
    aba.click("[data-marcar-respondida]")
    aba.wait_for_function("() => document.querySelector('[data-conversa-situacao]').innerText.includes('Resolvida')",
                          timeout=10000)
    conferir("a Horizonte ficou 'Resolvida'", "Resolvida" in aba.inner_text("[data-conversa-situacao]"))
    aba.wait_for_function("() => document.querySelector('.abas-banco [data-contador-mensagens]').hidden", timeout=10000)
    conferir("a bolinha do menu some com nenhuma conversa aberta", bolinha_do_menu(aba).is_hidden())
    conferir("nenhuma bolinha na Carteira", aba.locator("[data-lista-empresas] [data-sinal-conversa]").count() == 0)
    # 7. Depois da atualização do servidor, nada volta
    aba.evaluate("() => carregar_conversas_do_servidor()")
    aba.evaluate("() => buscar_conversas_abertas()")
    aba.wait_for_timeout(1000)
    conferir("resolvida continua resolvida, sem bolinhas, depois da atualização",
             "Resolvida" in aba.inner_text("[data-conversa-situacao]")
             and aba.locator("[data-lista-empresas] [data-sinal-conversa]").count() == 0
             and bolinha_do_menu(aba).is_hidden())
    # 8. Abrir de novo pelo endereço: a conversa gravada da Aurora continua lá, já marcada
    aba.goto(endereco + "/banco_empresas.html?empresa=EMP001&aba=conversa")
    aba.wait_for_function("() => document.querySelectorAll('[data-mensagens-banco] .bolha').length === 3", timeout=20000)
    conferir("a conversa da Aurora continua gravada, com a resposta",
             RESPOSTA_DO_BANCO in aba.inner_text("[data-mensagens-banco]"))
    conferir("aberta pelo endereço, a conversa marcada não mostra o 'Marcar como respondida'",
             aba.locator("[data-marcar-respondida]").is_hidden())
    aba.close()
