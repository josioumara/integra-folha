"""Roteiro: Benefícios e Materiais para divulgar nunca mostram os exemplos do protótipo.

O defeito: as telas nasceram do protótipo e trazem cartões, textos e listas DE EXEMPLO escritos no HTML (ou montados
no JavaScript). Servidas pela aplicação, esses exemplos apareciam por um instante a cada F5, até a API responder, e
ficavam na tela se a API falhasse. Agora eles viram barras cinza de "carregando" (js/carregando_dados.js).

O que ele confere, em cada uma das duas telas (beneficios.html e endomarketing.html):
1. com a resposta da API presa por 2 segundos, nenhum texto de exemplo está visível e as barras cinza estão lá;
2. depois que a resposta chega, não sobra nenhum elemento marcado esperando ([data-aguarda-...] sem data-dado-pronto);
3. com a API respondendo 500 (erro), nenhum exemplo aparece, nada fica cinza e aparece o aviso de erro.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Benefícios e Materiais para divulgar: sem exemplos do protótipo na espera, depois e com a API em erro"

# Quanto tempo a resposta da API fica presa, para a tela ficar "esperando" (em milissegundos)
TEMPO_COM_A_RESPOSTA_PRESA = 2000

# Os textos de exemplo escritos no beneficios.html (cartões, subtítulo, origem, filtro, dúvida e canal)
EXEMPLOS_DE_BENEFICIOS = [
    "Conta salário sem tarifa",
    "Seguro de vida acessível",
    "Pacote Folha Essencial sem tarifa no primeiro ano",
    "Vantagens que o banco definiu para os funcionários da Aurora",
    "Catálogo definido pelo banco para a Aurora",
    "Preciso abrir conta corrente",
    "atendimento.aurora@banco.example",
    "Proteção",
]
# Os exemplos que o catálogo real da Aurora não tem (os outros podem coincidir com o real, que também é da Aurora)
EXEMPLOS_QUE_O_REAL_NAO_TEM = [
    "Seguro de vida acessível",
    "Pacote Folha Essencial sem tarifa no primeiro ano",
    "Preciso abrir conta corrente para receber o salário?",
]
# Os títulos dos materiais de exemplo do js/endomarketing.js e o resumo que eles gerariam
EXEMPLOS_DE_MATERIAIS = [
    "Seu salário no Santander: conheça as vantagens",
    "Perguntas frequentes: seu salário no Santander",
    "Bem-vindo(a) à Aurora!",
    "3 materiais publicados",
]

# Uma função JavaScript: dos textos pedidos, quais estão VISÍVEIS dentro do <main> (texto transparente, escondido
# ou fora da tela desenhada não conta como visível). Devolve a lista dos textos que alguém veria.
TEXTOS_VISIVEIS_NO_PRINCIPAL = """(textos_procurados) => {
    const principal = document.querySelector('main');
    const textos_vistos = [];
    // Percorre cada pedaço de texto da página, um por um
    const caminhante = document.createTreeWalker(principal, NodeFilter.SHOW_TEXT);
    let pedaco_de_texto = caminhante.nextNode();
    while (pedaco_de_texto !== null) {
        const elemento = pedaco_de_texto.parentElement;
        const estilo = window.getComputedStyle(elemento);
        // Visível de verdade: desenhado na tela, sem visibility hidden e com uma cor que não é transparente
        const desenhado = elemento.getClientRects().length > 0;
        const cor_transparente = estilo.color === 'rgba(0, 0, 0, 0)' || estilo.color === 'transparent';
        const visivel = desenhado && estilo.visibility !== 'hidden' && !cor_transparente;
        if (visivel) {
            for (const texto of textos_procurados) {
                if (pedaco_de_texto.textContent.includes(texto) && !textos_vistos.includes(texto)) {
                    textos_vistos.push(texto);
                }
            }
        }
        pedaco_de_texto = caminhante.nextNode();
    }
    return textos_vistos;
}"""

# Os elementos marcados que ainda esperam o dado (continuam cinza)
SELETOR_DOS_QUE_ESPERAM = "[data-aguarda-dado]:not([data-dado-pronto]), [data-aguarda-bloco]:not([data-dado-pronto])"


def preparar() -> dict:
    """Só os usuários de teste: o catálogo da Aurora entra sozinho no banco novo (e nenhum material publicado)."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def quantos_esperam(aba) -> int:
    """Quantos elementos marcados ainda estão cinza, esperando o dado."""
    return aba.evaluate("(seletor) => document.querySelectorAll(seletor).length", SELETOR_DOS_QUE_ESPERAM)


def textos_visiveis(aba, textos_procurados: list) -> list:
    """Dos textos procurados, os que aparecem de verdade dentro do <main>."""
    return aba.evaluate(TEXTOS_VISIVEIS_NO_PRINCIPAL, textos_procurados)


def esperar_que_nada_fique_cinza(aba) -> bool:
    """Espera (até 15 s) todos os elementos marcados serem liberados. Devolve True se nenhum sobrou cinza."""
    # try/except: se o tempo acabar, o roteiro anota a falha em vez de parar
    try:
        aba.wait_for_function("(seletor) => document.querySelectorAll(seletor).length === 0",
                              arg=SELETOR_DOS_QUE_ESPERAM, timeout=15000)
        return True
    except Exception:  # noqa: BLE001 (o tempo acabou: a falha vira um "FALHOU" no resultado)
        return False


def abrir_com_a_resposta_presa(aba, endereco: str, pagina: str, rota: str, conferir, exemplos: list) -> None:
    """Abre a página com a resposta da rota presa, confere a espera e depois solta a resposta.

    Recebe: a aba; o endereço do servidor; a página (ex.: "/beneficios.html"); a rota da API que ela chama
    (ex.: "/api/empresa/beneficios"); a função conferir; os textos de exemplo que não podem aparecer.
    """
    # Os pedidos à rota ficam guardados aqui, sem resposta, até o roteiro soltá-los
    pedidos_presos = []

    def prender_o_pedido(pedido_da_rota) -> None:
        """Guarda o pedido sem responder: a tela fica esperando a API."""
        pedidos_presos.append(pedido_da_rota)

    aba.route("**" + rota, prender_o_pedido)
    aba.goto(endereco + pagina, wait_until="domcontentloaded")
    # Espera a tela pedir os dados (até 5 s), e então segura a resposta por 2 s
    for _tentativa in range(50):
        if pedidos_presos:
            break
        aba.wait_for_timeout(100)
    conferir(pagina + ": a tela pediu " + rota, len(pedidos_presos) > 0)
    aba.wait_for_timeout(TEMPO_COM_A_RESPOSTA_PRESA)
    # 1. Durante a espera: a marca na página, as barras cinza e nenhum exemplo visível
    tem_a_marca = aba.evaluate("() => document.documentElement.classList.contains('aguardando-dados')")
    conferir(pagina + ": servida pela aplicação, a página tem a marca 'aguardando-dados'", tem_a_marca)
    esperando = quantos_esperam(aba)
    conferir(pagina + ": durante a espera, " + str(esperando) + " elementos mostram a barra cinza", esperando > 0)
    vistos = textos_visiveis(aba, exemplos)
    conferir(pagina + ": durante a espera, nenhum exemplo visível (vistos: " + str(vistos) + ")", vistos == [])
    # Solta a resposta: a tela recebe os dados de verdade
    for pedido in pedidos_presos:
        pedido.continue_()
    aba.unroute("**" + rota)
    # 2. Depois da resposta: nenhum elemento marcado continua cinza
    conferir(pagina + ": depois da resposta, nenhum elemento ficou cinza", esperar_que_nada_fique_cinza(aba))


def abrir_com_a_api_em_erro(aba, endereco: str, pagina: str, rota: str, conferir, exemplos: list) -> None:
    """Abre a página com a rota respondendo 500 e confere que nada de exemplo aparece e nada fica cinza.

    Recebe: os mesmos dados de abrir_com_a_resposta_presa().
    """

    def responder_com_erro(pedido_da_rota) -> None:
        """Responde como um servidor com defeito (código 500)."""
        pedido_da_rota.fulfill(status=500, body="erro de teste")

    aba.route("**" + rota, responder_com_erro)
    aba.goto(endereco + pagina, wait_until="domcontentloaded")
    # 3. Com a API em erro: tudo liberado, nenhum exemplo à mostra
    conferir(pagina + " com a API em erro: nenhum elemento ficou cinza", esperar_que_nada_fique_cinza(aba))
    vistos = textos_visiveis(aba, exemplos)
    conferir(pagina + " com a API em erro: nenhum exemplo visível (vistos: " + str(vistos) + ")", vistos == [])
    aba.unroute("**" + rota)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """As duas telas, cada uma com a resposta presa e com a API em erro."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)

    # ===== Benefícios do seu time =====
    abrir_com_a_resposta_presa(aba, endereco, "/beneficios.html", "/api/empresa/beneficios", conferir,
                               EXEMPLOS_DE_BENEFICIOS)
    cartoes = aba.locator("[data-grade-beneficios] .cartao-beneficio").count()
    conferir("benefícios: os cartões do catálogo real aparecem (" + str(cartoes) + ")", cartoes == 6)
    vistos = textos_visiveis(aba, EXEMPLOS_QUE_O_REAL_NAO_TEM)
    conferir("benefícios: nenhum exemplo sobrou depois do catálogo real (vistos: " + str(vistos) + ")", vistos == [])
    abrir_com_a_api_em_erro(aba, endereco, "/beneficios.html", "/api/empresa/beneficios", conferir,
                            EXEMPLOS_DE_BENEFICIOS)
    origem = aba.inner_text("[data-origem-catalogo]")
    conferir("benefícios com a API em erro: a origem vira o aviso (" + origem + ")",
             "Não foi possível carregar" in origem)
    recado_dos_cartoes = aba.inner_text("[data-grade-beneficios]")
    conferir("benefícios com a API em erro: o recado no lugar dos cartões",
             "Não foi possível carregar agora." in recado_dos_cartoes)

    # ===== Materiais para divulgar =====
    abrir_com_a_resposta_presa(aba, endereco, "/endomarketing.html", "/api/empresa/endomarketing", conferir,
                               EXEMPLOS_DE_MATERIAIS)
    # Banco novo: nenhum material publicado, então aparece o aviso de lista vazia
    conferir("materiais: sem material publicado, aparece o aviso de lista vazia",
             aba.locator("[data-sem-materiais]").is_visible())
    abrir_com_a_api_em_erro(aba, endereco, "/endomarketing.html", "/api/empresa/endomarketing", conferir,
                            EXEMPLOS_DE_MATERIAIS)
    aviso_de_erro = aba.locator("[data-erro-materiais]")
    conferir("materiais com a API em erro: aparece o aviso de erro",
             aviso_de_erro.is_visible() and "Não conseguimos carregar" in aviso_de_erro.inner_text())
    conferir("materiais com a API em erro: sem o aviso de lista vazia", aba.locator("[data-sem-materiais]").is_hidden())
    aba.close()
