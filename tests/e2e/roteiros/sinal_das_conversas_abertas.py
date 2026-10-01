"""Roteiro: o sinal das conversas abertas (a "bolinha") no menu de todas as telas do banco, o cartão do Início e a
conversa que o especialista começa.

Uma conversa está ABERTA enquanto tem mensagem e não foi marcada como respondida. Os dados: a Aurora espera resposta;
a Horizonte foi respondida e ainda não marcada; a Brisa agradeceu e foi marcada como respondida; a Vale Verde nunca
escreveu. O que ele confere:
- no Início, a bolinha ao lado de "Empresas" conta as 2 abertas (a Aurora e a Horizonte), com a dica no plural, e o
  cartão "mensagens de empresas sem resposta" conta só a que espera resposta (1);
- nas outras telas do banco (Envios, Endomarketing, Indicadores, Parâmetros, Agentes e Teto), a bolinha do menu mostra
  o mesmo 2; a tela Envios não busca mais todas as conversas (só o sinal, que é leve);
- a Vale Verde, sem mensagem: a caixa aparece com "Enviar", sem as respostas prontas, sem o "Marcar como respondida" e
  sem bolinha; o especialista escreve primeiro, a conversa abre (o "Marcar como respondida" aparece, a bolinha entra
  na aba e na Carteira) e o menu vai a 3 sem recarregar a página;
- a Horizonte (respondida, não marcada): "Enviar", o "Marcar como respondida" à vista e a bolinha "respondida";
- a Brisa (marcada, com a última palavra da empresa): "Responder", sem o "Marcar como respondida" e sem bolinha.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Sinal das conversas abertas: a bolinha do menu em todas as telas do banco, o cartão do Início e a "
             "conversa começada pelo especialista (Enviar)")

# As outras telas do banco com o menu do alto (cada uma deve mostrar o mesmo total na bolinha)
OUTRAS_TELAS_DO_BANCO = ["banco_envios.html", "banco_endomarketing.html", "banco_indicadores.html",
                         "banco_parametros.html", "banco_agentes.html", "banco_teto_da_ia.html"]
# A mensagem que o especialista manda para começar a conversa com a Vale Verde
MENSAGEM_DO_ESPECIALISTA = "Olá! Vi que vocês ainda não mandaram o primeiro arquivo. Posso ajudar?"

# O script que diz se a tela buscou a lista inteira das conversas (e não só o sinal das abertas)
BUSCOU_TODAS_AS_CONVERSAS = """() => {
  for (const pedido of performance.getEntriesByType("resource")) {
    const caminho = new URL(pedido.name).pathname;
    if (caminho === "/api/banco/conversas") {
      return true;
    }
  }
  return false;
}"""


def gravar_mensagem(conexao, empresa_id: str, de: str, texto: str) -> None:
    """Grava uma mensagem (da empresa ou do banco), com a hora de agora, direto na tabela das conversas."""
    from datetime import datetime, timezone
    # A hora de agora, no formato que o serviço grava
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conexao.execute("INSERT INTO mensagens_de_ajuda (empresa_id, de, autor, contexto, texto, criado_em) "
                    "VALUES (?, ?, ?, 'Início', ?, ?)", (empresa_id, de, "autor." + de, texto, agora))


def preparar() -> dict:
    """Os usuários de teste e as conversas: Aurora esperando, Horizonte respondida, Brisa marcada e Vale Verde vazia."""
    from models.contratos import Perfil
    from services import auth, mensagens
    from services.auth import Usuario
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # Cria as tabelas das conversas
    mensagens.conversa_da_empresa(conexao, "EMP001")
    # Aurora: espera a resposta do especialista
    gravar_mensagem(conexao, "EMP001", "empresa", "O afastado pelo INSS entra no arquivo de inclusão?")
    # Horizonte: o especialista respondeu e não marcou
    gravar_mensagem(conexao, "EMP002", "empresa", "Quando o banco manda as contas abertas?")
    gravar_mensagem(conexao, "EMP002", "banco", "Em até 5 dias úteis depois da aprovação.")
    # Brisa: agradeceu, e o especialista marcou como respondida sem escrever
    gravar_mensagem(conexao, "EMP003", "empresa", "Achei. Obrigada!")
    conexao.commit()
    mensagens.marcar_resolvida(conexao, Usuario(login="teste.banco", perfil=Perfil.BANCO, empresa_id=None), "EMP003")
    conexao.close()
    return {}


def bolinha_do_menu(aba):
    """A bolinha ao lado de "Empresas", no menu do alto."""
    return aba.locator(".abas-banco a.aba[href='banco_empresas.html'] [data-contador-mensagens]")


def esperar_o_menu(aba, texto: str) -> None:
    """Espera a bolinha do menu mostrar o número (sem recarregar a página: o sinal é buscado de novo sozinho)."""
    aba.wait_for_function("(texto) => {"
                          "  const bolinha = document.querySelector('.abas-banco [data-contador-mensagens]');"
                          "  return bolinha !== null && bolinha.hasAttribute('data-dado-pronto')"
                          "    && bolinha.innerText.trim() === texto;"
                          "}", arg=texto, timeout=20000)


def bolinha_da_empresa(aba, empresa_id: str):
    """A bolinha de uma empresa na Carteira (não existe quando a conversa dela está fechada)."""
    return aba.locator(f"[data-lista-empresas] [data-abrir-empresa='{empresa_id}'] [data-sinal-conversa]")


def abrir_conversa_de(aba, empresa_id: str, texto_esperado: str) -> None:
    """Abre a empresa na Carteira (com a aba Conversa já escolhida) e espera a conversa dela aparecer."""
    aba.click(f"[data-abrir-empresa='{empresa_id}']")
    aba.wait_for_function("(texto) => document.querySelector('[data-mensagens-banco]').innerText.includes(texto)",
                          arg=texto_esperado, timeout=10000)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Confere a bolinha do menu em cada tela do banco, o cartão do Início e as situações da conversa na ficha."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    # 1. O Início: a bolinha do menu e o cartão das mensagens sem resposta
    aba.goto(endereco + "/banco_inicio.html")
    esperar_o_menu(aba, "2")
    conferir("no Início, a bolinha do menu conta as 2 conversas abertas (a sem resposta e a respondida sem marcar)",
             bolinha_do_menu(aba).is_visible() and bolinha_do_menu(aba).inner_text().strip() == "2")
    conferir("a dica da bolinha do menu, no plural ('" + (bolinha_do_menu(aba).get_attribute("title") or "") + "')",
             bolinha_do_menu(aba).get_attribute("title")
             == "2 conversas abertas: sem resposta ou ainda não marcadas como respondidas")
    aba.wait_for_function("() => document.querySelector('[data-numero-mensagens]').hasAttribute('data-dado-pronto')",
                          timeout=20000)
    conferir("o cartão 'mensagens de empresas sem resposta' do Início conta só a que espera resposta (1)",
             aba.inner_text("[data-numero-mensagens]").strip() == "1")
    # 2. As outras telas do banco: o mesmo total na bolinha do menu
    for tela in OUTRAS_TELAS_DO_BANCO:
        aba.goto(endereco + "/" + tela)
        esperar_o_menu(aba, "2")
        conferir("em " + tela + ", a bolinha do menu mostra o mesmo 2",
                 bolinha_do_menu(aba).is_visible() and bolinha_do_menu(aba).inner_text().strip() == "2")
        # Na tela Envios: só o sinal é buscado, e não mais a lista inteira das conversas
        if tela == "banco_envios.html":
            conferir("a tela Envios não busca a lista inteira das conversas (só o sinal)",
                     aba.evaluate(BUSCOU_TODAS_AS_CONVERSAS) is False)
    # 3. A Vale Verde, que nunca escreveu: o especialista começa a conversa
    aba.goto(endereco + "/banco_empresas.html?empresa=EMP004&aba=conversa")
    aba.wait_for_function("() => document.querySelector('[data-conversa-situacao]').innerText.includes('Nenhuma mensagem')",
                          timeout=20000)
    conferir("sem mensagem, a caixa aparece para começar a conversa, com o botão 'Enviar'",
             aba.locator("[data-formulario-banco]").is_visible()
             and aba.inner_text("[data-botao-de-mandar]").strip() == "Enviar")
    conferir("sem mensagem, as respostas prontas não aparecem", aba.locator("[data-respostas-prontas]").is_hidden())
    conferir("sem mensagem, não há o 'Marcar como respondida' nem a bolinha da aba",
             aba.locator("[data-marcar-respondida]").is_hidden() and aba.locator("[data-contador-conversa]").is_hidden())
    conferir("o aviso convida a começar a conversa",
             "comece a conversa" in aba.inner_text("[data-mensagens-banco]"))
    aba.fill("[data-texto-banco]", MENSAGEM_DO_ESPECIALISTA)
    aba.click("[data-botao-de-mandar]")
    aba.wait_for_function("() => document.querySelectorAll('[data-mensagens-banco] .bolha').length === 1", timeout=10000)
    conferir("a mensagem do especialista aparece na conversa",
             MENSAGEM_DO_ESPECIALISTA in aba.inner_text("[data-mensagens-banco]"))
    conferir("o botão continua 'Enviar' (a última mensagem é do especialista)",
             aba.inner_text("[data-botao-de-mandar]").strip() == "Enviar")
    conferir("a conversa abriu: o 'Marcar como respondida' aparece", aba.locator("[data-marcar-respondida]").is_visible())
    esperar_o_menu(aba, "3")
    conferir("a bolinha do menu foi a 3 sem recarregar a página", bolinha_do_menu(aba).inner_text().strip() == "3")
    bolinha_da_empresa(aba, "EMP004").wait_for(timeout=10000)
    conferir("a Vale Verde ganhou a bolinha na Carteira (aberta, com a última palavra do especialista)",
             bolinha_da_empresa(aba, "EMP004").get_attribute("data-sinal-conversa") == "respondida")
    conferir("a aba Conversa da Vale Verde mostra a bolinha", aba.locator("[data-contador-conversa]").is_visible())
    # 4. A Horizonte: respondida e ainda não marcada
    abrir_conversa_de(aba, "EMP002", "Em até 5 dias úteis depois da aprovação.")
    conferir("a Horizonte está 'Respondida'", "Respondida" in aba.inner_text("[data-conversa-situacao]"))
    conferir("a Horizonte mostra 'Enviar' (a última mensagem é do especialista)",
             aba.inner_text("[data-botao-de-mandar]").strip() == "Enviar")
    conferir("a Horizonte ainda tem o 'Marcar como respondida' e a bolinha na aba",
             aba.locator("[data-marcar-respondida]").is_visible() and aba.locator("[data-contador-conversa]").is_visible())
    conferir("a bolinha da Horizonte na Carteira é a de 'respondida', com a dica de marcar",
             bolinha_da_empresa(aba, "EMP002").get_attribute("data-sinal-conversa") == "respondida"
             and "falta marcar como respondida" in (bolinha_da_empresa(aba, "EMP002").get_attribute("title") or ""))
    # 5. A Brisa: marcada como respondida, com a última palavra da empresa
    abrir_conversa_de(aba, "EMP003", "Achei. Obrigada!")
    conferir("a Brisa está 'Resolvida'", "Resolvida" in aba.inner_text("[data-conversa-situacao]"))
    conferir("a Brisa mostra 'Responder' (a última mensagem é da empresa)",
             aba.inner_text("[data-botao-de-mandar]").strip() == "Responder")
    conferir("a Brisa não tem o 'Marcar como respondida' (já marcada) nem bolinha na aba",
             aba.locator("[data-marcar-respondida]").is_hidden() and aba.locator("[data-contador-conversa]").is_hidden())
    conferir("a Brisa não tem bolinha na Carteira", bolinha_da_empresa(aba, "EMP003").count() == 0)
    # 6. A Aurora: a dica da bolinha diz que ela espera a resposta
    conferir("a bolinha da Aurora diz que ela espera a resposta",
             bolinha_da_empresa(aba, "EMP001").get_attribute("data-sinal-conversa") == "sem-resposta"
             and "esperando a sua resposta" in (bolinha_da_empresa(aba, "EMP001").get_attribute("title") or ""))
    conferir("na Carteira, só as 3 abertas têm bolinha",
             aba.locator("[data-lista-empresas] [data-sinal-conversa]").count() == 3)
    aba.screenshot(path="storage/painel/sinal_das_conversas_abertas.png")
    aba.close()
