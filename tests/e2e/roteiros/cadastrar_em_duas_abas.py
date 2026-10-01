"""Roteiro: o resultado da leitura em duas abas, na tela "Cadastrar funcionários".

O que ele confere, com o parâmetro de 4 obrigatórios e planilhas inventadas (a primeira é a do roteiro
telas_dos_obrigatorios):
- antes do envio, a frase das outras informações: "entram quando nosso agente reconhece";
- depois do envio, duas abas: "Funcionários" (aberta) e "Como o agente leu";
- "Funcionários": a grade só com os campos obrigatórios do parâmetro (na ordem do layout), uma linha por pessoa do
  arquivo, com o CPF formatado; a renda, que está numa coluna em dúvida, espera a escolha (o aviso diz onde escolher);
  o clique na pessoa abre, logo abaixo, todos os campos do parâmetro e as informações sem rótulo; o clique de novo
  fecha;
- "Como o agente leu": as colunas como antes, SEM o bloco "Ajude o agente a acertar" (ele continua na página, oculto);
- as setas do teclado trocam de aba;
- o aceite sem escolher a coluna em dúvida leva à aba "Como o agente leu", com a coluna marcada; escolhida a coluna, a
  aba "Funcionários" avisa que a lista com a escolha aparece depois do aceite;
- aceitas as colunas (na tela inteira), a aba "Como o agente leu" abre, com a conferência; a aba "Funcionários" mostra
  a lista do jeito que vai para o banco, agora com a renda;
- na janela "Cadastrar funcionários", aberta em Acompanhar, as mesmas duas abas, com a grade na primeira.
Guarda duas fotos (storage/painel/cadastrar_aba_funcionarios.png e cadastrar_aba_como_o_agente_leu.png).
"""
from tests.e2e.abas_do_cadastro import (SELETOR_DA_ABA_DAS_COLUNAS, SELETOR_DA_ABA_DOS_FUNCIONARIOS,
                                        SELETOR_DO_PAINEL_DAS_COLUNAS, SELETOR_DO_PAINEL_DOS_FUNCIONARIOS,
                                        abrir_a_aba_das_colunas, abrir_a_aba_dos_funcionarios)
from tests.e2e.apoio import LOGIN_DA_EMPRESA, abrir_janela_de_cadastro, entrar, pasta_do_roteiro

DESCRICAO = ("Cadastrar em duas abas: a frase nova, a grade dos obrigatórios com o detalhe, a leitura das colunas sem o "
             "'Ajude o agente a acertar', o aceite e a janela")
# A frase das outras informações, no quadro de antes do envio (o texto exato da tela)
FRASE_DAS_OUTRAS_INFORMACOES = "As outras informações que vierem no arquivo entram quando nosso agente reconhece."
# Uma pessoa inventada para a planilha da janela (CPF válido e sorteado para os testes; nenhum dado das bases de teste)
PESSOA_DA_JANELA = "Ana Prado;390.533.447-05;Supervisora;03/03/2026;21998765432;B-01;4200,00"
# O JavaScript que lê os títulos da grade da aba "Funcionários" (só o texto do título, sem a marca "*")
TITULOS_DA_GRADE = """() => {
    const titulos = [];
    for (const titulo of document.querySelectorAll("[data-real-cabeca-da-previa] tr:last-child th")) {
        let texto = "";
        if (titulo.firstChild) {
            texto = titulo.firstChild.textContent;
        }
        titulos.push(texto);
    }
    return titulos;
}"""
# As linhas das pessoas na grade da aba "Funcionários" (sem a linha do detalhe aberto)
LINHAS_DAS_PESSOAS = "[data-real-corpo-da-previa] > tr:not(.linha-do-detalhe)"


def preparar() -> dict:
    """Os dados do roteiro telas_dos_obrigatorios (o parâmetro de 4 obrigatórios e a planilha) e a planilha da janela.

    Devolve: {campos, campos_obrigatorios, rotulos_obrigatorios, planilha, planilha_da_janela}.
    """
    from tests.e2e.roteiros.telas_dos_obrigatorios import CABECALHO_DA_PLANILHA
    from tests.e2e.roteiros.telas_dos_obrigatorios import preparar as preparar_os_dados_das_telas_dos_obrigatorios
    dados = preparar_os_dados_das_telas_dos_obrigatorios()
    # A planilha da janela: outra pessoa (outro conteúdo), para não ser o mesmo arquivo já enviado na tela inteira
    planilha_da_janela = pasta_do_roteiro() / "folha_da_janela.csv"
    planilha_da_janela.write_text(CABECALHO_DA_PLANILHA + "\n" + PESSOA_DA_JANELA + "\n", encoding="utf-8")
    dados["planilha_da_janela"] = str(planilha_da_janela)
    return dados


def aba_aberta(tela) -> str:
    """O nome da aba aberta ("funcionarios" ou "colunas"), pelo botão marcado para o leitor de tela."""
    return tela.locator("[data-aba-do-resultado][aria-selected='true']").get_attribute("data-aba-do-resultado")


def conferir_a_frase(aba, conferir) -> None:
    """Antes do envio: a frase das outras informações, com o texto novo."""
    aba.locator("[data-campos-obrigatorios]:not([hidden])").wait_for(timeout=20000)
    frase = aba.inner_text(".campos-obrigatorios-nota").strip()
    conferir(f"Cadastrar: a frase das outras informações (na tela: {frase})", frase == FRASE_DAS_OUTRAS_INFORMACOES)


def conferir_a_aba_dos_funcionarios(aba, dados: dict, conferir) -> None:
    """Depois do envio: a aba "Funcionários" aberta, com a grade dos obrigatórios e o detalhe no clique."""
    aba.set_input_files("#campo-arquivo", dados["planilha"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba.locator(LINHAS_DAS_PESSOAS).first.wait_for(timeout=30000)
    conferir("abas: duas, 'Funcionários' e 'Como o agente leu'",
             aba.locator(SELETOR_DA_ABA_DOS_FUNCIONARIOS).inner_text() == "Funcionários"
             and aba.locator(SELETOR_DA_ABA_DAS_COLUNAS).inner_text() == "Como o agente leu")
    conferir("abas: o resultado abre em 'Funcionários', e a outra fica escondida",
             aba_aberta(aba) == "funcionarios" and aba.locator(SELETOR_DO_PAINEL_DOS_FUNCIONARIOS).is_visible()
             and aba.locator(SELETOR_DO_PAINEL_DAS_COLUNAS).is_hidden())
    titulos = aba.evaluate(TITULOS_DA_GRADE)
    conferir(f"Funcionários: só os obrigatórios do parâmetro, na ordem do layout (na tela: {titulos})",
             titulos == dados["rotulos_obrigatorios"])
    pessoas = aba.locator(LINHAS_DAS_PESSOAS)
    conferir(f"Funcionários: uma linha por pessoa do arquivo (na tela: {pessoas.count()})", pessoas.count() == 2)
    primeira = pessoas.first.inner_text()
    conferir("Funcionários: o CPF formatado, como na grade de Acompanhar", "529.982.247-25" in primeira)
    conferir("Funcionários: a renda, numa coluna em dúvida, ainda não aparece (espera a escolha)",
             "R$" not in primeira and "Informação não encontrada" in primeira)
    aviso = aba.locator("[data-real-aviso-da-previa]")
    conferir(f"Funcionários: o aviso diz onde escolher (na tela: {aviso.inner_text()})",
             aviso.is_visible() and "1 coluna espera a sua escolha em \"Como o agente leu\"" in aviso.inner_text())
    conferir("Funcionários: a contagem das pessoas", "2 funcionários no arquivo" in aba.inner_text(
        "[data-real-contagem-da-previa]"))
    aba.locator("#resultado-real").screenshot(path="storage/painel/cadastrar_aba_funcionarios.png")
    # O clique numa célula comum da pessoa (a 2ª; a 1ª é o botão) abre o detalhe logo abaixo, com todos os campos
    pessoas.first.locator("td").nth(1).click()
    detalhe = aba.locator("[data-real-corpo-da-previa] tr.linha-do-detalhe")
    detalhe.wait_for(timeout=10000)
    campos_no_detalhe = detalhe.locator("dt").count()
    conferir(f"Funcionários: o detalhe mostra os {dados['campos']} campos do parâmetro (na tela: {campos_no_detalhe})",
             campos_no_detalhe == dados["campos"])
    sem_rotulo = detalhe.locator("[data-informacoes-sem-rotulo]")
    conferir("Funcionários: o 'Código' em dúvida entre opcionais aparece nas informações sem rótulo",
             sem_rotulo.count() == 1 and "Código" in sem_rotulo.inner_text())
    # O clique de novo fecha o detalhe
    pessoas.first.locator("td").nth(1).click()
    conferir("Funcionários: o clique de novo fecha o detalhe", detalhe.count() == 0)


def conferir_a_aba_das_colunas(aba, conferir) -> None:
    """A aba "Como o agente leu": as colunas como antes, sem o "Ajude o agente a acertar"; as setas trocam de aba."""
    abrir_a_aba_das_colunas(aba)
    conferir("Como o agente leu: a tabela das colunas aparece",
             aba.locator("[data-real-corpo-colunas] tr").first.is_visible())
    bloco_da_releitura = aba.locator("[data-real-bloco-ajude]")
    conferir("Como o agente leu: sem o 'Ajude o agente a acertar' (na página, com a marca de oculto)",
             bloco_da_releitura.count() == 1 and bloco_da_releitura.is_hidden()
             and bloco_da_releitura.get_attribute("data-oculto-nesta-versao") == "ajude-o-agente")
    aba.locator("#resultado-real").screenshot(path="storage/painel/cadastrar_aba_como_o_agente_leu.png")
    # O teclado: a seta para a esquerda volta a "Funcionários", e a seta para a direita vai a "Como o agente leu"
    aba.focus(SELETOR_DA_ABA_DAS_COLUNAS)
    aba.keyboard.press("ArrowLeft")
    conferir("teclado: a seta para a esquerda abre 'Funcionários'",
             aba_aberta(aba) == "funcionarios" and aba.locator(SELETOR_DO_PAINEL_DOS_FUNCIONARIOS).is_visible())
    aba.keyboard.press("ArrowRight")
    conferir("teclado: a seta para a direita abre 'Como o agente leu'",
             aba_aberta(aba) == "colunas" and aba.locator(SELETOR_DO_PAINEL_DAS_COLUNAS).is_visible())


def conferir_o_aceite(aba, conferir) -> None:
    """O aceite sem escolher leva à coluna que falta; escolhida, o aviso muda; aceitas, a conferência e a lista final."""
    abrir_a_aba_dos_funcionarios(aba)
    # Aceitar sem escolher o campo de "Vencimentos": o recado aparece, e a aba das colunas abre com a coluna marcada
    aba.click("[data-real-aceitar]")
    aba.locator("[data-real-erro]:not([hidden])").wait_for(timeout=60000)
    escolha_da_renda = aba.locator("[data-real-corpo-colunas] select[data-coluna='Vencimentos']")
    conferir("aceite sem escolher: a aba 'Como o agente leu' abre, com a coluna marcada",
             aba_aberta(aba) == "colunas" and "escolha-que-falta" in (escolha_da_renda.get_attribute("class") or ""))
    # Escolhida a coluna, a aba "Funcionários" avisa que a lista com a escolha aparece depois do aceite
    escolha_da_renda.select_option("valor_renda")
    abrir_a_aba_dos_funcionarios(aba)
    aviso = aba.inner_text("[data-real-aviso-da-previa]")
    conferir(f"escolhida a coluna, o aviso muda (na tela: {aviso})",
             "Você mudou o campo de 1 coluna" in aviso and "espera a sua escolha" not in aviso)
    # Aceita: na tela inteira, a aba "Como o agente leu" abre com a conferência da lista
    aba.click("[data-real-aceitar]")
    aba.wait_for_function("() => document.querySelector('[data-real-aceitar]').hidden", timeout=60000)
    aba.locator("[data-real-bloco-conferencia]").wait_for(state="visible", timeout=60000)
    conferir("aceitas as colunas: a aba 'Como o agente leu' abre, com a conferência", aba_aberta(aba) == "colunas")
    # A aba "Funcionários" agora é a lista do jeito que vai para o banco: a renda aparece
    abrir_a_aba_dos_funcionarios(aba)
    aba.wait_for_function("() => Array.from(document.querySelectorAll('[data-real-corpo-da-previa] > tr'))"
                          ".some(linha => linha.innerText.includes('R$'))", timeout=30000)
    conferir("aceitas as colunas: a aba 'Funcionários' mostra a lista que vai para o banco, com a renda",
             "do jeito que vão para o banco" in aba.inner_text("[data-real-nota-da-previa]"))


def conferir_a_janela(aba, endereco: str, dados: dict, conferir) -> None:
    """A janela "Cadastrar funcionários", aberta em Acompanhar: as mesmas duas abas, com a grade na primeira."""
    aba.goto(endereco + "/acompanhar.html")
    quadro = abrir_janela_de_cadastro(aba)
    quadro.locator("#campo-arquivo").set_input_files(dados["planilha_da_janela"])
    quadro.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    quadro.locator(LINHAS_DAS_PESSOAS).first.wait_for(timeout=30000)
    conferir("janela: o resultado abre em 'Funcionários'",
             aba_aberta(quadro) == "funcionarios" and quadro.locator(SELETOR_DO_PAINEL_DOS_FUNCIONARIOS).is_visible())
    conferir("janela: a grade mostra a pessoa do arquivo, com o CPF formatado",
             quadro.locator(LINHAS_DAS_PESSOAS).count() == 1
             and "390.533.447-05" in quadro.locator(LINHAS_DAS_PESSOAS).first.inner_text())
    abrir_a_aba_das_colunas(quadro)
    conferir("janela: 'Como o agente leu' sem o 'Ajude o agente a acertar'",
             quadro.locator("[data-real-corpo-colunas] tr").first.is_visible()
             and quadro.locator("[data-real-bloco-ajude]").is_hidden())
    aba.keyboard.press("Escape")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Cadastrar na tela inteira (as duas abas, o aceite) e, depois, na janela de Acompanhar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/cadastrar.html")
    conferir_a_frase(aba, conferir)
    conferir_a_aba_dos_funcionarios(aba, dados, conferir)
    conferir_a_aba_das_colunas(aba, conferir)
    conferir_o_aceite(aba, conferir)
    conferir_a_janela(aba, endereco, dados, conferir)
    aba.close()
