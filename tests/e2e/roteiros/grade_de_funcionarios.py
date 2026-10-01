"""Roteiro: a grade de consulta de funcionários com todos os campos do parâmetro do banco (ADR-111).

O que ele confere:
- uma coluna por campo do parâmetro vigente, na ordem do layout, mais Conta, Incluído e Situação;
- a marca "*" em cada coluna obrigatória do parâmetro (e só nelas);
- o valor identificado na célula quando existe, e "Informação não encontrada" quando o campo veio vazio;
- a legenda da marca e da frase acima da grade;
- o nome continua abrindo a ficha;
- a Situação é a primeira coluna, com o "i" em cima da grade, que explica os 6 status (sem o sinal de informação na
  situação; a legenda de texto saiu);
- no banco, a aba Empresas abre a empresa na Visão geral: os números e a mesma lista (ADR-112), com o mesmo "i" em cima
  da grade (a legenda do fim da aba saiu).
Também guarda uma foto da grade (storage/painel/grade_de_funcionarios.png) para conferir o visual.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = "Grade de funcionários (empresa e Visão geral do banco): campos do parâmetro, Situação primeiro, legendas"


def preparar() -> dict:
    """Aurora com a carga inicial cadastrada; devolve quantos campos o parâmetro tem e quantos são obrigatórios."""
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, parametros
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import RAIZ, busca_falsa
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
    # O banco dá baixa na conta de 3 funcionários, com o código do banco no arquivo (ADR-113): 2 contas novas viram
    # "Conta aberta" e 1 correntista vira "Já é correntista" (as duas últimas situações; ADR-123)
    from models.contratos import Perfil
    from services import contas_abertas
    especialista = auth.Usuario(login="teste.banco", perfil=Perfil.BANCO, empresa_id=None)
    tres_cpfs = []
    for (cpf,) in conexao.execute("SELECT cpf FROM funcionarios_homologados WHERE empresa_id = 'EMP001' ORDER BY cpf"):
        tres_cpfs.append(cpf)
    # O layout fixo do arquivo de contas, subido por empresa (ADR-122; o formato novo, ADR-149):
    # cpf;status;agencia;conta;data_abertura, com a data em AAAA-MM-DD; as duas primeiras com o status 1 (Conta nova)
    # e a terceira com o status 2 (a empresa vê "Já é correntista")
    linhas_do_arquivo = ["cpf;status;agencia;conta;data_abertura"]
    status_das_linhas = ["1", "1", "2"]
    for posicao, cpf in enumerate(tres_cpfs[:3]):
        # O layout pede o CPF só com os 11 dígitos
        digitos_do_cpf = ""
        for caractere in cpf:
            if caractere.isdigit():
                digitos_do_cpf = digitos_do_cpf + caractere
        linhas_do_arquivo.append(digitos_do_cpf + ";" + status_das_linhas[posicao] + ";0001;" + digitos_do_cpf[-5:] +
                                 "-0;2026-09-24")
    conteudo = "\n".join(linhas_do_arquivo).encode("utf-8")
    previa = contas_abertas.conferir_arquivo(conexao, especialista, "EMP001", conteudo, "contas_da_semana.csv")
    contas_abertas.confirmar_baixa(conexao, especialista, previa["arquivo_id"])
    # O parâmetro vigente: quantos campos e quantos obrigatórios a grade tem de mostrar
    _, campos_do_layout = parametros.layout_ativo(conexao)
    obrigatorios = 0
    for campo in campos_do_layout:
        if campo.obrigatorio:
            obrigatorios = obrigatorios + 1
    conexao.close()
    return {"campos": len(campos_do_layout), "obrigatorios": obrigatorios}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre Acompanhar como a empresa e confere a grade."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    # A grade do parâmetro está pronta quando a linha dos grupos aparece no cabeçalho
    aba.locator("[data-cabeca-tabela] .linha-de-grupos").wait_for(timeout=20000)
    aba.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    # 1. Uma coluna por campo do parâmetro, mais Conta, Incluído e Situação
    colunas_na_tela = aba.locator("[data-cabeca-tabela] tr:nth-child(2) th").count()
    # Situação + campos + Código do banco, Agência, Conta, Aberta em + Incluído
    conferir(f"{dados['campos']} campos do parâmetro + 6 colunas da consulta (na tela: {colunas_na_tela})",
             colunas_na_tela == dados["campos"] + 6)
    # 2. A marca "*" em cada obrigatório, e só neles
    marcas = aba.locator("[data-cabeca-tabela] .marca-obrigatorio").count()
    conferir(f"{dados['obrigatorios']} colunas obrigatórias marcadas (na tela: {marcas})", marcas == dados["obrigatorios"])
    # 3. A primeira linha tem uma célula por coluna, com o valor ou a frase fixa
    celulas = aba.locator("[data-corpo-tabela] tr").first.locator("td").count()
    conferir("cada linha tem uma célula por coluna", celulas == dados["campos"] + 6)
    nao_encontrados = aba.locator("[data-corpo-tabela] .valor-nao-encontrado").count()
    conferir("campo vazio aparece como 'Informação não encontrada'",
             nao_encontrados > 0 and aba.inner_text("[data-corpo-tabela] .valor-nao-encontrado >> nth=0")
             == "Informação não encontrada")
    # O CPF identificado aparece de fato, formatado (000.000.000-00)
    texto_da_primeira_linha = aba.inner_text("[data-corpo-tabela] tr >> nth=0")
    conferir("o valor identificado aparece (CPF formatado na linha)", "-" in texto_da_primeira_linha
             and "." in texto_da_primeira_linha)
    # 4. A legenda aparece acima da grade
    conferir("legenda da marca e da frase visível", aba.locator("[data-legenda-grade]").is_visible())
    # A foto da grade, para conferir o visual
    aba.set_viewport_size({"width": 1440, "height": 900})
    aba.locator(".tabela-rolavel").first.screenshot(path="storage/painel/grade_de_funcionarios.png")
    # 5. O nome continua abrindo a ficha
    aba.locator("[data-corpo-tabela] .botao-nome").first.click()
    aba.locator("#janela-ficha").wait_for(state="visible", timeout=10000)
    conferir("o nome abre a ficha", aba.locator("#janela-ficha").is_visible())
    # Na ficha, a conta que o banco informa se chama "Conta salário"
    itens_da_ficha = aba.locator("#janela-ficha-grupos dt").all_inner_texts()
    conferir(f"a ficha chama a conta de 'Conta salário' (na tela: {itens_da_ficha[-3:]})",
             "Conta salário" in itens_da_ficha and "Conta" not in itens_da_ficha)
    aba.keyboard.press("Escape")
    # 6. A Situação é a primeira coluna, e o "i" em cima da grade explica os 6 status (a legenda de texto saiu)
    primeira_coluna = aba.inner_text("[data-cabeca-tabela] tr:nth-child(2) th >> nth=0")
    conferir(f"a primeira coluna é a Situação (na tela: {primeira_coluna})", primeira_coluna == "Situação")
    conferir("a legenda de texto dos status saiu", aba.locator("[data-legenda-status]").count() == 0)
    botao_da_legenda = aba.locator("[data-legenda-dos-status='funcionarios'] [data-botao-da-legenda]")
    botao_da_legenda.hover()
    itens_do_balao = aba.locator("[data-legenda-dos-status='funcionarios'] .item-do-balao-dos-status")
    itens_do_balao.first.wait_for(timeout=15000)
    conferir("o \"i\" em cima da grade explica os 6 status (com 'Aguardando envio', 'Conta aberta' e 'Já é "
             "correntista')", itens_do_balao.count() == 6)
    # 7. As últimas situações: "Conta aberta" (2) e "Já é correntista" (1), com o código do banco, a agência e a conta
    # nas colunas separadas (ADR-113, ADR-123); o ATIVO do correntista nunca aparece para a empresa
    situacoes_com_conta = aba.locator("[data-corpo-tabela] .selo-conta-aberta").all_inner_texts()
    conferir(f"2 'Conta aberta' e 1 'Já é correntista' (na tela: {situacoes_com_conta})",
             sorted(situacoes_com_conta) == ["Conta aberta", "Conta aberta", "Já é correntista"]
             and "ATIVO" not in aba.inner_text("[data-corpo-tabela]"))
    titulos = aba.locator("[data-cabeca-tabela] tr:nth-child(2) th").all_inner_texts()
    conferir("colunas separadas da conta: código do banco, agência, conta e data",
             titulos[-5:] == ["Código do banco", "Agência", "Conta salário", "Aberta em", "Incluído"])
    # Os grupos do fim: "Informações bancárias" (com a nota ao passar o mouse) e "Inclusão"
    grupos = aba.locator("[data-cabeca-tabela] .linha-de-grupos th").all_inner_texts()
    conferir(f"grupos do fim: Informações bancárias e Inclusão (na tela: {grupos[-2:]})",
             [grupo.lower() for grupo in grupos[-2:]] == ["informações bancárias", "inclusão"])
    nota_do_grupo = aba.get_attribute("[data-cabeca-tabela] .linha-de-grupos th >> nth=-2", "title") or ""
    conferir("a nota diz que o banco envia essas informações ao final da integração",
             "banco" in nota_do_grupo and "final da integração" in nota_do_grupo)
    conferir("a nota fala da conta salário", "conta salário" in nota_do_grupo)
    conferir("a legenda explica as informações bancárias, com a conta salário",
             "enviadas pelo banco" in aba.inner_text("[data-legenda-grade]")
             and "conta salário" in aba.inner_text("[data-legenda-grade]"))
    # No balão do "i", os status ficam empilhados: cada um começa numa altura diferente (um abaixo do outro)
    botao_da_legenda.hover()
    itens_do_balao.first.wait_for(timeout=15000)
    alturas = []
    for item in itens_do_balao.all():
        alturas.append(round(item.bounding_box()["y"]))
    conferir(f"no balão, os status um abaixo do outro (alturas: {alturas})",
             len(alturas) == 6 and alturas == sorted(alturas) and len(set(alturas)) == 6)
    # O mouse sai do "i": o balão fecha
    aba.mouse.move(1, 1)
    linha_com_conta = aba.locator("[data-corpo-tabela] tr", has=aba.locator(".selo-conta-aberta")).first
    # O código do banco saiu do arquivo (ADR-149): a coluna dele fica com o traço; a agência e a data aparecem
    conferir("a conta aparece nas colunas (0001 · número · 24/09/2026)", "0001" in linha_com_conta.inner_text()
             and "24/09/2026" in linha_com_conta.inner_text())
    conferir("sem o sinal de informação na situação", aba.locator("[data-corpo-tabela] .aviso-pendencia").count() == 0)
    # A foto da tela como a pessoa vê: o "i", a legenda da grade e o começo dela
    botao_da_legenda.scroll_into_view_if_needed()
    aba.screenshot(path="storage/painel/grade_da_empresa_tela.png")

    # Os filtros: a situação com os 5 status; sem as consultas rápidas; só o "Limpar filtros"
    opcoes = aba.locator("[data-filtro-situacao] option").all_inner_texts()
    conferir(f"o filtro de situação tem os 6 status (na tela: {opcoes})",
             opcoes == ["Todas as situações", "Aguardando envio", "Pendente", "Em análise", "Cadastrado", "Conta aberta",
                        "Já é correntista"])
    conferir("as consultas rápidas saíram", aba.locator("[data-atalho]").count() == 0)
    aba.select_option("[data-filtro-situacao]", "Conta aberta")
    conferir("filtrar por 'Conta aberta' mostra só as 2 contas novas",
             aba.locator("[data-corpo-tabela] tr").count() == 2)
    aba.select_option("[data-filtro-situacao]", "Já é correntista")
    conferir("filtrar por 'Já é correntista' mostra só a 1 pessoa que já era cliente",
             aba.locator("[data-corpo-tabela] tr").count() == 1)
    aba.click("[data-limpar-filtros]")
    conferir("'Limpar filtros' volta a mostrar todos", aba.locator("[data-corpo-tabela] tr").count() > 3
             and aba.input_value("[data-filtro-situacao]") == "")
    # 8. O especialista do banco: aba Empresas → a empresa abre na Visão geral, com os números e a mesma lista
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    banco.goto(endereco + "/banco_empresas.html?empresa=EMP001")
    banco.locator("[data-cabeca-visao] .linha-de-grupos").wait_for(timeout=20000)
    conferir("a ficha abre na aba Visão geral",
             banco.get_attribute("[data-aba-ficha='visao']", "aria-selected") == "true")
    conferir("os números da empresa aparecem", banco.locator("[data-numeros-da-visao] .numero-da-visao").count() >= 4)
    colunas_do_banco = banco.locator("[data-cabeca-visao] tr:nth-child(2) th").count()
    conferir(f"a mesma grade no banco: {dados['campos']} campos + 6 colunas (na tela: {colunas_do_banco})",
             colunas_do_banco == dados["campos"] + 6)
    conferir("no banco, as 3 contas aparecem (2 abertas e 1 correntista)",
             banco.locator("[data-corpo-visao] .selo-conta-aberta").count() == 3)
    conferir("no banco, a Situação também é a primeira coluna",
             banco.inner_text("[data-cabeca-visao] tr:nth-child(2) th >> nth=0") == "Situação")
    conferir("a lista de funcionários da empresa aparece", banco.locator("[data-corpo-visao] tr").count() > 0)
    # A legenda do fim da Visão geral saiu: o "i" em cima da grade explica os status
    conferir("no banco, a legenda do fim da aba saiu", banco.locator("[data-legenda-status-visao]").count() == 0)
    botao_do_banco = banco.locator("[data-legenda-dos-status='funcionarios'] [data-botao-da-legenda]")
    altura_do_i = botao_do_banco.bounding_box()["y"]
    altura_da_grade = banco.locator("[data-corpo-visao]").bounding_box()["y"]
    botao_do_banco.hover()
    itens_do_balao_do_banco = banco.locator("[data-legenda-dos-status='funcionarios'] .item-do-balao-dos-status")
    itens_do_balao_do_banco.first.wait_for(timeout=15000)
    conferir("no banco, o \"i\" fica em cima da grade e explica os 6 status",
             altura_do_i < altura_da_grade and itens_do_balao_do_banco.count() == 6)
    banco.mouse.move(1, 1)
    banco.locator("[data-numeros-da-visao]").scroll_into_view_if_needed()
    banco.screenshot(path="storage/painel/visao_geral_do_banco.png")
