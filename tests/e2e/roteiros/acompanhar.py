"""Roteiro: Acompanhar cadastros como o lugar de resolver tudo (ADR-74).

O que ele confere:
- "Pronto para enviar ao banco": o envio sem pendência, com a lista (CPF inteiro) e "Conferi a lista";
- enviar volta com o recado de recebimento, e o bloco some;
- um Word com uma pessoa sem CPF: o cartão é uma conversa com a IA, com a pergunta
  num balão do agente; "Não cadastrar esta pessoa" e "Deixar em branco" não são respostas rápidas; escrito na
  caixa, "não cadastrar esta pessoa" pede confirmação e, com o "Sim", tira o cartão;
- "Descartar este envio": a janela explica o que acontece; "Continuar" desiste; "Sim, descartar" descarta, o aviso
  aparece e o cartão mostra quem descartou e quando.
Desde o ADR-138, a conversa de cada cartão abre no painel do lado: o roteiro abre o cartão e usa o painel.
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, abrir_janela_de_cadastro, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa, fechar_a_conversa_aberta

DESCRICAO = "Acompanhar: enviar os prontos ao banco, cartão da pergunta da IA, não cadastrar e trocar o arquivo"


def preparar() -> dict:
    """Aurora com a carga inicial cadastrada e a inclusão pronta para o banco; e o Word de exemplo."""
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro
    from tests.e2e.apoio import criar_usuarios_de_teste, criar_word_de_exemplo
    from tests.test_correcao import ENVIOS, RAIZ, _escolhas_do_gabarito, _gabarito, busca_falsa
    from tests.test_planejamento import homologar
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (para corrigir tudo e cadastrar a carga inicial)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    homologar(conexao, "aurora_carga_inicial", verdade)
    # A inclusão enviada e com as colunas aceitas, sem pendências: pronta para o banco
    gabarito = _gabarito("aurora_inclusao")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, gabarito["arquivo"],
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                _escolhas_do_gabarito(gabarito), busca=busca_falsa)
    conexao.close()
    return {"word": criar_word_de_exemplo()}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques em Acompanhar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # 1. Pronto para enviar ao banco: seção verde, e a lista inteira numa janela antes do envio
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-prontos]").wait_for(state="visible", timeout=20000)
    fundo = aba.evaluate("() => getComputedStyle(document.querySelector('[data-prontos]')).backgroundColor")
    conferir(f"a seção 'Pronto para enviar' tem o fundo verde clarinho (na tela: {fundo})", fundo == "rgb(227, 244, 234)")
    conferir("o botão 'Conferir a lista e enviar para o banco' aparece",
             aba.locator("[data-abrir-conferencia-prontos]").is_visible())
    # O "Ir para" do topo leva à seção: "Prontos para enviar", com o número de envios prontos
    atalho = aba.locator("[data-atalho-prontos]")
    conferir(f"o 'Ir para' tem 'Prontos para enviar' (na tela: {atalho.inner_text()})",
             atalho.is_visible() and "Prontos para enviar" in atalho.inner_text()
             and aba.inner_text("[data-atalho-contagem-prontos]") == "1" and atalho.get_attribute("href") == "#prontos")
    # A ficha de um cadastrado: o histórico vem das etapas reais do envio, com a data e quem enviou
    aba.locator("[data-corpo-tabela] .botao-nome").first.click()
    aba.locator("#janela-ficha[open]").wait_for(timeout=10000)
    aba.wait_for_function("() => document.getElementById('janela-ficha-historico').innerText.includes('Arquivo carregado ·')",
                          timeout=15000)
    historico = aba.inner_text("#janela-ficha-historico")
    conferir("a ficha mostra o histórico real (Arquivo carregado, com quem enviou, e a aprovação das contas)",
             "(por " in historico and "Aprovação das contas enviadas ·" in historico)
    aba.keyboard.press("Escape")
    # A janela da conferência: a grade completa do parâmetro, o aceite e o envio
    aba.click("[data-abrir-conferencia-prontos]")
    aba.locator("#janela-conferir-envio[open] .linha-de-grupos").wait_for(timeout=20000)
    grade = aba.inner_text("#janela-conferir-envio [data-grades-dos-prontos]")
    conferir("a janela mostra a grade completa, com o CPF inteiro",
             "***" not in grade and re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", grade) is not None)
    marcas = aba.locator("#janela-conferir-envio .marca-obrigatorio").count()
    conferir(f"a grade da janela tem os campos obrigatórios marcados ({marcas} marcas)", marcas > 20)
    conferir("o envio da janela diz 1 envio",
             "Enviar ao banco (1 envio(s)" in aba.inner_text("[data-enviar-prontos]"))
    conferir("botão desligado sem 'Conferi a lista'", aba.locator("[data-enviar-prontos]").is_disabled())
    aba.locator("#janela-conferir-envio").screenshot(path="storage/painel/conferir_e_enviar.png")
    aba.check("[data-conferi-prontos]")
    aba.click("[data-enviar-prontos]")
    aba.wait_for_url("**acompanhar.html?enviado=*", timeout=30000)
    conferir("enviado: volta com o recado de recebimento",
             "estão em análise pelo banco" in aba.inner_text("[data-aviso-recebido-texto]"))
    aba.wait_for_timeout(1500)
    conferir("o bloco some quando não há mais nada pronto", aba.locator("[data-prontos]").is_hidden())
    conferir("o atalho 'Prontos para enviar' também some", aba.locator("[data-atalho-prontos]").is_hidden())
    # 2. Um Word com a Luíza sem CPF: o cartão junta a pergunta da IA à correção
    quadro = abrir_janela_de_cadastro(aba)
    quadro.locator("#campo-arquivo").set_input_files(dados["word"])
    quadro.locator("[data-real-aceitar]").wait_for(state="visible", timeout=60000)
    quadro.locator("[data-real-aceitar]").click()
    aba.wait_for_url("**aviso=colunas_aceitas", timeout=60000)
    cartao = aba.locator("[data-pendencia]", has_text="Luíza").filter(has_text="CPF").first
    cartao.wait_for(timeout=20000)
    # A conversa do cartão, no painel do lado (ADR-138)
    painel = abrir_a_conversa(aba, cartao)
    conferir("o cartão da Luíza pergunta pelo CPF num balão do agente",
             "✦ Agente de validação" in painel.locator("[data-pergunta-da-pendencia]").inner_text())
    conferir("as respostas rápidas não têm 'Deixar este campo em branco' nem 'Não cadastrar esta pessoa'",
             painel.locator("text=Deixar este campo em branco").count() == 0
             and painel.locator("[data-sugestao-da-conversa]", has_text="Não cadastrar").count() == 0)
    # A conversa abre numa janela por cima da tela: fecha antes de mexer no filtro, atrás dela
    fechar_a_conversa_aberta(aba)
    # O filtro por arquivo: escolher o Word mostra só as pendências dele e o aviso de que ele
    # só fica disponível para envio quando todas forem resolvidas
    conferir("o filtro por arquivo aparece", aba.locator("[data-bloco-filtro-arquivo]").is_visible())
    opcoes_de_arquivo = aba.locator("[data-filtro-arquivo-pendencias] option").all_inner_texts()
    opcao_do_word = [opcao for opcao in opcoes_de_arquivo if ".docx" in opcao]
    conferir(f"o Word aparece no filtro com a contagem (opções: {opcoes_de_arquivo})",
             len(opcao_do_word) == 1 and "pendência" in opcao_do_word[0])
    aba.select_option("[data-filtro-arquivo-pendencias]", label=opcao_do_word[0])
    aviso = aba.inner_text("[data-aviso-arquivo-pendente]")
    conferir(f"o aviso: só fica disponível para envio depois de resolver tudo (na tela: {aviso[:90]})",
             "só fica disponível para envio" in aviso)
    visiveis = aba.locator("[data-pendencia]:visible").all_inner_texts()
    conferir("só as pendências do Word aparecem", len(visiveis) > 0
             and all(".docx" in cartao_visivel for cartao_visivel in visiveis))
    aba.locator("#pendencias").screenshot(path="storage/painel/pendencias_por_arquivo.png")
    aba.select_option("[data-filtro-arquivo-pendencias]", "")
    aba.locator("button", has_text="Descartar este envio").first.wait_for(timeout=20000)
    conferir("o envio tem 'Descartar este envio'", True)
    quantos_antes = aba.locator("[data-pendencia]", has_text="Luíza").count()
    painel = abrir_a_conversa(aba, cartao)
    painel.locator("[data-caixa-da-conversa]").fill("não cadastrar esta pessoa")
    painel.locator("button[type=submit]").click()
    # Não mandar a pessoa pede confirmação: o "Sim" fica dentro do balão do agente
    painel.locator("[data-confirmar-sim]").click(timeout=30000)
    # Confirmado, as pendências da Luíza saem das abertas (o cartão resolvido fica verde à vista)
    aba.wait_for_function(
        "() => Array.from(document.querySelectorAll('[data-pendencia]:not([data-resolvido-a-vista])'))"
        ".filter(cartao => cartao.innerText.includes('Luíza')).length < " + str(quantos_antes),
        timeout=30000)
    conferir("'não cadastrar esta pessoa', confirmado, tira as pendências da Luíza das abertas",
             aba.locator("[data-resolvido-a-vista]", has_text="Luíza").count() == 1)
    # A conversa resolvida continua na janela: fecha antes de descartar o envio, atrás dela
    fechar_a_conversa_aberta(aba)
    # 3. Descartar: a janela explica; "Continuar" desiste; "Sim, descartar" descarta (espera as listas recarregarem)
    aba.wait_for_load_state("networkidle")
    aba.wait_for_timeout(1500)
    descartar = aba.locator("button", has_text="Descartar este envio").first
    descartar.click()
    janela = aba.locator("dialog[open]", has_text="Descartar esta leitura?")
    janela.wait_for(timeout=15000)
    explicacao = janela.inner_text()
    conferir("a janela explica o que acontece (nada foi ao banco; fica como Descartado; dá para mandar outro)",
             "Nada foi enviado ao banco" in explicacao and "Descartado" in explicacao and "outro arquivo" in explicacao)
    janela.locator("text=Continuar com este envio").click()
    conferir("'Continuar' fecha a janela sem descartar",
             aba.locator("dialog[open]").count() == 0 and descartar.is_visible())
    descartar.click()
    janela.wait_for(timeout=15000)
    janela.locator("text=Sim, descartar").click()
    aba.locator("[data-aviso-descartado]:not([hidden])").wait_for(timeout=15000)
    conferir("depois de descartar, o aviso aparece em cima dos envios", True)
    aba.locator(".nota-do-descarte").first.wait_for(timeout=15000)
    conferir("o cartão mostra quem descartou e quando",
             "Descartado por " + LOGIN_DA_EMPRESA in aba.locator(".nota-do-descarte").first.inner_text())
    aba.close()
