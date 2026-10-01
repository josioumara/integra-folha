"""Roteiro: o banco devolve só uma pessoa do envio, e a empresa vê isso em Acompanhar (ADR-121).

O caso: o especialista aponta um problema numa pessoa do envio e decide "Aprovar N e devolver
M". As pessoas sem apontamento são cadastradas na hora; a apontada vai para um envio de devolução, com uma pendência
"Pedido do banco" para a empresa responder.

A preparação usa o caminho de verdade: a carga inicial da Aurora esperando o banco, um apontamento no salário da
primeira pessoa (services.avaliacao_do_banco.apontar) e a decisão "aprovar_e_devolver_marcados"
(services.avaliacao_do_banco.avaliar).

O que ele confere, em Acompanhar:
- no envio original, a etapa "Aprovação das contas enviadas" feita só em parte (bolinha verde clarinho), com o detalhe
  "N-1 de N aprovadas · 1 devolvida";
- embaixo da linha do tempo dele, o bloco "Idas e voltas com o banco": o envio e a aprovação em parte (com o nome da
  pessoa e o motivo), cada linha com a data curta "dd/mm às HHhMM";
- o envio de devolução, com a linha de origem "Devolução do envio de dd/mm (1 pessoa)" e a etapa devolvida em laranja,
  com o detalhe "Devolvido: ...";
- a pendência da pessoa, com o selo "Pedido do banco" (só nela) e a pergunta "O banco pediu: <recado>".
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = "Banco devolve uma pessoa: aprovação em parte, idas e voltas, envio de devolução e o selo 'Pedido do banco'"
# O recado que o especialista escreve para a empresa no apontamento (mínimo de 15 letras)
RECADO_DO_BANCO = "O salário parece alto demais para o cargo."
# O nome da etapa em que o banco aprova ou devolve
ETAPA_DA_APROVACAO = "Aprovação das contas enviadas"
# A cor de fundo da bolinha feita só em parte (--verde-sucesso-claro, #e3f4ea)
VERDE_CLARINHO = "rgb(227, 244, 234)"
# A cor de fundo da bolinha devolvida (--amarelo-atencao, #b35c00)
LARANJA_DE_ATENCAO = "rgb(179, 92, 0)"
# O jeito curto da data em cada ida e volta: "28/09 às 10h10"
DATA_CURTA = re.compile(r"^\d{2}/\d{2} às \d{2}h\d{2}$")


def preparar() -> dict:
    """A carga inicial da Aurora aprovada pelo banco com uma pessoa devolvida (salário). Devolve o que conferir."""
    import csv

    import rag.busca
    from models.contratos import Perfil
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, avaliacao_do_banco
    from services.auth import Usuario
    from tests.e2e.apoio import LOGIN_DO_BANCO, criar_usuarios_de_teste
    from tests.test_avaliacao_do_banco import enviar_a_aurora_ao_banco
    from tests.test_correcao import RAIZ, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (a correção do CPF da carga inicial usa o valor certo)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # A Aurora corrige a pendência e manda a carga inicial ao banco: o envio fica esperando o especialista
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    especialista = Usuario(login=LOGIN_DO_BANCO, perfil=Perfil.BANCO, empresa_id=None)
    # As pessoas do envio, como o especialista as vê; a primeira é a apontada
    pessoas = avaliacao_do_banco.pessoas_do_envio(conexao, especialista, processamento_id)
    apontada = pessoas[0]
    avaliacao_do_banco.apontar(conexao, especialista, processamento_id, apontada["linha"], "salario", RECADO_DO_BANCO)
    # "Aprovar N e devolver 1": as outras são cadastradas na hora; a apontada vai para o envio de devolução
    avaliacao_do_banco.avaliar(conexao, especialista, processamento_id, decisao="aprovar_e_devolver_marcados")
    conexao.close()
    total = len(pessoas)
    return {
        "nome": apontada["nome"],
        "total": total,
        # O detalhe da etapa de aprovação no envio original
        "detalhe_da_aprovacao": str(total - 1) + " de " + str(total) + " aprovadas · 1 devolvida",
    }


def etapa_da_aprovacao(cartao):
    """O passo "Aprovação das contas enviadas" da linha do tempo de um cartão de envio."""
    return cartao.locator(".linha-do-tempo .passo").filter(has_text=ETAPA_DA_APROVACAO)


def cor_da_bolinha(passo) -> str:
    """A cor de fundo da bolinha de um passo, como o navegador a pinta (ex.: "rgb(0, 132, 55)")."""
    return passo.locator(".passo-marca").evaluate("bolinha => getComputedStyle(bolinha).backgroundColor")


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


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre Acompanhar e confere os dois envios e a pendência "Pedido do banco"."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    # Espera os envios de verdade (o original e o de devolução) substituírem os exemplos do protótipo
    aba.wait_for_function("() => document.querySelector('[data-contador-envios]').innerText.includes('de 2 envios')",
                          timeout=20000)
    envios = aba.locator("[data-lista-envios] [data-envio]")
    # O envio de devolução é o que tem a linha de origem; o original, o que não tem
    devolucao = envios.filter(has=aba.locator("[data-origem-do-envio]"))
    original = envios.filter(has_not=aba.locator("[data-origem-do-envio]"))
    conferir("um envio de devolução e um envio original na lista", devolucao.count() == 1 and original.count() == 1)
    # O original já está "Cadastrado" e abre recolhido: abre o cartão, como a pessoa faria para ver a linha do tempo
    original.evaluate("cartao => { cartao.open = true; }")

    # 1. O envio original: "Aprovação" feita só em parte, em verde clarinho, com o detalhe
    aprovacao = etapa_da_aprovacao(original)
    classe_da_aprovacao = aprovacao.get_attribute("class")
    texto_da_aprovacao = aprovacao.text_content()
    conferir(f"no original, '{ETAPA_DA_APROVACAO}' feita em parte (classe: {classe_da_aprovacao})",
             "passo-feito" in classe_da_aprovacao and "passo-parcial" in classe_da_aprovacao)
    conferir(f"no original, o detalhe '{dados['detalhe_da_aprovacao']}' (na tela: {texto_da_aprovacao})",
             dados["detalhe_da_aprovacao"] in texto_da_aprovacao)
    cor_da_aprovacao = cor_da_bolinha(aprovacao)
    conferir(f"no original, a bolinha da aprovação é verde clarinho (na tela: {cor_da_aprovacao})",
             cor_da_aprovacao == VERDE_CLARINHO)

    # 2. O bloco "Idas e voltas com o banco", embaixo da linha do tempo do original
    bloco = original.locator("[data-idas-e-voltas]")
    conferir("no original, o bloco 'Idas e voltas com o banco' aparece",
             bloco.count() == 1 and "Idas e voltas com o banco" in bloco.text_content())
    # A ordem dos elementos: a linha do tempo vem antes do bloco
    bloco_depois_da_linha = original.evaluate("""cartao => {
        const linha = cartao.querySelector('.linha-do-tempo');
        const bloco = cartao.querySelector('[data-idas-e-voltas]');
        return linha !== null && bloco !== null
            && (linha.compareDocumentPosition(bloco) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
    }""")
    conferir("o bloco fica embaixo da linha do tempo", bloco_depois_da_linha)
    tipos = bloco.locator("[data-ida-e-volta]").evaluate_all("linhas => linhas.map(linha => linha.dataset.idaEVolta)")
    conferir(f"as rodadas 'enviado' e 'aprovado_em_parte' (na tela: {tipos})",
             "enviado" in tipos and "aprovado_em_parte" in tipos)
    em_parte = bloco.locator("[data-ida-e-volta='aprovado_em_parte']").first.text_content()
    conferir(f"a aprovação em parte cita a pessoa e o motivo (na tela: {em_parte})",
             dados["nome"] in em_parte and "Confirmar o salário" in em_parte)
    datas = bloco.locator(".ida-e-volta-quando").all_inner_texts()
    datas_certas = len(datas) > 0
    for data in datas:
        if not DATA_CURTA.match(data.strip()):
            datas_certas = False
    conferir(f"cada rodada com a data 'dd/mm às HHhMM' (na tela: {datas})", datas_certas)

    # 3. O envio de devolução: a linha de origem e a etapa laranja
    origem = devolucao.locator("[data-origem-do-envio]").inner_text()
    conferir(f"a linha de origem 'Devolução do envio de dd/mm (1 pessoa)' (na tela: {origem})",
             origem.startswith("Devolução do envio de") and "(1 pessoa)" in origem)
    devolvida = devolucao.locator(".linha-do-tempo .passo-devolvido")
    conferir("no envio de devolução, uma etapa devolvida", devolvida.count() == 1)
    texto_da_devolvida = devolvida.text_content()
    conferir(f"a etapa devolvida é a da aprovação, com o detalhe 'Devolvido: ...' (na tela: {texto_da_devolvida})",
             ETAPA_DA_APROVACAO in texto_da_devolvida and "Devolvido:" in texto_da_devolvida)
    cor_da_devolvida = cor_da_bolinha(devolvida)
    conferir(f"a bolinha da etapa devolvida é laranja (na tela: {cor_da_devolvida})", cor_da_devolvida == LARANJA_DE_ATENCAO)

    # 4. A pendência da pessoa: o selo "Pedido do banco" e a pergunta com o recado
    cartao_da_pessoa = aba.locator("[data-lista-pendencias] [data-pendencia]").filter(has_text=dados["nome"])
    cartao_da_pessoa.first.wait_for(timeout=20000)
    selo = cartao_da_pessoa.first.locator("[data-selo-pedido-do-banco]")
    conferir("a pendência da pessoa tem o selo 'Pedido do banco'",
             selo.count() == 1 and selo.inner_text().strip() == "Pedido do banco")
    # A pergunta fica na conversa, que abre no painel do lado (ADR-138)
    pergunta = abrir_a_conversa(aba, cartao_da_pessoa.first).locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"a pergunta traz o recado do banco (na tela: {pergunta})", "O banco pediu: " + RECADO_DO_BANCO in pergunta)
    # O selo só aparece nas pendências pedidas pelo banco (aqui, só nesta)
    selos_na_lista = aba.locator("[data-lista-pendencias] [data-selo-pedido-do-banco]").count()
    conferir(f"o selo aparece só na pendência pedida pelo banco (na tela: {selos_na_lista})", selos_na_lista == 1)

    # A lista de funcionários: a linha do título fica congelada quando a lista rola
    aba.locator("[data-corpo-tabela] tr").nth(10).wait_for(timeout=20000)
    parado, medida = titulo_fica_parado(aba, "[data-tabela-funcionarios]")
    conferir(f"o título da lista de funcionários fica congelado ao rolar ({medida})", parado)
    aba.close()
