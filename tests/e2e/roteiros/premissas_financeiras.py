"""Roteiro: a tela "Premissas financeiras" OCULTA nesta versão (ADR-148).

A tela serve para o especialista salvar as novas premissas oficiais, com registro de quem mudou. Nesta versão, ela
fica oculta: o código (a página, o script e a API) fica no projeto, o item sai do menu Sistema e o endereço leva aos
Indicadores. Os cliques de antes (ver a v1, mudar um
valor, confirmar e ver a v2 no registro) estão no histórico do Git (a tag antes-do-menu-e-indicadores) e voltam com a
tela; a gravação de uma versão nova continua provada pela API (tests/test_premissas_oficiais.py).

O que ele confere, no Chrome de verdade:
- o menu da engrenagem "Sistema" não tem o item "Premissas financeiras", e nenhuma tela tem link para ela;
- quem abre o endereço da tela (também com a barra ou o ponto no fim, e com uma letra maiúscula) chega aos
  Indicadores, com o título "Indicadores" e sem erro;
- o painel continua lendo as premissas oficiais: a API /api/banco/premissas responde com a v1 (12 meses, MOB cliente
  folha R$ 2.090,62).
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Premissas financeiras ocultas (ADR-148): fora do menu Sistema, o endereço leva aos Indicadores e a API "
             "continua respondendo")

# O endereço da tela oculta e as variações que o Windows abre como o mesmo arquivo (a barra e o ponto no fim; uma letra
# maiúscula no meio)
ENDERECOS_DA_TELA_OCULTA = ["/banco_premissas.html", "/banco_premissas.html/", "/banco_premissas.html.",
                            "/banco_Premissas.html"]

# As telas do banco em que o roteiro procura um link para a tela oculta
TELAS_COM_O_MENU = ["banco_inicio.html", "banco_empresas.html", "banco_envios.html", "banco_endomarketing.html",
                    "banco_indicadores.html", "banco_parametros.html", "banco_agentes.html"]


def preparar() -> dict:
    """Só os usuários de teste: a v1 das premissas entra sozinha no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    # Abre o banco temporário e cadastra o RH da Aurora e o especialista do banco
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def conferir_o_menu_sem_o_item(aba, endereco: str, conferir) -> None:
    """Parte 1: o menu Sistema não tem o item, e nenhuma tela do banco tem link para a tela oculta."""
    aba.goto(endereco + "/banco_inicio.html")
    aba.click(".acoes-usuario [data-botao-configuracao]")
    itens = aba.locator("[data-itens-configuracao] a").all_inner_texts()
    conferir(f"o menu Sistema não tem o item 'Premissas financeiras' (itens: {itens})",
             "Premissas financeiras" not in itens and len(itens) == 3)
    aba.keyboard.press("Escape")
    # Cada tela do banco, sem nenhum link para a tela oculta
    telas_com_link = []
    for tela in TELAS_COM_O_MENU:
        aba.goto(endereco + "/" + tela)
        aba.wait_for_load_state("networkidle")
        if aba.locator("a[href*='banco_premissas']").count() > 0:
            telas_com_link.append(tela)
    conferir(f"nenhuma tela do banco tem link para as Premissas financeiras (com link: {telas_com_link})",
             telas_com_link == [])


def conferir_o_endereco_da_tela_oculta(aba, endereco: str, conferir) -> None:
    """Parte 2: o endereço da tela oculta, e as variações dele, levam aos Indicadores."""
    for endereco_da_tela in ENDERECOS_DA_TELA_OCULTA:
        aba.goto(endereco + endereco_da_tela)
        aba.wait_for_load_state("networkidle")
        titulo = aba.inner_text("h1.titulo-pagina").strip()
        conferir(f"{endereco_da_tela} leva aos Indicadores (endereço: {aba.url})",
                 aba.url.endswith("/banco_indicadores.html") and titulo.startswith("Indicadores"))


def conferir_que_a_api_continua(aba, conferir) -> None:
    """Parte 3: o painel continua lendo as premissas oficiais (a tela está oculta; a API, não)."""
    premissas = aba.evaluate("async () => (await (await fetch('/api/banco/premissas')).json())")
    # A versão vigente: {"horizonte_meses": 12, "mob_cliente_folha": "2090.62", ...} (o dinheiro vem como texto)
    valores = premissas["vigente"]
    conferir(f"a API das premissas responde com a v1 (versão {premissas['versao']}; horizonte "
             f"{valores['horizonte_meses']}; MOB cliente folha {valores['mob_cliente_folha']})",
             premissas["versao"] == 1 and str(valores["horizonte_meses"]) == "12"
             and str(valores["mob_cliente_folha"]) == "2090.62")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Entra como especialista do banco e confere que as Premissas financeiras estão ocultas."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_o_menu_sem_o_item(aba, endereco, conferir)
    conferir_o_endereco_da_tela_oculta(aba, endereco, conferir)
    conferir_que_a_api_continua(aba, conferir)
    aba.close()
