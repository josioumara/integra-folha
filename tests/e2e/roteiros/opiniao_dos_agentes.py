"""Roteiro: o joinha nas respostas dos agentes e a seção "O que as pessoas acham das respostas dos agentes", na tela
Acompanhamento dos agentes (ADR-151).

O que ele confere, no Chrome de verdade (IA simulada, sem custo):
- Cadastrar, na conferência de um envio da Aurora:
    - a pergunta do Agente Conferidor sobre a renda da Helena tem o joinha "Esta pergunta fez sentido?". O 👍 fica
      marcado e o aviso aparece ao lado; clicar de novo retira o voto; o voto volta marcado depois do F5 (vem do
      servidor);
    - na conversa sobre o CPF que faltou da Luíza, a resposta do Agente de validação tem o joinha "Esta resposta
      ajudou?", e nem a fala da pessoa nem a pergunta do cartão têm. O 👍 e depois o 👎 trocam o voto (só um fica
      marcado); o 👎 abre "O que faltou? (opcional)", com o cursor na caixa; enviado, o comentário fica à vista embaixo
      do joinha ("Seu comentário: ..."), e o "Editar" abre a caixa com ele para trocar o texto;
- Acompanhar: na janela da conversa (por cima da tela), a resposta do agente tem o joinha; marcar e retirar;
- Endomarketing do banco: o rascunho tem o joinha sobre o texto do agente; o 👍 fica marcado; a janela "Ver" do mesmo
  material mostra o joinha já marcado;
- Acompanhamento dos agentes: a seção vem logo depois dos cartões do trabalho de cada agente, com um cartão por agente,
  na ordem. O resumo diz 3 votos, 66,7% para cima e 1 com comentário. Cada cartão mostra a satisfação dele (o Agente
  Leitor, sem voto, com o traço). A linha das semanas mostra a dica com o mouse e com as setas do teclado; a tabela tem
  as 12 semanas. O período do alto da tela vale para a seção (um De/até em janeiro: "Nenhum voto no período"; de volta
  aos 30 dias: os 3 votos). O texto do comentário nunca aparece na tela do banco;
- Indicadores: a seção não está mais lá.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = ("O joinha nas respostas dos agentes (conversa, pergunta da leitura, material), o comentário à vista e a "
             "seção do Acompanhamento dos agentes")
# A linha da Helena na tabela do Word de exemplo (o cabeçalho é a linha 1)
LINHA_DA_HELENA = 2
# O material de exemplo do Endomarketing (um rascunho da Aurora)
MATERIAL_DE_EXEMPLO = "material-do-joinha"
# O comentário do joinha para baixo, e o texto dele depois do "Editar": a tela do banco nunca mostra nenhum dos dois
COMENTARIO = "Faltou dizer qual CPF usar."
COMENTARIO_EDITADO = "Faltou dizer qual CPF usar e onde achar."
# O resumo da seção com os 3 votos do roteiro (a pergunta, a resposta da conversa e o material)
RESUMO_COM_OS_3_VOTOS = "No período: 3 votos, 66,7% de joinha para cima, 1 com comentário."


def preparar() -> dict:
    """Os usuários de teste; um envio da Aurora na conferência, com a pergunta do Conferidor sobre a renda da Helena; e
    um rascunho do Endomarketing da Aurora.

    Por que a pergunta entra aqui: a IA simulada não desconfia de nada, então a pergunta é guardada no envio do mesmo
    jeito que a leitura a guardaria (a lista das perguntas da leitura), e a validação roda de novo.
    """
    import json
    from pathlib import Path

    import rag.busca
    from agents import conferidor_da_leitura, endomarketing
    from services import auth, cadastro, processamentos, validador
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo
    from tests.test_correcao import busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # O Word de exemplo (a Luíza vem sem CPF: a conversa com o Agente de validação), com as colunas aceitas
    conteudo = Path(criar_word_de_exemplo()).read_bytes()
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, "novos_funcionarios.docx",
                                      busca=busca_falsa)
    envio = leitura["processamento_id"]
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, envio, {}, busca=busca_falsa)
    # A pergunta do Conferidor sobre a renda da Helena, guardada no envio, e a validação de novo
    perfil = processamentos.obter(conexao, envio)
    perfil.perguntas_da_ia.append({
        "linha": LINHA_DA_HELENA, "campo": "valor_renda",
        "pergunta": conferidor_da_leitura.INICIO_DA_PERGUNTA + "no documento está R$ 5.200,00, mas ficou "
                                                               "R$ 5.020,00. Qual é o certo?"})
    conexao.execute("UPDATE processamentos SET perfil = ? WHERE processamento_id = ?", (perfil.model_dump_json(), envio))
    conexao.commit()
    validador.executar(conexao, envio, "EMP001")
    # Um rascunho do Endomarketing da Aurora (o texto que o agente teria escrito)
    endomarketing._preparar(conexao)
    conteudo_do_material = {"titulo": "A conta-salário da Aurora", "canal": endomarketing.CANAL_PADRAO,
                            "beneficios": ["Conta salário"], "observacoes": [],
                            "blocos": [{"texto": "Receba o salário na conta do banco parceiro, sem tarifa.",
                                        "fontes": ["Catálogo da Aurora · Conta salário"]}]}
    conexao.execute("INSERT INTO materiais_endomarketing (material_id, empresa_id, tipo, conteudo, status, modelo, "
                    "versao_prompt, criado_em, criado_por) VALUES (?, 'EMP001', 'comunicado', ?, 'RASCUNHO', 'mock', "
                    "'v', '2026-09-30T12:00:00+00:00', ?)",
                    (MATERIAL_DE_EXEMPLO, json.dumps(conteudo_do_material, ensure_ascii=False), LOGIN_DO_BANCO))
    conexao.commit()
    conexao.close()
    return {"envio": envio}


# ---------------- Apoio ----------------

def botao(joinha, voto: str):
    """O botão do joinha para cima ("para_cima") ou para baixo ("para_baixo")."""
    return joinha.locator(f"[data-botao-do-joinha='{voto}']")


def marcado(joinha, voto: str) -> bool:
    """Diz se o botão do voto está marcado (aria-pressed)."""
    return botao(joinha, voto).get_attribute("aria-pressed") == "true"


def esperar_o_aviso(joinha, texto: str) -> None:
    """Espera o aviso ao lado dos botões dizer o texto pedido."""
    joinha.locator("[data-aviso-do-joinha]", has_text=texto).wait_for(timeout=15000)


def abrir_a_conferencia(aba, endereco: str, envio: str) -> None:
    """Abre o envio na tela Cadastrar e espera a conferência aberta, com os cartões."""
    aba.goto(endereco + "/cadastrar.html?envio=" + envio)
    aba.locator("[data-real-bloco-conferencia][open]").wait_for(timeout=60000)
    aba.locator(".pendencia-real").first.wait_for(timeout=30000)


def joinha_da_pergunta_da_leitura(aba):
    """O joinha no balão da pergunta do cartão da pergunta da leitura (a regra PERGUNTA_DA_IA da renda)."""
    cartao = aba.locator(".pendencia-real:has([data-chave-conversa*='PERGUNTA_DA_IA:valor_renda'])").first
    return cartao.locator("[data-pergunta-da-pendencia] [data-joinha]")


def resumo_das_opinioes(aba) -> str:
    """O resumo da seção do Acompanhamento dos agentes, como está na tela."""
    return aba.inner_text("[data-resumo-das-opinioes]")


def esperar_o_resumo(aba, texto: str) -> None:
    """Espera o resumo da seção dizer o texto pedido (os números chegam do servidor depois do clique)."""
    aba.wait_for_function("(texto) => document.querySelector('[data-resumo-das-opinioes]').textContent === texto",
                          arg=texto, timeout=15000)


def cartao_do_agente(aba, agente: str):
    """O cartão de um agente na seção do Acompanhamento dos agentes."""
    return aba.locator(f"[data-cartao-opiniao='{agente}']")


# ---------------- As partes ----------------

def conferir_a_pergunta_da_leitura(aba, endereco: str, dados: dict, conferir) -> None:
    """O joinha na pergunta do Conferidor: marcar, retirar, marcar de novo e o voto depois do F5."""
    abrir_a_conferencia(aba, endereco, dados["envio"])
    joinha = joinha_da_pergunta_da_leitura(aba)
    joinha.wait_for(timeout=20000)
    conferir(f"a pergunta da leitura tem o joinha (na tela: {joinha.locator('.joinha-pergunta').inner_text()})",
             joinha.locator(".joinha-pergunta").inner_text() == "Esta pergunta fez sentido?"
             and not marcado(joinha, "para_cima") and not marcado(joinha, "para_baixo"))
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Obrigado pela opinião.")
    conferir("o 👍 fica marcado, e o aviso aparece ao lado dos botões",
             marcado(joinha, "para_cima") and not marcado(joinha, "para_baixo"))
    # Clicar de novo no joinha marcado retira o voto
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Voto retirado.")
    conferir("clicar de novo retira o voto (nenhum botão marcado)",
             not marcado(joinha, "para_cima") and not marcado(joinha, "para_baixo"))
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Obrigado pela opinião.")
    # A página aberta de novo (como um F5): o voto volta marcado, porque vem do servidor
    abrir_a_conferencia(aba, endereco, dados["envio"])
    joinha = joinha_da_pergunta_da_leitura(aba)
    joinha.locator("[data-botao-do-joinha='para_cima'][aria-pressed='true']").wait_for(timeout=15000)
    conferir("depois do F5, o 👍 da pergunta continua marcado", marcado(joinha, "para_cima"))


def conferir_a_resposta_da_conversa(aba, conferir) -> None:
    """O joinha na resposta do Agente de validação: trocar o voto, o comentário do 👎 à vista e o "Editar"."""
    conversa = aba.locator(".pendencia-real", has_text="Luíza").first.locator(".conversa-ia-pendencia")
    conversa.locator("[data-caixa-da-conversa]").fill("Por que isso é um erro?")
    conversa.locator("button[type=submit]").click()
    conversa.locator(".balao-voce").first.wait_for(timeout=30000)
    aba.wait_for_function("() => !document.querySelector('[data-contador-processando]')", timeout=30000)
    resposta = conversa.locator(".fala-ia").last
    joinha = resposta.locator("[data-joinha]")
    joinha.wait_for(timeout=15000)
    conferir("a resposta do agente tem o joinha; a fala da pessoa e a pergunta do cartão, não",
             joinha.locator(".joinha-pergunta").inner_text() == "Esta resposta ajudou?"
             and conversa.locator(".balao-voce [data-joinha]").count() == 0
             and conversa.locator("[data-pergunta-da-pendencia] [data-joinha]").count() == 0)
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Obrigado pela opinião.")
    # Mudar de ideia: o 👎 troca o voto, e só ele fica marcado
    botao(joinha, "para_baixo").click()
    caixa = joinha.locator("[data-comentario-do-joinha]")
    caixa.wait_for(timeout=15000)
    cursor_na_caixa = aba.evaluate("() => document.activeElement.hasAttribute('data-comentario-do-joinha')")
    conferir("o 👎 troca o voto (só ele marcado) e abre 'O que faltou?' com o cursor na caixa",
             marcado(joinha, "para_baixo") and not marcado(joinha, "para_cima") and cursor_na_caixa
             and "O que faltou? (opcional)" in joinha.inner_text())
    caixa.fill(COMENTARIO)
    joinha.locator("[data-enviar-comentario-do-joinha]").click()
    esperar_o_aviso(joinha, "Comentário enviado.")
    comentario_a_vista = joinha.locator("[data-comentario-dado-no-joinha]")
    conferir(f"enviado, o comentário fica à vista embaixo do joinha (na tela: {comentario_a_vista.inner_text()})",
             joinha.locator("[data-comentario-do-joinha]").count() == 0 and marcado(joinha, "para_baixo")
             and "Seu comentário:" in comentario_a_vista.inner_text() and COMENTARIO in comentario_a_vista.inner_text())
    # "Editar": a caixa abre com o texto de agora; o texto novo fica à vista
    comentario_a_vista.locator("[data-editar-comentario-do-joinha]").click()
    caixa = joinha.locator("[data-comentario-do-joinha]")
    caixa.wait_for(timeout=15000)
    conferir("o 'Editar' abre a caixa com o comentário de agora", caixa.input_value() == COMENTARIO)
    caixa.fill(COMENTARIO_EDITADO)
    joinha.locator("[data-enviar-comentario-do-joinha]").click()
    esperar_o_aviso(joinha, "Comentário enviado.")
    conferir("o comentário editado fica à vista no lugar do outro",
             COMENTARIO_EDITADO in joinha.locator("[data-comentario-dado-no-joinha]").inner_text())


def conferir_a_janela_do_acompanhar(aba, endereco: str, conferir) -> None:
    """Em Acompanhar, a conversa abre numa janela por cima da tela: a resposta do agente tem o joinha lá também.

    O voto é marcado e depois retirado (clicar de novo): os números da tela do banco, conferidos adiante, não mudam.
    """
    from tests.e2e.painel_da_conversa import abrir_a_conversa, fechar_a_conversa_aberta
    aba.goto(endereco + "/acompanhar.html")
    cartao = aba.locator("[data-pendencia]", has_text="Luíza").first
    cartao.wait_for(timeout=30000)
    janela = abrir_a_conversa(aba, cartao)
    janela.locator("[data-caixa-da-conversa]").fill("Por que isso é um erro?")
    janela.locator("form:has([data-caixa-da-conversa]) button[type=submit]").click()
    janela.locator(".balao-voce").first.wait_for(timeout=30000)
    aba.wait_for_function("() => !document.querySelector('[data-contador-processando]')", timeout=30000)
    joinha = janela.locator(".fala-ia").last.locator("[data-joinha]")
    joinha.wait_for(timeout=15000)
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Obrigado pela opinião.")
    conferir("na janela da conversa de Acompanhar, a resposta do agente tem o joinha, e o 👍 fica marcado",
             marcado(joinha, "para_cima"))
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Voto retirado.")
    conferir("na janela, clicar de novo retira o voto", not marcado(joinha, "para_cima"))
    fechar_a_conversa_aberta(aba)


def conferir_o_material(navegador, endereco: str, conferir, erros_da_pagina: list) -> None:
    """O joinha no rascunho do Endomarketing e na janela "Ver" do mesmo material."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_endomarketing.html?empresa=EMP001&aba=material")
    material = aba.locator(f"[data-lista-materiais] [data-material-id='{MATERIAL_DE_EXEMPLO}']")
    material.wait_for(timeout=20000)
    material.get_by_role("button", name="Abrir rascunho", exact=True).click()
    joinha = aba.locator("[data-opiniao-do-rascunho] [data-joinha]")
    joinha.wait_for(timeout=15000)
    conferir("o rascunho tem o joinha sobre o texto do agente",
             joinha.locator(".joinha-pergunta").inner_text() == "O texto do Agente de Endomarketing ficou bom?")
    botao(joinha, "para_cima").click()
    esperar_o_aviso(joinha, "Obrigado pela opinião.")
    conferir("o 👍 do material fica marcado", marcado(joinha, "para_cima"))
    material.get_by_role("button", name="Ver", exact=True).click()
    janela = aba.locator("#janela-material[open]")
    janela.wait_for(timeout=10000)
    joinha_da_janela = janela.locator("[data-opiniao-da-janela-material] [data-joinha]")
    joinha_da_janela.wait_for(timeout=10000)
    conferir("a janela 'Ver' do mesmo material mostra o joinha já marcado", marcado(joinha_da_janela, "para_cima"))
    janela.locator("[data-fechar-janela]").first.click()
    aba.close()


def conferir_o_acompanhamento_dos_agentes(navegador, endereco: str, conferir, erros_da_pagina: list) -> None:
    """A seção: o lugar, os cartões, o resumo, a linha das semanas, a tabela e o período do alto da tela."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_agentes.html")
    cartao_do_agente(aba, "agente_de_validacao").wait_for(timeout=30000)
    depois_dos_cartoes = aba.evaluate("""() => {
      const cartoes = document.querySelector('#titulo-agentes');
      const opinioes = document.querySelector('[data-parte-opinioes]');
      return Boolean(cartoes.compareDocumentPosition(opinioes) & Node.DOCUMENT_POSITION_FOLLOWING);
    }""")
    conferir("a seção vem depois dos cartões do trabalho de cada agente", depois_dos_cartoes)
    nomes = aba.locator("[data-cartao-opiniao] .cartao-opiniao-nome").all_inner_texts()
    conferir(f"um cartão por agente, na ordem (na tela: {nomes})",
             nomes == ["Agente de validação", "Agente Leitor", "Agente Conferidor", "Agente de Endomarketing"])
    esperar_o_resumo(aba, RESUMO_COM_OS_3_VOTOS)
    conferir(f"o resumo do período (na tela: {resumo_das_opinioes(aba)})",
             resumo_das_opinioes(aba) == RESUMO_COM_OS_3_VOTOS)
    satisfacoes = []
    for agente in ("agente_de_validacao", "leitor", "conferidor", "endomarketing"):
        satisfacoes.append(cartao_do_agente(aba, agente).locator("[data-satisfacao-do-agente]").inner_text())
    conferir(f"a satisfação de cada agente, e o traço sem voto (na tela: {satisfacoes})",
             satisfacoes == ["0%", "—", "100%", "100%"])
    votos = cartao_do_agente(aba, "agente_de_validacao").locator(".cartao-opiniao-votos").inner_text()
    conferir(f"os votos do Agente de validação, com a contagem do comentário (na tela: {votos})",
             votos == "0 para cima · 1 para baixo · 1 voto · 1 com comentário")
    texto_da_tela = aba.inner_text("body")
    conferir("o texto do comentário nunca aparece na tela do banco",
             COMENTARIO not in texto_da_tela and COMENTARIO_EDITADO not in texto_da_tela)
    conferir_a_linha_das_semanas(aba, conferir)
    # A tabela: a mesma tendência, sem gráfico
    aba.click("[data-tendencia-em-tabela] summary")
    linhas = aba.locator("[data-corpo-da-tendencia] tr").count()
    colunas = aba.locator("[data-cabecalho-da-tendencia] th").count()
    conferir(f"a tabela tem as 12 semanas e uma coluna por agente (na tela: {linhas} linhas, {colunas} colunas)",
             linhas == 12 and colunas == 5)
    # O período do alto da tela: um De/até em janeiro, sem votos
    aba.click("[data-escolha-do-periodo] [data-periodo='de_ate']")
    aba.fill("[data-campo-de]", "2026-01-01")
    aba.fill("[data-campo-ate]", "2026-01-31")
    aba.click("[data-formulario-de-ate] button[type=submit]")
    esperar_o_resumo(aba, "Nenhum voto no período.")
    conferir("o De/até do alto vale para a seção: em janeiro, 'Nenhum voto no período.'", True)
    # De volta aos últimos 30 dias: os 3 votos
    aba.click("[data-escolha-do-periodo] [data-periodo='30']")
    esperar_o_resumo(aba, RESUMO_COM_OS_3_VOTOS)
    conferir("de volta aos 30 dias, os 3 votos", True)
    # Nos Indicadores, a seção não existe mais
    aba.goto(endereco + "/banco_indicadores.html")
    aba.locator("[data-parte-painel='numeros']").wait_for(timeout=20000)
    conferir("nos Indicadores, a seção não aparece mais",
             aba.locator("[data-cartoes-das-opinioes], [data-cartao-opiniao]").count() == 0)
    aba.close()


def conferir_a_linha_das_semanas(aba, conferir) -> None:
    """A dica da linha das semanas: com o mouse sobre a semana de agora, e com as setas do teclado."""
    linha = cartao_do_agente(aba, "agente_de_validacao").locator(".linha-das-semanas")
    desenho = linha.locator(".linha-das-semanas-desenho")
    # A seção pode estar fora da vista: primeiro ela vem para a vista, depois o mouse vai à ponta direita (a semana de
    # agora)
    desenho.scroll_into_view_if_needed()
    caixa = desenho.bounding_box()
    desenho.hover(position={"x": caixa["width"] - 2, "y": caixa["height"] / 2})
    dica = linha.locator(".linha-das-semanas-dica")
    dica.wait_for(state="visible", timeout=5000)
    texto_do_mouse = dica.inner_text()
    conferir(f"com o mouse, a dica mostra a semana de agora (na tela: {texto_do_mouse})",
             texto_do_mouse.startswith("Semana de ") and "0% de joinha para cima, em 1 voto." in texto_do_mouse)
    aba.mouse.move(0, 0)
    # Com o foco do teclado e a seta para a esquerda: a semana anterior, sem voto
    linha.focus()
    aba.keyboard.press("ArrowLeft")
    texto_do_teclado = dica.inner_text()
    conferir(f"com as setas, a dica anda uma semana (na tela: {texto_do_teclado})",
             texto_do_teclado.endswith(": nenhum voto."))
    linha.blur()


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """A empresa vota (a pergunta da leitura e a resposta da conversa), o banco vota no material e lê a seção no
    Acompanhamento dos agentes."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    conferir_a_pergunta_da_leitura(aba, endereco, dados, conferir)
    conferir_a_resposta_da_conversa(aba, conferir)
    conferir_a_janela_do_acompanhar(aba, endereco, conferir)
    aba.close()
    conferir_o_material(navegador, endereco, conferir, erros_da_pagina)
    conferir_o_acompanhamento_dos_agentes(navegador, endereco, conferir, erros_da_pagina)
