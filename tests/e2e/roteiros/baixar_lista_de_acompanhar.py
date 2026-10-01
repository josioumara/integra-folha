"""Roteiro: o "Baixar lista" de "Acompanhar cadastros" baixa a grade que está na tela (ADR-155).

O defeito: com a grade cheia, mas sem ninguém cadastrado ainda (a carga com o banco, "Em análise"), o botão não baixava
nada e não dizia nada. O que ele confere:
- a Aurora com a carga inicial em análise pelo banco: o "Baixar lista" baixa "funcionarios.csv", com o cabeçalho certo e
  uma linha por pessoa da grade (os mesmos CPFs), todas "Em análise";
- com a grade vazia (a situação "Cadastrado", que ninguém tem ainda), nada é baixado, e o recado "Nenhum funcionário
  para baixar com esses filtros." aparece logo abaixo do botão, à vista na tela de 1366 × 768;
- com o filtro "Em análise" e com a busca por um pedaço do CPF, o arquivo segue a grade, e o download que dá certo tira o
  recado.
"""
import csv
import io
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Acompanhar: o \"Baixar lista\" baixa a grade (todas as situações) e avisa logo abaixo do botão quando não dá"
# As linhas da grade de funcionários
LINHAS_DA_GRADE = "[data-corpo-tabela] tr"
# O botão "Baixar lista", o recado dele e o filtro de situação
BOTAO_DE_BAIXAR = "[data-baixar-lista]"
RECADO_DO_DOWNLOAD = "[data-recado-do-download]"
FILTRO_DE_SITUACAO = "[data-filtro-situacao]"
# O cabeçalho que o arquivo tem de trazer, coluna por coluna
CABECALHO_ESPERADO = ["Nome", "CPF", "Matrícula", "Cargo", "Unidade", "Admissão", "Salário", "Incluído em",
                      "Incluído por", "Situação", "Conta salário aberta em", "Código do banco", "Agência",
                      "Conta salário"]
# A posição da coluna do CPF e a da Situação no arquivo
COLUNA_DO_CPF = CABECALHO_ESPERADO.index("CPF")
COLUNA_DA_SITUACAO = CABECALHO_ESPERADO.index("Situação")
# A frase do servidor quando ninguém da grade pode ser baixado
FRASE_DA_GRADE_VAZIA = "Nenhum funcionário para baixar com esses filtros."
# Um CPF formatado dentro do texto de uma linha da grade (ex.: "529.982.247-25")
PADRAO_DO_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
# A tela de um notebook comum: o recado tem de aparecer nela
LARGURA_DA_TELA = 1366
ALTURA_DA_TELA = 768
# A maior distância (em pixels) entre o pé do botão e o recado: "logo abaixo do botão"
DISTANCIA_MAXIMA_DO_RECADO = 60


def preparar() -> dict:
    """A Aurora corrige a pendência e manda a carga inicial ao banco: a grade tem as pessoas, todas "Em análise"."""
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth
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
    # A carga inicial vai ao banco: a grade mostra as pessoas "Em análise", e ninguém está cadastrado ainda
    enviar_a_aurora_ao_banco(conexao, verdade)
    conexao.close()
    return {}


def cpfs_na_grade(aba) -> list[str]:
    """Os CPFs das linhas que a grade mostra agora (um por linha, como a tela escreve)."""
    cpfs = []
    for texto_da_linha in aba.locator(LINHAS_DA_GRADE).all_inner_texts():
        encontrado = PADRAO_DO_CPF.search(texto_da_linha)
        if encontrado:
            cpfs.append(encontrado.group(0))
    return cpfs


def baixar(aba) -> tuple[str, list[list[str]]]:
    """Clica em "Baixar lista" e espera o arquivo. Devolve (o nome do arquivo, as linhas do CSV, lidas como o Excel lê)."""
    with aba.expect_download(timeout=15000) as espera_do_download:
        aba.click(BOTAO_DE_BAIXAR)
    download = espera_do_download.value
    # "utf-8-sig" tira a marca do UTF-8 do começo (a que avisa o Excel)
    with open(download.path(), encoding="utf-8-sig") as arquivo:
        linhas = list(csv.reader(io.StringIO(arquivo.read()), delimiter=";"))
    return download.suggested_filename, linhas


def coluna_do_arquivo(linhas: list[list[str]], posicao: int) -> list[str]:
    """Os valores de uma coluna do arquivo, sem o cabeçalho. Ex.: (linhas, COLUNA_DO_CPF) → ["529.982.247-25", ...]."""
    valores = []
    for linha in linhas[1:]:
        valores.append(linha[posicao])
    return valores


def conferir_o_arquivo_igual_a_grade(aba, conferir, quando: str) -> None:
    """Baixa a lista e confere que o arquivo é a grade de agora: as mesmas pessoas (pelo CPF) e a mesma quantidade."""
    cpfs_da_grade = cpfs_na_grade(aba)
    nome_do_arquivo, linhas = baixar(aba)
    conferir(quando + ": o arquivo baixado se chama funcionarios.csv (na tela: " + nome_do_arquivo + ")",
             nome_do_arquivo == "funcionarios.csv")
    conferir(quando + ": o cabeçalho tem as colunas certas, com a Conta salário", linhas[0] == CABECALHO_ESPERADO)
    conferir(quando + ": uma linha por pessoa da grade (" + str(len(linhas) - 1) + " no arquivo, " +
             str(len(cpfs_da_grade)) + " na grade)", len(linhas) - 1 == len(cpfs_da_grade) and len(cpfs_da_grade) > 0)
    conferir(quando + ": os CPFs do arquivo são os da grade",
             sorted(coluna_do_arquivo(linhas, COLUNA_DO_CPF)) == sorted(cpfs_da_grade))
    conferir(quando + ": toda linha com a situação \"Em análise\", como na grade",
             set(coluna_do_arquivo(linhas, COLUNA_DA_SITUACAO)) == {"Em análise"})
    conferir(quando + ": o download que deu certo não deixa recado", aba.locator(RECADO_DO_DOWNLOAD).is_hidden())


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre Acompanhar como a empresa, numa tela de 1366 × 768, e baixa a lista com e sem filtros."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.set_viewport_size({"width": LARGURA_DA_TELA, "height": ALTURA_DA_TELA})
    aba.goto(endereco + "/acompanhar.html")
    # A grade de verdade chegou: a primeira linha e a marca de "pronto" da tabela
    aba.locator(LINHAS_DA_GRADE).first.wait_for(timeout=30000)
    aba.wait_for_function("() => document.querySelector('[data-tabela-funcionarios]').hasAttribute('data-dado-pronto')",
                          timeout=30000)
    conferir("a grade mostra a carga em análise pelo banco (" + str(len(cpfs_na_grade(aba))) + " pessoas)",
             len(cpfs_na_grade(aba)) > 0)

    # 1. Sem filtro: o arquivo é a grade inteira (o defeito: aqui nada era baixado)
    conferir_o_arquivo_igual_a_grade(aba, conferir, "sem filtro")

    # 2. A grade vazia: nada é baixado, e o motivo aparece logo abaixo do botão, à vista
    downloads_sem_espera = []
    aba.on("download", lambda download: downloads_sem_espera.append(download))
    aba.select_option(FILTRO_DE_SITUACAO, "Cadastrado")
    aba.locator("[data-sem-resultados]").wait_for(state="visible", timeout=10000)
    aba.click(BOTAO_DE_BAIXAR)
    recado = aba.locator(RECADO_DO_DOWNLOAD)
    recado.wait_for(state="visible", timeout=10000)
    conferir("com a grade vazia, o recado diz por que nada foi baixado (na tela: " + recado.inner_text() + ")",
             recado.inner_text() == FRASE_DA_GRADE_VAZIA)
    conferir("e nada foi baixado", downloads_sem_espera == [])
    caixa_do_recado = recado.bounding_box()
    caixa_do_botao = aba.locator(BOTAO_DE_BAIXAR).bounding_box()
    conferir("o recado está à vista na tela de 1366 × 768",
             caixa_do_recado["y"] >= 0 and caixa_do_recado["y"] + caixa_do_recado["height"] <= ALTURA_DA_TELA)
    distancia_do_botao = caixa_do_recado["y"] - (caixa_do_botao["y"] + caixa_do_botao["height"])
    conferir("o recado fica logo abaixo do botão (" + str(round(distancia_do_botao)) + " px)",
             0 <= distancia_do_botao <= DISTANCIA_MAXIMA_DO_RECADO)

    # 3. O filtro "Em análise": o arquivo segue a grade (e o recado de antes sai)
    aba.select_option(FILTRO_DE_SITUACAO, "Em análise")
    aba.locator(LINHAS_DA_GRADE).first.wait_for(timeout=10000)
    conferir_o_arquivo_igual_a_grade(aba, conferir, "com o filtro \"Em análise\"")

    # 4. A busca por um pedaço do CPF da primeira pessoa: a grade encolhe, e o arquivo traz quem ela mostra
    quantidade_antes_da_busca = len(cpfs_na_grade(aba))
    digitos_buscados = re.sub(r"\D", "", cpfs_na_grade(aba)[0])[:6]
    aba.fill("[data-busca]", digitos_buscados)
    aba.wait_for_function("(quantidade) => document.querySelectorAll('[data-corpo-tabela] tr').length < quantidade",
                          arg=quantidade_antes_da_busca, timeout=10000)
    conferir_o_arquivo_igual_a_grade(aba, conferir, "com a busca por \"" + digitos_buscados + "\"")
