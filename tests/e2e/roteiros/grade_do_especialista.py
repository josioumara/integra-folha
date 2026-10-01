"""Roteiro: a grade de pessoas de um envio na tela Envios do especialista do banco (ADR-111).

O que ele confere (a mesma grade da empresa, na tela do especialista do banco):
- uma coluna por campo do parâmetro vigente, mais Situação e Ação;
- a marca "*" em cada coluna obrigatória do parâmetro (e só nelas);
- o valor identificado na célula, e "Informação não encontrada" quando o campo veio vazio;
- a legenda acima da grade.
Também guarda uma foto da grade (storage/painel/grade_do_especialista.png) para conferir o visual.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Grade do especialista: pessoas do envio com todos os campos do parâmetro e os obrigatórios marcados"


def preparar() -> dict:
    """A carga inicial da Aurora esperando o banco; devolve quantos campos e obrigatórios o parâmetro tem."""
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, parametros
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_avaliacao_do_banco import enviar_a_aurora_ao_banco
    from tests.test_correcao import RAIZ, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (a correção do CPF usa o valor certo)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    enviar_a_aurora_ao_banco(conexao, verdade)
    # O parâmetro vigente: quantos campos e quantos obrigatórios a grade tem de mostrar
    _, campos_do_layout = parametros.layout_ativo(conexao)
    obrigatorios = 0
    for campo in campos_do_layout:
        if campo.obrigatorio:
            obrigatorios = obrigatorios + 1
    conexao.close()
    return {"campos": len(campos_do_layout), "obrigatorios": obrigatorios}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre Envios como o especialista e confere a grade de pessoas do envio."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_envios.html")
    # A grade do parâmetro está pronta quando a linha dos grupos aparece no cabeçalho das pessoas
    aba.locator("[data-cabeca-pessoas] .linha-de-grupos").wait_for(timeout=20000)
    aba.locator("[data-corpo-pessoas] tr").first.wait_for(timeout=20000)
    # 1. Uma coluna por campo do parâmetro, mais Situação e Ação
    colunas_na_tela = aba.locator("[data-cabeca-pessoas] tr:nth-child(2) th").count()
    conferir(f"{dados['campos']} campos do parâmetro + Situação e Ação (na tela: {colunas_na_tela})",
             colunas_na_tela == dados["campos"] + 2)
    # 2. A marca "*" em cada obrigatório, e só neles
    marcas = aba.locator("[data-cabeca-pessoas] .marca-obrigatorio").count()
    conferir(f"{dados['obrigatorios']} colunas obrigatórias marcadas (na tela: {marcas})", marcas == dados["obrigatorios"])
    # 3. Uma célula por coluna, com o valor ou a frase fixa
    celulas = aba.locator("[data-corpo-pessoas] tr").first.locator("td").count()
    conferir("cada linha tem uma célula por coluna", celulas == dados["campos"] + 2)
    nao_encontrados = aba.locator("[data-corpo-pessoas] .valor-nao-encontrado").count()
    conferir("campo vazio aparece como 'Informação não encontrada'", nao_encontrados > 0)
    texto_da_primeira_linha = aba.inner_text("[data-corpo-pessoas] tr >> nth=0")
    conferir("o valor identificado aparece (CPF formatado na linha)", "-" in texto_da_primeira_linha
             and "." in texto_da_primeira_linha)
    # 4. A legenda aparece acima da grade
    conferir("legenda da marca e da frase visível", aba.locator("[data-legenda-grade]").is_visible())
    # A foto da grade, para conferir o visual
    aba.set_viewport_size({"width": 1440, "height": 900})
    aba.locator(".tabela-pessoas-envio").first.locator("xpath=..").screenshot(path="storage/painel/grade_do_especialista.png")
