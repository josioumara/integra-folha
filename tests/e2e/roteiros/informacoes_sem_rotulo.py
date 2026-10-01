"""Roteiro: as informações sem rótulo (ADR-143, Parte 1).

A regra: para um campo OPCIONAL, a IA tenta encontrar; se ficar em dúvida, guarda a informação, mas não a
rotula, para o banco entender depois o que dá para reaproveitar. O que este roteiro confere na tela:
- o aceite das colunas (Cadastrar): a coluna em dúvida só entre campos opcionais ("Código", entre a matrícula e o
  código da unidade, na IA simulada) fica de fora com a nota "Fica guardada sem rótulo". Escolher um campo tira a nota,
  e voltar para "Deixar de fora" põe a nota de novo. A coluna em dúvida com um obrigatório ("Vencimentos") não tem a
  nota;
- o detalhe da pessoa nas 5 listas (a conferência do Cadastrar; a ficha e o "Conferir e enviar" de Acompanhar; a ficha
  de Envios e o detalhe da Visão geral, no banco): a seção "Informações sem rótulo", com a frase que explica e uma
  linha por informação ("C.E.P: 01310-100 · pode ser: CEP residencial ou CEP comercial"). O valor do arquivo aparece
  como texto, nunca como HTML, e as grades nunca mostram essas informações;
- sem a chave "informacoes_sem_rotulo" na resposta (o servidor de antes), o detalhe abre sem a seção.
Para conferir só a tela (a regra de o que guardar é do servidor, com os testes dele), o navegador troca a resposta do
servidor (page.route): cada pessoa das 5 listas ganha a mesma lista inventada. O "Conferir e enviar" usa o envio deste
roteiro como se estivesse pronto para o banco. Os dados são os do roteiro telas_dos_obrigatorios: a Aurora do gerador
sintético e uma planilha escrita lá, com CPFs sorteados.
Guarda duas fotos (storage/painel/aceite_com_a_nota_sem_rotulo.png e ficha_com_informacoes_sem_rotulo.png).
"""
from tests.e2e.abas_do_cadastro import abrir_a_aba_das_colunas
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar
from tests.e2e.roteiros.telas_dos_obrigatorios import CONFERENCIA_COM_PESSOA
from tests.e2e.roteiros.telas_dos_obrigatorios import preparar as preparar_os_dados_das_telas_dos_obrigatorios

DESCRICAO = ("Informações sem rótulo: a nota no aceite do Cadastrar e a seção no detalhe das 5 listas de "
             "funcionários, com e sem a chave")
# A lista que o roteiro põe em cada pessoa (inventada): um CEP em dúvida entre os dois CEPs opcionais e um ramal com
# cara de HTML, que tem de aparecer como texto
INFORMACOES_SEM_ROTULO = [
    {"coluna": "C.E.P", "valor": "01310-100",
     "candidatos": [{"campo": "cep_residencial", "rotulo": "CEP residencial"},
                    {"campo": "cep_comercial", "rotulo": "CEP comercial"}]},
    {"coluna": "Ramal", "valor": "<b>2201</b>",
     "candidatos": [{"campo": "telefone_celular", "rotulo": "Telefone celular"},
                    {"campo": "telefone_comercial", "rotulo": "Telefone comercial"}]},
]
# As linhas que a seção tem de mostrar, na ordem
LINHAS_NA_TELA = [
    "C.E.P: 01310-100 · pode ser: CEP residencial ou CEP comercial",
    "Ramal: <b>2201</b> · pode ser: Telefone celular ou Telefone comercial",
]
# A frase que explica a seção
EXPLICACAO_DA_SECAO = ("O Agente Interpretador encontrou estas informações, mas não teve certeza de qual campo "
                       "são. Elas ficam guardadas e não entram nas análises.")
# As respostas do servidor que trazem as pessoas das 5 listas (o * é um pedaço do endereço, sem barra)
ROTAS_DAS_PESSOAS = [
    "**/api/empresa/funcionarios",
    "**/api/empresa/cadastro/*/lista",
    "**/api/banco/envios/*/pessoas",
    "**/api/banco/empresas/*/visao_geral",
]
# O JavaScript que lê a seção dentro de um lugar da tela: o título, a frase, as linhas e se o valor do arquivo virou
# HTML (não pode). Sem a seção, devolve null
LER_A_SECAO = """lugar => {
    const secao = lugar.querySelector("[data-informacoes-sem-rotulo]");
    if (secao === null) {
        return null;
    }
    const linhas = [];
    for (const item of secao.querySelectorAll("li")) {
        linhas.push(item.textContent);
    }
    return {titulo: secao.querySelector("h3").textContent, explicacao: secao.querySelector("p").textContent,
        linhas: linhas, virou_html: secao.querySelector("li b") !== null};
}"""


def preparar() -> dict:
    """Os mesmos dados do roteiro telas_dos_obrigatorios (a Aurora esperando o banco, o parâmetro de 4 obrigatórios e
    a planilha com as colunas "Código" e "Vencimentos")."""
    return preparar_os_dados_das_telas_dos_obrigatorios()


def pessoas_da_resposta(dados) -> list:
    """As pessoas de uma resposta das 5 listas: a própria lista (funcionários da empresa e pessoas de um envio), as
    linhas da conferência ou os funcionários da Visão geral. Uma resposta de erro não tem pessoas."""
    if isinstance(dados, list):
        return dados
    if "linhas" in dados:
        return dados["linhas"]
    return dados.get("funcionarios", [])


def trocar_a_lista_das_pessoas(rota, com_a_lista: bool) -> None:
    """Busca a resposta de verdade no servidor e troca a chave de cada pessoa: a lista inventada, ou nenhuma chave."""
    resposta = rota.fetch()
    dados = resposta.json()
    for pessoa in pessoas_da_resposta(dados):
        if com_a_lista:
            pessoa["informacoes_sem_rotulo"] = INFORMACOES_SEM_ROTULO
        else:
            pessoa.pop("informacoes_sem_rotulo", None)
    rota.fulfill(response=resposta, json=dados)


def trocar_as_respostas(aba, com_a_lista: bool) -> None:
    """Liga, nesta aba, a troca das respostas das 5 listas (com a lista inventada, ou tirando a chave)."""
    for rota in ROTAS_DAS_PESSOAS:
        aba.unroute(rota)
        aba.route(rota, lambda pedido: trocar_a_lista_das_pessoas(pedido, com_a_lista))


def conferir_a_secao(aba, seletor: str, onde: str, conferir) -> None:
    """Confere a seção num lugar da tela: o título, a frase, as linhas e o valor como texto."""
    secao = aba.eval_on_selector(seletor, LER_A_SECAO)
    conferir(f"{onde}: o detalhe mostra a seção 'Informações sem rótulo'",
             secao is not None and secao["titulo"] == "Informações sem rótulo")
    if secao is None:
        return
    conferir(f"{onde}: a frase explica que elas ficam guardadas e não entram nas análises",
             secao["explicacao"] == EXPLICACAO_DA_SECAO)
    conferir(f"{onde}: uma linha por informação (na tela: {secao['linhas']})", secao["linhas"] == LINHAS_NA_TELA)
    conferir(f"{onde}: o valor do arquivo aparece como texto, nunca como HTML", not secao["virou_html"])


def conferir_a_nota_do_aceite(aba, dados: dict, conferir) -> None:
    """Cadastrar: a coluna em dúvida só entre opcionais fica de fora com a nota, e a nota acompanha a escolha."""
    aba.set_input_files("#campo-arquivo", dados["planilha"])
    aba.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba.locator("[data-real-aceitar]:not([hidden])").wait_for(timeout=60000)
    # As colunas ficam na aba "Como o agente leu" (o resultado abre na aba "Funcionários")
    abrir_a_aba_das_colunas(aba)
    escolha_do_codigo = "select[data-coluna='Código']"
    nota_do_codigo = aba.locator("tr[data-campos-da-coluna]", has=aba.locator(escolha_do_codigo)).locator(
        "[data-nota-sem-rotulo]")
    conferir("aceite: 'Código' (dúvida só entre opcionais) fica de fora com a nota 'Fica guardada sem rótulo'",
             aba.input_value(escolha_do_codigo) == "(ignorar coluna)" and nota_do_codigo.count() == 1
             and nota_do_codigo.text_content() == "Fica guardada sem rótulo")
    nota_da_renda = aba.locator("tr[data-campos-da-coluna]", has=aba.locator(
        "select[data-coluna='Vencimentos']")).locator("[data-nota-sem-rotulo]")
    conferir("aceite: 'Vencimentos' (dúvida com um obrigatório) não tem a nota", nota_da_renda.count() == 0)
    # A pessoa abre as outras informações e escolhe um campo para o "Código": a nota some; "Deixar de fora", volta
    aba.click("[data-real-bloco-colunas-opcionais] > summary")
    aba.select_option(escolha_do_codigo, "matricula")
    conferir("aceite: escolher um campo para o 'Código' tira a nota", nota_do_codigo.count() == 0)
    aba.select_option(escolha_do_codigo, "(ignorar coluna)")
    conferir("aceite: voltar para 'Deixar de fora' põe a nota de novo", nota_do_codigo.count() == 1)
    # A foto do aceite, para conferir o visual
    aba.locator("[data-real-bloco-colunas]").screenshot(path="storage/painel/aceite_com_a_nota_sem_rotulo.png")
    # A pessoa escolhe só o campo de "Vencimentos" e aceita
    aba.select_option("[data-real-corpo-colunas] select[data-coluna='Vencimentos']", "valor_renda")
    aba.click("[data-real-aceitar]")
    aba.wait_for_function("() => document.querySelector('[data-real-aceitar]').hidden", timeout=60000)


def conferir_a_conferencia(aba, conferir) -> None:
    """Cadastrar: a ficha da pessoa na conferência da lista mostra a seção; a lista não."""
    bloco = aba.locator("[data-real-bloco-conferencia]")
    bloco.wait_for(state="visible", timeout=60000)
    # Sem pendência, a conferência vem fechada: abrir busca a lista
    if not bloco.evaluate("elemento => elemento.open"):
        aba.click("[data-real-bloco-conferencia] > summary")
    # Todas as pessoas, e não só as com pendência
    aba.uncheck("[data-real-so-pendencias]")
    aba.wait_for_function(CONFERENCIA_COM_PESSOA, timeout=30000)
    corpo = "[data-real-corpo-conferencia]"
    conferir("conferência: a lista não mostra o que ficou sem rótulo", "01310-100" not in aba.inner_text(corpo))
    # O clique numa célula comum da pessoa abre a ficha dela, logo abaixo
    pessoa = aba.locator(corpo + " > tr").filter(has=aba.locator("td:nth-child(4)")).first
    pessoa.locator("td").nth(2).click()
    aba.locator(corpo + " tr.linha-ficha-real").wait_for(timeout=10000)
    conferir_a_secao(aba, corpo + " tr.linha-ficha-real", "conferência (Cadastrar)", conferir)


def conferir_acompanhar(aba, endereco: str, processamento_id: str, conferir) -> None:
    """Acompanhar: a ficha da pessoa e o detalhe do "Conferir e enviar" mostram a seção; a grade não."""
    # O envio deste roteiro aparece como pronto para o banco: o "Conferir e enviar" monta a grade dele
    pronto = [{"processamento_id": processamento_id, "nome_arquivo": "folha_com_4_obrigatorios.csv",
               "enviado_em": "2026-09-30T10:00:00", "pessoas": 2, "ficam_de_fora": []}]
    aba.route("**/api/empresa/prontos_para_o_banco", lambda pedido: pedido.fulfill(status=200, json=pronto))
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    conferir("Acompanhar: a grade não mostra o que ficou sem rótulo",
             "01310-100" not in aba.inner_text("[data-corpo-tabela]"))
    # O clique numa célula comum da pessoa (o 2º obrigatório; o 1º é o botão) abre a ficha
    aba.locator("[data-corpo-tabela] tr").first.locator("td").nth(2).click()
    aba.locator("#janela-ficha[open]").wait_for(timeout=10000)
    conferir_a_secao(aba, "#janela-ficha-grupos", "Acompanhar (ficha)", conferir)
    # A foto da ficha, para conferir o visual
    aba.locator("#janela-ficha").screenshot(path="storage/painel/ficha_com_informacoes_sem_rotulo.png")
    aba.keyboard.press("Escape")
    # "Conferir e enviar": a grade do envio pronto; o botão da primeira coluna abre o detalhe logo abaixo da pessoa
    aba.locator("[data-abrir-conferencia-prontos]").wait_for(state="visible", timeout=20000)
    aba.click("[data-abrir-conferencia-prontos]")
    primeira_pessoa = aba.locator("[data-grades-dos-prontos] tbody tr").first
    primeira_pessoa.wait_for(timeout=20000)
    conferir("Conferir e enviar: a grade não mostra o que ficou sem rótulo",
             "01310-100" not in aba.inner_text("[data-grades-dos-prontos]"))
    primeira_pessoa.locator("button").first.click()
    aba.locator("[data-grades-dos-prontos] tr.linha-do-detalhe").wait_for(timeout=10000)
    conferir_a_secao(aba, "[data-grades-dos-prontos] tr.linha-do-detalhe", "Conferir e enviar", conferir)
    aba.click("[data-fechar-conferencia-prontos]")


def conferir_o_banco(banco, endereco: str, conferir) -> None:
    """Banco: a ficha de Envios e o detalhe da Visão geral mostram a seção; as grades não."""
    banco.goto(endereco + "/banco_envios.html")
    banco.locator("[data-corpo-pessoas] tr").first.wait_for(timeout=20000)
    conferir("Envios: a grade não mostra o que ficou sem rótulo",
             "01310-100" not in banco.inner_text("[data-corpo-pessoas]"))
    banco.locator("[data-corpo-pessoas] tr").first.locator("td").nth(1).click()
    banco.locator("#janela-ficha-pessoa[open]").wait_for(timeout=10000)
    conferir_a_secao(banco, "#janela-ficha-pessoa [data-ficha-grupos]", "Envios (ficha)", conferir)
    banco.locator("#janela-ficha-pessoa [data-fechar-janela]").first.click()
    banco.goto(endereco + "/banco_empresas.html?empresa=EMP001")
    banco.locator("[data-corpo-visao] tr").first.wait_for(timeout=20000)
    conferir("Visão geral: a grade não mostra o que ficou sem rótulo",
             "01310-100" not in banco.inner_text("[data-corpo-visao]"))
    banco.locator("[data-corpo-visao] tr").first.locator("td").nth(2).click()
    banco.locator("#janela-detalhe-funcionario[open]").wait_for(timeout=10000)
    conferir_a_secao(banco, "#janela-detalhe-funcionario [data-detalhe-grupos]", "Visão geral (detalhe)", conferir)
    banco.locator("#janela-detalhe-funcionario [data-fechar-janela]").last.click()


def conferir_sem_a_chave(aba, banco, endereco: str, conferir) -> None:
    """Sem a chave "informacoes_sem_rotulo" nas respostas (o servidor de antes), o detalhe abre sem a seção."""
    trocar_as_respostas(aba, com_a_lista=False)
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-corpo-tabela] tr").first.wait_for(timeout=20000)
    aba.locator("[data-corpo-tabela] tr").first.locator("td").nth(2).click()
    aba.locator("#janela-ficha[open]").wait_for(timeout=10000)
    conferir("sem a chave: a ficha de Acompanhar abre sem a seção",
             aba.locator("#janela-ficha-grupos [data-informacoes-sem-rotulo]").count() == 0)
    aba.keyboard.press("Escape")
    trocar_as_respostas(banco, com_a_lista=False)
    banco.goto(endereco + "/banco_empresas.html?empresa=EMP001")
    banco.locator("[data-corpo-visao] tr").first.wait_for(timeout=20000)
    banco.locator("[data-corpo-visao] tr").first.locator("td").nth(2).click()
    banco.locator("#janela-detalhe-funcionario[open]").wait_for(timeout=10000)
    conferir("sem a chave: o detalhe da Visão geral abre sem a seção",
             banco.locator("#janela-detalhe-funcionario [data-informacoes-sem-rotulo]").count() == 0)
    banco.locator("#janela-detalhe-funcionario [data-fechar-janela]").last.click()


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Cadastrar e Acompanhar como a empresa; Envios e a Visão geral como o especialista do banco; e o detalhe sem a
    chave, nas duas pontas."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    trocar_as_respostas(aba, com_a_lista=True)
    aba.goto(endereco + "/cadastrar.html")
    conferir_a_nota_do_aceite(aba, dados, conferir)
    conferir_a_conferencia(aba, conferir)
    # O envio deste roteiro (o "Conferir e enviar" de Acompanhar monta a grade dele)
    processamento_id = aba.evaluate("() => envio_de_verdade.id")
    conferir_acompanhar(aba, endereco, processamento_id, conferir)
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    trocar_as_respostas(banco, com_a_lista=True)
    conferir_o_banco(banco, endereco, conferir)
    conferir_sem_a_chave(aba, banco, endereco, conferir)
