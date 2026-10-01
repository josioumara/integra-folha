"""Roteiro: as telas com só os campos obrigatórios do parâmetro (ADR-143).

A regra: a página de carregar o arquivo diz quais campos são obrigatórios; a grade da lista de funcionários mostra só
os obrigatórios, e o clique na pessoa abre o detalhe com todas as informações; depois de carregar, a confirmação é só
dos campos obrigatórios.

O que ele confere, com o parâmetro de 4 obrigatórios (gravado pelo mesmo scripts/aplicar_parametro_adr_143.py que
gravou a v7 no banco de todos):
- Cadastrar: o quadro "O arquivo precisa ter" lista os obrigatórios do parâmetro, e só eles;
- o aceite das colunas: em cima, só as colunas que alimentam um obrigatório; as outras descem para "Outras
  informações do arquivo", fechado. A coluna em dúvida com um obrigatório ("Vencimentos") continua pedindo a escolha;
  a em dúvida só entre opcionais ("Código") fica de fora sem pergunta, e o aceite dá certo sem escolher nada nela;
- a conferência da lista: a linha, os obrigatórios, a situação e as ações (sem o "Nome"); o clique na pessoa abre a
  ficha dela, logo abaixo;
- Acompanhar: a grade com os obrigatórios (mais a Situação, a conta e o Incluído); o clique numa célula comum abre a
  ficha com todos os campos do parâmetro, e o CBO, que não veio, aparece como "Informação não encontrada";
- o banco, na tela Envios: a grade com os obrigatórios (mais a Situação e a Ação); o clique abre a ficha com todos os
  campos do parâmetro;
- o banco, na Visão geral da empresa: a mesma grade; o clique abre o detalhe com todos os campos e a conta.
Guarda duas fotos (storage/painel/aceite_so_dos_obrigatorios.png e grade_so_dos_obrigatorios.png) para conferir o
visual. Dados 100% inventados: a Aurora do gerador sintético e uma planilha escrita aqui, com CPFs sorteados.
"""
from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar, pasta_do_roteiro

DESCRICAO = ("Telas dos obrigatórios: o aviso do Cadastrar, o aceite só dos obrigatórios, a conferência e as grades "
             "da empresa e do banco com o detalhe completo")
# As colunas da planilha do envio novo. A IA simulada (modo MOCK) marca "Vencimentos" como dúvida só com a renda (um
# obrigatório) e "Código" como dúvida entre a matrícula e o código da unidade (os dois opcionais); o "Nome" e o
# "Cargo" não são obrigatórios no parâmetro de 4 obrigatórios
CABECALHO_DA_PLANILHA = "Nome;CPF;Cargo;Data de admissão;Telefone;Código;Vencimentos"
# As pessoas da planilha (inventadas; os CPFs são válidos e sorteados para os testes, nenhum vem das bases de teste)
PESSOAS_DA_PLANILHA = [
    "Maria Souza;529.982.247-25;Analista;01/02/2026;11987654321;A-01;3500,00",
    "João Lima;111.444.777-35;Assistente;15/02/2026;11912345678;A-02;2800,00",
]
# O JavaScript que diz como o aceite ficou separado: as colunas de cima e as de baixo (pelo nome no arquivo), se todas
# as de cima alimentam um obrigatório, se nenhuma de baixo alimenta, e se o bloco de baixo está fechado
SEPARACAO_DO_ACEITE = """obrigatorios => {
    function tem_obrigatorio(linha) {
        for (const campo of linha.dataset.camposDaColuna.split(" ")) {
            if (obrigatorios.includes(campo)) {
                return true;
            }
        }
        return false;
    }
    const em_cima = Array.from(document.querySelectorAll("[data-real-corpo-colunas] tr[data-campos-da-coluna]"));
    const embaixo = Array.from(document.querySelectorAll(
        "[data-real-corpo-colunas-opcionais] tr[data-campos-da-coluna]"));
    const resultado = {em_cima: [], embaixo: [], em_cima_so_obrigatorios: true, embaixo_sem_obrigatorio: true,
        bloco_fechado: !document.querySelector("[data-real-bloco-colunas-opcionais]").open};
    for (const linha of em_cima) {
        resultado.em_cima.push(linha.dataset.grupoDaColuna);
        if (!tem_obrigatorio(linha)) {
            resultado.em_cima_so_obrigatorios = false;
        }
    }
    for (const linha of embaixo) {
        resultado.embaixo.push(linha.dataset.grupoDaColuna);
        if (tem_obrigatorio(linha)) {
            resultado.embaixo_sem_obrigatorio = false;
        }
    }
    return resultado;
}"""
# O JavaScript que lê os títulos da conferência da lista (só o texto do título, sem a marca "*" dos obrigatórios)
TITULOS_DA_CONFERENCIA = """() => {
    const titulos = [];
    for (const titulo of document.querySelectorAll("[data-real-cabeca-conferencia] th")) {
        let texto = "";
        if (titulo.firstChild) {
            texto = titulo.firstChild.textContent;
        }
        titulos.push(texto);
    }
    return titulos;
}"""
# O JavaScript que diz se a conferência já mostra uma pessoa (uma linha com mais de 3 células)
CONFERENCIA_COM_PESSOA = """() => {
    for (const linha of document.querySelectorAll("[data-real-corpo-conferencia] > tr")) {
        if (linha.children.length > 3) {
            return true;
        }
    }
    return false;
}"""


def preparar() -> dict:
    """A carga inicial da Aurora esperando o banco, o parâmetro de 4 obrigatórios e a planilha do envio novo.

    Devolve: {campos (quantos o parâmetro tem), campos_obrigatorios e rotulos_obrigatorios (na ordem do layout),
    planilha (o caminho do arquivo)}.
    """
    import csv

    import rag.busca
    from scripts.aplicar_parametro_adr_143 import aplicar as aplicar_o_parametro_de_4_obrigatorios
    from scripts.gerar_dados import main as gerar_dados
    from services import acompanhamento, auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_avaliacao_do_banco import enviar_a_aurora_ao_banco
    from tests.test_correcao import RAIZ, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (a correção do CPF da Aurora usa o valor certo)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # A Aurora manda a carga inicial ao banco com o parâmetro de antes: as grades da empresa e do banco a mostram
    enviar_a_aurora_ao_banco(conexao, verdade)
    # Depois, o parâmetro passa a ter só 4 obrigatórios, com o campo novo do CBO (em branco para todo mundo)
    aplicar_o_parametro_de_4_obrigatorios(conexao)
    # As colunas do parâmetro vigente: todas (o detalhe) e as obrigatórias (a grade), na ordem do layout
    colunas = acompanhamento.colunas_da_consulta(conexao)
    campos_obrigatorios = []
    rotulos_obrigatorios = []
    for coluna in colunas:
        if coluna["obrigatorio"]:
            campos_obrigatorios.append(coluna["campo"])
            rotulos_obrigatorios.append(coluna["rotulo"])
    conexao.close()
    # A planilha do envio novo, na pasta temporária do roteiro
    planilha = pasta_do_roteiro() / "folha_com_4_obrigatorios.csv"
    planilha.write_text(CABECALHO_DA_PLANILHA + "\n" + "\n".join(PESSOAS_DA_PLANILHA) + "\n", encoding="utf-8")
    return {"campos": len(colunas), "campos_obrigatorios": campos_obrigatorios,
            "rotulos_obrigatorios": rotulos_obrigatorios, "planilha": str(planilha)}


def conferir_o_quadro_dos_obrigatorios(aba, dados: dict, conferir) -> None:
    """Antes do envio: o quadro "O arquivo precisa ter" lista os obrigatórios do parâmetro, e só eles."""
    aba.locator("[data-campos-obrigatorios]:not([hidden])").wait_for(timeout=20000)
    # Cada item é "Nome do campo: descrição do banco"; o nome vem antes dos dois-pontos
    nomes_nos_itens = []
    for item in aba.locator("[data-lista-campos-obrigatorios] li").all_inner_texts():
        nomes_nos_itens.append(item.split(":")[0])
    conferir(f"Cadastrar: o quadro lista os obrigatórios do parâmetro (na tela: {nomes_nos_itens})",
             nomes_nos_itens == dados["rotulos_obrigatorios"])
    conferir("Cadastrar: o quadro diz que as outras informações entram quando o agente reconhece",
             "entram quando nosso agente reconhece" in aba.inner_text("[data-campos-obrigatorios]"))


def conferir_o_aceite(aba, dados: dict, conferir) -> None:
    """O aceite das colunas: em cima, só as dos obrigatórios; embaixo, fechadas, as outras; o aceite dá certo."""
    aba.set_input_files("#campo-arquivo", dados["planilha"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba.locator("[data-real-aceitar]:not([hidden])").wait_for(timeout=60000)
    # As colunas ficam na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    separacao = aba.evaluate(SEPARACAO_DO_ACEITE, dados["campos_obrigatorios"])
    conferir(f"aceite: em cima, só colunas de obrigatórios (na tela: {separacao['em_cima']})",
             len(separacao["em_cima"]) > 0 and separacao["em_cima_so_obrigatorios"])
    conferir(f"aceite: embaixo, as outras, com o Nome e o Código (na tela: {separacao['embaixo']})",
             separacao["embaixo_sem_obrigatorio"] and "Nome" in separacao["embaixo"]
             and "Código" in separacao["embaixo"])
    conferir("aceite: as outras informações ficam fechadas", separacao["bloco_fechado"])
    conferir("aceite: a nota de cima explica que as outras entram sem pergunta",
             aba.locator("[data-real-nota-obrigatorias]").is_visible())
    # A dúvida só entre opcionais ("Código") fica de fora sem pergunta; a dúvida com um obrigatório ("Vencimentos")
    # continua pedindo a escolha
    conferir("aceite: a dúvida só entre opcionais já vem em 'Deixar de fora'",
             aba.input_value("select[data-coluna='Código']") == "(ignorar coluna)")
    escolha_da_renda = aba.locator("[data-real-corpo-colunas] select[data-coluna='Vencimentos']")
    conferir("aceite: a dúvida com um obrigatório fica em cima, pedindo a escolha",
             escolha_da_renda.count() == 1 and escolha_da_renda.input_value() == "")
    # A foto do aceite, para conferir o visual
    aba.locator("#resultado-real").screenshot(path="storage/painel/aceite_so_dos_obrigatorios.png")
    # A pessoa escolhe só o campo de "Vencimentos" e aceita: nada das outras colunas é pedido
    escolha_da_renda.select_option("valor_renda")
    aba.click("[data-real-aceitar]")
    aba.wait_for_function("() => document.querySelector('[data-real-aceitar]').hidden", timeout=60000)
    conferir("aceite: dá certo sem escolher nada nas outras informações",
             not aba.locator("[data-real-erro]").is_visible())


def conferir_a_conferencia_da_lista(aba, dados: dict, conferir) -> None:
    """A conferência da lista: a linha, os obrigatórios, a situação e as ações; o clique na pessoa abre a ficha."""
    bloco = aba.locator("[data-real-bloco-conferencia]")
    bloco.wait_for(state="visible", timeout=60000)
    # Sem pendência a conferência vem fechada: abre (abrir busca a lista)
    if not bloco.evaluate("elemento => elemento.open"):
        aba.click("[data-real-bloco-conferencia] > summary")
    # Todas as pessoas, e não só as com pendência
    aba.uncheck("[data-real-so-pendencias]")
    aba.wait_for_function(CONFERENCIA_COM_PESSOA, timeout=30000)
    titulos = aba.evaluate(TITULOS_DA_CONFERENCIA)
    esperados = ["Linha"] + dados["rotulos_obrigatorios"] + ["Situação", ""]
    conferir(f"conferência: a linha, os obrigatórios, a situação e as ações (na tela: {titulos})", titulos == esperados)
    # O clique numa célula comum da pessoa (o 2º campo obrigatório) abre a ficha logo abaixo dela
    pessoa = aba.locator("[data-real-corpo-conferencia] > tr").filter(has=aba.locator("td:nth-child(4)")).first
    pessoa.locator("td").nth(2).click()
    conferir("conferência: o clique na pessoa abre a ficha dela",
             aba.locator("[data-real-corpo-conferencia] tr.linha-ficha-real").count() == 1)


def conferir_a_grade_da_empresa(aba, endereco: str, dados: dict, conferir) -> None:
    """Acompanhar: a grade só com os obrigatórios; o clique abre a ficha com todos os campos do parâmetro."""
    obrigatorios = len(dados["campos_obrigatorios"])
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-cabeca-tabela] .linha-de-grupos").wait_for(timeout=20000)
    aba.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    # Situação + os obrigatórios + Código do banco, Agência, Conta, Aberta em + Incluído
    colunas_na_tela = aba.locator("[data-cabeca-tabela] tr:nth-child(2) th").count()
    conferir(f"Acompanhar: {obrigatorios} obrigatórios + 6 colunas da consulta (na tela: {colunas_na_tela})",
             colunas_na_tela == obrigatorios + 6)
    marcas = aba.locator("[data-cabeca-tabela] .marca-obrigatorio").count()
    conferir(f"Acompanhar: todas as colunas do parâmetro com a marca de obrigatório (na tela: {marcas})",
             marcas == obrigatorios)
    conferir("Acompanhar: a legenda diz que a grade mostra as informações obrigatórias",
             "informações obrigatórias" in aba.inner_text("[data-legenda-grade]"))
    # A foto da grade, para conferir o visual
    aba.locator("[data-tabela-funcionarios]").screenshot(path="storage/painel/grade_so_dos_obrigatorios.png")
    # O clique numa célula comum da pessoa (o 2º obrigatório; o 1º é o botão) abre a ficha
    aba.locator("[data-corpo-tabela] tr").first.locator("td").nth(2).click()
    aba.locator("#janela-ficha[open]").wait_for(timeout=10000)
    # + 3: a conta no banco (agência, conta e data de abertura), que não é do parâmetro
    campos_na_ficha = aba.locator("#janela-ficha-grupos dt").count()
    conferir(f"Acompanhar: a ficha mostra os {dados['campos']} campos do parâmetro e a conta (na tela: "
             f"{campos_na_ficha})", campos_na_ficha == dados["campos"] + 3)
    conferir("Acompanhar: o CBO, que não veio, aparece como 'Informação não encontrada'",
             aba.locator("#janela-ficha-grupos .valor-nao-encontrado").count() > 0)
    aba.keyboard.press("Escape")


def conferir_a_grade_de_envios(banco, endereco: str, dados: dict, conferir) -> None:
    """Envios, no banco: a grade só com os obrigatórios; o clique abre a ficha com todos os campos do parâmetro."""
    obrigatorios = len(dados["campos_obrigatorios"])
    banco.goto(endereco + "/banco_envios.html")
    banco.locator("[data-cabeca-pessoas] .linha-de-grupos").wait_for(timeout=20000)
    banco.locator("[data-corpo-pessoas] tr").first.wait_for(timeout=20000)
    colunas_na_tela = banco.locator("[data-cabeca-pessoas] tr:nth-child(2) th").count()
    conferir(f"Envios: {obrigatorios} obrigatórios + Situação e Ação (na tela: {colunas_na_tela})",
             colunas_na_tela == obrigatorios + 2)
    # O clique numa célula comum da pessoa (o 2º obrigatório; o 1º é o botão) abre a ficha
    banco.locator("[data-corpo-pessoas] tr").first.locator("td").nth(1).click()
    banco.locator("#janela-ficha-pessoa[open]").wait_for(timeout=10000)
    campos_na_ficha = banco.locator("#janela-ficha-pessoa [data-ficha-grupos] dt").count()
    conferir(f"Envios: a ficha mostra os {dados['campos']} campos do parâmetro (na tela: {campos_na_ficha})",
             campos_na_ficha == dados["campos"])
    banco.locator("#janela-ficha-pessoa [data-fechar-janela]").first.click()


def conferir_a_visao_geral(banco, endereco: str, dados: dict, conferir) -> None:
    """A Visão geral da empresa, no banco: a grade só com os obrigatórios; o clique abre o detalhe com tudo."""
    obrigatorios = len(dados["campos_obrigatorios"])
    banco.goto(endereco + "/banco_empresas.html?empresa=EMP001")
    banco.locator("[data-cabeca-visao] .linha-de-grupos").wait_for(timeout=20000)
    banco.locator("[data-corpo-visao] tr").first.wait_for(timeout=20000)
    colunas_na_tela = banco.locator("[data-cabeca-visao] tr:nth-child(2) th").count()
    conferir(f"Visão geral: {obrigatorios} obrigatórios + 6 colunas (na tela: {colunas_na_tela})",
             colunas_na_tela == obrigatorios + 6)
    banco.locator("[data-corpo-visao] tr").first.locator("td").nth(2).click()
    banco.locator("#janela-detalhe-funcionario[open]").wait_for(timeout=10000)
    # + 4: as informações bancárias (código do banco, agência, conta e data de abertura)
    campos_na_janela = banco.locator("#janela-detalhe-funcionario [data-detalhe-grupos] dt").count()
    conferir(f"Visão geral: o detalhe mostra os {dados['campos']} campos do parâmetro e a conta (na tela: "
             f"{campos_na_janela})", campos_na_janela == dados["campos"] + 4)
    # Nas informações bancárias do detalhe, a conta que o banco informa se chama "Conta salário"
    itens_do_detalhe = banco.locator("#janela-detalhe-funcionario [data-detalhe-grupos] dt").all_inner_texts()
    conferir(f"Visão geral: o detalhe chama a conta de 'Conta salário' (na tela: {itens_do_detalhe[-4:]})",
             "Conta salário" in itens_do_detalhe and "Conta" not in itens_do_detalhe)
    banco.locator("#janela-detalhe-funcionario [data-fechar-janela]").last.click()
    conferir("Visão geral: 'Voltar' fecha o detalhe", banco.locator("#janela-detalhe-funcionario[open]").count() == 0)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Cadastrar e Acompanhar como a empresa; Envios e a Visão geral como o especialista do banco."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    conferir_o_quadro_dos_obrigatorios(aba, dados, conferir)
    conferir_o_aceite(aba, dados, conferir)
    conferir_a_conferencia_da_lista(aba, dados, conferir)
    conferir_a_grade_da_empresa(aba, endereco, dados, conferir)
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_a_grade_de_envios(banco, endereco, dados, conferir)
    conferir_a_visao_geral(banco, endereco, dados, conferir)
