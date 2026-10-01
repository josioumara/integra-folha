"""Roteiro: a política de conteúdo (CSP) não quebra nenhuma tela (ADR-110).

O que ele confere, no Chrome de verdade:
- cada página dos dois portais chega com a política e o navegador não bloqueia NADA dela (nenhum aviso "Content
  Security Policy" no console): scripts, estilos, fontes do Google e o atributo style="...";
- a janela "Cadastrar funcionários" continua abrindo cadastrar.html num quadro (a política deixa o próprio site) e a
  tela lá dentro recebe a marca "em-janela" (o script que era escrito dentro da página virou js/em_janela.js);
- as fontes do Google Fonts carregam (a política libera fonts.googleapis.com e fonts.gstatic.com).
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, abrir_janela_de_cadastro, entrar

DESCRICAO = "Política de conteúdo (CSP): nenhuma tela bloqueada, janela do envio e fontes funcionando"
# As páginas de cada portal
PAGINAS_DA_EMPRESA = ("home.html", "acompanhar.html", "beneficios.html", "endomarketing.html")
# (no banco: as 5 abas do menu e as telas do Sistema, no menu da engrenagem: os Parâmetros do layout e o
# Acompanhamento dos agentes; o Simulador de Rentabilidade e as Premissas financeiras estão ocultos, ADR-148)
PAGINAS_DO_BANCO = ("banco_inicio.html", "banco_empresas.html", "banco_envios.html", "banco_endomarketing.html",
                    "banco_indicadores.html?aba=painel", "banco_parametros.html", "banco_agentes.html")
# O começo do aviso que o Chrome escreve no console quando a política bloqueia algo
AVISO_DE_BLOQUEIO = "Content Security Policy"


def preparar() -> dict:
    """Só os usuários de teste."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def anotar_bloqueios(aba, bloqueios: list) -> None:
    """Liga a escuta do console da aba: todo aviso de bloqueio da política vai para a lista."""

    def ao_escrever_no_console(mensagem):
        # Só os avisos da política de conteúdo interessam aqui
        if AVISO_DE_BLOQUEIO in mensagem.text:
            bloqueios.append(mensagem.text[:200])

    aba.on("console", ao_escrever_no_console)


def visitar(aba, endereco: str, paginas: tuple, bloqueios: list, conferir) -> None:
    """Abre cada página, espera ela assentar e confere a política no cabeçalho e nenhum bloqueio no console."""
    for nome in paginas:
        # Quantos bloqueios havia antes desta página
        bloqueios_antes = len(bloqueios)
        resposta = aba.goto(endereco + "/" + nome)
        aba.wait_for_load_state("networkidle")
        conferir(nome + ": chega com a política e nada é bloqueado",
                 "content-security-policy" in resposta.headers and len(bloqueios) == bloqueios_antes)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Visita todas as páginas dos dois portais e abre a janela do envio."""
    bloqueios = []
    # 1. Portal Empresa
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    anotar_bloqueios(aba, bloqueios)
    visitar(aba, endereco, ("login.html",) + PAGINAS_DA_EMPRESA, bloqueios, conferir)
    # As fontes do Google carregaram (a página pede a Nunito Sans)
    conferir("fontes do Google Fonts carregadas",
             aba.evaluate("() => document.fonts.ready.then(() => document.fonts.check(\"16px 'Nunito Sans'\"))"))
    # 2. A janela do envio: o quadro abre cadastrar.html, que recebe a marca "em-janela"
    bloqueios_antes = len(bloqueios)
    quadro = abrir_janela_de_cadastro(aba)
    quadro.locator("#campo-arquivo").wait_for(state="attached", timeout=15000)
    marca_da_janela = aba.evaluate("""() => document.querySelector('.janela-novo-envio-quadro')
        .contentDocument.documentElement.classList.contains('em-janela')""")
    conferir("janela do envio: o quadro abre e a tela recebe a marca 'em-janela'", marca_da_janela)
    conferir("janela do envio: nada bloqueado pela política", len(bloqueios) == bloqueios_antes)
    aba.close()
    # 3. Portal Interno (banco)
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    anotar_bloqueios(aba, bloqueios)
    visitar(aba, endereco, PAGINAS_DO_BANCO, bloqueios, conferir)
    aba.close()
    # Os bloqueios encontrados aparecem no resultado, para saber o que corrigir
    descricao = "nenhum bloqueio da política em todo o roteiro"
    if bloqueios:
        descricao = descricao + ": " + " | ".join(bloqueios)
    conferir(descricao, len(bloqueios) == 0)
