"""Roteiro: cada pendência é uma conversa com a IA, com respostas rápidas.

O que ele confere (com a IA simulada, sem custo):
- o cartão: o nome e o campo no alto; a pergunta num balão do agente ("✦ Agente de validação") com o CPF lido; as respostas rápidas
  (pílulas); a caixa "Responda ao agente..." com o botão de enviar (➤, "Enviar"); a linha "arquivo · dd/mm"; nada de
  "Conversar com a IA", "O que fazer" nem "Lido no arquivo";
- uma mensagem sobre outro dado (o salário) vira um balão "você" e é recusada num balão âmbar, e nada muda;
- com mais de 4 balões, os antigos se recolhem em "Ver a conversa inteira (N)";
- a mensagem com o CPF certo mostra o balão com os pontinhos e "Processando… N s"; a IA já corrige, e o cartão fica
  no lugar, verde ("✓ Resolvida"), com o "Pronto: ..." no chat e o Desfazer (ele sai quando a pessoa vai para outro
  cartão, ver o roteiro pendencias_em_grupo); o Desfazer traz a pendência de volta, aberta;
- "Não cadastrar esta pessoa" e "Deixar este campo em branco" não são respostas rápidas; escrito na caixa, "não
  cadastrar esta pessoa" pede confirmação num balão do agente com dois botões: "Cancelar" não muda nada; "Sim, não
  cadastrar" resolve;
- o rodapé fixo tem os dois botões de descarte: com dois arquivos, a janela pede qual; com um, diz o nome dele; o
  segundo botão abre a janela "Cadastrar funcionários" depois de descartar;
- na tela Cadastrar, a conferência mostra o mesmo cartão-conversa.
Desde o ADR-138, em Acompanhar a conversa de cada cartão abre no painel do lado: o roteiro abre o cartão e usa o
painel.
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa, fechar_a_conversa_aberta

DESCRICAO = "Pendências por conversa: balões, respostas rápidas, IA corrige, Desfazer, recusa, conversa longa e descarte"
# Os CPFs com o dígito verificador errado que a preparação põe em três pessoas (um diferente para cada uma: CPF
# repetido viraria outra pendência, a de pessoa repetida)
CPF_ERRADO = "123.456.789-00"
CPF_ERRADO_DO_NAO_CADASTRAR = "987.654.321-99"
CPF_ERRADO_DO_SEGUNDO_ENVIO = "111.444.777-00"
# O CPF certo que a empresa conta na conversa (válido e inventado)
CPF_CERTO = "529.982.247-25"


def somente_digitos(texto: str) -> str:
    """Só os números de um texto. Ex.: "123.456.789-00" → "12345678900"."""
    return re.sub(r"\D", "", texto)


def cpf_no_texto(cpf: str):
    """Uma expressão que acha o CPF num texto, com ou sem pontos e traço. Ex.: "123.456.789-00" acha "12345678900"."""
    digitos = somente_digitos(cpf)
    return re.compile(digitos[0:3] + r"\.?" + digitos[3:6] + r"\.?" + digitos[6:9] + r"-?" + digitos[9:11])


def por_cpfs_errados(conexao, gabarito_do_envio: str, cpfs_errados: list[str]) -> dict:
    """Envia um arquivo da Aurora, aceita as colunas e põe um CPF errado em cada uma das primeiras pessoas.

    Recebe: conexao; o nome do envio de exemplo (ex.: "aurora_carga_inicial"); os CPFs errados, um por pessoa.
    Devolve: {processamento_id, nome_arquivo, nomes}: o envio e as pessoas que ficaram com CPF errado, na ordem.
    """
    from services import acompanhamento, cadastro, correcoes
    from tests.test_correcao import ENVIOS, _escolhas_do_gabarito, _gabarito, busca_falsa
    gabarito = _gabarito(gabarito_do_envio)
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, gabarito["arquivo"],
                                      busca=busca_falsa)
    leitura = cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                          _escolhas_do_gabarito(gabarito), busca=busca_falsa)
    # As primeiras pessoas do envio ficam com CPF de dígito errado (cada uma vira a pendência "CPF inválido")
    registros = correcoes.dados_atuais(conexao, leitura["processamento_id"]).registros
    nomes = []
    for posicao, cpf_errado in enumerate(cpfs_errados):
        pessoa = registros[posicao]
        acompanhamento.corrigir_pendencia(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                          pessoa["_linha"], "cpf", cpf_errado, "Preparação do roteiro")
        nomes.append(pessoa["nome_completo"])
    return {"processamento_id": leitura["processamento_id"], "nome_arquivo": gabarito["arquivo"], "nomes": nomes}


def preparar() -> dict:
    """Dois envios da Aurora: o primeiro com duas pessoas de CPF errado, o segundo com uma.

    Devolve: {"primeiro": ..., "segundo": ...} (ver por_cpfs_errados).
    """
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    primeiro = por_cpfs_errados(conexao, "aurora_carga_inicial", [CPF_ERRADO, CPF_ERRADO_DO_NAO_CADASTRAR])
    segundo = por_cpfs_errados(conexao, "aurora_inclusao", [CPF_ERRADO_DO_SEGUNDO_ENVIO])
    conexao.close()
    return {"primeiro": primeiro, "segundo": segundo}


def cartao_do_cpf_errado(aba, nome: str, cpf_errado: str):
    """O cartão da pendência do CPF errado de uma pessoa (pelo nome e pelo CPF lido)."""
    return aba.locator("[data-pendencia]", has_text=nome).filter(has_text=cpf_no_texto(cpf_errado))


def conferir_o_cartao_e_a_conversa(aba, dados: dict, conferir) -> None:
    """O cartão-conversa, a recusa de outro dado num balão âmbar e a conversa longa que se recolhe."""
    nome = dados["primeiro"]["nomes"][0]
    cartao = cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first
    cartao.wait_for(timeout=30000)
    # A conversa do cartão, no painel do lado (ADR-138)
    painel = abrir_a_conversa(aba, cartao)
    pergunta = painel.locator("[data-pergunta-da-pendencia]")
    conferir(f"a pergunta vem num balão do agente, com o selo e o CPF lido (na tela: {pergunta.inner_text()})",
             "balao-ia" in pergunta.get_attribute("class") and "✦ Agente de validação" in pergunta.inner_text()
             and somente_digitos(CPF_ERRADO) in somente_digitos(pergunta.inner_text())
             and pergunta.inner_text().strip().endswith("?"))
    # O título diz o ajuste, o campo e de quem (ADR-120), sem nome técnico, com o botão da ficha
    titulo = cartao.locator(".ajuste-titulo").inner_text()
    conferir(f"o título diz o ajuste, o campo e de quem (na tela: {titulo})",
             titulo == f'Ajuste na informação "CPF" de {nome}' and "_" not in titulo
             and cartao.locator(".ajuste-cabecalho [data-ver-ficha]").count() == 1)
    origem = cartao.locator(".ajuste-origem").inner_text()
    conferir(f"embaixo, o arquivo e o dia (na tela: {origem})",
             re.fullmatch(re.escape(dados["primeiro"]["nome_arquivo"]) + r" · \d{2}/\d{2}", origem) is not None)
    conferir("'Não cadastrar esta pessoa' e 'Deixar este campo em branco' não são respostas rápidas",
             painel.locator("[data-sugestao-da-conversa]", has_text="Não cadastrar").count() == 0
             and painel.locator("[data-sugestao-da-conversa]", has_text="Deixar este campo em branco").count() == 0)
    texto_do_cartao = cartao.inner_text() + painel.inner_text()
    conferir("sem 'Conversar com a IA', 'O que fazer' nem 'Lido no arquivo'",
             all(sobra not in texto_do_cartao for sobra in ["Conversar com a IA", "O que fazer", "Lido no arquivo"]))
    caixa = painel.locator("[data-caixa-da-conversa]")
    enviar = painel.locator("button[type=submit]")
    conferir("a caixa 'Responda ao agente...' e o botão de enviar em ícone, com o nome 'Enviar'",
             caixa.is_visible() and caixa.get_attribute("placeholder") == "Responda ao agente..."
             and enviar.is_visible() and enviar.get_attribute("aria-label") == "Enviar" and enviar.inner_text() == "➤")
    aba.locator("#pendencias").screenshot(path="storage/painel/pendencias_conversa_com_respostas_rapidas.png")
    # Outro dado: o balão "você" e a recusa num balão âmbar; nada muda
    caixa.fill("Aproveita e muda o salário dele para 9.000,00")
    enviar.click()
    aba.locator(".fala-recusada").first.wait_for(timeout=30000)
    conferir("a mensagem vira um balão 'você' à direita",
             painel.locator(".balao-voce").count() == 1 and "você" in painel.locator(".balao-voce").inner_text())
    conferir("a mensagem sobre o salário é recusada num balão âmbar",
             painel.locator(".balao-ia.fala-recusada").count() == 1 and aba.locator(".mudanca-da-ia").count() == 0)
    conferir("depois da recusa, a pendência continua", cartao_do_cpf_errado(aba, nome, CPF_ERRADO).count() == 1)
    # Mais uma pergunta: 5 balões, e os mais antigos se recolhem (a conversa continua no painel)
    cartao = painel
    cartao.locator("[data-caixa-da-conversa]").fill("Por que isso é um erro?")
    cartao.locator("button[type=submit]").click()
    botao_da_conversa = cartao.locator("[data-conversa-inteira]")
    botao_da_conversa.wait_for(timeout=30000)
    conferir(f"com 5 balões, os antigos se recolhem (na tela: {botao_da_conversa.inner_text()})",
             botao_da_conversa.inner_text() == "Ver a conversa inteira (5)"
             and cartao.locator(".historico-conversa-ia .balao").count() == 4
             and cartao.locator("[data-pergunta-da-pendencia]").count() == 0)
    botao_da_conversa.click()
    conferir("'Ver a conversa inteira' mostra os 5, com a pergunta de volta",
             cartao.locator(".historico-conversa-ia .balao").count() == 5
             and cartao.locator("[data-pergunta-da-pendencia]").count() == 1)


def conferir_a_correcao_e_o_desfazer(aba, dados: dict, conferir) -> None:
    """O CPF certo pela conversa: o contador, a pendência resolvida, o aviso e o Desfazer."""
    nome = dados["primeiro"]["nomes"][0]
    # A conversa do cartão, no painel do lado (ADR-138)
    painel = abrir_a_conversa(aba, cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first)
    conversa = painel.locator(".conversa-ia-pendencia")
    # Segura a resposta da IA um instante, para ver o contador andar
    pedidos_segurados = []
    aba.route("**/assistente", lambda rota: pedidos_segurados.append(rota))
    conversa.locator("[data-caixa-da-conversa]").fill("O certo é " + CPF_CERTO)
    conversa.locator("button[type=submit]").click()
    contador = aba.locator("[data-contador-processando]")
    contador.wait_for(timeout=10000)
    # O contador passa de 0 para 1 s em cerca de um segundo (até 5 s de folga, para uma máquina lenta)
    aba.wait_for_function("() => /Processando… [1-9]/.test(document.querySelector('[data-contador-processando]')"
                          ".innerText)", timeout=5000)
    conferir(f"enquanto a IA trabalha, o contador anda (na tela: {contador.inner_text()})",
             re.search(r"Processando… [1-9]\d* s", contador.inner_text()) is not None)
    conferir("a caixa fica parada enquanto espera", conversa.locator("[data-caixa-da-conversa]").is_disabled())
    pedidos_segurados[0].continue_()
    aba.unroute("**/assistente")
    # A IA corrigiu: o cartão fica no lugar, verde, com o que mudou no chat e o Desfazer
    resolvido = aba.locator("[data-lista-pendencias] [data-resolvido-a-vista]", has_text=nome)
    resolvido.wait_for(timeout=30000)
    painel.locator("[data-desfazer-mudanca]").wait_for(timeout=30000)
    pronto = painel.locator(".mudanca-da-ia").last.inner_text()
    conferir(f"o cartão fica na tela, verde, com o CPF novo no chat (na tela: {pronto[:120]})",
             "✓ Resolvida" in resolvido.inner_text() and "Pronto:" in pronto
             and somente_digitos(CPF_CERTO) in somente_digitos(pronto)
             and painel.locator("[data-desfazer-mudanca]").count() == 1)
    conferir("resolvido, ele já não conta como aberto nem tem a caixa para responder",
             painel.locator("[data-caixa-da-conversa]").is_hidden()
             and aba.inner_text("[data-contagem-tipo='abertas']")
             == "(" + aba.inner_text("[data-total-pendencias]") + ")")
    aba.locator("#pendencias").screenshot(path="storage/painel/pendencias_resolvido_agora.png")
    # Desfazer: a pendência volta a ficar aberta, com o CPF de antes
    painel.locator("[data-desfazer-mudanca]").click()
    resolvido.wait_for(state="detached", timeout=30000)
    cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first.wait_for(timeout=30000)
    conferir("o Desfazer traz a pendência de volta, aberta",
             somente_digitos(CPF_ERRADO)
             in somente_digitos(cartao_do_cpf_errado(aba, nome, CPF_ERRADO).first.inner_text()))
    conversa_de_volta = painel.locator(".conversa-ia-pendencia")
    conferir("a conversa volta com o histórico, marcando o Desfeito",
             "Desfeito" in conversa_de_volta.inner_text())


def pedir_para_nao_cadastrar(cartao):
    """Escreve "não cadastrar esta pessoa" na caixa e espera a pergunta de confirmação do agente. Devolve o balão."""
    cartao.locator("[data-caixa-da-conversa]").fill("não cadastrar esta pessoa")
    cartao.locator("button[type=submit]").click()
    balao = cartao.locator(".balao-ia:has([data-confirmar-sim])")
    balao.wait_for(timeout=30000)
    return balao


def conferir_o_nao_cadastrar(aba, dados: dict, conferir) -> None:
    """ "Não cadastrar esta pessoa" pede confirmação: "Cancelar" não muda nada; "Sim" resolve (a segunda pessoa do
    primeiro envio)."""
    nome = dados["primeiro"]["nomes"][1]
    cartao = cartao_do_cpf_errado(aba, nome, CPF_ERRADO_DO_NAO_CADASTRAR).first
    cartao.wait_for(timeout=30000)
    # O cartão da lista, pela chave; a conversa dele, no painel do lado (ADR-138)
    cartao_da_lista = aba.locator("[data-chave-pendencia='" + cartao.get_attribute("data-chave-pendencia") + "']")
    cartao = abrir_a_conversa(aba, cartao_da_lista)
    # 1. Não cadastrar → a pergunta de confirmação, com os dois botões dentro do balão do agente; nada muda ainda
    balao = pedir_para_nao_cadastrar(cartao)
    conferir(f"o agente pede confirmação, com os dois botões (na tela: {balao.inner_text()[:90]})",
             "Confirma" in balao.inner_text() and balao.locator("[data-confirmar-nao]").count() == 1)
    conferir("antes da escolha, a pessoa continua na lista", cartao_da_lista.count() == 1)
    # 2. Cancelar: os botões somem, a escolha vira o balão "você", e nada muda
    escolha_nao = balao.locator("[data-confirmar-nao]").inner_text()
    balao.locator("[data-confirmar-nao]").click()
    aba.wait_for_function("() => !document.querySelector('[data-contador-processando]')", timeout=30000)
    conferir("'Cancelar': os botões somem e a escolha vira o balão 'você'",
             cartao.locator("[data-confirmar-sim]").count() == 0
             and cartao.locator(".balao-voce").last.inner_text().startswith(escolha_nao))
    conferir("depois de cancelar, a pessoa continua na lista e nada foi resolvido",
             cartao_da_lista.count() == 1 and aba.locator("[data-resolvido-a-vista]", has_text=nome).count() == 0)
    # 3. De novo, agora com "Sim": o cartão fica verde no lugar, com o que mudou e o Desfazer
    balao = pedir_para_nao_cadastrar(cartao)
    balao.locator("[data-confirmar-sim]").click()
    resolvido = aba.locator("[data-lista-pendencias] [data-resolvido-a-vista]", has_text=nome)
    resolvido.wait_for(timeout=30000)
    cartao.locator("[data-desfazer-mudanca]").first.wait_for(timeout=30000)
    conferir("'Sim, não cadastrar' resolve: o cartão fica verde, com o 'Pronto: ...' e o Desfazer",
             "Pronto:" in cartao.locator(".mudanca-da-ia").last.inner_text()
             and cartao.locator("[data-desfazer-mudanca]").count() >= 1)


def conferir_o_rodape(aba, dados: dict, conferir) -> None:
    """O rodapé fixo: com dois arquivos, a janela pede qual; com um, o nome; "e enviar outro" abre a janela."""
    # A conversa resolvida continua na janela por cima da tela: fecha antes de usar o rodapé, atrás dela
    fechar_a_conversa_aberta(aba)
    rodape = aba.locator("[data-rodape-pendencias]")
    conferir("o rodapé tem os dois botões",
             rodape.is_visible() and rodape.locator("text=Descartar a leitura e enviar outro arquivo").count() == 1
             and rodape.locator("[data-descartar-pelo-rodape]").inner_text() == "Descartar a leitura")
    texto = aba.inner_text("[data-arquivo-do-rodape]")
    conferir(f"com 'Todos os arquivos' e dois arquivos, o rodapé avisa (na tela: {texto})", "2 arquivos" in texto)
    # Com dois arquivos: a janela pede qual, e o botão só liga depois da escolha
    rodape.locator("[data-descartar-pelo-rodape]").click()
    janela = aba.locator("dialog[open]", has_text="Descartar esta leitura?")
    janela.wait_for(timeout=15000)
    conferir("a janela pede o arquivo, com o descarte desligado até a escolha",
             janela.locator("[data-arquivo-a-descartar]").is_visible()
             and janela.locator("[data-confirmar-descarte]").is_disabled())
    janela.locator("[data-arquivo-a-descartar]").select_option(dados["segundo"]["processamento_id"])
    janela.locator("[data-confirmar-descarte]:not([disabled])").wait_for(timeout=10000)
    janela.locator("[data-confirmar-descarte]").click()
    aba.locator("[data-aviso-descartado]:not([hidden])").wait_for(timeout=15000)
    # Sobrou um arquivo: o rodapé diz o nome dele
    aba.wait_for_function("() => document.querySelector('[data-arquivo-do-rodape]').innerText.startsWith('Arquivo:')",
                          timeout=20000)
    texto = aba.inner_text("[data-arquivo-do-rodape]")
    conferir(f"com um arquivo só, o rodapé diz o nome dele (na tela: {texto})",
             texto == "Arquivo: " + dados["primeiro"]["nome_arquivo"])
    # "Descartar a leitura e enviar outro arquivo": descarta e abre a janela "Cadastrar funcionários"
    rodape.locator("text=Descartar a leitura e enviar outro arquivo").click()
    janela.wait_for(timeout=15000)
    conferir("com um arquivo, a janela não pede a escolha",
             janela.locator("[data-arquivo-a-descartar]").is_hidden())
    janela.locator("[data-confirmar-descarte]").click()
    aba.locator("dialog.janela-novo-envio[open]").wait_for(timeout=20000)
    conferir("depois do descarte, a janela 'Cadastrar funcionários' abre", True)


def conferir_o_cadastrar(aba, endereco: str, dados: dict, conferir) -> None:
    """Na conferência da tela Cadastrar: o mesmo cartão-conversa, com a pergunta no balão, as respostas rápidas e a
    caixa."""
    aba.goto(endereco + "/cadastrar.html?envio=" + dados["primeiro"]["processamento_id"])
    aba.locator("[data-real-bloco-conferencia][open]").wait_for(timeout=60000)
    item = aba.locator(".pendencia-real").filter(has_text=cpf_no_texto(CPF_ERRADO)).first
    item.wait_for(timeout=30000)
    titulo = item.locator(".ajuste-titulo").inner_text()
    conferir(f"no Cadastrar, o título novo do cartão, com o botão da ficha (na tela: {titulo})",
             titulo.startswith('Ajuste na informação "CPF" de ') and item.locator("[data-ver-ficha]").count() == 1)
    pergunta = item.locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"no Cadastrar, a pergunta no balão do agente traz o CPF lido (na tela: {pergunta})",
             "✦ Agente de validação" in pergunta and somente_digitos(CPF_ERRADO) in somente_digitos(pergunta))
    conferir("no Cadastrar, a caixa para o agente, sem 'Não cadastrar', 'Corrigir este valor' nem 'Está certo assim'",
             item.locator("[data-sugestao-da-conversa]", has_text="Não cadastrar").count() == 0
             and item.locator("[data-caixa-da-conversa]").is_visible()
             and item.locator("text=Corrigir este valor").count() == 0 and item.locator("text=Está certo assim").count() == 0)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: Cadastrar (a conferência), depois Acompanhar (conversa, Desfazer, não cadastrar e rodapé)."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    conferir_o_cadastrar(aba, endereco, dados, conferir)
    aba.goto(endereco + "/acompanhar.html")
    conferir_o_cartao_e_a_conversa(aba, dados, conferir)
    conferir_a_correcao_e_o_desfazer(aba, dados, conferir)
    conferir_o_nao_cadastrar(aba, dados, conferir)
    conferir_o_rodape(aba, dados, conferir)
    aba.close()
