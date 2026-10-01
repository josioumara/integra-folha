"""Roteiro: a tela de envio com os arquivos do Leitor de fichas (ADR-130).

O que ele confere (com a IA simulada, sem custo; os arquivos são inventados aqui, nenhum vem das bases de teste):
- fichas em pedaços, com uma coluna de referência: o resumo da leitura diz que a IA montou uma pessoa por referência
  (3 pessoas, e não uma por linha);
- uma planilha com duas abas ligadas pelo CPF: o resumo diz que as abas foram juntadas, uma linha por pessoa;
- pedaços de ficha sem referência e quase sem CPF: o envio é recusado com a mensagem que diz o que fazer.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Leitor de fichas: pedaços por referência, abas ligadas pelo CPF e a recusa dos pedaços sem dono"


def _cpfs_do_roteiro() -> list[str]:
    """Quatro CPFs inventados com o dígito certo (sempre os mesmos: o sorteio tem semente fixa)."""
    import random

    from services.documentos import gerar_cpf
    sorteio = random.Random(1300)
    cpfs = []
    for _ in range(4):
        cpfs.append(gerar_cpf(sorteio))
    return cpfs


def _escrever_csv(caminho, linhas: list[list[str]]) -> str:
    """Grava um CSV com ";" e aspas em volta de cada célula. Devolve o caminho, como texto."""
    texto = ""
    for linha in linhas:
        celulas = []
        for celula in linha:
            celulas.append('"' + celula + '"')
        texto += ";".join(celulas) + "\n"
    caminho.write_text(texto, encoding="utf-8")
    return str(caminho)


def _escrever_planilha(caminho, abas: dict[str, list[list[str]]]) -> str:
    """Grava um .xlsx com as abas pedidas. Devolve o caminho, como texto."""
    from openpyxl import Workbook
    livro = Workbook()
    livro.remove(livro.active)
    for nome_da_aba, linhas in abas.items():
        aba = livro.create_sheet(nome_da_aba)
        for linha in linhas:
            aba.append(linha)
    livro.save(caminho)
    return str(caminho)


def preparar() -> dict:
    """Os usuários de teste e os três arquivos: fichas em pedaços, abas ligadas e pedaços sem referência."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste, pasta_do_roteiro
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    pasta = pasta_do_roteiro()
    cpf_1, cpf_2, cpf_3, cpf_4 = _cpfs_do_roteiro()
    fichas = _escrever_csv(pasta / "fichas_em_pedacos.csv", [
        ["codigo", "parte", "texto"],
        ["Q2", "contato", "Rua Nove, 9; Vitória/ES; CEP 29010-000; celular (27) 98123-4567."],
        ["Q1", "pessoa", f"Joana Prates Leal; CPF {cpf_1}; nascida em 21/04/1993."],
        ["Q3", "vaga", "Cozinheiro; admissão em 02/09/2026; salário R$ 2.700,00."],
        ["Q2", "pessoa", f"Marcos Viana Pires; CPF {cpf_2}; nascido em 30/10/1980."],
        ["Q1", "vaga", "Recepcionista; admissão em 09/09/2026; salário R$ 2.200,00."],
        ["Q3", "pessoa", f"Lara Neves Bastos; CPF {cpf_3}; nascida em 05/06/2001."],
    ])
    abas = _escrever_planilha(pasta / "abas_ligadas.xlsx", {
        "Dados pessoais": [["Nome", "CPF"], ["Joana Prates Leal", cpf_1], ["Rui Castro Melo", cpf_4]],
        "Contrato": [["CPF", "Cargo", "Salário"], [cpf_4, "Porteiro", "2.100,00"], [cpf_1, "Recepcionista", "2.200,00"]],
    })
    sem_dono = _escrever_csv(pasta / "pedacos_sem_dono.csv", [
        ["anotacoes do rh"],
        [f"Joana Prates Leal; CPF {cpf_1}; nascida em 21/04/1993."],
        ["Rua Nove, 9; Vitória/ES; CEP 29010-000; celular (27) 98123-4567."],
        ["Cozinheiro; admissão em 02/09/2026; salário R$ 2.700,00."],
    ])
    return {"fichas": fichas, "abas": abas, "sem_dono": sem_dono}


def _enviar_e_esperar_a_leitura(aba, endereco: str, caminho: str) -> str:
    """Abre a tela de envio, manda o arquivo e espera a leitura. Devolve o resumo da leitura."""
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", caminho)
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    return aba.inner_text("[data-real-resumo-leitura]")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os três envios e o que a empresa vê em cada um."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # 1. Fichas em pedaços: uma pessoa por referência
    resumo = _enviar_e_esperar_a_leitura(aba, endereco, dados["fichas"])
    conferir("fichas em pedaços: a IA montou 3 pessoas, uma por referência (" + resumo[:90] + ")",
             "montou 3 funcionário(s)" in resumo and "referência" in resumo)
    # 2. Abas ligadas pelo CPF: uma linha por pessoa
    resumo = _enviar_e_esperar_a_leitura(aba, endereco, dados["abas"])
    conferir("abas ligadas: juntadas pelo CPF, 2 pessoas (" + resumo[:90] + ")",
             "Juntei as abas Dados pessoais e Contrato" in resumo and "2 funcionário(s)" in resumo)
    # 3. Pedaços sem referência: recusado, com o que fazer
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["sem_dono"])
    aba.wait_for_function("() => document.querySelector('#painel-ia').innerText.includes('referência da pessoa')",
                          timeout=30000)
    conferir("pedaços sem referência: recusado com a mensagem que diz o que fazer", True)
    aba.close()
