"""Roteiro: "a matrícula é o CPF" no cartão da informação que o arquivo inteiro não trouxe (ADR-124).

O que ele confere (com a IA simulada, sem custo), num arquivo sem coluna de CPF, em que a coluna "Registro" traz os
CPFs e foi aceita como a matrícula:
- no cartão do CPF, a resposta da empresa ("Na verdade o campo matrícula é o CPF") mostra a conferência da coluna
  ("3 de 3 valores passaram", com o dígito verificador), avisa que a Matrícula fica sem coluna e pergunta, com "Sim,
  usar como CPF" e "Cancelar" (antes: "Aqui eu só ajusto a informação CPF");
- "Sim, usar como CPF" troca a coluna na hora: o chat diz 'Pronto: a coluna "Registro" agora é a informação "CPF"...',
  e a matrícula, opcional desde o ADR-128, fica sem coluna e sem cartão;
- o Desfazer volta a coluna para a matrícula: o chat diz o que voltou, e o cartão do CPF volta.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa, painel_da_conversa

DESCRICAO = "A matrícula é o CPF: a conferência da coluna, a confirmação, a troca na hora e o Desfazer"
# Os CPFs da coluna "Registro" (válidos e inventados: o dígito verificador confere)
CPFS = ["52998224725", "11144477735", "12345678909"]
# O título do cartão da informação que o arquivo inteiro não trouxe, e o nome da matrícula nos títulos
TITULO_DO_CPF = 'Ajuste na informação "CPF" no arquivo inteiro'
INFORMACAO_DA_MATRICULA = "Identificador do funcionário dentro da empresa"


def preparar() -> dict:
    """Um envio da Aurora sem coluna de CPF: a coluna "Registro" (os CPFs) aceita como a matrícula."""
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    linhas = ["Nome;Registro;Estado civil"]
    for nome, cpf in zip(["Ana Lima", "Bia Souza", "Caio Reis"], CPFS):
        linhas.append(f"{nome};{cpf};Casado")
    conteudo = ("\n".join(linhas) + "\n").encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, "registro.csv",
                                      busca=busca_falsa)
    escolhas = {"Nome": "nome_completo", "Registro": "matricula", "Estado civil": "estado_civil"}
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], escolhas,
                                busca=busca_falsa)
    conexao.close()
    return {"processamento_id": leitura["processamento_id"]}


def cartao_do_cpf(aba):
    """O cartão da informação "CPF" que o arquivo inteiro não trouxe."""
    return aba.locator("[data-pendencia]").filter(has=aba.locator(".ajuste-titulo", has_text=TITULO_DO_CPF)).first


def cartoes_da_matricula(aba):
    """Os títulos dos cartões da matrícula que o arquivo inteiro não trouxe (0 ou 1)."""
    return aba.locator(".ajuste-titulo", has_text=f'"{INFORMACAO_DA_MATRICULA}" no arquivo inteiro')


def conferir_a_proposta(aba, conferir) -> None:
    """A resposta da empresa vira a conferência da coluna e a pergunta (nada muda antes do "Sim")."""
    cartao_da_lista = cartao_do_cpf(aba)
    cartao_da_lista.wait_for(timeout=30000)
    # A conversa do cartão, no painel do lado (ADR-138)
    cartao = abrir_a_conversa(aba, cartao_da_lista)
    caixa = cartao.locator("[data-caixa-da-conversa]")
    caixa.fill("Na verdade o campo matrícula é o CPF")
    caixa.press("Enter")
    sim = cartao.locator("[data-confirmar-sim]")
    sim.wait_for(timeout=30000)
    fala = cartao.get_by_text('Conferi a coluna "Registro"').first.inner_text()
    conferir(f"a conferência da coluna, com o dígito, e o aviso da matrícula (na tela: {fala})",
             "3 de 3 valores passaram" in fala and "dígito verificador" in fala
             and '"Matrícula" fica sem coluna' in fala)
    conferir("a pergunta tem 'Sim, usar como CPF' e 'Cancelar', e não há mais 'fora do assunto'",
             sim.inner_text() == "Sim, usar como CPF"
             and cartao.locator("[data-confirmar-nao]").inner_text() == "Cancelar"
             and cartao.get_by_text("Aqui eu só ajusto").count() == 0)
    conferir("antes do 'Sim', a matrícula ainda não tem cartão", cartoes_da_matricula(aba).count() == 0)


def conferir_a_troca_e_o_desfazer(aba, conferir) -> None:
    """ "Sim, usar como CPF" troca a coluna na hora; o Desfazer volta tudo."""
    painel_da_conversa(aba).locator("[data-confirmar-sim]").click()
    pronto = aba.get_by_text('Pronto: a coluna "Registro" agora é a informação "CPF"').first
    pronto.wait_for(timeout=30000)
    # A matrícula é opcional (ADR-128): fica sem coluna, sem cartão de revisão
    conferir(f"o chat diz o que mudou (na tela: {pronto.inner_text()})",
             '"Matrícula" ficou sem coluna.' in pronto.inner_text() and "cartão" not in pronto.inner_text())
    conferir("a matrícula, opcional, fica sem coluna e sem cartão", cartoes_da_matricula(aba).count() == 0)
    # O Desfazer, no balão do "Pronto"
    painel_da_conversa(aba).locator("[data-desfazer-mudanca]").first.click()
    voltei = aba.get_by_text('Voltei a coluna "Registro" para "Matrícula".').first
    voltei.wait_for(timeout=30000)
    cartao_do_cpf(aba).wait_for(timeout=30000)
    conferir("o Desfazer volta a coluna para a matrícula, e o cartão do CPF volta (a matrícula continua sem cartão)",
             cartao_do_cpf(aba).count() == 1 and cartoes_da_matricula(aba).count() == 0)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques em Acompanhar: a resposta da empresa, a confirmação, a troca e o Desfazer."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_a_proposta(aba, conferir)
    conferir_a_troca_e_o_desfazer(aba, conferir)
    aba.close()
