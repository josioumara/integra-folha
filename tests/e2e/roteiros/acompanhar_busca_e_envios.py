"""Roteiro: a busca de funcionários por CPF e situação e as ações de cada envio do histórico, em Acompanhar cadastros.

O que ele confere (com a IA simulada, sem custo):
- a consulta dos funcionários busca por CPF e por situação: a caixa diz "Buscar por CPF", o filtro de unidade não
  aparece (continua na página, oculto), e o "i" dos status continua em cima da grade;
- a busca acha pelos números do CPF, com ou sem pontos e traço; um texto sem número não acha ninguém, e o aviso sugere
  outro CPF; "Limpar filtros" volta a lista inteira;
- no histórico, o envio que espera a conferência das colunas tem, na mesma linha, "Descartar este envio" no canto
  esquerdo, em letra menor, e "Conferir arquivo" no canto direito, discreto (um link, sem a cara de botão); o
  "Conferir arquivo" abre a janela do envio, com as duas abas do resultado.
Dados 100% sintéticos: a Aurora do gerador (a carga inicial com o banco e a inclusão parada nas colunas).
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Acompanhar: busca por CPF e situação (sem o filtro de unidade) e as ações de cada envio nos cantos"
# Um CPF formatado dentro do texto de uma linha da grade (ex.: "529.982.247-25")
PADRAO_DO_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
# As linhas da grade de funcionários
LINHAS_DA_GRADE = "[data-corpo-tabela] tr"


def preparar() -> dict:
    """A carga inicial da Aurora com o banco (a grade tem funcionários) e a inclusão parada na conferência das colunas.

    Devolve: {inclusao} — o número do envio que espera a conferência das colunas.
    """
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_avaliacao_do_banco import enviar_a_aurora_ao_banco
    from tests.test_correcao import RAIZ, busca_falsa
    from tests.test_fluxo_empresa import iniciar, receber
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
    # A carga inicial vai ao banco: as pessoas dela aparecem na grade, "Em análise"
    enviar_a_aurora_ao_banco(conexao, verdade)
    # A inclusão para na conferência das colunas: o cartão dela no histórico tem as duas ações
    processamento_id, empresa_id = receber(conexao, "aurora_inclusao")
    iniciar(conexao, processamento_id, empresa_id)
    conexao.close()
    return {"inclusao": processamento_id}


def cpfs_na_grade(aba) -> list[str]:
    """Os CPFs das linhas que a grade mostra agora (um por linha, como a tela escreve)."""
    cpfs = []
    for texto_da_linha in aba.locator(LINHAS_DA_GRADE).all_inner_texts():
        encontrado = PADRAO_DO_CPF.search(texto_da_linha)
        if encontrado:
            cpfs.append(encontrado.group(0))
    return cpfs


def somente_numeros(texto: str) -> str:
    """Só os números de um texto. Ex.: "529.982.247-25" → "52998224725"."""
    return re.sub(r"\D", "", texto)


def conferir_a_busca(aba, conferir) -> None:
    """A consulta dos funcionários: a busca por CPF (com ou sem pontos), a situação e o filtro de unidade oculto."""
    aba.locator(LINHAS_DA_GRADE).first.wait_for(timeout=30000)
    aba.wait_for_function("() => document.querySelector('[data-tabela-funcionarios]').hasAttribute('data-dado-pronto')",
                          timeout=30000)
    busca = aba.locator("[data-busca]")
    conferir(f"a busca é por CPF (na tela: {busca.get_attribute('placeholder')})",
             busca.get_attribute("placeholder") == "Buscar por CPF")
    conferir("o filtro de situação continua à vista", aba.locator("[data-filtro-situacao]").is_visible())
    unidade = aba.locator("[data-filtro-unidade]")
    conferir("o filtro de unidade não aparece (continua na página, com a marca de oculto)",
             unidade.count() == 1 and unidade.is_hidden()
             and unidade.get_attribute("data-oculto-nesta-versao") == "filtro-de-unidade")
    conferir("o 'i' dos status continua em cima da grade",
             aba.locator("[data-legenda-dos-status='funcionarios'] [data-botao-da-legenda]").count() == 1)
    total = aba.locator(LINHAS_DA_GRADE).count()
    cpf_da_primeira = cpfs_na_grade(aba)[0]
    numeros_do_cpf = somente_numeros(cpf_da_primeira)
    # Os 6 primeiros números, sem pontos: só aparece quem tem esses números no CPF
    busca.fill(numeros_do_cpf[:6])
    achados = cpfs_na_grade(aba)
    todos_tem_os_numeros = True
    for cpf in achados:
        if numeros_do_cpf[:6] not in somente_numeros(cpf):
            todos_tem_os_numeros = False
    conferir(f"a busca pelos números do CPF acha só quem tem esses números ({len(achados)} de {total})",
             len(achados) >= 1 and todos_tem_os_numeros and len(achados) == aba.locator(LINHAS_DA_GRADE).count())
    # Os mesmos números com o ponto (como o CPF é escrito): o mesmo resultado
    busca.fill(cpf_da_primeira[:7])
    conferir("com o ponto, a busca acha as mesmas pessoas", cpfs_na_grade(aba) == achados)
    # O CPF inteiro: a pessoa dele
    busca.fill(cpf_da_primeira)
    conferir("o CPF inteiro acha a pessoa", cpf_da_primeira in cpfs_na_grade(aba))
    # Um texto sem número não é um CPF: ninguém aparece, e o aviso sugere outro CPF
    busca.fill("Maria")
    aviso = aba.locator("[data-sem-resultados]")
    conferir("um nome não acha ninguém (a busca é por CPF), e o aviso sugere outro CPF",
             aba.locator(LINHAS_DA_GRADE).count() == 0 and aviso.is_visible() and "outro CPF" in aviso.inner_text())
    # "Limpar filtros": a lista inteira volta
    aba.click("[data-limpar-filtros]")
    conferir("'Limpar filtros' volta a lista inteira", aba.locator(LINHAS_DA_GRADE).count() == total)
    aba.locator("#funcionarios").screenshot(path="storage/painel/acompanhar_busca_por_cpf.png")


def conferir_as_acoes_do_envio(aba, dados: dict, conferir) -> None:
    """O cartão do envio que espera as colunas: "Descartar este envio" à esquerda e "Conferir arquivo" à direita."""
    marca_do_envio = "[data-continuar-envio='" + dados["inclusao"] + "']"
    link = aba.locator("[data-lista-envios] " + marca_do_envio)
    link.wait_for(timeout=30000)
    # A linha das ações que tem o link deste envio (o "has" procura dentro da linha)
    acoes = aba.locator("[data-lista-envios] .acoes-do-envio", has=aba.locator(marca_do_envio))
    descartar = acoes.locator("button", has_text="Descartar este envio")
    conferir("as duas ações na mesma linha do cartão: 'Descartar este envio' e 'Conferir arquivo'",
             acoes.count() == 1 and descartar.count() == 1 and link.inner_text().strip() == "Conferir arquivo")
    caixa_da_linha = acoes.bounding_box()
    caixa_do_descartar = descartar.bounding_box()
    caixa_do_conferir = link.bounding_box()
    conferir("'Descartar este envio' fica no canto esquerdo", abs(caixa_do_descartar["x"] - caixa_da_linha["x"]) < 2)
    fim_do_conferir = caixa_do_conferir["x"] + caixa_do_conferir["width"]
    fim_da_linha = caixa_da_linha["x"] + caixa_da_linha["width"]
    conferir("'Conferir arquivo' fica no canto direito", abs(fim_do_conferir - fim_da_linha) < 2)
    fonte_do_descartar = descartar.evaluate("elemento => parseFloat(getComputedStyle(elemento).fontSize)")
    conferir(f"'Descartar este envio' em letra menor (na tela: {fonte_do_descartar}px)", fonte_do_descartar <= 12)
    conferir("'Conferir arquivo' é discreto: um link, sem a cara de botão",
             "botao" not in (link.get_attribute("class") or ""))
    acoes.screenshot(path="storage/painel/acompanhar_acoes_do_envio.png")
    # "Conferir arquivo" abre a janela do envio, com as duas abas do resultado
    link.click()
    aba.locator(".janela-novo-envio[open]").wait_for(timeout=10000)
    quadro = aba.frame_locator(".janela-novo-envio-quadro")
    quadro.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    conferir("'Conferir arquivo' abre a janela do envio, na aba 'Funcionários'",
             quadro.locator("[data-aba-do-resultado='funcionarios'][aria-selected='true']").count() == 1)
    aba.keyboard.press("Escape")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """A consulta dos funcionários e o histórico dos envios, como a empresa."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_a_busca(aba, conferir)
    conferir_as_acoes_do_envio(aba, dados, conferir)
    aba.close()
