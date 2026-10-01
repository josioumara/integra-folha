"""Roteiro: ao atualizar (F5), nenhuma tela do Portal Interno mostra os números e as listas de exemplo do protótipo.

O defeito: ao recarregar uma tela do banco, os números grandes mostravam por um instante valores que pareciam
aleatórios. As telas do banco (front/banco_*.html) nasceram do protótipo e trazem no HTML números e listas de
exemplo ("3 envios esperando", "69%", "Carteira Sul e Sudeste · 6 empresas", o nome "Rafael Lima"...). A cada
"Atualizar", eles apareciam até a API responder; se a API falhava, ficavam. O mesmo mecanismo do Portal da empresa
(js/carregando_dados.js) agora vale em todas as telas do banco (as 5 abas do menu e as telas do Sistema: os
Parâmetros do layout e o Acompanhamento dos agentes). O Simulador de Rentabilidade e as Premissas financeiras ficam
ocultos nesta versão (ADR-148) e saíram da lista: o simulador fica numa caixa <template> (o navegador não desenha o que
está dentro), e o endereço das Premissas leva aos Indicadores.

O que ele confere, em cada tela do Portal Interno:
- com TODAS as respostas da API seguradas: a página tem a marca "aguardando-dados", há elementos marcados esperando
  a API, nenhum número que espera está à mostra (texto transparente) e nenhum texto de exemplo pode ser lido;
- soltas as respostas: nenhum elemento fica esperando para sempre e nenhum texto de exemplo aparece;
- com a API respondendo erro (500): nada fica esperando, nenhum exemplo aparece e a página não tem erro de
  JavaScript (o rodar.py reprova qualquer erro).

Para rodar só algumas telas (útil enquanto se mexe numa delas), a variável SEM_EXEMPLOS_TELAS recebe os nomes
separados por vírgula. Ex.: SEM_EXEMPLOS_TELAS=banco_inicio.html,banco_envios.html
"""
import os

from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Portal Interno ao atualizar: nenhum número de exemplo nas telas e guias (esperando, carregado e com a "
             "API em erro)")

# As rotas da API que as telas chamam (seguradas ou respondidas com erro): todas, para nenhuma escapar
ROTAS_DA_API = "**/api/**"

# Textos de exemplo do cabeçalho, iguais em todas as telas (nome, papel e a faixa escura da carteira)
TEXTOS_DE_EXEMPLO_DO_CABECALHO = ["Rafael Lima", "Especialista Folha · Santander", "Carteira Sul e Sudeste"]

# Cada tela do Portal Interno e os textos de exemplo dela que nunca podem ser lidos com a tela ligada ao servidor
# (trechos curtos e únicos do exemplo; nomes de empresas ficam de fora, porque a base de teste tem as mesmas)
TEXTOS_DE_EXEMPLO_POR_TELA = {
    "banco_inicio.html": [
        "Bom dia, Rafael",
        "Sexta-feira, 25 de setembro",
        "7 itens esperando você",
        "(260 funcionários)",
        "A mais antiga: ontem, 17h40",
        "55 dias",
        "dos 1.840 funcionários aprovados",
        "+38 desde o último arquivo",
        "enviada em 23/09",
        "Funcionária afastada entra no arquivo de inclusão?",
        "Último arquivo: sexta, 18/09",
        "do último arquivo, de 18/09",
    ],
    # Empresas: o que se vê ao abrir são nomes e CNPJs que também existem na base de teste; a prova é a contagem
    "banco_empresas.html": ["Marina Costa", "marina.costa@aurora.com.br", "Hoje, 08h12", "243 (78%)"],
    "banco_envios.html": ["por Cláudia Ramos", "Planilha com 205 funcionários", "reconheceu 41 dos 44 campos",
                          "Prazo: segunda, 28/09", "por Jonas Pereira", "311 valores padronizados"],
    # Indicadores: só o painel, sem guias (o Simulador de Rentabilidade está oculto, ADR-148). O painel junta o que eram
    # as sub-abas Planejamento e Uso das empresas; a guia do Consultor saiu (ADR-144). A Conversa e as Contas abertas
    # agora são abas da ficha da empresa (o roteiro delas confere a ficha)
    "banco_indicadores.html?aba=painel": ["Neste rascunho, só os filtros de empresa e região mudam os números",
                                          "Setembro de 2026",
                                          "empresas entraram nos últimos 7 dias", "envios feitos ao banco no mês",
                                          "dia útil, em média, do envio à avaliação do banco",
                                          "Acessos e envios em setembro",
                                          "9 vezes alguém abriu a tela e saiu sem mandar arquivo", "Hoje, 08h12"],
    # Sistema (Parâmetros): o único exemplo é a versão "v1", que é também a versão real num banco novo; a prova é a
    # contagem
    "banco_parametros.html": [],
    # Sistema (Acompanhamento dos agentes): os cartões de exemplo dos agentes e as execuções de exemplo (que eram
    # da antiga sub-aba "Desempenho da IA" de Indicadores)
    "banco_agentes.html": ["Exemplo de como a tela mostra cada agente", "25/09/2026, 10:12", "24/09/2026, 16:40",
                           "US$ 0,0312", "Exemplo de como a aba mostra cada execução",
                           "Reaproveitou o mapeamento aprovado (sem chamar o modelo)",
                           "2 alertas de renda fora do padrão do cargo", "Hoje, 07h52"],
    # Endomarketing: a tela não traz exemplo, só a lista de empresas que espera a API
    "banco_endomarketing.html": [],
}

# O script que conta os elementos que ainda esperam o dado (devem ser zero depois da carga ou da falha)
CONTAR_OS_QUE_ESPERAM = ("() => document.querySelectorAll('[data-aguarda-dado]:not([data-dado-pronto]), "
                         "[data-aguarda-bloco]:not([data-dado-pronto]), .usuario-logado:not([data-dado-pronto])').length")

# O script que junta só o texto que uma pessoa consegue LER: pula o que está escondido e o texto transparente (a barra
# cinza de "carregando" tem o texto transparente, mas ele continua na página). O mesmo de sem_exemplos_em_acompanhar.
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

# O script que descreve a espera: a marca na página, quantos elementos marcados, quantos prontos e quantos números
# marcados estão com o texto à mostra (cor diferente de transparente)
SITUACAO_DA_ESPERA = """() => {
  const marca_na_pagina = document.documentElement.classList.contains("aguardando-dados");
  const marcados = document.querySelectorAll("[data-aguarda-dado], [data-aguarda-bloco]");
  let prontos = 0;
  let numeros_a_mostra = 0;
  for (const elemento of marcados) {
    if (elemento.hasAttribute("data-dado-pronto")) {
      prontos = prontos + 1;
    }
    const e_numero = elemento.hasAttribute("data-aguarda-dado");
    const esperando = !elemento.hasAttribute("data-dado-pronto");
    const visivel = elemento.getClientRects().length > 0;
    if (e_numero && esperando && visivel && getComputedStyle(elemento).color !== "rgba(0, 0, 0, 0)") {
      numeros_a_mostra = numeros_a_mostra + 1;
    }
  }
  return {marca_na_pagina: marca_na_pagina, marcados: marcados.length, prontos: prontos,
          numeros_a_mostra: numeros_a_mostra};
}"""


def preparar() -> dict:
    """Só os usuários de teste: as empresas da carteira entram sozinhas no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    # Abre o banco temporário e cadastra o RH da Aurora e o especialista do banco
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def telas_escolhidas() -> list[str]:
    """As telas a percorrer: todas, ou só as da variável SEM_EXEMPLOS_TELAS (nomes separados por vírgula)."""
    escolha = os.environ.get("SEM_EXEMPLOS_TELAS", "").strip()
    # Sem escolha: todas as telas
    if not escolha:
        return list(TEXTOS_DE_EXEMPLO_POR_TELA.keys())
    # Com escolha: só as telas pedidas (ex.: "banco_inicio.html")
    telas = []
    # Cada nome da lista, sem espaços em volta
    for nome in escolha.split(","):
        if nome.strip():
            telas.append(nome.strip())
    return telas


def exemplos_a_mostra(aba, textos_de_exemplo: list[str]) -> list[str]:
    """Os textos de exemplo que uma pessoa consegue ler na página agora (sem o escondido e sem o transparente)."""
    texto_da_pagina = aba.evaluate(TEXTO_LEGIVEL)
    encontrados = []
    # Confere um por um os textos de exemplo da tela
    for texto_de_exemplo in textos_de_exemplo:
        if texto_de_exemplo in texto_da_pagina:
            encontrados.append(texto_de_exemplo)
    return encontrados


def conferir_a_espera_e_a_carga(aba, endereco: str, pagina: str, textos: list[str], conferir) -> None:
    """Partes 1 e 2: segura todas as respostas da API, confere que nada de exemplo aparece, solta e confere o fim."""
    # Os pedidos à API que chegarem ficam guardados aqui, sem resposta, até o roteiro soltar
    pedidos_segurados = []
    segurando = {"ligado": True}

    def segurar_ou_deixar_passar(pedido):
        """Enquanto segura, guarda o pedido sem responder; depois, deixa passar direto."""
        if segurando["ligado"]:
            pedidos_segurados.append(pedido)
        else:
            pedido.continue_()

    aba.route(ROTAS_DA_API, segurar_ou_deixar_passar)
    aba.goto(endereco + "/" + pagina)
    aba.wait_for_function("() => document.documentElement.classList.contains('aguardando-dados')", timeout=10000)
    # Um tempo com as respostas seguradas: é quando os exemplos apareciam antes da correção
    aba.wait_for_timeout(1000)
    situacao = aba.evaluate(SITUACAO_DA_ESPERA)
    conferir(f"{pagina} esperando: a página tem a marca 'aguardando-dados'", situacao["marca_na_pagina"])
    # Pronto antes da API só o que não depende dela (ex.: a saudação do Início, que vem da hora do dia)
    conferir(f"{pagina} esperando: {situacao['marcados']} elementos de exemplo marcados, "
             f"{situacao['marcados'] - situacao['prontos']} esperando a API",
             situacao["marcados"] > 0 and situacao["prontos"] < situacao["marcados"])
    conferir(f"{pagina} esperando: nenhum número de exemplo à mostra (à mostra: {situacao['numeros_a_mostra']})",
             situacao["numeros_a_mostra"] == 0)
    achados = exemplos_a_mostra(aba, textos)
    conferir(f"{pagina} esperando: nenhum texto de exemplo à mostra (achados: {achados})", achados == [])
    # Solta as respostas: os dados de verdade entram e nada fica esperando
    segurando["ligado"] = False
    for pedido_segurado in pedidos_segurados:
        pedido_segurado.continue_()
    aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    conferir(f"{pagina} carregada: nenhum elemento ficou esperando", True)
    achados = exemplos_a_mostra(aba, textos)
    conferir(f"{pagina} carregada: nenhum texto de exemplo (achados: {achados})", achados == [])
    conferir(f"{pagina} carregada: o cabeçalho mostra quem entrou ({aba.inner_text('.nome-usuario')})",
             aba.inner_text(".nome-usuario").strip() == LOGIN_DO_BANCO)
    aba.unroute(ROTAS_DA_API)


def conferir_a_falha(aba, endereco: str, pagina: str, textos: list[str], conferir) -> None:
    """Parte 3: toda a API responde erro (500); nada fica esperando e nenhum exemplo aparece."""

    def responder_com_erro(pedido):
        """Responde o pedido com erro 500, como um servidor com defeito."""
        pedido.fulfill(status=500, body="{}", content_type="application/json")

    aba.route(ROTAS_DA_API, responder_com_erro)
    aba.goto(endereco + "/" + pagina)
    aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    conferir(f"{pagina} com a API em erro: nenhum elemento ficou esperando", True)
    # Uns instantes a mais: um script atrasado não pode trazer o exemplo de volta
    aba.wait_for_timeout(500)
    achados = exemplos_a_mostra(aba, textos)
    conferir(f"{pagina} com a API em erro: nenhum texto de exemplo (achados: {achados})", achados == [])
    conferir(f"{pagina} com a API em erro: o cabeçalho fica com um traço, sem o nome de exemplo",
             aba.inner_text(".nome-usuario").strip() == "—")
    aba.unroute(ROTAS_DA_API)


def conferir_o_inicio(aba, endereco: str, conferir) -> None:
    """O Início (a tela do defeito): os quatro números do alto são os de verdade e, com a API em erro, um traço."""
    aba.goto(endereco + "/banco_inicio.html")
    aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    valores = aba.locator(".grade-numeros .cartao-numero-valor").all_inner_texts()
    # O Início de um banco de teste novo: nenhum envio esperando, e as 6 empresas sem carga
    conferir(f"Início carregado: os 4 números do alto são os de verdade (na tela: {valores})",
             valores[0].strip() == "0" and valores[2].strip() == "6" and "69%" not in valores[3])
    faixa = aba.inner_text("[data-faixa-carteira]").strip()
    conferir(f"Início carregado: a faixa mostra a carteira de verdade (na tela: {faixa})",
             faixa == "Sua carteira · 6 empresas")

    def responder_com_erro(pedido):
        """Responde o pedido com erro 500, como um servidor com defeito."""
        pedido.fulfill(status=500, body="{}", content_type="application/json")

    aba.route(ROTAS_DA_API, responder_com_erro)
    aba.goto(endereco + "/banco_inicio.html")
    aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    valores = aba.locator(".grade-numeros .cartao-numero-valor").all_inner_texts()
    # Os quatro valores sem espaços em volta
    valores_limpos = []
    for valor in valores:
        valores_limpos.append(valor.strip())
    conferir(f"Início com a API em erro: os 4 números do alto mostram '—' (na tela: {valores_limpos})",
             valores_limpos == ["—", "—", "—", "—"])
    fila = aba.inner_text("[data-fila-do-dia]")
    conferir("Início com a API em erro: a fila diz que não foi possível carregar",
             "Não foi possível carregar agora" in fila)
    aba.unroute(ROTAS_DA_API)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre cada tela do Portal Interno três vezes: com a API segurada, respondendo e respondendo erro."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    # Cada tela escolhida, com os textos de exemplo dela e os do cabeçalho
    for pagina in telas_escolhidas():
        textos = TEXTOS_DE_EXEMPLO_DO_CABECALHO + TEXTOS_DE_EXEMPLO_POR_TELA[pagina]
        conferir_a_espera_e_a_carga(aba, endereco, pagina, textos, conferir)
        conferir_a_falha(aba, endereco, pagina, textos, conferir)
    # O Início, a tela do defeito, com os números conferidos um por um
    if "banco_inicio.html" in telas_escolhidas():
        conferir_o_inicio(aba, endereco, conferir)
    aba.close()
