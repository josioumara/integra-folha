"""Roteiro: o "i" em cima de cada grade com a coluna "Situação" explica cada situação.

A regra: um ícone "i" no canto direito, em cima de TODA grade que tem status, no banco e na empresa; ao passar o mouse
ou clicar, ele explica cada status daquela grade; funciona no teclado e no celular (clicar abre e fecha). Onde havia uma
legenda de texto (Acompanhar e o fim da Visão geral), o "i" a substitui.

O que ele confere, nas 8 grades:
- empresa: Cadastrar (as duas tabelas das colunas lidas e a conferência da lista) e Acompanhar (os funcionários);
- banco: o Início (a carteira), Empresas (a lista da Carteira, a Visão geral e os Usuários) e Envios (as pessoas);
- em cada uma: o "i" encostado à direita e logo acima da grade; o mouse em cima abre o balão com o título e um selo
  para cada situação que o servidor deu para aquela grade (o texto, a cor e a explicação, na mesma ordem); o mouse
  fora fecha;
- o clique fixa o balão (ele fica aberto com o mouse longe) e o clique de novo fecha; o clique fora fecha;
- o teclado: com o foco no "i", o Enter abre (aria-expanded="true") e o Esc fecha, com o foco de volta no "i";
- o celular (390 × 844, com toque): o toque abre e fecha, e o balão cabe na largura da tela;
- as legendas antigas saíram (a de Acompanhar e a do fim da Visão geral);
- com a rota da legenda em erro (500), o balão diz "Não foi possível carregar agora.", sem nenhum selo.
Os textos esperados vêm da própria rota (a fonte única fica no servidor, services/legenda_dos_status.py, com os testes
dela no pytest): aqui, o roteiro confere a TELA. Guarda a foto de um balão aberto (storage/painel/legenda_dos_status.png).
Os dados são os do roteiro telas_dos_obrigatorios: a carga da Aurora esperando o banco, o parâmetro de 4 obrigatórios e
uma planilha inventada para o Cadastrar.
"""
from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, SENHA_DE_TESTE, entrar

DESCRICAO = ("O \"i\" em cima das 8 grades com Situação: o balão com os textos do servidor, o mouse, o clique, o "
             "teclado, o celular e o erro")
# O que o balão diz quando a legenda não veio do servidor
AVISO_SEM_LEGENDA = "Não foi possível carregar agora."
# O título de todo balão
TITULO_DO_BALAO = "O que quer dizer cada situação"
# A largura da tela do celular do teste (um celular comum)
LARGURA_DO_CELULAR = 390
# A distância máxima, em pixels, entre o "i" e a grade (logo acima dela) e entre as bordas direitas dos dois
FOLGA_DE_POSICAO = 40
# O JavaScript que busca as legendas na rota do portal, com a sessão da própria aba
BUSCAR_AS_LEGENDAS = """rota => fetch(rota).then(resposta => resposta.json())"""
# O JavaScript que diz se o foco está num "i" das legendas
FOCO_NO_I = """() => document.activeElement !== null && document.activeElement.hasAttribute("data-botao-da-legenda")"""


def preparar() -> dict:
    """Os mesmos dados do roteiro telas_dos_obrigatorios (a carga da Aurora esperando o banco, o parâmetro de 4
    obrigatórios e a planilha do envio novo). Devolve o que ele devolve."""
    from tests.e2e.roteiros.telas_dos_obrigatorios import preparar as preparar_as_telas_dos_obrigatorios
    return preparar_as_telas_dos_obrigatorios()


def situacoes_esperadas(aba, portal: str, grade: str) -> list[dict]:
    """As situações que o servidor dá para a grade: [{texto, classe, explicacao}], na ordem do balão.

    Recebe: aba (já logada); portal ("banco" ou "empresa"); grade (ex.: "funcionarios").
    """
    legendas = aba.evaluate(BUSCAR_AS_LEGENDAS, "/api/" + portal + "/legenda_dos_status")
    return legendas[grade]


def o_que_o_balao_mostra(balao) -> list[dict]:
    """O que o balão aberto mostra: [{texto, classe, explicacao}] de cada situação, na ordem da tela."""
    situacoes = []
    for item in balao.locator(".item-do-balao-dos-status").all():
        selo = item.locator(".selo")
        situacoes.append({
            "texto": selo.inner_text(),
            # A classe da cor é a que sobra depois das classes de todo selo ("selo selo-pequeno selo-atencao")
            "classe": selo.get_attribute("class").replace("selo selo-pequeno", "").strip(),
            "explicacao": item.locator(".explicacao-do-balao-dos-status").inner_text(),
        })
    return situacoes


def conferir_a_posicao_do_i(botao, grade_na_tela, nome: str, conferir) -> None:
    """O "i" fica no canto direito, logo acima da grade: a borda direita perto da borda direita da grade, e embaixo
    dele, a grade."""
    caixa_do_i = botao.bounding_box()
    caixa_da_grade = grade_na_tela.bounding_box()
    borda_direita_do_i = caixa_do_i["x"] + caixa_do_i["width"]
    borda_direita_da_grade = caixa_da_grade["x"] + caixa_da_grade["width"]
    base_do_i = caixa_do_i["y"] + caixa_do_i["height"]
    conferir(f"{nome}: o \"i\" fica no canto direito (a {round(borda_direita_da_grade - borda_direita_do_i)} px da "
             "borda da grade)", abs(borda_direita_da_grade - borda_direita_do_i) <= FOLGA_DE_POSICAO)
    conferir(f"{nome}: o \"i\" fica logo acima da grade",
             base_do_i <= caixa_da_grade["y"] + 1 and caixa_da_grade["y"] - base_do_i <= FOLGA_DE_POSICAO)


def conferir_o_i_da_grade(aba, marcador, grade_na_tela, esperadas: list[dict], nome: str, conferir) -> None:
    """O "i" de uma grade: a posição, o balão que abre com o mouse em cima (com as situações do servidor) e fecha com
    o mouse fora.

    Recebe: aba; marcador (a linha do "i" na página); grade_na_tela (a caixa da tabela, ou a lista, que o "i" explica);
    esperadas (as situações do servidor para a grade); nome (o nome da grade nas mensagens); conferir.
    """
    botao = marcador.locator("[data-botao-da-legenda]")
    balao = marcador.locator("[data-balao-da-legenda]")
    botao.scroll_into_view_if_needed()
    conferir_a_posicao_do_i(botao, grade_na_tela, nome, conferir)
    # O mouse em cima abre o balão, com as situações do servidor
    botao.hover()
    balao.locator(".item-do-balao-dos-status").first.wait_for(timeout=15000)
    conferir(f"{nome}: o mouse em cima abre o balão, com o título",
             balao.is_visible() and TITULO_DO_BALAO in balao.inner_text())
    mostradas = o_que_o_balao_mostra(balao)
    textos_mostrados = []
    for situacao in mostradas:
        textos_mostrados.append(situacao["texto"])
    conferir(f"{nome}: o balão tem as {len(esperadas)} situações do servidor, com a cor e a explicação de cada uma "
             f"(na tela: {textos_mostrados})", mostradas == esperadas)
    # O balão cabe na janela
    caixa_do_balao = balao.bounding_box()
    largura_da_janela = aba.viewport_size["width"]
    conferir(f"{nome}: o balão cabe na janela",
             caixa_do_balao["x"] >= 0 and caixa_do_balao["x"] + caixa_do_balao["width"] <= largura_da_janela)
    # O mouse fora (no canto de cima, longe do "i") fecha o balão
    aba.mouse.move(1, 1)
    balao.wait_for(state="hidden", timeout=5000)
    conferir(f"{nome}: o mouse fora fecha o balão",
             balao.is_hidden() and botao.get_attribute("aria-expanded") == "false")


def conferir_o_clique_e_o_teclado(aba, marcador, lugar_neutro, conferir) -> None:
    """O clique fixa e fecha; o clique fora fecha; o Enter abre e o Esc fecha, com o foco de volta no "i".

    Recebe: aba; marcador (a linha do "i"); lugar_neutro (um elemento da página que não faz nada ao clicar); conferir.
    """
    botao = marcador.locator("[data-botao-da-legenda]")
    balao = marcador.locator("[data-balao-da-legenda]")
    # O clique fixa: o balão continua aberto com o mouse longe
    botao.click()
    aba.mouse.move(1, 1)
    aba.wait_for_timeout(700)
    conferir("clique: o balão fica aberto com o mouse longe (fixo)", balao.is_visible())
    # O clique no texto do balão (ex.: para copiar) não fecha o balão fixo
    balao.locator(".balao-dos-status-titulo").click()
    aba.mouse.move(1, 1)
    aba.wait_for_timeout(700)
    conferir("clique: o clique no texto do balão fixo não o fecha", balao.is_visible())
    # O clique de novo no "i" fecha
    botao.click()
    conferir("clique: o segundo clique fecha", balao.is_hidden())
    # O clique fora fecha
    botao.click()
    lugar_neutro.click()
    conferir("clique: o clique fora fecha", balao.is_hidden())
    # O teclado: o foco no "i", o Enter abre, o Esc fecha e o foco volta ao "i"
    aba.mouse.move(1, 1)
    botao.focus()
    aba.keyboard.press("Enter")
    balao.locator(".item-do-balao-dos-status").first.wait_for(timeout=10000)
    conferir("teclado: o Enter abre o balão (aria-expanded=\"true\")",
             balao.is_visible() and botao.get_attribute("aria-expanded") == "true")
    aba.keyboard.press("Escape")
    conferir("teclado: o Esc fecha e o foco volta ao \"i\"", balao.is_hidden() and aba.evaluate(FOCO_NO_I))


def conferir_o_cadastrar(aba, dados: dict, conferir) -> None:
    """Cadastrar: o "i" das duas tabelas das colunas lidas e o da conferência da lista."""
    colunas = situacoes_esperadas(aba, "empresa", "colunas")
    conferencia = situacoes_esperadas(aba, "empresa", "conferencia")
    # Envia a planilha e espera a leitura das colunas
    aba.set_input_files("#campo-arquivo", dados["planilha"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba.locator("[data-real-aceitar]:not([hidden])").wait_for(timeout=60000)
    # As colunas lidas ficam na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    marcadores_das_colunas = aba.locator("[data-legenda-dos-status='colunas']")
    conferir("Cadastrar: um \"i\" em cada tabela das colunas lidas", marcadores_das_colunas.count() == 2)
    conferir_o_i_da_grade(aba, marcadores_das_colunas.nth(0), aba.locator("[data-real-bloco-colunas] > .tabela-rolavel"),
                          colunas, "Cadastrar, as colunas das obrigatórias", conferir)
    # "Outras informações do arquivo" vem fechado: abre para ver a tabela de baixo
    aba.click("[data-real-bloco-colunas-opcionais] > summary")
    conferir_o_i_da_grade(aba, marcadores_das_colunas.nth(1),
                          aba.locator("[data-real-bloco-colunas-opcionais] .tabela-rolavel"), colunas,
                          "Cadastrar, as outras colunas", conferir)
    # A foto de um balão aberto, para conferir o visual
    marcadores_das_colunas.nth(0).locator("[data-botao-da-legenda]").click()
    aba.locator("#resultado-real").screenshot(path="storage/painel/legenda_dos_status.png")
    marcadores_das_colunas.nth(0).locator("[data-botao-da-legenda]").click()
    # Escolhe o campo da coluna em dúvida e aceita: a conferência da lista aparece
    aba.locator("[data-real-corpo-colunas] select[data-coluna='Vencimentos']").select_option("valor_renda")
    aba.click("[data-real-aceitar]")
    aba.wait_for_function("() => document.querySelector('[data-real-aceitar]').hidden", timeout=60000)
    bloco = aba.locator("[data-real-bloco-conferencia]")
    bloco.wait_for(state="visible", timeout=60000)
    # Sem pendência a conferência vem fechada: abre, com todas as pessoas
    if not bloco.evaluate("elemento => elemento.open"):
        aba.click("[data-real-bloco-conferencia] > summary")
    aba.uncheck("[data-real-so-pendencias]")
    aba.locator("[data-real-corpo-conferencia] > tr").first.wait_for(timeout=30000)
    conferir_o_i_da_grade(aba, aba.locator("[data-legenda-dos-status='conferencia']"),
                          aba.locator("[data-real-bloco-conferencia] .tabela-rolavel"), conferencia,
                          "Cadastrar, a conferência da lista", conferir)


def conferir_o_acompanhar(aba, endereco: str, conferir) -> None:
    """Acompanhar: o "i" da grade de funcionários (a legenda antiga saiu), o clique e o teclado."""
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    funcionarios = situacoes_esperadas(aba, "empresa", "funcionarios")
    conferir("Acompanhar: a legenda antiga dos status saiu", aba.locator("[data-legenda-status]").count() == 0)
    marcador = aba.locator("[data-legenda-dos-status='funcionarios']")
    conferir_o_i_da_grade(aba, marcador, aba.locator("[data-tabela-funcionarios]"), funcionarios,
                          "Acompanhar, os funcionários", conferir)
    # O contador "Mostrando..." é só texto: clicar nele não faz nada além de fechar o balão
    conferir_o_clique_e_o_teclado(aba, marcador, aba.locator("[data-contador-resultados]"), conferir)


def conferir_o_erro_da_rota(aba, endereco: str, conferir) -> None:
    """Com a rota da legenda em erro (500), o balão diz "Não foi possível carregar agora.", sem nenhum selo."""
    rota_da_legenda = "**/api/empresa/legenda_dos_status"
    aba.route(rota_da_legenda, lambda pedido: pedido.fulfill(status=500, body="erro"))
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    marcador = aba.locator("[data-legenda-dos-status='funcionarios']")
    marcador.locator("[data-botao-da-legenda]").click()
    marcador.locator(".balao-dos-status-aviso").wait_for(timeout=10000)
    balao = marcador.locator("[data-balao-da-legenda]")
    conferir("erro: o balão diz \"Não foi possível carregar agora.\", sem nenhum selo",
             AVISO_SEM_LEGENDA in balao.inner_text() and balao.locator(".selo").count() == 0)
    aba.unroute(rota_da_legenda)


def conferir_no_celular(navegador, endereco: str, erros_da_pagina: list, conferir) -> None:
    """No celular (390 × 844, com toque): o toque abre e fecha o balão, e ele cabe na largura da tela."""
    celular = navegador.new_page(viewport={"width": LARGURA_DO_CELULAR, "height": 844}, has_touch=True,
                                 is_mobile=True)
    celular.on("pageerror", lambda erro: erros_da_pagina.append(str(erro)))
    # Entra como a empresa (o mesmo caminho do apoio.entrar, nesta aba de celular)
    celular.goto(endereco + "/login.html")
    celular.fill("[name='usuario']", LOGIN_DA_EMPRESA)
    celular.fill("[name='senha']", SENHA_DE_TESTE)
    celular.click("button[type='submit']")
    celular.wait_for_url(lambda url: "login.html" not in url, timeout=20000)
    celular.goto(endereco + "/acompanhar.html")
    celular.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    marcador = celular.locator("[data-legenda-dos-status='funcionarios']")
    botao = marcador.locator("[data-botao-da-legenda]")
    balao = marcador.locator("[data-balao-da-legenda]")
    botao.scroll_into_view_if_needed()
    # O toque abre
    botao.tap()
    balao.locator(".item-do-balao-dos-status").first.wait_for(timeout=15000)
    caixa_do_balao = balao.bounding_box()
    conferir("celular: o toque abre o balão", balao.is_visible())
    conferir(f"celular: o balão cabe na tela de {LARGURA_DO_CELULAR} px (de {round(caixa_do_balao['x'])} a "
             f"{round(caixa_do_balao['x'] + caixa_do_balao['width'])} px)",
             caixa_do_balao["x"] >= 0 and caixa_do_balao["x"] + caixa_do_balao["width"] <= LARGURA_DO_CELULAR)
    # O toque de novo fecha
    botao.tap()
    conferir("celular: o segundo toque fecha o balão", balao.is_hidden())
    celular.close()


def conferir_o_inicio_do_banco(banco, endereco: str, conferir) -> None:
    """O Início do banco: o "i" da carteira."""
    banco.goto(endereco + "/banco_inicio.html")
    banco.locator("[data-tabela-carteira][data-dado-pronto]").wait_for(timeout=20000)
    empresas = situacoes_esperadas(banco, "banco", "empresas")
    conferir_o_i_da_grade(banco, banco.locator("[data-legenda-dos-status='empresas']"),
                          banco.locator("[data-tabela-carteira]"), empresas, "Início, a carteira", conferir)


def conferir_as_empresas(banco, endereco: str, conferir) -> None:
    """Empresas: o "i" da lista da Carteira, o da Visão geral (a legenda do fim saiu) e o dos Usuários."""
    banco.goto(endereco + "/banco_empresas.html?empresa=EMP001")
    banco.locator("[data-corpo-visao] tr").first.wait_for(timeout=20000)
    legendas_do_banco = banco.evaluate(BUSCAR_AS_LEGENDAS, "/api/banco/legenda_dos_status")
    conferir_o_i_da_grade(banco, banco.locator("[data-legenda-dos-status='empresas']"),
                          banco.locator("[data-lista-empresas]"), legendas_do_banco["empresas"],
                          "Empresas, a lista da Carteira", conferir)
    conferir("Visão geral: a legenda do fim da aba saiu", banco.locator("[data-legenda-status-visao]").count() == 0)
    conferir_o_i_da_grade(banco, banco.locator("[data-legenda-dos-status='funcionarios']"),
                          banco.locator("[data-visao-geral] .tabela-rolavel"), legendas_do_banco["funcionarios"],
                          "Visão geral, os funcionários", conferir)
    # A aba Usuários
    banco.click("[data-aba-ficha='usuarios']")
    banco.locator("[data-corpo-usuarios] tr").first.wait_for(timeout=20000)
    conferir_o_i_da_grade(banco, banco.locator("[data-legenda-dos-status='usuarios']"),
                          banco.locator("[data-conteudo-aba='usuarios'] .tabela-rolavel"), legendas_do_banco["usuarios"],
                          "Usuários da empresa", conferir)


def conferir_os_envios(banco, endereco: str, conferir) -> None:
    """Envios: o "i" da grade das pessoas do envio."""
    banco.goto(endereco + "/banco_envios.html")
    banco.locator("[data-corpo-pessoas] tr").first.wait_for(timeout=20000)
    pessoas = situacoes_esperadas(banco, "banco", "pessoas_do_envio")
    conferir_o_i_da_grade(banco, banco.locator("[data-legenda-dos-status='pessoas_do_envio']"),
                          banco.locator(".tabela-rolavel:has(.tabela-pessoas-envio)"), pessoas,
                          "Envios, as pessoas do envio", conferir)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Cadastrar, Acompanhar, o erro e o celular como a empresa; o Início, Empresas e Envios como o banco."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    conferir_o_cadastrar(aba, dados, conferir)
    conferir_o_acompanhar(aba, endereco, conferir)
    conferir_o_erro_da_rota(aba, endereco, conferir)
    conferir_no_celular(navegador, endereco, erros_da_pagina, conferir)
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_o_inicio_do_banco(banco, endereco, conferir)
    conferir_as_empresas(banco, endereco, conferir)
    conferir_os_envios(banco, endereco, conferir)
