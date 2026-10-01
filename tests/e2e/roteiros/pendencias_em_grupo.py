"""Roteiro: o mesmo valor fora da lista em várias pessoas vira UM cartão, e a resposta vale para todas (ADR-120).

O que ele confere (com a IA simulada, sem custo), num arquivo com três pessoas de estado civil "Casdo" e uma "Noiva":
- em Acompanhar, as três viram UM cartão, "3 pessoas com o mesmo valor", com uma pergunta só (o número, o valor lido e
  o palpite) e a resposta rápida 'Sim, use "Casado" para as 3'; "Noiva" continua num cartão próprio;
- os números continuam contando pessoas: o 3º cartão do alto é o mesmo total da lista do servidor;
- "Ver quem são (3)" mostra os nomes; "Responder uma a uma" abre um cartão por pessoa (cada um com "Responder as 3 de
  uma vez", que volta ao cartão do grupo);
- os filtros no alto são só "Pendências em aberto (N)" e "Resolvidas (M)", contando pessoas;
- o clique no palpite resolve as três de uma vez: o cartão fica no lugar, verde ("✓ Resolvida"), com o "Pronto: ..."
  no chat e o Desfazer, e os números mudam; resolver a pessoa sozinha (mexer em outro cartão) tira o do grupo da tela;
- em "Resolvidas": os dois, com o que mudou, quando e quem; "Ver a conversa" abre os balões; depois do F5, a
  resolvida e a conversa continuam (guardadas no servidor); o Desfazer ali devolve o grupo para as abertas;
- na conferência do Cadastrar, cada uma das três linhas mostra o cartão do grupo;
- o título do cartão diz o ajuste ('Ajuste na informação "Estado civil"
  de 3 pessoas', '... de Davi Melo', '... no arquivo inteiro'); "Ver a ficha completa" abre a ficha da pessoa, com
  os grupos de campos e a informação em revisão em destaque ("Em revisão" e "No arquivo veio"), e o Esc fecha; no
  grupo, cada nome em "Ver quem são" abre a ficha daquela pessoa;
- a coluna que falta (o CPF é sempre único, ADR-124): a data de nascimento, que é de cada pessoa,
  nunca pede um valor para todos, e o botão "Descartar a leitura e enviar outro arquivo" do cartão abre a janela de
  descarte ("Continuar com este envio" não muda nada; no fim, "Sim, descartar" apaga a leitura e abre a janela
  "Cadastrar funcionários"); o CNPJ, dado da empresa, continua pedindo o valor uma vez;
- quando o dado da empresa não é o mesmo para todos (ADR-124): "Não é a mesma para todos" mostra os dois caminhos, e
  a lista "Informar pessoa a pessoa" do código da unidade grava "001" em Ana e Bia (pelos marcados) e "002" em Caio;
  o chat diz o que mudou, e Davi, em branco, ganha um cartão de revisão.
Desde o ADR-138, a conversa de cada cartão abre no painel do lado: o roteiro abre o cartão e usa o painel.
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa, fechar_a_conversa_aberta

DESCRICAO = "Pendências em grupo: um cartão para o mesmo valor em várias pessoas, resposta para todas e Desfazer"
# As três pessoas com o mesmo valor fora da lista e a pessoa sozinha (CPFs válidos e inventados)
PESSOAS_DO_GRUPO = [("Ana Lima", "52998224725"), ("Bia Souza", "11144477735"), ("Caio Reis", "12345678909")]
PESSOA_SOZINHA = ("Davi Melo", "98765432100")
# O valor que veio no arquivo e o palpite seguro do agente
VALOR_DO_ARQUIVO = "Casdo"
PALPITE = "Casado"
# O nome da informação nos títulos (a descrição do parâmetro, sem "do funcionário") e o título do cartão do grupo
INFORMACAO = "Estado civil"
TITULO_DO_GRUPO = f'Ajuste na informação "{INFORMACAO}" de 3 pessoas'
# Duas colunas obrigatórias que o arquivo não traz: uma de cada pessoa e um dado da empresa (a marcação "Pode ser igual
# para todos" do parâmetro)
INFORMACAO_DE_CADA_PESSOA = "Data de nascimento"
INFORMACAO_DA_EMPRESA = "CNPJ da empresa empregadora"
# Um dado da empresa que não é o mesmo para todos (ADR-124): a lista "Informar pessoa a pessoa"
INFORMACAO_DA_UNIDADE = "Código da unidade onde o funcionário trabalha"


def preparar() -> dict:
    """Um envio da Aurora com as quatro pessoas, com as colunas aceitas. Devolve {processamento_id}."""
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro
    from tests.apoio_do_parametro import marcar_como_obrigatorios
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # O estado civil é opcional no layout, e um campo opcional não abre pendência (ADR-143): o parâmetro deste banco de
    # teste o marca como obrigatório, para o cartão do grupo continuar testado (como nos testes do pytest)
    marcar_como_obrigatorios(conexao, "estado_civil")
    # O arquivo: três "Casdo" (uma em minúsculas, com espaço: é o mesmo valor) e uma "Noiva"
    linhas = ["Nome;CPF;Estado civil"]
    for posicao, (nome, cpf) in enumerate(PESSOAS_DO_GRUPO):
        valor = VALOR_DO_ARQUIVO
        if posicao == 1:
            valor = VALOR_DO_ARQUIVO.lower() + " "
        linhas.append(f"{nome};{cpf};{valor}")
    linhas.append(f"{PESSOA_SOZINHA[0]};{PESSOA_SOZINHA[1]};Noiva")
    conteudo = ("\n".join(linhas) + "\n").encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, "estado_civil_em_grupo.csv",
                                      busca=busca_falsa)
    escolhas = {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"}
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], escolhas,
                                busca=busca_falsa)
    conexao.close()
    return {"processamento_id": leitura["processamento_id"]}


def cartao_do_grupo(aba):
    """O cartão do grupo em Acompanhar (o que vale por 3 pessoas)."""
    return aba.locator("[data-pendencia][data-quantidade='3']")


def total_do_servidor(aba) -> int:
    """Quantas pendências a lista do servidor tem (uma por pessoa)."""
    return aba.evaluate("async () => (await (await fetch('/api/empresa/pendencias')).json()).length")


def conferir_o_cartao_do_grupo(aba, conferir) -> None:
    """Um cartão para as três, com a pergunta do grupo, e os números contando pessoas."""
    cartao = cartao_do_grupo(aba)
    cartao.wait_for(timeout=30000)
    conferir("as três pessoas com o mesmo valor viram um cartão só", cartao.count() == 1)
    titulo = cartao.locator(".ajuste-titulo").inner_text()
    conferir(f"o título diz o ajuste e quantas são (na tela: {titulo})", titulo == TITULO_DO_GRUPO)
    # Um cartão, um problema (ADR-120): a linha "Problema:" embaixo do título diz qual é, e só ele
    problema = cartao.locator("[data-problema-do-cartao]").inner_text()
    conferir(f"embaixo do título, o problema do cartão, só ele (na tela: {problema})",
             problema == "Problema: valor que o sistema não reconheceu")
    painel = abrir_a_conversa(aba, cartao)
    pergunta = painel.locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"uma pergunta só, com o número, o valor lido e o palpite (na tela: {pergunta})",
             "3 pessoas" in pergunta and f'"{VALOR_DO_ARQUIVO}"' in pergunta and f'"{PALPITE}"' in pergunta
             and pergunta.strip().endswith("?"))
    primeira_resposta = painel.locator("[data-sugestao-da-conversa]").first.inner_text()
    conferir(f"a primeira resposta rápida aceita o palpite para todas (na tela: {primeira_resposta})",
             primeira_resposta == f'Sim, use "{PALPITE}" para as 3')
    conferir("nenhum outro cartão fala do mesmo valor, e 'Noiva' continua num cartão próprio",
             aba.locator("[data-pendencia]", has_text=f'"{VALOR_DO_ARQUIVO}"').count() == 1
             and aba.locator("[data-pendencia]", has_text=PESSOA_SOZINHA[0]).count() == 1)
    total_na_tela = int(aba.inner_text("[data-total-pendencias]"))
    total = total_do_servidor(aba)
    conferir(f"o número do alto conta pessoas, como o servidor (na tela: {total_na_tela}; servidor: {total})",
             total_na_tela == total)
    aba.locator("#pendencias").screenshot(path="storage/painel/pendencias_em_grupo.png")


def conferir_quem_sao_e_uma_a_uma(aba, conferir) -> None:
    """ "Ver quem são", "Responder uma a uma" e a volta para o cartão do grupo."""
    cartao = abrir_a_conversa(aba, cartao_do_grupo(aba))
    botao = cartao.locator("[data-ver-quem-sao]")
    conferir(f"o botão diz quantas são (na tela: {botao.inner_text()})", botao.inner_text() == "Ver quem são (3)")
    botao.click()
    nomes = cartao.locator("[data-nomes-do-grupo]").inner_text()
    conferir(f"os nomes aparecem (na tela: {nomes})",
             all(nome in nomes for nome, _ in PESSOAS_DO_GRUPO) and PESSOA_SOZINHA[0] not in nomes)
    # Cada nome abre a ficha daquela pessoa, com o campo do grupo em destaque
    cartao.locator("[data-ficha-da-pessoa]", has_text=PESSOAS_DO_GRUPO[1][0]).click()
    janela = janela_da_ficha_aberta(aba)
    destaque = janela.locator("[data-campo-em-revisao]")
    nome_na_ficha = janela.locator("[data-nome-da-ficha]").inner_text()
    conferir(f"o nome em 'Ver quem são' abre a ficha certa (na tela: {nome_na_ficha})",
             nome_na_ficha == PESSOAS_DO_GRUPO[1][0] and destaque.get_attribute("data-campo-da-ficha") == "estado_civil"
             and VALOR_DO_ARQUIVO.lower() in destaque.inner_text())
    janela.locator("[data-fechar-ficha-da-pendencia]").click()
    aba.locator("#janela-ficha-da-pendencia:not([open])").wait_for(state="attached", timeout=10000)
    total_antes = int(aba.inner_text("[data-total-pendencias]"))
    cartao.locator("[data-responder-uma-a-uma]").click()
    cartao_do_grupo(aba).wait_for(state="detached", timeout=30000)
    # Um cartão por pessoa na lista; a conversa de cada um (no painel) tem o botão para voltar ao grupo
    cartoes_das_pessoas = 0
    for nome, _ in PESSOAS_DO_GRUPO:
        cartoes_das_pessoas = cartoes_das_pessoas + aba.locator("[data-lista-pendencias] [data-pendencia]",
                                                                has_text=nome).count()
    painel = abrir_a_conversa(aba, aba.locator("[data-lista-pendencias] [data-pendencia]",
                                               has_text=PESSOAS_DO_GRUPO[0][0]).first)
    conferir("'Responder uma a uma' abre um cartão por pessoa, cada um com 'Responder as 3 de uma vez'",
             cartao_do_grupo(aba).count() == 0 and cartoes_das_pessoas == 3
             and painel.locator("[data-responder-todas-de-uma-vez]").inner_text() == "Responder as 3 de uma vez")
    conferir("uma a uma, o número do alto não muda", int(aba.inner_text("[data-total-pendencias]")) == total_antes)
    painel.locator("[data-responder-todas-de-uma-vez]").click()
    cartao_do_grupo(aba).wait_for(timeout=30000)
    # O painel acompanha a lista logo depois (ele espera as "Resolvidas" chegarem): espera o botão sair dele
    aba.locator("[data-responder-todas-de-uma-vez]").first.wait_for(state="detached", timeout=30000)
    conferir("'Responder as 3 de uma vez' volta ao cartão do grupo",
             aba.locator("[data-responder-todas-de-uma-vez]").count() == 0)


def janela_da_ficha_aberta(aba):
    """A janela da ficha, depois de aberta e carregada (com os grupos de campos)."""
    janela = aba.locator("#janela-ficha-da-pendencia[open]")
    janela.locator("[data-grupos-da-ficha] .ficha-grupo").first.wait_for(timeout=30000)
    return janela


def conferir_os_titulos_e_a_ficha(aba, conferir) -> None:
    """Os títulos novos (pessoa, grupo e arquivo inteiro) e a ficha completa da pessoa, com o campo em destaque."""
    # A conversa aberta antes fica numa janela por cima da tela: fecha antes de clicar nos cartões da lista
    fechar_a_conversa_aberta(aba)
    conferir("o cartão do grupo não tem 'Ver a ficha completa' (os nomes abrem as fichas)",
             cartao_do_grupo(aba).locator("[data-ver-ficha]").count() == 0)
    cartao = aba.locator("[data-pendencia]", has_text=PESSOA_SOZINHA[0]).first
    titulo = cartao.locator(".ajuste-titulo").inner_text()
    esperado = r'(Ajuste na|Conferir a) informação "' + INFORMACAO + '" de ' + PESSOA_SOZINHA[0]
    conferir(f"o título do cartão da pessoa diz o ajuste, o campo e de quem (na tela: {titulo})",
             re.fullmatch(esperado, titulo) is not None and cartao.locator(".ajuste-campo").count() == 0)
    titulo_do_arquivo = aba.locator(".ajuste-titulo", has_text=re.compile("^Ajuste .*no arquivo inteiro$")).first
    do_arquivo = aba.locator("[data-pendencia]").filter(has=titulo_do_arquivo).first
    texto_do_arquivo = titulo_do_arquivo.inner_text()
    conferir(f"a pendência do arquivo inteiro diz isso no título, sem ficha (na tela: {texto_do_arquivo})",
             texto_do_arquivo.startswith("Ajuste ") and do_arquivo.locator("[data-ver-ficha]").count() == 0)
    # A ficha completa: o nome, os grupos e o campo em revisão em destaque
    botao = cartao.locator("[data-ver-ficha]")
    conferir("o cartão da pessoa tem o botão 'Ver a ficha completa'", botao.inner_text() == "Ver a ficha completa")
    botao.click()
    janela = janela_da_ficha_aberta(aba)
    destaque = janela.locator("[data-campo-em-revisao]")
    nome_na_ficha = janela.locator("[data-nome-da-ficha]").inner_text()
    conferir(f"a ficha mostra o nome e os campos em grupos (na tela: {nome_na_ficha})",
             nome_na_ficha == PESSOA_SOZINHA[0] and janela.locator(".ficha-grupo").count() >= 1
             and janela.locator("[data-campo-da-ficha]").count() >= 3)
    conferir(f"a informação em revisão fica em destaque, com o que veio no arquivo (na tela: {destaque.inner_text()})",
             destaque.count() == 1 and destaque.get_attribute("data-campo-da-ficha") == "estado_civil"
             and "Em revisão" in destaque.inner_text() and 'No arquivo veio: "Noiva"' in destaque.inner_text())
    aba.locator("#janela-ficha-da-pendencia").screenshot(path="storage/painel/ficha_da_pendencia.png")
    aba.keyboard.press("Escape")
    aba.locator("#janela-ficha-da-pendencia:not([open])").wait_for(state="attached", timeout=10000)
    conferir("o Esc fecha a ficha, e o foco volta ao botão",
             aba.evaluate("() => document.activeElement.hasAttribute('data-ver-ficha')"))


def cartao_do_arquivo_inteiro(aba, informacao: str):
    """O cartão da coluna que o arquivo inteiro não trouxe, pela informação (ex.: "Data de nascimento")."""
    titulo = f'Ajuste na informação "{informacao}" no arquivo inteiro'
    return aba.locator("[data-pendencia]").filter(has=aba.locator(".ajuste-titulo", has_text=titulo)).first


def conferir_a_informacao_de_cada_pessoa(aba, conferir) -> None:
    """A coluna que falta: a informação de cada pessoa (a data de nascimento) nunca pede um valor para todos, e o botão
    do cartão abre a janela de descarte; o dado da empresa (o CNPJ) continua pedindo o valor uma vez (o CPF é sempre
    único, ADR-124)."""
    cartao = cartao_do_arquivo_inteiro(aba, INFORMACAO_DE_CADA_PESSOA)
    painel = abrir_a_conversa(aba, cartao)
    pergunta = painel.locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"a informação de cada pessoa não pede um valor para todos (na tela: {pergunta})",
             "única por funcionário" in pergunta and "Se for a mesma para todos" not in pergunta)
    botao = painel.locator("[data-acao-do-cartao='descartar_e_enviar_outro']")
    conferir("o cartão oferece 'Descartar a leitura e enviar outro arquivo'",
             botao.count() == 1 and botao.inner_text() == "Descartar a leitura e enviar outro arquivo")
    cartao_do_cnpj = abrir_a_conversa(aba, cartao_do_arquivo_inteiro(aba, INFORMACAO_DA_EMPRESA))
    pergunta_do_cnpj = cartao_do_cnpj.locator("[data-pergunta-da-pendencia]").inner_text()
    respostas_do_cnpj = cartao_do_cnpj.locator("[data-sugestao-da-conversa]").all_inner_texts()
    conferir(f"o dado da empresa pede o valor uma vez e oferece os caminhos para quando não é o mesmo (na tela: "
             f"{pergunta_do_cnpj} | {respostas_do_cnpj})",
             "Se for a mesma para todos" in pergunta_do_cnpj
             and len(respostas_do_cnpj) == 4
             # Primeiro, o CNPJ que o cadastro da empresa já tem (ADR-127); depois, os caminhos de sempre
             and respostas_do_cnpj[0].startswith("Usar o CNPJ da empresa (")
             and respostas_do_cnpj[1:] == ["Não é a mesma para todos", "Informar pessoa a pessoa",
                                           "Descartar a leitura e enviar outro arquivo"])
    # O botão abre a janela de descarte deste arquivo; "Continuar com este envio" fecha, e nada muda
    total_antes = int(aba.inner_text("[data-total-pendencias]"))
    # O painel está com a conversa do CNPJ: volta à da data de nascimento
    abrir_a_conversa(aba, cartao).locator("[data-acao-do-cartao='descartar_e_enviar_outro']").click()
    janela = aba.locator("dialog[open]", has_text="Descartar esta leitura?")
    janela.wait_for(timeout=15000)
    conferir("o botão abre a janela de descarte, já com o arquivo (sem pedir a escolha)",
             janela.locator("[data-arquivo-a-descartar]").is_hidden()
             and janela.locator("[data-confirmar-descarte]").is_enabled())
    janela.locator("[data-continuar-envio]").click()
    aba.locator("dialog[open]", has_text="Descartar esta leitura?").wait_for(state="detached", timeout=10000)
    conferir("'Continuar com este envio' fecha a janela, e nada muda",
             int(aba.inner_text("[data-total-pendencias]")) == total_antes and cartao.is_visible())


def conferir_a_lista_pessoa_a_pessoa(aba, endereco: str, conferir) -> None:
    """O código da unidade não é o mesmo para todos (ADR-124): "Não é a mesma para todos" mostra os dois caminhos, e a
    lista "Informar pessoa a pessoa" grava o valor de cada pessoa (Ana e Bia "001" pelos marcados, Caio "002" e Davi
    em branco, que ganha um cartão de revisão)."""
    aba.goto(endereco + "/acompanhar.html")
    cartao_da_lista = cartao_do_arquivo_inteiro(aba, INFORMACAO_DA_UNIDADE)
    cartao_da_lista.wait_for(timeout=30000)
    # A conversa do cartão, no painel do lado (ADR-138)
    cartao = abrir_a_conversa(aba, cartao_da_lista)
    # A: "Não é a mesma para todos" não muda nada e mostra os dois caminhos
    cartao.locator("[data-sugestao-da-conversa]", has_text="Não é a mesma para todos").click()
    resposta = cartao.get_by_text("Sem problema: então esse valor não vale para todos.").first
    resposta.wait_for(timeout=30000)
    conferir("'Não é a mesma para todos': o agente mostra os dois caminhos, sem perguntar de novo o valor",
             "Informar pessoa a pessoa" in resposta.inner_text()
             and cartao.get_by_text("Qual é o valor para todos?").count() == 0)
    # B: a lista, dentro do cartão, com as quatro pessoas e a marcação em lote (dado da empresa)
    cartao.locator("[data-acao-do-cartao='informar_pessoa_a_pessoa']").click()
    lista = cartao.locator("[data-lista-pessoa-a-pessoa]")
    lista.locator("[data-valor-da-pessoa]").first.wait_for(timeout=30000)
    conferir("a lista abre na conversa, com uma caixa por pessoa e 'Marcar todos'",
             lista.locator("[data-linha-pessoa]").count() == 4 and lista.locator("[data-marcar-todos]").count() == 1)
    # Ana e Bia marcadas, com "001" nos marcados; Caio "002"; Davi em branco
    for nome in ("Ana Lima", "Bia Souza"):
        lista.locator("[data-linha-pessoa]", has_text=nome).locator("[data-marcar-pessoa]").check()
    lista.locator("[data-valor-dos-marcados]").fill("001")
    lista.locator("[data-usar-nos-marcados]").click()
    valor_da_bia = lista.locator("[data-linha-pessoa]", has_text="Bia Souza").locator("[data-valor-da-pessoa]")
    conferir("'Usar nos marcados' preenche as marcadas", valor_da_bia.input_value() == "001")
    lista.locator("[data-linha-pessoa]", has_text="Caio Reis").locator("[data-valor-da-pessoa]").fill("002")
    lista.locator("[data-salvar-lista-pessoa-a-pessoa]").click()
    pronto = aba.get_by_text(f'Pronto: informei "{INFORMACAO_DA_UNIDADE}" de 3 pessoas: Ana, Bia e Caio.').first
    pronto.wait_for(timeout=30000)
    conferir(f"salvar: o chat diz o que mudou e quem ficou sem (na tela: {pronto.inner_text()})",
             "1 pessoa ficou sem esta informação e ganhou um cartão de revisão." in pronto.inner_text())
    # O Davi, que ficou em branco, ganha um cartão de revisão
    cartao_do_davi = aba.locator(".ajuste-titulo", has_text=f'"{INFORMACAO_DA_UNIDADE}" de {PESSOA_SOZINHA[0]}')
    cartao_do_davi.first.wait_for(timeout=30000)
    conferir("quem ficou em branco ganha um cartão de revisão", cartao_do_davi.count() == 1)


def conferir_o_descarte_pelo_cartao(aba, endereco: str, conferir) -> None:
    """O botão do cartão de ponta a ponta: "Sim, descartar" apaga a leitura e abre a janela "Cadastrar funcionários"."""
    aba.goto(endereco + "/acompanhar.html")
    cartao = cartao_do_arquivo_inteiro(aba, INFORMACAO_DE_CADA_PESSOA)
    cartao.wait_for(timeout=30000)
    abrir_a_conversa(aba, cartao).locator("[data-acao-do-cartao='descartar_e_enviar_outro']").click()
    janela = aba.locator("dialog[open]", has_text="Descartar esta leitura?")
    janela.wait_for(timeout=15000)
    janela.locator("[data-confirmar-descarte]").click()
    aba.locator("[data-aviso-descartado]:not([hidden])").wait_for(timeout=15000)
    aba.locator("dialog.janela-novo-envio[open]").wait_for(timeout=20000)
    conferir("'Sim, descartar' apaga a leitura, avisa e abre a janela 'Cadastrar funcionários'", True)


def contagem_do_filtro(aba, filtro: str) -> str:
    """O número entre parênteses de um filtro ("abertas" ou "resolvidas"), sem os parênteses."""
    return aba.inner_text(f"[data-contagem-tipo='{filtro}']").strip("()")


def resolvidos_a_vista(aba):
    """Os cartões que a conversa acabou de resolver e que continuam na lista das abertas."""
    return aba.locator("[data-lista-pendencias] [data-resolvido-a-vista]")


def conferir_os_filtros(aba, conferir) -> None:
    """Os dois filtros no alto, com os números: só "Pendências em aberto" e "Resolvidas"."""
    textos = [botao.inner_text() for botao in aba.locator("[data-filtro-pendencia]").all()]
    conferir(f"os filtros são só 'Pendências em aberto' e 'Resolvidas' (na tela: {textos})",
             len(textos) == 2 and textos[0].startswith("Pendências em aberto (")
             and textos[1].startswith("Resolvidas ("))
    conferir("'Pendências em aberto' conta pessoas, como o número do alto",
             contagem_do_filtro(aba, "abertas") == aba.inner_text("[data-total-pendencias]"))
    conferir("sem nada resolvido ainda, 'Resolvidas (0)'", contagem_do_filtro(aba, "resolvidas") == "0")


def conferir_a_resposta_e_o_cartao_que_fica(aba, conferir) -> None:
    """O palpite para as três: o cartão fica, verde, com o "Pronto: ..."; resolver outro tira o primeiro da tela."""
    total_antes = int(aba.inner_text("[data-total-pendencias]"))
    painel = abrir_a_conversa(aba, cartao_do_grupo(aba))
    painel.locator("[data-sugestao-da-conversa]").first.click()
    resolvido = resolvidos_a_vista(aba).first
    resolvido.wait_for(timeout=30000)
    painel.locator("[data-desfazer-mudanca]").wait_for(timeout=30000)
    pronto = painel.locator(".mudanca-da-ia").last.inner_text()
    conferir(f"o cartão do grupo fica na tela, verde, com o que mudou no chat (na tela: {pronto[:160]})",
             "✓ Resolvida" in resolvido.inner_text() and "Pronto:" in pronto and PALPITE in pronto
             and painel.locator("[data-desfazer-mudanca]").count() == 1
             and painel.locator("[data-caixa-da-conversa]").is_hidden())
    conferir("o número do alto e o de 'Pendências em aberto' caem 3; 'Resolvidas (3)'",
             int(aba.inner_text("[data-total-pendencias]")) == total_antes - 3
             and contagem_do_filtro(aba, "abertas") == str(total_antes - 3)
             and contagem_do_filtro(aba, "resolvidas") == "3")
    # Resolver a pessoa sozinha (clicar noutro cartão): o grupo sai da tela, e ela fica verde no lugar
    cartao_sozinho = aba.locator("[data-pendencia]", has_text=PESSOA_SOZINHA[0]).first
    painel = abrir_a_conversa(aba, cartao_sozinho)
    painel.locator("[data-sugestao-da-conversa]", has_text="Solteiro").first.click()
    aba.wait_for_function("() => document.querySelectorAll('[data-lista-pendencias] [data-resolvido-a-vista]').length"
                          " === 1 && document.querySelector('[data-lista-pendencias] [data-resolvido-a-vista]')"
                          f".innerText.includes('{PESSOA_SOZINHA[0]}')", timeout=30000)
    # A tela refaz as abertas primeiro e só depois busca as "Resolvidas": espera o número delas mudar antes de conferir
    aba.wait_for_function("() => document.querySelector(\"[data-contagem-tipo='resolvidas']\").innerText !== '(3)'",
                          timeout=30000)
    cartoes_do_grupo = cartao_do_grupo(aba).count()
    resolvidas = contagem_do_filtro(aba, "resolvidas")
    conferir(f"ao mexer em outro cartão, o grupo resolvido sai da tela, e o outro fica verde no lugar dele (na tela: "
             f"{cartoes_do_grupo} cartão do grupo; Resolvidas ({resolvidas}))",
             cartoes_do_grupo == 0 and resolvidas == "4")
    aba.locator("#pendencias").screenshot(path="storage/painel/pendencias_resolvida_a_vista.png")


def conferir_as_resolvidas(aba, conferir) -> None:
    """O filtro "Resolvidas": os cartões, o resumo, a conversa, o F5 e o Desfazer."""
    # A conversa aberta antes fica numa janela por cima da tela: fecha antes de trocar o filtro
    fechar_a_conversa_aberta(aba)
    aba.locator("[data-filtro-pendencia='resolvidas']").click()
    resolvidas = aba.locator("[data-lista-resolvidas] [data-resolvida]")
    resolvidas.first.wait_for(timeout=30000)
    # O cartão verde desliza para fora (~300 ms) e sai
    aba.wait_for_function("() => document.querySelectorAll('[data-lista-pendencias] [data-resolvido-a-vista]')"
                          ".length === 0", timeout=5000)
    conferir("trocar o filtro tira da tela o cartão verde que ainda estava lá", resolvidos_a_vista(aba).count() == 0)
    do_grupo = aba.locator("[data-resolvida]", has_text=TITULO_DO_GRUPO)
    resumo = do_grupo.locator("[data-resumo-da-resolvida]").inner_text()
    conferir(f"'Resolvidas' mostra o grupo e a pessoa, com o que mudou (na tela: {resumo})",
             resolvidas.count() == 2 and f"{VALOR_DO_ARQUIVO} → {PALPITE} em 3 pessoas" in resumo
             and "Resolvida em" in do_grupo.inner_text())
    conversa = abrir_a_conversa(aba, do_grupo)
    conferir("'Ver a conversa' abre os balões no painel: a pergunta, a resposta e o 'Pronto: ...'",
             conversa.locator("[data-pergunta-da-pendencia]").count() == 1
             and conversa.locator(".balao-voce").count() == 1 and "Pronto:" in conversa.inner_text())
    aba.locator("#pendencias").screenshot(path="storage/painel/pendencias_resolvidas.png")
    # Depois do F5: as resolvidas e a conversa continuam (guardadas no servidor)
    aba.reload()
    aba.locator("[data-contagem-tipo='resolvidas']:not(:empty)").wait_for(timeout=30000)
    aba.wait_for_function("() => document.querySelector(\"[data-contagem-tipo='resolvidas']\").innerText === '(4)'",
                          timeout=30000)
    aba.locator("[data-filtro-pendencia='resolvidas']").click()
    do_grupo = aba.locator("[data-resolvida]", has_text=TITULO_DO_GRUPO)
    do_grupo.wait_for(timeout=30000)
    conversa = abrir_a_conversa(aba, do_grupo)
    conferir("depois de recarregar a página, a resolvida e a conversa continuam",
             "Pronto:" in conversa.inner_text() and conversa.locator(".balao-voce").count() == 1)
    # O Desfazer na resolvida devolve o grupo para as abertas
    conversa.locator("[data-desfazer-mudanca]").click()
    aba.wait_for_function("() => document.querySelector(\"[data-contagem-tipo='resolvidas']\").innerText === '(1)'",
                          timeout=30000)
    fechar_a_conversa_aberta(aba)
    aba.locator("[data-filtro-pendencia='abertas']").click()
    cartao_do_grupo(aba).wait_for(timeout=30000)
    conversa = abrir_a_conversa(aba, cartao_do_grupo(aba))
    conferir("o Desfazer em 'Resolvidas' devolve o grupo para 'Pendências em aberto', com o Desfeito na conversa",
             "Desfeito" in conversa.inner_text()
             and contagem_do_filtro(aba, "abertas") == aba.inner_text("[data-total-pendencias]"))


def conferir_o_cadastrar(aba, endereco: str, dados: dict, conferir) -> None:
    """Na conferência do Cadastrar, cada linha do grupo mostra o cartão do grupo."""
    aba.goto(endereco + "/cadastrar.html?envio=" + dados["processamento_id"])
    aba.locator("[data-real-bloco-conferencia][open]").wait_for(timeout=60000)
    cartoes = aba.locator(".pendencia-real", has_text=TITULO_DO_GRUPO)
    cartoes.first.wait_for(timeout=30000)
    conferir(f"no Cadastrar, as três linhas mostram o cartão do grupo (na tela: {cartoes.count()})",
             cartoes.count() == 3
             and cartoes.first.locator("[data-sugestao-da-conversa]").first.inner_text()
             == f'Sim, use "{PALPITE}" para as 3')


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: Acompanhar (cartão do grupo, uma a uma, resposta e Desfazer), depois a conferência do Cadastrar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_o_cartao_do_grupo(aba, conferir)
    conferir_os_filtros(aba, conferir)
    conferir_os_titulos_e_a_ficha(aba, conferir)
    conferir_a_informacao_de_cada_pessoa(aba, conferir)
    conferir_quem_sao_e_uma_a_uma(aba, conferir)
    conferir_a_resposta_e_o_cartao_que_fica(aba, conferir)
    conferir_as_resolvidas(aba, conferir)
    conferir_o_cadastrar(aba, endereco, dados, conferir)
    # Depois das contagens: a lista pessoa a pessoa (muda as pendências) e, por último, o descarte pelo cartão
    conferir_a_lista_pessoa_a_pessoa(aba, endereco, conferir)
    conferir_o_descarte_pelo_cartao(aba, endereco, conferir)
    aba.close()
