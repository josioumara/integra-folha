"""Apoio dos roteiros de clique: as duas abas do resultado da leitura, na tela "Cadastrar funcionários".

Para que serve: depois do envio, o resultado abre na aba "Funcionários" (a grade das pessoas do arquivo, com as
informações obrigatórias). A tabela das colunas, os detalhes da leitura, o formato das colunas e a conferência da lista
ficam na aba "Como o agente leu". Os roteiros que mexem nas colunas ANTES do aceite abrem essa aba primeiro; depois do
aceite, a tela já abre nela.

Uso:
    abrir_a_aba_das_colunas(aba)        # a aba do navegador, ou o quadro da janela "Cadastrar funcionários"
"""

# O botão da aba "Como o agente leu" (front/cadastrar.html)
SELETOR_DA_ABA_DAS_COLUNAS = "[data-aba-do-resultado='colunas']"
# O conteúdo da aba, que aparece quando ela abre
SELETOR_DO_PAINEL_DAS_COLUNAS = "[data-painel-do-resultado='colunas']"
# O botão e o conteúdo da aba "Funcionários"
SELETOR_DA_ABA_DOS_FUNCIONARIOS = "[data-aba-do-resultado='funcionarios']"
SELETOR_DO_PAINEL_DOS_FUNCIONARIOS = "[data-painel-do-resultado='funcionarios']"


def abrir_a_aba_das_colunas(tela) -> None:
    """Abre a aba "Como o agente leu" do resultado e espera o conteúdo dela aparecer.

    Recebe: tela — a aba do navegador, ou o quadro (frame) da janela "Cadastrar funcionários". Devolve: nada.
    """
    tela.locator(SELETOR_DA_ABA_DAS_COLUNAS).click()
    tela.locator(SELETOR_DO_PAINEL_DAS_COLUNAS).wait_for(state="visible", timeout=10000)


def abrir_a_aba_dos_funcionarios(tela) -> None:
    """Abre a aba "Funcionários" do resultado e espera o conteúdo dela aparecer.

    Recebe: tela — a aba do navegador, ou o quadro (frame) da janela "Cadastrar funcionários". Devolve: nada.
    """
    tela.locator(SELETOR_DA_ABA_DOS_FUNCIONARIOS).click()
    tela.locator(SELETOR_DO_PAINEL_DOS_FUNCIONARIOS).wait_for(state="visible", timeout=10000)
