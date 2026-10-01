"""Roteiro: o menu do Portal Interno, o menu da engrenagem "Sistema" e a aba Indicadores sem guias (ADR-148: a
engrenagem se chama "Sistema", e as Premissas e o Simulador de Rentabilidade ficam ocultos).

O que ele confere, no Chrome de verdade:
- em cada tela do banco, o menu tem exatamente Início, Empresas, Envios, Endomarketing e Indicadores, nessa ordem, e
  a aba marcada é a da própria tela (nas telas do Sistema, nenhuma);
- nenhuma tela tem link para as telas que saíram (Mensagens, Contas abertas, Telemetria e Planejamento), para as que
  estão ocultas (Premissas financeiras e o Simulador de Rentabilidade) nem para os endereços antigos de Indicadores
  (?aba=planejamento, ?aba=uso, ?aba=ia, ?aba=consultor e #consultor);
- a engrenagem "Sistema" fica no alto, antes do nome de quem entrou, com o desenho da engrenagem à vista, e é um botão
  (aria-expanded, aria-controls) que abre um menu com "Parâmetros do layout", "Acompanhamento dos agentes" e "Teto de
  custo com agentes", nessa ordem; Esc e o clique fora fecham; as setas andam entre os itens à vista (o item oculto não
  recebe o foco); cada item leva à sua tela, onde o botão fica marcado e o item leva aria-current="page";
- o nome "Sistema" também nos títulos: o título dos Parâmetros do layout e o sobretítulo do Acompanhamento dos agentes
  e do Teto de gasto da IA ("Sistema › Acompanhamento dos agentes");
- quem abre o endereço das Premissas financeiras (a tela oculta) volta para os Indicadores;
- a aba Indicadores mostra só o Painel de acompanhamento, sem guias: sem ?aba, com ?aba=painel e com ?aba=simulador (a
  guia oculta) abre o painel, e o simulador não está na página;
- o Início não tem mais o botão "Perguntar ao Consultor" (o Consultor saiu do sistema, ADR-144), e o endereço dele
  (?aba=consultor) abre o painel.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Menu do Portal Interno: 5 abas na ordem, o menu da engrenagem Sistema (3 telas; as Premissas ocultas) e "
             "Indicadores sem guias")

# As abas do menu, na ordem fixa (ADR-122)
ABAS_DO_MENU = ["Início", "Empresas", "Envios", "Endomarketing", "Indicadores"]

# Cada tela do banco e a aba do menu que fica marcada nela (as telas do Sistema não marcam nenhuma aba: marcam a
# engrenagem). As Premissas financeiras não entram: a tela está oculta (ADR-148) e o endereço leva aos Indicadores
ABA_MARCADA_POR_TELA = {
    "banco_inicio.html": "Início",
    "banco_empresas.html": "Empresas",
    "banco_envios.html": "Envios",
    "banco_endomarketing.html": "Endomarketing",
    "banco_indicadores.html": "Indicadores",
    "banco_parametros.html": None,
    "banco_agentes.html": None,
    "banco_teto_da_ia.html": None,
}

# Os itens do menu da engrenagem, na ordem, e a tela de cada um (as Premissas financeiras estão ocultas, ADR-148)
ITENS_DO_SISTEMA = {
    "Parâmetros do layout": "banco_parametros.html",
    "Acompanhamento dos agentes": "banco_agentes.html",
    "Teto de custo com agentes": "banco_teto_da_ia.html",
}

# O título (h1) de cada tela do Sistema (nos Parâmetros, o título é o nome do menu; ADR-148)
TITULO_DA_TELA_DO_SISTEMA = {
    "banco_parametros.html": "Sistema",
    "banco_agentes.html": "Acompanhamento dos agentes",
    "banco_teto_da_ia.html": "Teto de custo com agentes",
}

# O sobretítulo (o texto pequeno acima do título) das telas que ficam dentro do Sistema
SOBRETITULO_POR_TELA = {
    "banco_agentes.html": "Sistema",
    "banco_teto_da_ia.html": "Sistema › Acompanhamento dos agentes",
}

# O nome da engrenagem: o texto ao lado do desenho e o que o leitor de tela lê
NOME_DA_ENGRENAGEM = "Sistema"

# As telas que saíram do menu, as ocultas e os endereços antigos de Indicadores: nenhum link pode apontar para eles
LINKS_PARA_O_QUE_SAIU = ("a[href*='banco_mensagens'], a[href*='banco_contas'], "
                         "a[href*='banco_telemetria'], a[href*='banco_planejamento'], "
                         "a[href*='banco_premissas'], a[href*='aba=simulador'], "
                         "a[href*='aba=planejamento'], a[href*='aba=uso'], a[href*='aba=ia'], "
                         "a[href*='aba=consultor'], a[href*='#consultor']")

# Os endereços de Indicadores que abrem o painel: sem ?aba, o do painel e o da guia oculta do simulador (ADR-148)
ENDERECOS_QUE_ABREM_O_PAINEL = ["banco_indicadores.html", "banco_indicadores.html?aba=painel",
                                "banco_indicadores.html?aba=simulador"]

# Os seletores do menu da engrenagem
BOTAO_DA_ENGRENAGEM = ".acoes-usuario [data-botao-configuracao]"
LISTA_DA_ENGRENAGEM = "[data-itens-configuracao]"

# O script que lê as abas do menu, na ordem: o nome (só o texto da própria aba, sem o número do contador, ex.:
# "Envios") e se ela está marcada como a aba da tela aberta
ABAS_DA_TELA = """() => {
  const abas = [];
  for (const aba of document.querySelectorAll(".abas-banco .aba")) {
    let nome = "";
    for (const pedaco of aba.childNodes) {
      if (pedaco.nodeType === Node.TEXT_NODE) {
        nome = nome + pedaco.textContent;
      }
    }
    abas.push({nome: nome.trim(), marcada: aba.classList.contains("aba-ativa")});
  }
  return abas;
}"""

# O script que diz se a engrenagem vem antes do nome de quem entrou, dentro das ações do alto
ENGRENAGEM_ANTES_DO_USUARIO = """() => {
  const engrenagem = document.querySelector(".acoes-usuario .botao-configuracao");
  const usuario = document.querySelector(".acoes-usuario .usuario-logado");
  if (!engrenagem || !usuario) {
    return false;
  }
  return Boolean(engrenagem.compareDocumentPosition(usuario) & Node.DOCUMENT_POSITION_FOLLOWING);
}"""

# O script que confere o botão da engrenagem: é um <button>, fechado, e aria-controls aponta para a lista do menu
BOTAO_DA_ENGRENAGEM_CERTO = """() => {
  const botao = document.querySelector(".acoes-usuario [data-botao-configuracao]");
  if (!botao) {
    return false;
  }
  const lista = document.getElementById(botao.getAttribute("aria-controls"));
  return botao.tagName === "BUTTON" && botao.getAttribute("aria-expanded") === "false" && lista !== null
    && lista.hasAttribute("data-itens-configuracao") && lista.hidden;
}"""

# O script que confere o desenho da engrenagem no botão: o ícone aponta para o desenho guardado na página e aparece
# (tem largura e altura na tela)
DESENHO_DA_ENGRENAGEM_A_VISTA = """() => {
  const icone = document.querySelector(".acoes-usuario [data-botao-configuracao] svg");
  const uso = icone ? icone.querySelector("use") : null;
  if (!uso || !document.querySelector(uso.getAttribute("href"))) {
    return false;
  }
  const tamanho = icone.getBoundingClientRect();
  return tamanho.width > 0 && tamanho.height > 0;
}"""

# O script que diz o texto do elemento que está com o foco agora
TEXTO_DO_FOCO = "() => document.activeElement ? document.activeElement.textContent.trim() : ''"


def preparar() -> dict:
    """Só os usuários de teste: as empresas da carteira entram sozinhas no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    # Abre o banco temporário e cadastra o RH da Aurora e o especialista do banco
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def ler_o_menu(aba) -> tuple[list[str], list[str]]:
    """Os nomes das abas do menu da tela aberta, na ordem, e os nomes das abas marcadas (o esperado é uma ou nenhuma).

    Exemplo, no Início: (["Início", "Empresas", "Envios", "Endomarketing", "Indicadores"], ["Início"]).
    """
    nomes = []
    marcadas = []
    # Cada aba do menu, na ordem da tela
    for aba_do_menu in aba.evaluate(ABAS_DA_TELA):
        nomes.append(aba_do_menu["nome"])
        if aba_do_menu["marcada"]:
            marcadas.append(aba_do_menu["nome"])
    return nomes, marcadas


def conferir_o_menu_de_cada_tela(aba, endereco: str, conferir) -> None:
    """Parte 1: em cada tela, as 5 abas na ordem, a aba certa marcada, a engrenagem "Sistema" no alto e nada do que
    saiu ou está oculto."""
    for tela, aba_esperada in ABA_MARCADA_POR_TELA.items():
        aba.goto(endereco + "/" + tela)
        aba.wait_for_load_state("networkidle")
        nomes, marcadas = ler_o_menu(aba)
        conferir(f"{tela}: o menu é {ABAS_DO_MENU} (na tela: {nomes})", nomes == ABAS_DO_MENU)
        # Nas telas do Sistema, nenhuma aba marcada; nas outras, só a da própria tela
        marcadas_esperadas = []
        if aba_esperada is not None:
            marcadas_esperadas.append(aba_esperada)
        conferir(f"{tela}: aba marcada {marcadas_esperadas} (na tela: {marcadas})", marcadas == marcadas_esperadas)
        texto_do_botao = aba.inner_text(BOTAO_DA_ENGRENAGEM).strip()
        conferir(f"{tela}: a engrenagem '{NOME_DA_ENGRENAGEM}' está no alto, antes do nome de quem entrou, com o desenho "
                 f"da engrenagem (texto: {texto_do_botao})",
                 aba.evaluate(ENGRENAGEM_ANTES_DO_USUARIO)
                 and aba.get_attribute(BOTAO_DA_ENGRENAGEM, "aria-label") == NOME_DA_ENGRENAGEM
                 and texto_do_botao == NOME_DA_ENGRENAGEM and aba.evaluate(DESENHO_DA_ENGRENAGEM_A_VISTA))
        conferir(f"{tela}: a engrenagem é um botão fechado, com aria-expanded e aria-controls apontando para o menu",
                 aba.evaluate(BOTAO_DA_ENGRENAGEM_CERTO))
        conferir(f"{tela}: nenhum link para as telas que saíram, para as ocultas nem para os endereços antigos",
                 aba.locator(LINKS_PARA_O_QUE_SAIU).count() == 0)


def itens_do_menu_aberto(aba) -> list[str]:
    """Os textos dos itens do menu da engrenagem, na ordem (só quando o menu está à vista)."""
    textos = []
    # Cada item do menu, na ordem da tela
    for texto in aba.locator(LISTA_DA_ENGRENAGEM + " a").all_inner_texts():
        textos.append(texto.strip())
    return textos


def conferir_abrir_e_fechar(aba, endereco: str, conferir) -> None:
    """Parte 2: no Início, o clique abre o menu com os 3 itens; Esc fecha; o clique fora fecha; as setas andam."""
    aba.goto(endereco + "/banco_inicio.html")
    aba.wait_for_load_state("networkidle")
    # O clique abre
    aba.click(BOTAO_DA_ENGRENAGEM)
    conferir("o clique na engrenagem abre o menu (aria-expanded='true')",
             aba.locator(LISTA_DA_ENGRENAGEM).is_visible()
             and aba.get_attribute(BOTAO_DA_ENGRENAGEM, "aria-expanded") == "true")
    itens = itens_do_menu_aberto(aba)
    conferir(f"o menu tem os 3 itens na ordem, sem as Premissas financeiras (na tela: {itens})",
             itens == list(ITENS_DO_SISTEMA.keys()))
    # Esc fecha e devolve o foco ao botão
    aba.keyboard.press("Escape")
    conferir("Esc fecha o menu e o foco volta ao botão",
             not aba.locator(LISTA_DA_ENGRENAGEM).is_visible()
             and aba.get_attribute(BOTAO_DA_ENGRENAGEM, "aria-expanded") == "false"
             and aba.evaluate(TEXTO_DO_FOCO) == NOME_DA_ENGRENAGEM)
    # O clique fora fecha (no aviso da faixa escura, no alto à esquerda, longe da lista aberta)
    aba.click(BOTAO_DA_ENGRENAGEM)
    aba.click(".faixa-interna-linha > span:first-child")
    conferir("o clique fora do menu fecha o menu", not aba.locator(LISTA_DA_ENGRENAGEM).is_visible())
    # Pelo teclado: com o foco no botão, a seta para baixo abre e vai ao 1º item; de novo, ao 2º e ao 3º; de novo,
    # volta ao 1º (o item oculto das Premissas nunca recebe o foco)
    aba.focus(BOTAO_DA_ENGRENAGEM)
    aba.keyboard.press("ArrowDown")
    primeiro = aba.evaluate(TEXTO_DO_FOCO)
    aba.keyboard.press("ArrowDown")
    segundo = aba.evaluate(TEXTO_DO_FOCO)
    aba.keyboard.press("ArrowDown")
    terceiro = aba.evaluate(TEXTO_DO_FOCO)
    aba.keyboard.press("ArrowDown")
    de_volta = aba.evaluate(TEXTO_DO_FOCO)
    conferir(f"as setas andam entre os 3 itens e dão a volta (foco: {primeiro} → {segundo} → {terceiro} → {de_volta})",
             primeiro == "Parâmetros do layout" and segundo == "Acompanhamento dos agentes"
             and terceiro == "Teto de custo com agentes" and de_volta == "Parâmetros do layout")
    aba.keyboard.press("Escape")


def conferir_cada_item(aba, endereco: str, conferir) -> None:
    """Parte 3: cada item do menu, clicado no Início, leva à sua tela; lá o botão fica marcado e o item também."""
    for texto_do_item, tela in ITENS_DO_SISTEMA.items():
        aba.goto(endereco + "/banco_inicio.html")
        aba.click(BOTAO_DA_ENGRENAGEM)
        aba.click(LISTA_DA_ENGRENAGEM + f" a:has-text('{texto_do_item}')")
        aba.wait_for_url("**/" + tela, timeout=10000)
        aba.wait_for_load_state("networkidle")
        titulo = aba.inner_text("h1.titulo-pagina").strip()
        conferir(f"'{texto_do_item}' leva a {tela}, com o título '{TITULO_DA_TELA_DO_SISTEMA[tela]}'",
                 titulo.startswith(TITULO_DA_TELA_DO_SISTEMA[tela]))
        classes_do_botao = aba.get_attribute(BOTAO_DA_ENGRENAGEM, "class")
        conferir(f"{tela}: o botão da engrenagem fica marcado",
                 "botao-configuracao-marcado" in classes_do_botao.split())
        item_atual = aba.locator(LISTA_DA_ENGRENAGEM + " a[aria-current='page']")
        conferir(f"{tela}: só o item '{texto_do_item}' leva aria-current='page'",
                 item_atual.count() == 1 and item_atual.get_attribute("href") == tela)


def conferir_os_sobretitulos_do_sistema(aba, endereco: str, conferir) -> None:
    """Parte 3b: nas telas que ficam dentro do Sistema, o sobretítulo diz "Sistema" (o antigo "Configuração")."""
    for tela, esperado in SOBRETITULO_POR_TELA.items():
        aba.goto(endereco + "/" + tela)
        aba.wait_for_load_state("networkidle")
        # text_content: o texto como está no HTML (o CSS mostra o sobretítulo em letras maiúsculas)
        sobretitulo = aba.locator(".cabecalho-pagina .sobretitulo").first.text_content().strip()
        conferir(f"{tela}: o sobretítulo é '{esperado}' (na tela: {sobretitulo})", sobretitulo == esperado)


def conferir_a_tela_oculta_das_premissas(aba, endereco: str, conferir) -> None:
    """Parte 4: o endereço das Premissas financeiras (a tela oculta, ADR-148) leva aos Indicadores."""
    aba.goto(endereco + "/banco_premissas.html")
    aba.wait_for_load_state("networkidle")
    titulo = aba.inner_text("h1.titulo-pagina").strip()
    conferir(f"o endereço das Premissas financeiras (oculta) leva aos Indicadores (endereço: {aba.url})",
             aba.url.endswith("/banco_indicadores.html") and titulo.startswith("Indicadores"))


def conferir_indicadores_sem_guias(aba, endereco: str, conferir) -> None:
    """Parte 5: a aba Indicadores mostra só o painel, sem guias, por qualquer endereço (inclusive o do simulador)."""
    for endereco_da_tela in ENDERECOS_QUE_ABREM_O_PAINEL:
        aba.goto(endereco + "/" + endereco_da_tela)
        aba.wait_for_load_state("networkidle")
        conferir(f"{endereco_da_tela}: o Painel de acompanhamento à vista, sem guias e sem o simulador na página",
                 aba.locator("[data-conteudo-indicadores='painel']").is_visible()
                 and aba.locator("[data-aba-indicadores]").count() == 0
                 and aba.locator("[data-conteudo-indicadores='simulador'], #guia-simulador").count() == 0)


def conferir_que_o_botao_do_consultor_saiu(aba, endereco: str, conferir) -> None:
    """Parte 6: o Início não tem mais o botão "Perguntar ao Consultor" (ADR-144), e o endereço dele abre o painel."""
    aba.goto(endereco + "/banco_inicio.html")
    aba.wait_for_load_state("networkidle")
    # Pelo texto exato do botão que saiu e pelo endereço dele
    conferir("o Início não tem o botão 'Perguntar ao Consultor' nem link para a guia que saiu",
             aba.get_by_text("Perguntar ao Consultor").count() == 0
             and aba.locator("a[href*='aba=consultor']").count() == 0)
    # Quem guardou o endereço do botão antigo cai no painel
    aba.goto(endereco + "/banco_indicadores.html?aba=consultor")
    aba.wait_for_load_state("networkidle")
    conferir("o endereço do botão antigo (?aba=consultor) abre o Painel de acompanhamento",
             aba.locator("[data-conteudo-indicadores='painel']").is_visible())


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Entra como especialista do banco e confere o menu, a engrenagem, a tela oculta, os Indicadores sem guias e a
    saída do botão do Consultor."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_o_menu_de_cada_tela(aba, endereco, conferir)
    conferir_abrir_e_fechar(aba, endereco, conferir)
    conferir_cada_item(aba, endereco, conferir)
    conferir_os_sobretitulos_do_sistema(aba, endereco, conferir)
    conferir_a_tela_oculta_das_premissas(aba, endereco, conferir)
    conferir_indicadores_sem_guias(aba, endereco, conferir)
    conferir_que_o_botao_do_consultor_saiu(aba, endereco, conferir)
    aba.close()
