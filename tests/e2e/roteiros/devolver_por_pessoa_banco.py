"""Roteiro: o especialista aponta um problema numa pessoa e decide "Aprovar N e devolver 1" (ADR-121).

O que ele confere na aba Envios do Portal Interno:
- os filtros novos das pessoas: "Todos", "Confirmados pela empresa (N)" e "Apontados por você (N)";
- a janela "Apontar problema" com a lista fechada de motivos do servidor; recado curto é recusado na própria janela;
- a pessoa apontada ganha o selo "Apontado por você" e o recado embaixo; o botão vira "Aprovar N pessoas e devolver 1";
- "Desfazer" tira o apontamento e o botão volta a ser "Aprovar o envio";
- apontar de novo, "Aprovar N e devolver 1" pede confirmação na própria barra, e o "Sim" aprova: o envio fica
  "Aprovado", a linha "aprovado em parte" aparece em "Idas e voltas com o banco" e o envio de devolução aparece
  entre os avaliados, com a origem.
"""
import re

from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Envios do banco: apontar problema numa pessoa, desfazer, e 'Aprovar N e devolver 1' com idas e voltas"

# O recado que o especialista escreve para a empresa (mais de 15 letras)
RECADO = "O salário parece ter um zero a mais para o cargo. Pode confirmar?"


def preparar() -> dict:
    """A carga inicial da Aurora esperando o banco (a mesma preparação do roteiro grade_do_especialista)."""
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth
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
    # O envio que espera o banco
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    conexao.close()
    return {"processamento_id": processamento_id}


def texto_esperado_do_botao(aprovadas: int) -> str:
    """O texto do botão com 1 apontamento. Exemplo: 33 → "Aprovar 33 pessoas e devolver 1" (1 → "1 pessoa")."""
    palavra = "pessoas"
    if aprovadas == 1:
        palavra = "pessoa"
    return f"Aprovar {aprovadas} {palavra} e devolver 1"


def aceitar_alertas_abertos(aba) -> None:
    """Aceita os alertas que a empresa confirmou (com alerta aberto, a tela não deixa aprovar)."""
    # No máximo 50 voltas: um alerta que não sai não prende o roteiro para sempre
    for _volta in range(50):
        botoes_de_aceitar = aba.locator("[data-aceitar-alerta]")
        if botoes_de_aceitar.count() == 0:
            return
        botoes_de_aceitar.first.click()


def titulo_fica_parado(aba, seletor_da_grade: str) -> tuple[bool, str]:
    """Rola a grade por dentro até o fim e diz se a linha do título continua colada no alto dela (como o "Congelar
    painéis" do Excel). Devolve: (deu certo, o que foi medido, para a mensagem)."""
    medida = aba.evaluate("""seletor => {
        const grade = document.querySelector(seletor);
        grade.scrollTop = grade.scrollHeight;
        const topo_da_grade = grade.getBoundingClientRect().top;
        const topo_do_titulo = grade.querySelector("thead").getBoundingClientRect().top;
        return {rolou: grade.scrollTop, distancia: Math.round(topo_do_titulo - topo_da_grade)};
    }""", seletor_da_grade)
    # Volta a grade para o começo, para os passos seguintes
    aba.evaluate("seletor => { document.querySelector(seletor).scrollTop = 0; }", seletor_da_grade)
    texto = f"rolou {medida['rolou']} px; título a {medida['distancia']} px do alto da grade"
    return medida["rolou"] > 0 and abs(medida["distancia"]) <= 2, texto


def apontar_problema(aba, linha: str, recado: str) -> None:
    """Abre "Apontar problema" na pessoa da linha, escolhe "Confirmar o salário", escreve o recado e confirma."""
    aba.locator(f"[data-corpo-pessoas] tr[data-linha-pessoa='{linha}'] [data-apontar-problema]").click()
    aba.locator("#janela-pedir-ajuste[open]").wait_for(timeout=10000)
    aba.select_option("[data-ajuste-motivo]", "salario")
    aba.fill("[data-ajuste-mensagem]", recado)
    aba.click("[data-confirmar-apontamento]")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: apontar, desfazer, apontar de novo e "Aprovar N e devolver 1"."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_envios.html?envio=" + dados["processamento_id"])
    # Os dados de verdade chegaram quando a grade do parâmetro aparece e as pessoas estão na tabela
    aba.locator("[data-cabeca-pessoas] .linha-de-grupos").wait_for(timeout=20000)
    aba.locator("[data-corpo-pessoas] tr[data-linha-pessoa]").first.wait_for(timeout=20000)

    # 1. Os filtros novos das pessoas, com os números
    texto_confirmados = aba.inner_text("[data-filtro-pessoas='confirmados']")
    texto_apontados = aba.inner_text("[data-filtro-pessoas='apontados']")
    conferir(f"filtro 'Confirmados pela empresa (N)' (na tela: {texto_confirmados})",
             re.fullmatch(r"Confirmados pela empresa \(\d+\)", texto_confirmados.strip()) is not None)
    conferir(f"filtro 'Apontados por você (0)' antes de apontar (na tela: {texto_apontados})",
             texto_apontados.strip() == "Apontados por você (0)")
    conferir("o filtro antigo 'Só com alerta ou ajuste' saiu",
             aba.locator("[data-filtro-pessoas='atencao']").count() == 0)
    # A lista de motivos veio do servidor: "Escolha o motivo" + os 8 motivos do contrato
    opcoes = aba.locator("[data-ajuste-motivo] option").count()
    conferir(f"a janela tem os 8 motivos da lista fechada (opções na lista: {opcoes})", opcoes == 9)

    # 2. Sem apontamento, o botão é "Aprovar o envio" (depois de aceitar os alertas confirmados, se houver)
    aceitar_alertas_abertos(aba)
    texto_do_botao = aba.inner_text("[data-aprovar-envio]").strip()
    conferir(f"sem apontamento, o botão diz 'Aprovar o envio' (na tela: {texto_do_botao})",
             texto_do_botao == "Aprovar o envio")
    total_de_pessoas = int(aba.inner_text("[data-numero-pessoas]").strip())

    # 2b. A fila fica em cima e o envio aberto embaixo, na largura toda
    caixa_da_fila = aba.locator(".painel-fila-envios").bounding_box()
    caixa_do_envio = aba.locator("[data-envio-aberto]").bounding_box()
    conferir("a fila de envios fica em cima do envio aberto",
             caixa_da_fila["y"] + caixa_da_fila["height"] <= caixa_do_envio["y"] + 1)
    conferir(f"o envio aberto ocupa a largura toda (fila {caixa_da_fila['width']:.0f} px, envio "
             f"{caixa_do_envio['width']:.0f} px)", abs(caixa_da_fila["width"] - caixa_do_envio["width"]) < 2)

    # 2c. Clicar no nome abre a ficha completa da pessoa, com os grupos do parâmetro
    primeira_linha = aba.locator("[data-corpo-pessoas] tr[data-linha-pessoa]").first.get_attribute("data-linha-pessoa")
    botao_do_nome = aba.locator(f"[data-corpo-pessoas] tr[data-linha-pessoa='{primeira_linha}'] [data-abrir-ficha-pessoa]")
    nome_na_grade = botao_do_nome.inner_text().strip()
    botao_do_nome.click()
    aba.locator("#janela-ficha-pessoa[open]").wait_for(timeout=10000)
    nome_na_ficha = aba.inner_text("[data-ficha-nome]").strip()
    conferir(f"clicar no nome abre a ficha da pessoa (na tela: {nome_na_ficha})", nome_na_ficha == nome_na_grade)
    grupos_na_ficha = aba.locator("[data-ficha-grupos] .ficha-grupo").count()
    conferir(f"a ficha mostra os campos em grupos do parâmetro (grupos: {grupos_na_ficha})", grupos_na_ficha >= 2)
    campos_na_ficha = aba.locator("[data-ficha-grupos] dt").count()
    # As colunas do parâmetro na grade: as células da linha, menos Situação e Ação
    colunas_da_grade = aba.locator(f"[data-corpo-pessoas] tr[data-linha-pessoa='{primeira_linha}'] td").count() - 2
    conferir(f"a ficha tem todos os campos da grade ({campos_na_ficha} de {colunas_da_grade})",
             campos_na_ficha == colunas_da_grade)
    conferir("a ficha tem o botão 'Apontar problema'",
             aba.locator("#janela-ficha-pessoa [data-apontar-problema]").count() == 1)
    # O CPF da pessoa, como a ficha mostra no resumo ("Cargo · CPF 123.456.789-09 · linha 2 do arquivo")
    resumo_da_ficha = aba.inner_text("[data-ficha-resumo]")
    cpf_da_pessoa = re.search(r"CPF (\d{3}\.\d{3}\.\d{3}-\d{2})", resumo_da_ficha).group(1)
    aba.locator("#janela-ficha-pessoa").get_by_text("Voltar", exact=True).click()
    conferir("'Voltar' fecha a ficha", aba.locator("#janela-ficha-pessoa[open]").count() == 0)

    # 2d. A busca acha a pessoa pelo CPF, com ou sem ponto e traço
    campo_de_busca = aba.locator("[data-busca-pessoas]")
    conferir("a busca diz que procura também pelo CPF",
             "CPF" in (campo_de_busca.get_attribute("placeholder") or ""))
    for cpf_digitado in (cpf_da_pessoa, cpf_da_pessoa.replace(".", "").replace("-", "")):
        campo_de_busca.fill(cpf_digitado)
        linhas_achadas = aba.locator("[data-corpo-pessoas] tr[data-linha-pessoa]")
        conferir(f"buscar '{cpf_digitado}' acha só a pessoa desse CPF (linhas: {linhas_achadas.count()})",
                 linhas_achadas.count() == 1 and linhas_achadas.first.get_attribute("data-linha-pessoa") == primeira_linha)
    campo_de_busca.fill("")

    # 2f. A linha do título da grade fica congelada quando a lista rola
    parado, medida = titulo_fica_parado(aba, ".tabela-com-titulo-fixo")
    conferir(f"o título da grade fica congelado ao rolar a lista ({medida})", parado)

    # 2g. "Baixar a lista (.csv)": a mesma lista da grade, com todos os campos
    with aba.expect_download() as espera_do_download:
        aba.click("[data-baixar-envio]")
    download = espera_do_download.value
    conferir(f"o arquivo baixado tem o nome do envio (na tela: {download.suggested_filename})",
             download.suggested_filename == "envio_EMP001_" + dados["processamento_id"] + ".csv")
    conteudo = open(download.path(), encoding="utf-8-sig").read().strip().split("\n")
    conferir(f"o arquivo tem o cabeçalho e uma linha por pessoa ({len(conteudo) - 1} de {total_de_pessoas})",
             conteudo[0].startswith("Linha no arquivo;") and len(conteudo) - 1 == total_de_pessoas)

    # 2e. A barra de decisão continua flutuando no pé da tela, mas baixa (discreta num monitor menor)
    barra = aba.locator("[data-barra-decisao]")
    altura_da_barra = barra.bounding_box()["height"]
    posicao_da_barra = barra.evaluate("elemento => getComputedStyle(elemento).position")
    conferir(f"a barra de decisão é baixa ({altura_da_barra:.0f} px, até 72 px)", altura_da_barra <= 72)
    conferir(f"a barra de decisão continua flutuando (position: {posicao_da_barra})", posicao_da_barra == "sticky")

    # 3. Apontar problema na 1ª pessoa: recado curto é recusado na própria janela
    aba.locator(f"[data-corpo-pessoas] tr[data-linha-pessoa='{primeira_linha}'] [data-apontar-problema]").click()
    aba.locator("#janela-pedir-ajuste[open]").wait_for(timeout=10000)
    # O texto como está no HTML (o CSS do sobretítulo mostra em maiúsculas, e inner_text devolveria assim)
    sobretitulo = aba.text_content("#janela-pedir-ajuste .sobretitulo").strip()
    conferir(f"a janela se chama 'Apontar problema' (na tela: {sobretitulo})", sobretitulo == "Apontar problema")
    aba.select_option("[data-ajuste-motivo]", "salario")
    aba.fill("[data-ajuste-mensagem]", "curto")
    aba.click("[data-confirmar-apontamento]")
    conferir("recado curto: o aviso aparece e a janela continua aberta",
             aba.locator("[data-ajuste-erro]").is_visible() and aba.locator("#janela-pedir-ajuste[open]").count() == 1)
    # Agora com o recado inteiro
    aba.fill("[data-ajuste-mensagem]", RECADO)
    aba.click("[data-confirmar-apontamento]")
    linha_apontada = aba.locator(f"[data-corpo-pessoas] tr[data-linha-pessoa='{primeira_linha}']")
    linha_apontada.locator("[data-selo-apontado]").wait_for(timeout=20000)
    conferir("a janela fechou depois de gravar", aba.locator("#janela-pedir-ajuste[open]").count() == 0)
    selo = linha_apontada.locator("[data-selo-apontado]").inner_text().strip()
    conferir(f"a pessoa ganhou o selo 'Apontado por você' (na tela: {selo})", selo == "Apontado por você")
    recado_na_tela = linha_apontada.locator("[data-recado-apontamento]").inner_text()
    conferir("o recado aparece embaixo do selo, com o motivo",
             "Confirmar o salário" in recado_na_tela and "zero a mais" in recado_na_tela)
    esperado = texto_esperado_do_botao(total_de_pessoas - 1)
    texto_do_botao = aba.inner_text("[data-aprovar-envio]").strip()
    conferir(f"o botão vira '{esperado}' (na tela: {texto_do_botao})", texto_do_botao == esperado)
    texto_apontados = aba.inner_text("[data-filtro-pessoas='apontados']").strip()
    conferir(f"o filtro diz 'Apontados por você (1)' (na tela: {texto_apontados})",
             texto_apontados == "Apontados por você (1)")
    # A ficha da pessoa apontada mostra o problema no bloco "Avaliação do banco"
    linha_apontada.locator("[data-abrir-ficha-pessoa]").click()
    aba.locator("#janela-ficha-pessoa[open]").wait_for(timeout=10000)
    avaliacao = aba.locator("#janela-ficha-pessoa [data-ficha-avaliacao]")
    conferir("a ficha da pessoa apontada mostra o problema em 'Avaliação do banco'",
             avaliacao.count() == 1 and "zero a mais" in avaliacao.inner_text())
    conferir("a ficha da pessoa apontada tem 'Desfazer o apontamento'",
             aba.locator("#janela-ficha-pessoa [data-desfazer-apontamento]").count() == 1)
    aba.locator("#janela-ficha-pessoa [data-fechar-janela]").first.click()
    # O filtro "Apontados por você" mostra só a pessoa apontada
    aba.click("[data-filtro-pessoas='apontados']")
    linhas_no_filtro = aba.locator("[data-corpo-pessoas] tr[data-linha-pessoa]").count()
    conferir(f"o filtro 'Apontados por você' mostra 1 pessoa (na tela: {linhas_no_filtro})", linhas_no_filtro == 1)
    aba.click("[data-filtro-pessoas='todos']")

    # 4. Desfazer: o selo some e o botão volta a ser "Aprovar o envio"
    linha_apontada.locator("[data-desfazer-apontamento]").click()
    aba.wait_for_function("() => document.querySelector('[data-aprovar-envio]').textContent === 'Aprovar o envio'",
                          timeout=20000)
    conferir("depois de desfazer, a pessoa fica sem o selo", linha_apontada.locator("[data-selo-apontado]").count() == 0)
    conferir("depois de desfazer, o botão volta a ser 'Aprovar o envio'",
             aba.inner_text("[data-aprovar-envio]").strip() == "Aprovar o envio")

    # 5. Apontar de novo e "Aprovar N e devolver 1", com a confirmação na barra
    apontar_problema(aba, primeira_linha, RECADO)
    linha_apontada.locator("[data-selo-apontado]").wait_for(timeout=20000)
    conferir("apontada de novo, o botão volta a ser 'Aprovar N e devolver 1'",
             aba.inner_text("[data-aprovar-envio]").strip() == esperado)
    aba.click("[data-aprovar-envio]")
    confirmacao = aba.locator("[data-confirmacao-decisao]")
    conferir("a confirmação aparece na própria barra", confirmacao.is_visible())
    conferir("a confirmação avisa que não dá para desfazer",
             "Não dá para desfazer" in aba.inner_text("[data-confirmacao-decisao-texto]"))
    aba.click("[data-confirmar-decisao]")
    aba.locator("[data-resultado-avaliacao]").wait_for(state="visible", timeout=20000)

    # 6. O envio ficou aprovado, com a rodada nas idas e voltas
    conferir("a barra de decisão sumiu", not aba.locator("[data-barra-decisao]").is_visible())
    selo_do_envio = aba.inner_text("[data-envio-prazo]").strip()
    conferir(f"o envio aparece como 'Aprovado' (na tela: {selo_do_envio})", selo_do_envio == "Aprovado")
    conferir("o bloco 'Idas e voltas com o banco' aparece", aba.locator("[data-bloco-idas-e-voltas]").is_visible())
    rodada = aba.locator("[data-lista-idas-e-voltas] [data-tipo='aprovado_em_parte']")
    conferir("a rodada 'aprovado em parte' está nas idas e voltas", rodada.count() == 1)
    if rodada.count() == 1:
        texto_da_rodada = rodada.inner_text()
        conferir(f"a rodada diz quantas aprovou e devolveu (na tela: {texto_da_rodada})",
                 f"aprovou {total_de_pessoas - 1}" in texto_da_rodada and "devolveu 1" in texto_da_rodada)

    # 7. O envio de devolução aparece entre os avaliados, com a origem
    aba.click("[data-filtro-fila='avaliados']")
    origens = aba.locator("[data-lista-fila] .botao-envio-fila-origem")
    conferir("o envio de devolução aparece na fila dos avaliados, com 'Devolução do envio de ...'",
             origens.count() >= 1 and "Devolução do envio de" in origens.first.inner_text())
