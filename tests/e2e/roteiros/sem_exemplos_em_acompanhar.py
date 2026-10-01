"""Roteiro: ao atualizar (F5), Acompanhar cadastros nunca mostra os números e as listas de exemplo do protótipo.

O defeito: a página trazia no HTML os números de exemplo ("312 funcionários com
cadastro aprovado", "78%"), as pendências e os envios da Aurora e o nome "Marina Costa" no cabeçalho. A cada
"Atualizar", eles apareciam até o servidor responder e pareciam números aleatórios; com o servidor fora do ar, ficavam.

O que ele confere:
- com as respostas do servidor SEGURADAS: os números esperam com a barra cinza (texto transparente), as listas de
  exemplo não aparecem e o nome de exemplo do cabeçalho também não;
- soltas as respostas: nenhum elemento fica esperando para sempre, e os números são os de verdade;
- com o servidor respondendo erro: um traço ("—") no lugar dos números e o aviso nas listas, nunca um exemplo.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Acompanhar ao atualizar: nenhum número de exemplo (esperando, carregado e com o servidor em erro)"

# Textos que só existem nos exemplos do protótipo (HTML e amostra do acompanhar.js)
TEXTOS_DE_EXEMPLO = ["Rafael Moreira Lima", "+22 em setembro", "243 de 312", "Retorno em até 1 dia útil",
                     "26 funcionários · enviado por Marina Costa"]

# As rotas da API que a tela chama ao abrir (seguradas ou respondidas com erro)
ROTAS_DA_TELA = ["**/api/empresa/**", "**/api/cabecalho"]

# O script que conta os elementos que ainda esperam o dado (devem ser zero depois da carga)
CONTAR_OS_QUE_ESPERAM = ("() => document.querySelectorAll('[data-aguarda-dado]:not([data-dado-pronto]), "
                         "[data-aguarda-bloco]:not([data-dado-pronto]), .usuario-logado:not([data-dado-pronto])').length")


def preparar() -> dict:
    """A mesma preparação do roteiro acompanhar: carga inicial cadastrada e a inclusão pronta para o banco."""
    from tests.e2e.roteiros.acompanhar import preparar as preparar_acompanhar
    return preparar_acompanhar()


def cor_do_texto(aba, seletor: str) -> str:
    """A cor com que o texto do elemento está sendo desenhado. Ex.: "rgba(0, 0, 0, 0)" = transparente."""
    return aba.evaluate("(seletor) => getComputedStyle(document.querySelector(seletor)).color", seletor)


# O script que junta só o texto que uma pessoa consegue LER: pula o que está escondido e o texto transparente (a barra
# cinza de "carregando" tem o texto transparente, mas ele continua na página)
TEXTO_LEGIVEL = """() => {
  let texto_legivel = "";
  const caminhante = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let pedaco = caminhante.nextNode();
  while (pedaco) {
    const elemento = pedaco.parentElement;
    const estilo = getComputedStyle(elemento);
    const escondido = elemento.getClientRects().length === 0 || estilo.visibility === "hidden";
    const transparente = estilo.color === "rgba(0, 0, 0, 0)";
    if (!escondido && !transparente) {
      texto_legivel = texto_legivel + pedaco.textContent + " ";
    }
    pedaco = caminhante.nextNode();
  }
  return texto_legivel.replace(/\\s+/g, " ");
}"""


def exemplos_a_mostra(aba) -> list[str]:
    """Os textos de exemplo que uma pessoa consegue ler na página agora (sem o escondido e sem o transparente)."""
    texto_da_pagina = aba.evaluate(TEXTO_LEGIVEL)
    encontrados = []
    for texto_de_exemplo in TEXTOS_DE_EXEMPLO:
        if texto_de_exemplo in texto_da_pagina:
            encontrados.append(texto_de_exemplo)
    return encontrados


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre Acompanhar três vezes: com o servidor segurado, respondendo e respondendo erro."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # 1. Respostas seguradas: a tela abre e espera, sem mostrar exemplo nenhum
    respostas_seguradas = []
    segurando = {"ligado": True}

    def segurar_ou_deixar_passar(pedido):
        """Enquanto segura, guarda o pedido sem responder; depois, deixa passar direto."""
        if segurando["ligado"]:
            respostas_seguradas.append(pedido)
        else:
            pedido.continue_()

    for rota in ROTAS_DA_TELA:
        aba.route(rota, segurar_ou_deixar_passar)
    aba.goto(endereco + "/acompanhar.html")
    aba.wait_for_function("() => document.documentElement.classList.contains('aguardando-dados')", timeout=10000)
    aba.wait_for_timeout(800)
    conferir(f"esperando: nenhum texto de exemplo à mostra (achados: {exemplos_a_mostra(aba)})",
             exemplos_a_mostra(aba) == [])
    transparentes = []
    for seletor in ["[data-resumo-aprovados]", "[data-resumo-andamento-valor]", "[data-total-pendencias]",
                    "[data-resumo-contas-valor]", ".nome-usuario"]:
        transparentes.append(cor_do_texto(aba, seletor) == "rgba(0, 0, 0, 0)")
    conferir("esperando: os 4 números e o nome do cabeçalho são barras cinza (texto transparente)", all(transparentes))
    aba.locator(".grade-numeros").screenshot(path="storage/painel/numeros_esperando.png")
    # Solta as respostas: os dados de verdade entram e nada fica esperando
    segurando["ligado"] = False
    for pedido_segurado in respostas_seguradas:
        pedido_segurado.continue_()
    aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    conferir("carregado: nenhum elemento ficou esperando", True)
    conferir(f"carregado: nenhum texto de exemplo (achados: {exemplos_a_mostra(aba)})", exemplos_a_mostra(aba) == [])
    conferir(f"carregado: o cabeçalho mostra quem entrou ({aba.inner_text('.nome-usuario')})",
             aba.inner_text(".nome-usuario") == LOGIN_DA_EMPRESA)
    conferir(f"carregado: o 1º cartão tem o número de verdade ({aba.inner_text('[data-resumo-aprovados]')})",
             aba.inner_text("[data-resumo-aprovados]").strip() not in ("312", "—"))
    # 2. Servidor respondendo erro: traço nos números e aviso nas listas, nunca um exemplo
    for rota in ROTAS_DA_TELA:
        aba.unroute(rota)
    for rota in ROTAS_DA_TELA:
        aba.route(rota, lambda pedido: pedido.fulfill(status=500, body="{}", content_type="application/json"))
    aba.goto(endereco + "/acompanhar.html")
    aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    conferir(f"com erro: nenhum texto de exemplo (achados: {exemplos_a_mostra(aba)})", exemplos_a_mostra(aba) == [])
    conferir("com erro: traço nos números do alto",
             aba.inner_text("[data-resumo-aprovados]").strip() == "—"
             and aba.inner_text("[data-total-pendencias]").strip() == "—")
    conferir("com erro: as listas avisam que não carregaram",
             "Não foi possível carregar agora" in aba.inner_text("[data-lista-pendencias]")
             and "Não foi possível carregar agora" in aba.inner_text("[data-lista-envios]"))
    conferir("com erro: o cabeçalho fica com um traço, sem o nome de exemplo", aba.inner_text(".nome-usuario") == "—")
    for rota in ROTAS_DA_TELA:
        aba.unroute(rota)
    aba.close()
