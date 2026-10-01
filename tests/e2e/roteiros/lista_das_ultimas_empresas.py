"""Roteiro: a Carteira (aba Empresas) e a "Escolha a empresa" (aba Endomarketing) mostram só as últimas empresas
cadastradas, com a mesma função.

O que ele confere, no Chrome de verdade, com 11 empresas na carteira (as 6 da semente e 5 cadastradas no roteiro):
- as duas listas mostram só as 8 últimas cadastradas, da mais nova para a mais antiga, com o aviso "Últimas empresas
  cadastradas. Pesquise para encontrar outras.", e sem rolagem por dentro da lista;
- a busca acha pelo nome sem acento ("logistica" acha a Horizonte Logística), por um pedaço do CNPJ com pontuação, pelo
  CNPJ de uma filial e, na Carteira, pela cidade; sem nada, diz "Nenhuma empresa com essa busca."; limpar a busca
  volta às 8 últimas;
- o Endomarketing busca pelo nome ou pelo CNPJ (o campo diz isso) e abre a empresa escolhida da lista.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Carteira e Endomarketing: as 8 últimas empresas cadastradas, o aviso, sem rolagem e a busca por nome e CNPJ"
# O aviso das duas listas (o texto exato da tela)
AVISO_DAS_ULTIMAS = "Últimas empresas cadastradas. Pesquise para encontrar outras."
# As 5 empresas cadastradas no roteiro, na ordem do cadastro (a última é a mais nova); CNPJs com os dígitos certos
EMPRESAS_DO_ROTEIRO = [
    ("Cedro Engenharia Ltda.", "Construção", "Belo Horizonte", "MG", "11222333000181", "cedro.com.br"),
    ("Pampa Transportes Ltda.", "Logística", "Porto Alegre", "RS", "11444777000161", "pampa.com.br"),
    ("Maré Pescados Ltda.", "Alimentos", "Fortaleza", "CE", "45997418000153", "mare.com.br"),
    ("Serra Têxtil Ltda.", "Indústria", "Blumenau", "SC", "04252011000110", "serratextil.com.br"),
    ("Lótus Clínicas Ltda.", "Saúde", "Goiânia", "GO", "33000167000101", "lotus.com.br"),
]
# Uma filial da Aurora (mesma raiz 10433218, estabelecimento 0002): a busca pelo CNPJ dela acha a Aurora
FILIAL_DA_AURORA = "10433218000274"


def preparar() -> dict:
    """Os usuários de teste, as 5 empresas novas (cada uma um segundo depois da outra) e a filial da Aurora."""
    import time

    from models.contratos import Perfil
    from services import auth, empresas
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    especialista = auth.Usuario(login="teste.banco", perfil=Perfil.BANCO, empresa_id=None)
    # A semente entra na primeira leitura; as novas vêm depois, uma por segundo (a data de cadastro tem segundos)
    empresas.listar(conexao)
    time.sleep(1.1)
    for nome, setor, municipio, uf, cnpj, dominio in EMPRESAS_DO_ROTEIRO:
        empresas.cadastrar(conexao, especialista, {"nome": nome, "setor": setor, "municipio": municipio, "uf": uf,
                                                   "cnpj": cnpj, "endereco_comercial": "Rua Exemplo, 100",
                                                   "dominio_email": dominio, "contrato_desde": "2026-09-01"})
        time.sleep(1.1)
    empresas.adicionar_cnpj(conexao, especialista, "EMP001", FILIAL_DA_AURORA, empresas.CNPJ_FILIAL)
    # As 8 últimas: as 5 novas (da mais nova para a mais antiga) e as 3 últimas da semente (pelo código, no empate)
    nomes_da_semente = []
    for empresa in empresas.listar(conexao):
        if empresa["empresa_id"] <= "EMP006":
            nomes_da_semente.append(empresa["nome"])
    conexao.close()
    novas_da_mais_nova = []
    for empresa_do_roteiro in reversed(EMPRESAS_DO_ROTEIRO):
        novas_da_mais_nova.append(empresa_do_roteiro[0])
    ultimas = novas_da_mais_nova + list(reversed(nomes_da_semente))[:3]
    return {"ultimas": ultimas, "semente": nomes_da_semente}


def nomes_da_lista(aba, seletor_da_lista: str) -> list[str]:
    """Os nomes das empresas da lista, na ordem da tela."""
    return aba.locator(seletor_da_lista + " .botao-envio-fila-empresa").all_inner_texts()


def lista_sem_rolagem(aba, seletor_da_lista: str) -> bool:
    """True se a lista não rola por dentro: tudo o que ela tem cabe na altura que ela ocupa."""
    return aba.evaluate("(seletor) => { const lista = document.querySelector(seletor);"
                        " return lista.scrollHeight <= lista.clientHeight + 1"
                        " && getComputedStyle(lista).overflowY === 'visible'; }", seletor_da_lista)


def buscar(aba, campo: str, texto: str, seletor_da_lista: str) -> list[str]:
    """Digita na busca e devolve os nomes que a lista mostra depois."""
    aba.fill(campo, texto)
    # A lista é refeita a cada letra: espera o próximo desenho da página
    aba.wait_for_timeout(300)
    return nomes_da_lista(aba, seletor_da_lista)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """A Carteira e o Endomarketing, com a mesma lista das últimas cadastradas e a mesma busca."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.set_viewport_size({"width": 1366, "height": 768})
    # 1. A Carteira
    aba.goto(endereco + "/banco_empresas.html")
    lista = "[data-lista-empresas]"
    aba.locator(lista + " .botao-envio-fila").first.wait_for(timeout=20000)
    nomes = nomes_da_lista(aba, lista)
    conferir(f"Carteira: as 8 últimas cadastradas, da mais nova para a mais antiga (na tela: {nomes})",
             nomes == dados["ultimas"])
    conferir("Carteira: o aviso das últimas cadastradas aparece",
             aba.locator("[data-aviso-ultimas-empresas]").is_visible()
             and aba.inner_text("[data-aviso-ultimas-empresas]") == AVISO_DAS_ULTIMAS)
    conferir("Carteira: a lista não rola por dentro", lista_sem_rolagem(aba, lista))
    aba.screenshot(path="storage/painel/carteira_ultimas_empresas.png")
    campo = "[data-busca-empresas]"
    conferir("Carteira: 'logistica' (sem acento) acha a Horizonte Logística",
             buscar(aba, campo, "logistica", lista) == ["Horizonte Logística Ltda."])
    conferir("Carteira: um pedaço do CNPJ com pontuação acha a Aurora",
             buscar(aba, campo, "10.433.218", lista) == ["Aurora Alimentos Ltda."])
    conferir("Carteira: o CNPJ da filial acha a Aurora",
             buscar(aba, campo, FILIAL_DA_AURORA, lista) == ["Aurora Alimentos Ltda."])
    conferir("Carteira: a cidade acha a empresa ('belo horizonte' → Cedro)",
             buscar(aba, campo, "belo horizonte", lista) == ["Cedro Engenharia Ltda."])
    conferir("Carteira: a busca por uma empresa antiga acha além das 8 últimas",
             buscar(aba, campo, "aurora", lista) == ["Aurora Alimentos Ltda."])
    conferir("Carteira: com a busca, o aviso das últimas some",
             aba.locator("[data-aviso-ultimas-empresas]").is_hidden())
    buscar(aba, campo, "nada disso", lista)
    conferir("Carteira: sem nada, 'Nenhuma empresa com essa busca.'", aba.locator("[data-sem-empresas]").is_visible())
    conferir("Carteira: limpar a busca volta às 8 últimas", buscar(aba, campo, "", lista) == dados["ultimas"])
    # 2. O Endomarketing
    aba.goto(endereco + "/banco_endomarketing.html")
    lista = "[data-lista-empresas-endomarketing]"
    aba.locator(lista + " .botao-envio-fila").first.wait_for(timeout=20000)
    nomes = nomes_da_lista(aba, lista)
    conferir(f"Endomarketing: as mesmas 8 últimas cadastradas (na tela: {nomes})", nomes == dados["ultimas"])
    conferir("Endomarketing: o mesmo aviso aparece",
             aba.inner_text("[data-aviso-ultimas-empresas]") == AVISO_DAS_ULTIMAS)
    conferir("Endomarketing: a lista não rola por dentro", lista_sem_rolagem(aba, lista))
    campo = "[data-busca-endomarketing]"
    conferir("Endomarketing: o campo diz que a busca é pelo nome ou pelo CNPJ",
             aba.get_attribute(campo, "placeholder") == "Nome ou CNPJ da empresa")
    conferir("Endomarketing: 'mare' (sem acento) acha a Maré Pescados",
             buscar(aba, campo, "mare", lista) == ["Maré Pescados Ltda."])
    conferir("Endomarketing: o CNPJ com pontuação acha a Pampa",
             buscar(aba, campo, "11.444.777/0001-61", lista) == ["Pampa Transportes Ltda."])
    conferir("Endomarketing: o CNPJ da filial acha a Aurora",
             buscar(aba, campo, FILIAL_DA_AURORA, lista) == ["Aurora Alimentos Ltda."])
    aba.screenshot(path="storage/painel/endomarketing_ultimas_empresas.png")
    # A empresa achada abre (o topo passa a mostrar o nome dela)
    aba.click(lista + " [data-abrir-empresa-endomarketing='EMP001']")
    aba.locator("[data-empresa-escolhida]:not([hidden])").wait_for(timeout=20000)
    conferir("Endomarketing: a empresa achada abre", "Aurora" in aba.inner_text("[data-nome-da-empresa]"))
    aba.close()
