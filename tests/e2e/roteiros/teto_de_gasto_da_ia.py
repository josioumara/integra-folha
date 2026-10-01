"""Roteiro: a página "Teto de gasto da IA" do Portal Interno e o botão "Tentar de novo" da empresa (ADR-139).

O teto é configurável: quando ele é atingido, o especialista do banco o ajusta nesta página. O acesso fica no painel
dos dados da IA (Acompanhamento dos agentes), com uma faixa no alto das outras telas enquanto a IA estiver pausada.

O preparar() deixa o banco do roteiro com o gasto de hoje (US$ 25) acima dos dois tetos (US$ 20) e um envio da
Aurora parado pelo teto (a IA pausada no Interpretador). O que ele confere, no Chrome de verdade:
- a empresa: o envio pausado mostra o recado com o botão "Tentar de novo"; o clique, com a IA ainda pausada, devolve
  o recado e o envio continua guardado (o botão continua lá);
- o banco: a faixa amarela no Início diz que o teto do dia foi atingido e leva à página; no Acompanhamento dos agentes,
  a mesma faixa avisa (o cartão do teto de lá está oculto nesta versão, ADR-148), com o link "Ver e ajustar o teto";
- a página: "pausada", desde quando, o gasto × os tetos e "1 envio" esperando; o histórico vazio;
- um teto negativo é recusado com o motivo; um valor abaixo do gasto mostra o aviso antes de salvar;
- salvar o teto do mês (100) mantém a pausa pelo dia; salvar o teto do dia (30) libera: "funcionando", o aviso verde
  diz que o envio volta para a análise, o histórico mostra as 2 mudanças (quem e de → para) e, em instantes, nenhum
  envio espera mais;
- a faixa some do Início, e o envio da empresa voltou sozinho (o botão sumiu), sem ninguém clicar.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = ("Teto de gasto da IA: a empresa vê o envio pausado e o botão; o banco vê a faixa, abre a página, ajusta os "
             "tetos, e o envio volta sozinho")

# Os seletores da página do teto
SELO = "[data-selo-situacao-teto]"
SITUACAO = "[data-texto-situacao-teto]"
ENVIOS_ESPERANDO = "[data-envios-esperando]"
CAMPO_DIA = "[data-campo-teto='dia']"
CAMPO_MES = "[data-campo-teto='mes']"
LINHAS_DO_HISTORICO = "[data-corpo-historico-teto] tr"


def preparar() -> dict:
    """Os usuários, o gasto de hoje acima dos tetos e um envio da Aurora parado pelo teto."""
    from pathlib import Path

    from services import auth, cadastro, mapeamentos, teto_de_gasto
    from tests.e2e.apoio import criar_planilha_com_endereco, criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # O Interpretador encontra a IA pausada pelo teto (como o cliente de IA faz quando o gasto passa do teto)
    interpretar_de_verdade = mapeamentos.interpretar_processamento

    def interpretar_com_a_ia_pausada(*argumentos, **argumentos_nomeados):
        """O trabalho do Interpretador que não chega à IA."""
        raise teto_de_gasto.TetoDeGastoAtingido("dia")
    mapeamentos.interpretar_processamento = interpretar_com_a_ia_pausada
    try:
        caminho = Path(criar_planilha_com_endereco())
        leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, caminho.read_bytes(), caminho.name)
    finally:
        mapeamentos.interpretar_processamento = interpretar_de_verdade
    # O gasto de hoje passa dos dois tetos (US$ 20 cada)
    teto_de_gasto.somar_no_dia(conexao, 25.0)
    conexao.close()
    return {"processamento_id": leitura["processamento_id"], "etapa": leitura["etapa"]}


def conferir_a_empresa_com_a_ia_pausada(navegador, endereco: str, dados: dict, conferir, erros_da_pagina) -> None:
    """Parte 1: a empresa vê o recado e o botão; o clique, com a IA pausada, não muda nada."""
    conferir("o preparar deixou o envio parado em 'tentar de novo'", dados["etapa"] == "aguardar_nova_tentativa")
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html?envio=" + dados["processamento_id"])
    botao = aba.locator("[data-real-tentar-de-novo]")
    botao.wait_for(state="visible", timeout=20000)
    recado = aba.inner_text("[data-real-erro]")
    conferir("o envio pausado mostra o recado com o botão 'Tentar de novo'",
             "Tentar de novo" in recado and "fica guardado" in recado and botao.is_visible())
    conferir("a frase da etapa diz que o envio está guardado",
             "Seu envio está guardado" in aba.inner_text("[data-real-subtitulo]"))
    botao.click()
    aba.wait_for_function("""() => document.querySelector('[data-real-erro]').textContent.includes('banco já foi avisado')""",
                          timeout=15000)
    conferir("com a IA ainda pausada, o clique devolve o recado e o botão continua (o envio segue guardado)",
             botao.is_visible())
    aba.close()


def conferir_a_faixa_e_o_painel(aba, endereco: str, conferir) -> None:
    """Parte 2: a faixa amarela no Início e a mesma faixa no Acompanhamento dos agentes (o cartão do teto de lá está
    oculto nesta versão)."""
    aba.goto(endereco + "/banco_inicio.html")
    faixa = aba.locator("[data-faixa-teto-da-ia]")
    faixa.wait_for(state="visible", timeout=15000)
    conferir("a faixa do Início diz que o teto do dia foi atingido e até quando",
             "teto de gasto do dia foi atingido" in faixa.inner_text() and "meia-noite" in faixa.inner_text())
    aba.goto(endereco + "/banco_agentes.html")
    # O cartão do teto está oculto nesta versão (ADR-148): quem avisa, também aqui, é a faixa, com o link para a página
    faixa_dos_agentes = aba.locator("[data-faixa-teto-da-ia]")
    faixa_dos_agentes.wait_for(state="visible", timeout=15000)
    conferir("no Acompanhamento dos agentes, a faixa avisa e leva à página ('Ver e ajustar o teto')",
             faixa_dos_agentes.locator("a").get_attribute("href") == "banco_teto_da_ia.html")
    conferir("no Acompanhamento dos agentes, o cartão do teto está oculto",
             aba.locator("[data-link-ajustar-teto]").is_hidden())
    aba.goto(endereco + "/banco_inicio.html")
    aba.locator("[data-faixa-teto-da-ia] a").click()
    aba.wait_for_url("**/banco_teto_da_ia.html", timeout=10000)


def conferir_a_pagina_pausada(aba, conferir) -> None:
    """Parte 3: a página mostra a pausa, o gasto × os tetos e o envio esperando."""
    aba.wait_for_function("""() => document.querySelector('[data-envios-esperando]').hasAttribute('data-dado-pronto')""",
                          timeout=15000)
    conferir("o título da página é 'Teto de custo com agentes'",
             aba.inner_text("h1.titulo-pagina").strip().startswith("Teto de custo com agentes"))
    conferir("o selo diz 'pausados' e a frase diz desde quando e que o teto do dia foi atingido",
             aba.inner_text(SELO).strip() == "pausados" and "pausados desde" in aba.inner_text(SITUACAO)
             and "teto do dia foi atingido" in aba.inner_text(SITUACAO))
    conferir("o gasto de hoje × o teto do dia: 'US$ 25,00 de US$ 20,00'",
             aba.inner_text("[data-gasto-teto='dia']").strip() == "US$ 25,00 de US$ 20,00")
    conferir("1 envio de empresa esperando (só o número)", aba.inner_text(ENVIOS_ESPERANDO).strip() == "1 envio")
    conferir("o histórico começa vazio", "Nenhuma mudança ainda" in aba.inner_text("[data-tabela-historico-teto]"))
    conferir("os campos começam com os tetos que valem (20)",
             aba.input_value(CAMPO_DIA) == "20" and aba.input_value(CAMPO_MES) == "20")


def conferir_as_recusas_e_a_previa(aba, conferir) -> None:
    """Parte 4: um teto negativo é recusado; um valor abaixo do gasto avisa antes de salvar."""
    aba.fill(CAMPO_DIA, "-5")
    aba.click("[data-salvar-teto='dia']")
    aba.locator("[data-erro-teto]:not([hidden])").wait_for(timeout=10000)
    conferir("um teto negativo é recusado ('maior que zero')", "maior que zero" in aba.inner_text("[data-erro-teto]"))
    aba.fill(CAMPO_DIA, "10")
    previa = aba.locator("[data-previa-teto='dia']")
    conferir("com US$ 10 (abaixo do gasto de US$ 25), o aviso aparece antes de salvar",
             previa.is_visible() and "não passa do gasto de hoje" in previa.inner_text())


def conferir_o_ajuste(aba, conferir) -> None:
    """Parte 5: o teto do mês sobe (a pausa pelo dia continua); o do dia sobe e libera a IA."""
    aba.fill(CAMPO_MES, "100")
    aba.click("[data-salvar-teto='mes']")
    aba.wait_for_function("""() => document.querySelector('[data-aviso-teto-texto]').textContent.includes('do mês')""",
                          timeout=15000)
    conferir("salvo o teto do mês, os agentes continuam pausados pelo teto do dia",
             aba.inner_text(SELO).strip() == "pausados")
    aba.fill(CAMPO_DIA, "30")
    aba.click("[data-salvar-teto='dia']")
    aba.wait_for_function("""() => document.querySelector('[data-aviso-teto-texto]').textContent.includes('do dia')""",
                          timeout=15000)
    conferir("salvo o teto do dia, o selo diz 'funcionando'", aba.inner_text(SELO).strip() == "funcionando")
    conferir("o aviso verde diz que os agentes voltaram e o envio volta para a análise",
             "Os agentes voltaram: 1 envio volta para a análise" in aba.inner_text("[data-aviso-teto-texto]"))
    linhas = aba.locator(LINHAS_DO_HISTORICO)
    primeira = linhas.first.inner_text()
    conferir("o histórico mostra as 2 mudanças, a do dia no alto, com quem mudou e 'US$ 20,00 → US$ 30,00'",
             linhas.count() == 2 and LOGIN_DO_BANCO in primeira and "US$ 20,00 → US$ 30,00" in primeira)
    # A retomada roda depois da resposta: em instantes, nenhum envio espera mais
    for _tentativa in range(10):
        aba.reload()
        aba.wait_for_function("""() => document.querySelector('[data-envios-esperando]').hasAttribute('data-dado-pronto')""",
                              timeout=15000)
        if aba.inner_text(ENVIOS_ESPERANDO).strip() == "0 envios":
            break
        aba.wait_for_timeout(1000)
    conferir("em instantes, nenhum envio espera mais ('0 envios')", aba.inner_text(ENVIOS_ESPERANDO).strip() == "0 envios")


def conferir_depois_da_volta(navegador, aba, endereco: str, dados: dict, conferir, erros_da_pagina) -> None:
    """Parte 6: a faixa sumiu do Início, e o envio da empresa voltou sozinho (sem o botão)."""
    aba.goto(endereco + "/banco_inicio.html")
    aba.wait_for_timeout(1500)
    conferir("a faixa sumiu do Início", not aba.locator("[data-faixa-teto-da-ia]").is_visible())
    aba_da_empresa = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba_da_empresa.goto(endereco + "/cadastrar.html?envio=" + dados["processamento_id"])
    aba_da_empresa.locator("[data-real-etapa]").wait_for(timeout=20000)
    aba_da_empresa.wait_for_function("""() => document.querySelector('[data-real-etapa]').textContent.trim() !== ''""",
                                     timeout=20000)
    conferir("o envio voltou sozinho para a análise: o botão 'Tentar de novo' sumiu",
             not aba_da_empresa.locator("[data-real-tentar-de-novo]").is_visible())
    aba_da_empresa.close()


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """A empresa com a IA pausada; o banco ajusta o teto; o envio volta sozinho."""
    conferir_a_empresa_com_a_ia_pausada(navegador, endereco, dados, conferir, erros_da_pagina)
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_a_faixa_e_o_painel(aba, endereco, conferir)
    conferir_a_pagina_pausada(aba, conferir)
    conferir_as_recusas_e_a_previa(aba, conferir)
    conferir_o_ajuste(aba, conferir)
    conferir_depois_da_volta(navegador, aba, endereco, dados, conferir, erros_da_pagina)
    aba.close()
