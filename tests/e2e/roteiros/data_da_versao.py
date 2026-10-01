"""Roteiro: a data da versão ("Atualizado em ...") fica oculta nesta versão em todas as telas (ADR-133 e ADR-148).

O que ele confere:
- a tela de login (sem entrar), a Home e Acompanhar da empresa e o Início do banco não mostram o rótulo
  "Atualizado em ...", e nenhuma data aparece no lugar dele;
- o lugar do rótulo continua na página, escondido e com a marca data-oculto-nesta-versao (o código fica, ADR-148);
- nenhuma dessas telas pede a data ao servidor (nenhum pedido à rota /api/versao).
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, SENHA_DE_TESTE

DESCRICAO = ("Rótulo 'Atualizado em ...' oculto nesta versão: não aparece no login, na Home e em Acompanhar da empresa "
             "nem no Início do banco; o lugar fica com a marca de oculto, e a tela não pede a data ao servidor")

# O lugar do rótulo em todas as telas, e o mesmo lugar com a marca de oculto nesta versão
LUGAR_DO_ROTULO = "[data-data-da-versao]"
LUGAR_OCULTO = "[data-data-da-versao][data-oculto-nesta-versao]"
# A rota que daria a data da versão (continua no servidor, mas nenhuma tela a chama nesta versão)
ROTA_DA_DATA = "/api/versao"


def preparar() -> dict:
    """Os usuários de teste da empresa e do banco."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def entrar(aba, endereco: str, login: str) -> None:
    """Entra pela tela de login com o usuário informado e espera sair do login."""
    # Abre o login
    aba.goto(endereco + "/login.html")
    # Digita o usuário e a senha de teste
    aba.fill("[name='usuario']", login)
    aba.fill("[name='senha']", SENHA_DE_TESTE)
    # Clica em Entrar
    aba.click("button[type='submit']")
    # Espera a página inicial do perfil
    aba.wait_for_url(lambda url: "login.html" not in url, timeout=20000)


def abrir_aba_que_anota_a_data(navegador, erros_da_pagina: list, pedidos_da_data: list):
    """Abre uma aba que anota os erros de JavaScript e cada pedido à rota da data da versão. Devolve a aba."""
    aba = navegador.new_page(viewport={"width": 1440, "height": 1000})
    aba.on("pageerror", lambda erro: erros_da_pagina.append(str(erro)))

    def anotar_se_pede_a_data(pedido) -> None:
        """Anota o pedido à rota da data da versão (nesta versão, nenhuma tela pode fazê-lo)."""
        if ROTA_DA_DATA in pedido.url:
            pedidos_da_data.append(pedido.url)

    aba.on("request", anotar_se_pede_a_data)
    return aba


def conferir_o_rotulo_oculto(aba, conferir, tela: str, pedidos_da_data: list) -> None:
    """Na tela aberta: o rótulo não aparece, o lugar dele está oculto e com a marca, e a data não foi pedida."""
    # Espera a rede sossegar: se a tela fosse pedir a data, o pedido já teria saído
    aba.wait_for_load_state("networkidle")
    lugar = aba.locator(LUGAR_DO_ROTULO)
    conferir(tela + ": o lugar do rótulo continua na página, oculto e com a marca",
             lugar.count() == 1 and aba.locator(LUGAR_OCULTO).count() == 1 and not lugar.is_visible())
    conferir(tela + ": nenhum \"Atualizado em\" na tela", "Atualizado em" not in aba.inner_text("body"))
    conferir(tela + ": a tela não pediu a data ao servidor", pedidos_da_data == [])


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: o login sem entrar, a empresa (Home e Acompanhar) e o banco (Início)."""
    # Cada pedido à rota da data fica anotado aqui (não pode haver nenhum)
    pedidos_da_data = []
    # 1. A tela de login, sem entrar
    aba = abrir_aba_que_anota_a_data(navegador, erros_da_pagina, pedidos_da_data)
    aba.goto(endereco + "/login.html")
    conferir_o_rotulo_oculto(aba, conferir, "o login, sem entrar", pedidos_da_data)
    # 2. A empresa: a Home (a primeira tela depois do login) e Acompanhar
    entrar(aba, endereco, LOGIN_DA_EMPRESA)
    conferir_o_rotulo_oculto(aba, conferir, "a Home da empresa", pedidos_da_data)
    aba.goto(endereco + "/acompanhar.html")
    conferir_o_rotulo_oculto(aba, conferir, "Acompanhar", pedidos_da_data)
    aba.close()
    # 3. O banco: o Início do Portal Interno (uma aba nova, sem a sessão da empresa)
    aba_do_banco = abrir_aba_que_anota_a_data(navegador, erros_da_pagina, pedidos_da_data)
    entrar(aba_do_banco, endereco, LOGIN_DO_BANCO)
    conferir_o_rotulo_oculto(aba_do_banco, conferir, "o Início do Portal Interno", pedidos_da_data)
    aba_do_banco.close()
