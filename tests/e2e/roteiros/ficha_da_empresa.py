"""Roteiro: a ficha da empresa no Portal Interno (menu Empresas): a Carteira, a Visão geral e o "Baixar CSV".

O que ele confere, no Chrome de verdade, com 11 empresas na carteira (as 6 da semente e 5 cadastradas no roteiro), a
Aurora com a carga inicial cadastrada e o parâmetro dos 4 campos obrigatórios (ADR-143):
- a Carteira "congela" a empresa escolhida, como a escolha do Endomarketing: escolhida, a lista some e fica só ela,
  com o "Trocar empresa"; o F5 volta nela; "Trocar empresa" traz a busca e a lista de volta;
- as empresas com conversa aberta vêm primeiro na Carteira, sem limite (mesmo as que não estão entre as 8 últimas
  cadastradas): primeiro as que esperam resposta, a mais antiga antes; depois, as 8 últimas cadastradas. A lista vem
  do sinal da Conversa (window.conversas_abertas e o evento "conversas-abertas-atualizadas"). Com o
  sinal ainda sem resposta (null), a Carteira segue como antes, sem erro, e a mesma empresa repetida na lista aparece
  uma vez só;
- a Visão geral tem o "Baixar CSV": o arquivo da empresa aberta, com os obrigatórios, os opcionais que vieram, a
  situação, a conta e a inclusão, no padrão dos outros arquivos (";" e UTF-8 com a marca do Excel); some na empresa
  sem funcionários;
- a grade de funcionários da Visão geral cabe na ficha, sem rolar para o lado, a 1366 e a 1920 px, com o CPF inteiro
  numa linha só.
Também guarda fotos em storage/painel/ (ficha_carteira_*.png e ficha_visao_*.png) para conferir o visual.
"""
import csv
import io

from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Ficha da empresa: Carteira congelada, conversas abertas primeiro, Baixar CSV e grade sem rolagem"
# As empresas que a Carteira mostra sem busca: as 5 do roteiro (da mais nova para a mais antiga) e as 3 últimas da
# semente (pelo código, no empate da data de cadastro)
ULTIMAS_EMPRESAS = ["EMP011", "EMP010", "EMP009", "EMP008", "EMP007", "EMP006", "EMP005", "EMP004"]
# A marca do começo do arquivo que avisa o Excel de que ele é UTF-8
MARCA_DO_UTF8 = "﻿"


def gravar_mensagem(conexao, empresa_id: str, de: str, texto: str, criado_em: str) -> None:
    """Grava uma mensagem da conversa (da empresa ou do banco), direto na tabela das conversas."""
    conexao.execute("INSERT INTO mensagens_de_ajuda (empresa_id, de, autor, contexto, texto, criado_em) "
                    "VALUES (?, ?, 'roteiro', 'Início', ?, ?)", (empresa_id, de, texto, criado_em))


def preparar() -> dict:
    """A Aurora com a carga e 3 contas, o parâmetro dos 4 obrigatórios, 5 empresas novas e duas conversas abertas."""
    import time

    from models.contratos import Perfil
    from scripts.aplicar_parametro_adr_143 import aplicar
    from services import auth, empresas, mensagens
    from tests.e2e.roteiros import grade_de_funcionarios, lista_das_ultimas_empresas
    # A Aurora com a carga inicial cadastrada e 3 contas abertas (e os usuários de teste)
    grade_de_funcionarios.preparar()
    conexao = auth.conectar()
    # O parâmetro de hoje: só os 4 obrigatórios do ADR-143 (o do banco novo tem os 24 antigos)
    aplicar(conexao)
    # As 5 empresas novas, uma por segundo (a data de cadastro tem segundos)
    especialista = auth.Usuario(login=LOGIN_DO_BANCO, perfil=Perfil.BANCO, empresa_id=None)
    time.sleep(1.1)
    for nome, setor, municipio, uf, cnpj, dominio in lista_das_ultimas_empresas.EMPRESAS_DO_ROTEIRO:
        empresas.cadastrar(conexao, especialista, {"nome": nome, "setor": setor, "municipio": municipio, "uf": uf,
                                                   "cnpj": cnpj, "endereco_comercial": "Rua Exemplo, 100",
                                                   "dominio_email": dominio, "contrato_desde": "2026-09-01"})
        time.sleep(1.1)
    # Duas conversas abertas em empresas que NÃO estão entre as 8 últimas: a Horizonte espera a resposta do
    # especialista; a Brisa já teve resposta, mas a conversa não foi marcada como resolvida
    mensagens.conversa_da_empresa(conexao, "EMP001")
    gravar_mensagem(conexao, "EMP002", "empresa", "Quando o banco manda as contas abertas?", "2026-09-30T09:00:00+00:00")
    gravar_mensagem(conexao, "EMP003", "empresa", "Posso mandar a matrícula com letras?", "2026-09-29T09:00:00+00:00")
    gravar_mensagem(conexao, "EMP003", "banco", "Pode, sim.", "2026-09-29T10:00:00+00:00")
    conexao.commit()
    conexao.close()
    return {}


def codigos_da_carteira(aba) -> list[str]:
    """Os códigos das empresas da Carteira, na ordem da tela."""
    codigos = []
    for botao in aba.locator("[data-lista-empresas] [data-abrir-empresa]").all():
        codigos.append(botao.get_attribute("data-abrir-empresa"))
    return codigos


def conferir_a_carteira_congelada(aba, conferir, codigo: str, momento: str) -> None:
    """Confere a Carteira congelada numa empresa: só ela na lista, sem a busca e com o "Trocar empresa"."""
    conferir(f"{momento}: a lista fica só com a escolhida ({codigos_da_carteira(aba)})", codigos_da_carteira(aba) == [codigo])
    conferir(f"{momento}: a busca some", aba.locator("[data-campo-busca-da-carteira]").is_hidden())
    conferir(f"{momento}: o 'Trocar empresa' aparece", aba.locator("[data-trocar-empresa]").is_visible())
    conferir(f"{momento}: o aviso das últimas empresas some", aba.locator("[data-aviso-ultimas-empresas]").is_hidden())


def grade_sem_rolagem(aba) -> dict:
    """A largura da caixa da grade da Visão geral e a do conteúdo dela, e quantas linhas o 1º CPF ocupa."""
    return aba.evaluate("""() => {
        const moldura = document.querySelector('[data-cabeca-visao]').closest('.tabela-rolavel');
        const cpf = document.querySelector('[data-corpo-visao] tr td .botao-nome');
        return {caixa: moldura.clientWidth, conteudo: moldura.scrollWidth, linhas_do_cpf: cpf.getClientRects().length,
                altura_do_cpf: cpf.getBoundingClientRect().height,
                altura_da_linha: parseFloat(getComputedStyle(cpf).lineHeight) || 20};
    }""")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """A Carteira, as conversas abertas, o CSV e a grade da Visão geral."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.set_viewport_size({"width": 1366, "height": 768})
    # 1. Sem empresa no endereço: a Carteira mostra a busca e a lista
    aba.goto(endereco + "/banco_empresas.html")
    aba.locator("[data-lista-empresas] [data-abrir-empresa]").first.wait_for(timeout=20000)
    aba.wait_for_timeout(1500)
    conferir("sem empresa no endereço, a busca aparece e o 'Trocar empresa' não",
             aba.locator("[data-campo-busca-da-carteira]").is_visible()
             and aba.locator("[data-trocar-empresa]").is_hidden())
    # 2. As conversas abertas primeiro. Com o sinal da Conversa, as de verdade: a Horizonte (sem resposta) e
    #    a Brisa (respondida, não resolvida), antes das 8 últimas cadastradas
    tem_o_sinal = aba.evaluate("() => typeof buscar_conversas_abertas === 'function'")
    if tem_o_sinal:
        # O sinal começa em null e chega na primeira busca (js/sinal_de_conversas.js)
        aba.wait_for_function("() => window.conversas_abertas !== null", timeout=15000)
        aba.wait_for_timeout(500)
        esperado = ["EMP002", "EMP003"] + ULTIMAS_EMPRESAS
        conferir(f"com o sinal da Conversa: as abertas primeiro (Horizonte, Brisa) e depois as 8 últimas "
                 f"({codigos_da_carteira(aba)})", codigos_da_carteira(aba) == esperado)
    else:
        conferir(f"sem o sinal da Conversa nesta cópia: a Carteira segue com as 8 últimas, sem erro "
                 f"({codigos_da_carteira(aba)})", codigos_da_carteira(aba) == ULTIMAS_EMPRESAS)
    # A lista do sinal, trocada por uma de mentira (no formato do sinal): a Aurora e a Horizonte esperam a
    # resposta (a Aurora há mais tempo), e a Brisa já foi respondida
    aba.evaluate("""() => {
        window.conversas_abertas = {total: 3, empresas: [
            {empresa_id: "EMP003", sem_resposta: false, ultima_mensagem_em: "2026-09-29T10:00:00+00:00"},
            {empresa_id: "EMP002", sem_resposta: true, ultima_mensagem_em: "2026-09-30T09:00:00+00:00"},
            {empresa_id: "EMP001", sem_resposta: true, ultima_mensagem_em: "2026-09-28T09:00:00+00:00"}]};
        document.dispatchEvent(new CustomEvent("conversas-abertas-atualizadas"));
    }""")
    esperado = ["EMP001", "EMP002", "EMP003"] + ULTIMAS_EMPRESAS
    conferir(f"as abertas vêm primeiro, sem limite: sem resposta antes (a mais antiga primeiro), depois a respondida, "
             f"e as 8 últimas ({codigos_da_carteira(aba)})", codigos_da_carteira(aba) == esperado)
    aba.screenshot(path="storage/painel/ficha_carteira_abertas_primeiro.png")
    # Com a busca, as abertas que combinam continuam na frente
    aba.fill("[data-busca-empresas]", "ltda")
    aba.wait_for_timeout(300)
    conferir("com a busca, as abertas que combinam continuam na frente",
             codigos_da_carteira(aba)[:3] == ["EMP001", "EMP002", "EMP003"])
    aba.fill("[data-busca-empresas]", "")
    aba.wait_for_timeout(300)
    # O sinal ainda sem resposta (window.conversas_abertas fica null até o sinal chegar):
    # nenhuma aberta, sem erro
    aba.evaluate("() => { window.conversas_abertas = null;"
                 " document.dispatchEvent(new CustomEvent('conversas-abertas-atualizadas', { detail: null })); }")
    conferir("sem a resposta do sinal (null), nenhuma conversa aberta e nenhum erro",
             codigos_da_carteira(aba) == ULTIMAS_EMPRESAS)
    # A mesma empresa duas vezes na lista do sinal: o cartão aparece uma vez só
    aba.evaluate("""() => {
        window.conversas_abertas = {total: 1, empresas: [
            {empresa_id: "EMP002", sem_resposta: true, ultima_mensagem_em: "2026-09-30T09:00:00+00:00"},
            {empresa_id: "EMP002", sem_resposta: true, ultima_mensagem_em: "2026-09-30T09:00:00+00:00"}]};
        document.dispatchEvent(new CustomEvent("conversas-abertas-atualizadas"));
    }""")
    conferir("a mesma empresa repetida na lista do sinal aparece uma vez só",
             codigos_da_carteira(aba) == ["EMP002"] + ULTIMAS_EMPRESAS)
    # 3. Escolher uma empresa: a Carteira congela nela
    aba.click("[data-lista-empresas] [data-abrir-empresa='EMP009']")
    aba.wait_for_function("() => document.querySelector('[data-ficha-nome]').innerText.includes('Maré')", timeout=10000)
    conferir_a_carteira_congelada(aba, conferir, "EMP009", "escolhida a Maré")
    conferir("a ficha é a da empresa escolhida", "Maré Pescados" in aba.inner_text("[data-ficha-nome]"))
    conferir("o endereço guarda a empresa (?empresa=EMP009)", "empresa=EMP009" in aba.url)
    aba.screenshot(path="storage/painel/ficha_carteira_congelada.png")
    # O F5 volta congelada na mesma empresa
    aba.reload()
    aba.locator("[data-lista-empresas] [data-abrir-empresa]").first.wait_for(timeout=20000)
    aba.wait_for_function("() => document.querySelector('[data-ficha-nome]').innerText.includes('Maré')", timeout=10000)
    conferir_a_carteira_congelada(aba, conferir, "EMP009", "depois do F5")
    # 4. "Trocar empresa": a busca e a lista voltam, com o cursor na busca; a ficha continua a da escolhida
    aba.click("[data-trocar-empresa]")
    conferir("'Trocar empresa' traz a lista de volta", len(codigos_da_carteira(aba)) >= 8)
    conferir("'Trocar empresa' traz a busca, com o cursor nela",
             aba.locator("[data-campo-busca-da-carteira]").is_visible()
             and aba.evaluate("() => document.activeElement.hasAttribute('data-busca-empresas')"))
    conferir("o 'Trocar empresa' some enquanto a lista está à mostra", aba.locator("[data-trocar-empresa]").is_hidden())
    conferir("a ficha continua a da Maré até escolher outra", "Maré Pescados" in aba.inner_text("[data-ficha-nome]"))
    # Buscar e escolher outra (uma antiga, achada pela busca): congela nela
    aba.fill("[data-busca-empresas]", "aurora")
    aba.wait_for_timeout(300)
    aba.click("[data-lista-empresas] [data-abrir-empresa='EMP001']")
    aba.wait_for_function("() => document.querySelector('[data-ficha-nome]').innerText.includes('Aurora')",
                          timeout=10000)
    conferir_a_carteira_congelada(aba, conferir, "EMP001", "escolhida a Aurora pela busca")
    # 5. A Visão geral da Aurora: o "Baixar CSV" e a grade sem rolar para o lado, a 1366 e a 1920 px
    aba.locator("[data-corpo-visao] tr").first.wait_for(timeout=20000)
    quantas_pessoas = aba.locator("[data-corpo-visao] > tr").count()
    for largura in (1366, 1920):
        aba.set_viewport_size({"width": largura, "height": 900})
        aba.wait_for_timeout(300)
        medida = grade_sem_rolagem(aba)
        conferir(f"a {largura} px, a grade cabe na ficha, sem rolar para o lado ({medida['conteudo']} de "
                 f"{medida['caixa']} px)", medida["conteudo"] <= medida["caixa"] + 1)
        conferir(f"a {largura} px, o CPF fica numa linha só", medida["linhas_do_cpf"] == 1
                 and medida["altura_do_cpf"] < medida["altura_da_linha"] * 1.6)
        aba.locator("[data-visao-geral]").screenshot(path=f"storage/painel/ficha_visao_{largura}.png")
    aba.set_viewport_size({"width": 1366, "height": 768})
    conferir("o 'Baixar CSV' aparece na Visão geral", aba.locator("[data-baixar-csv-visao]").is_visible())
    with aba.expect_download() as baixado:
        aba.click("[data-baixar-csv-visao]")
    arquivo = baixado.value
    conteudo = open(arquivo.path(), encoding="utf-8", newline="").read()
    conferir(f"o arquivo se chama funcionarios_EMP001.csv ({arquivo.suggested_filename})",
             arquivo.suggested_filename == "funcionarios_EMP001.csv")
    conferir("o arquivo começa com a marca do UTF-8 (o Excel lê os acentos)", conteudo.startswith(MARCA_DO_UTF8))
    linhas = list(csv.reader(io.StringIO(conteudo[len(MARCA_DO_UTF8):]), delimiter=";"))
    cabecalho = linhas[0]
    conferir(f"o cabeçalho começa pelos 4 obrigatórios ({cabecalho[:4]})",
             cabecalho[:4] == ["CPF", "Código CBO", "Data admissão", "Valor renda"])
    conferir("o cabeçalho traz opcionais que vieram (o nome) e a situação, a conta e a inclusão",
             "Nome completo" in cabecalho and "Situação" in cabecalho and "Agência" in cabecalho
             and cabecalho[-2:] == ["Incluído em", "Incluído por"])
    conferir(f"o cabeçalho chama a conta de 'Conta salário' ({cabecalho[-5:]})",
             "Conta salário" in cabecalho and "Conta salário aberta em" in cabecalho and "Conta" not in cabecalho)
    conferir(f"uma linha por pessoa da grade ({len(linhas) - 1} de {quantas_pessoas})",
             len(linhas) - 1 == quantas_pessoas)
    situacoes = set()
    for linha in linhas[1:]:
        situacoes.add(linha[cabecalho.index("Situação")])
    conferir(f"as situações do arquivo são as da grade ({sorted(situacoes)})",
             {"Cadastrado", "Conta aberta", "Já é correntista"} <= situacoes)
    # 6. Uma empresa sem funcionários: o botão some
    aba.goto(endereco + "/banco_empresas.html?empresa=EMP004")
    aba.wait_for_function("() => document.querySelector('[data-ficha-nome]').innerText.length > 0", timeout=20000)
    aba.locator("[data-visao-sem-funcionarios]:not([hidden])").wait_for(timeout=20000)
    conferir("na empresa sem funcionários, o 'Baixar CSV' some", aba.locator("[data-baixar-csv-visao]").is_hidden())
    conferir("vinda pelo endereço, a Carteira já começa congelada na empresa pedida",
             codigos_da_carteira(aba) == ["EMP004"] and aba.locator("[data-trocar-empresa]").is_visible())
    aba.close()
