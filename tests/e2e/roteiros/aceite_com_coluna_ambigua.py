"""Roteiro: o aceite das colunas com uma coluna ainda sem escolha nunca fica mudo.

O defeito: numa planilha com colunas em que a IA pediu a escolha do campo, clicar em "Aceitar as colunas
e conferir os dados" sem escolher não mudava nada perto do botão. O servidor recusava com um recado ("Escolha o campo
(ou ignore) destas colunas: ..."), mas o recado ia para o alto do cartão, acima da tabela, longe do botão.

O que ele confere, na tela Cadastrar e na janela "Cadastrar funcionários" (a mesma tela, dentro de um quadro):
- enquanto o servidor trabalha, o botão diz "Aguarde…" e fica desligado;
- o aceite recusado traz o recado para a vista (dentro da tela visível), com o nome da coluna que falta;
- o recado é anunciado pelo leitor de tela (role="alert");
- a coluna sem escolha fica marcada, e a marca sai quando a pessoa escolhe o campo;
- com a escolha feita, o aceite dá certo (a conferência abre; na janela, a tela vai para Acompanhar).
A planilha tem uma coluna "Vencimentos", que a IA simulada (modo MOCK) sempre marca como ambígua, e colunas
suficientes para a tabela passar da altura da tela (o recado no alto sai da vista quando o botão está à vista).
"""
from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, abrir_janela_de_cadastro, entrar, pasta_do_roteiro

DESCRICAO = "Aceite com coluna ambígua: 'Aguarde…', o recado à vista, a coluna marcada e o aceite depois da escolha"
# As colunas da planilha: a última, "Vencimentos", é a ambígua; as outras enchem a tabela
CABECALHO = ("Nome;CPF;Cargo;Data de nascimento;Sexo;Estado civil;E-mail;Telefone;CEP;Cidade;UF;Data de admissão;"
             "Vencimentos")
# O JavaScript que diz se um elemento está inteiro dentro da parte visível da tela (a da janela, dentro do quadro)
ESTA_A_VISTA = """elemento => {
    const caixa = elemento.getBoundingClientRect();
    return caixa.top >= 0 && caixa.bottom <= window.innerHeight;
}"""
# O JavaScript do clique: clica e lê o botão na mesma hora (antes de a resposta do servidor chegar)
CLICAR_E_LER_O_BOTAO = """botao => {
    botao.click();
    return [botao.textContent, botao.disabled];
}"""


def gravar_planilha(nome_do_arquivo: str, pessoas: list[str]) -> str:
    """Grava uma planilha (CSV) com o cabeçalho de cima e uma linha por pessoa. Devolve o caminho do arquivo (texto).

    Ex.: gravar_planilha("folha.csv", ["Maria Souza;529.982.247-25;...;3500,00"]) → ".../folha.csv".
    """
    caminho = pasta_do_roteiro() / nome_do_arquivo
    caminho.write_text(CABECALHO + "\n" + "\n".join(pessoas) + "\n", encoding="utf-8")
    return str(caminho)


def preparar() -> dict:
    """Os usuários de teste e duas planilhas diferentes (uma para a tela sozinha, outra para a janela)."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    # Dados inventados, com CPFs válidos sorteados para o teste (nenhum vem das bases de teste)
    planilha_da_tela = gravar_planilha("folha_com_vencimentos.csv", [
        "Maria Souza;529.982.247-25;Analista;12/03/1990;F;Solteiro;maria@exemplo.com;11987654321;01310100;"
        "São Paulo;SP;01/02/2026;3500,00",
        "João Lima;111.444.777-35;Assistente;05/07/1985;M;Casado;joao@exemplo.com;11912345678;01310100;"
        "São Paulo;SP;15/02/2026;2800,00",
    ])
    planilha_da_janela = gravar_planilha("equipe_com_vencimentos.csv", [
        "Ana Prado;390.533.447-05;Supervisora;20/11/1988;F;Casado;ana@exemplo.com;21998765432;20040002;"
        "Rio de Janeiro;RJ;03/03/2026;4200,00",
    ])
    return {"planilha_da_tela": planilha_da_tela, "planilha_da_janela": planilha_da_janela}


def aceitar_sem_escolher(tela, conferir, onde: str) -> None:
    """Clica em "Aceitar as colunas" sem escolher o campo de "Vencimentos" e confere o que aparece.

    Recebe: tela — a aba (Cadastrar sozinha) ou o quadro da janela; conferir; onde — "na tela" ou "na janela", para o
    texto de cada conferência.
    """
    botao = tela.locator("[data-real-aceitar]")
    # O botão à vista, como a pessoa o vê no fim da tabela
    botao.scroll_into_view_if_needed()
    # O caso do defeito: com o botão à vista, o alto do cartão (onde o recado aparece) está fora da vista
    conferir(f"{onde}: com o botão à vista, o alto do cartão está fora da vista (a tabela é comprida)",
             not tela.locator("[data-real-titulo]").evaluate(ESTA_A_VISTA))
    texto_do_botao, desligado = botao.evaluate(CLICAR_E_LER_O_BOTAO)
    conferir(f"{onde}: enquanto espera, o botão diz 'Aguarde…' e fica desligado (na tela: {texto_do_botao})",
             texto_do_botao == "Aguarde…" and desligado)
    recado = tela.locator("[data-real-erro]:not([hidden])")
    recado.wait_for(timeout=60000)
    conferir(f"{onde}: o recado diz qual coluna falta (na tela: {recado.inner_text()})",
             "Vencimentos" in recado.inner_text())
    conferir(f"{onde}: o recado está à vista depois do clique", recado.evaluate(ESTA_A_VISTA))
    conferir(f"{onde}: o recado é anunciado pelo leitor de tela", recado.get_attribute("role") == "alert")
    conferir(f"{onde}: o botão volta ao texto de antes",
             botao.inner_text() == "Aceitar as colunas e conferir os dados" and botao.is_enabled())
    escolha = tela.locator("[data-real-corpo-colunas] select[data-coluna='Vencimentos']")
    conferir(f"{onde}: a coluna 'Vencimentos' fica marcada",
             "escolha-que-falta" in (escolha.get_attribute("class") or "")
             and escolha.get_attribute("aria-invalid") == "true")
    # A pessoa escolhe o campo: a marca sai
    escolha.select_option("valor_renda")
    conferir(f"{onde}: escolhido o campo, a marca sai",
             "escolha-que-falta" not in (escolha.get_attribute("class") or "")
             and escolha.get_attribute("aria-invalid") is None)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """A tela Cadastrar sozinha e, depois, a janela "Cadastrar funcionários" em Acompanhar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # 1. Cadastrar, a tela sozinha
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["planilha_da_tela"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba.locator("[data-real-aceitar]:not([hidden])").wait_for(timeout=60000)
    # As colunas ficam na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    aceitar_sem_escolher(aba, conferir, "na tela")
    # Com a escolha feita, o aceite dá certo: a conferência da lista abre
    aba.click("[data-real-aceitar]")
    aba.wait_for_function("() => document.querySelector('[data-real-aceitar]').hidden", timeout=60000)
    conferir("na tela: com a escolha feita, o aceite dá certo e o recado some",
             not aba.locator("[data-real-erro]").is_visible())
    # 2. A janela "Cadastrar funcionários", aberta em Acompanhar (a mesma tela, dentro de um quadro)
    aba.goto(endereco + "/acompanhar.html")
    quadro = abrir_janela_de_cadastro(aba)
    quadro.locator("#campo-arquivo").set_input_files(dados["planilha_da_janela"])
    quadro.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    quadro.locator("[data-real-aceitar]:not([hidden])").wait_for(timeout=60000)
    abrir_a_aba_das_colunas(quadro)
    aceitar_sem_escolher(quadro, conferir, "na janela")
    # Com a escolha feita, a janela leva a Acompanhar, com o envio aberto
    quadro.locator("[data-real-aceitar]").click()
    aba.wait_for_url("**/acompanhar.html?envio=*", timeout=60000)
    conferir("na janela: com a escolha feita, o aceite leva a Acompanhar", True)
    aba.close()
