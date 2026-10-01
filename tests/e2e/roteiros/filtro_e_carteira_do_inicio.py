"""Roteiro: o Início do Portal Interno, com o filtro da fila "O que precisa de você" e a carteira que cabe sem rolar
para o lado.

O filtro fica em cima da fila: a empresa ("Todas as empresas" e as que têm item na fila) e o prazo da avaliação do
banco, com os nomes que a fila já mostra ("Dentro do prazo" e "Passou do prazo" de 1 dia útil). Só o envio que espera a
avaliação tem prazo; os outros itens (empresa sem carga, com pendência ou em andamento) aparecem em "Todos".

O que ele confere, no Chrome de verdade:
- com os dados reais de um banco novo (as 6 empresas da carteira, todas sem carga): o filtro aparece, com as 6 empresas
  em ordem alfabética; a empresa escolhida deixa só o item dela; os dois prazos ficam vazios (nenhum envio espera o
  banco), com o aviso e o resumo "Mostrando 0 de 6 itens"; o número de cada botão é o que o clique mostra;
- com a resposta do servidor trocada pelo roteiro (envios dentro e fora do prazo, de empresas diferentes, e duas empresas
  de nome comprido, uma delas sem espaço nenhum): cada prazo mostra só os seus envios, na ordem da fila; a empresa e o
  prazo se combinam; o número de cada botão é o que o clique mostra; com "Todas as empresas" e "Todos", o resumo some;
- a carteira cabe no cartão sem rolar para o lado, e a fila e a página também, nas larguras 1093 (1366 com o zoom de
  125% do Windows), 1280, 1366, 1536 (1920 com 125%) e 1920 px, com os dados reais e com os nomes compridos e números
  grandes;
- a coluna "Envios" em duas linhas ("1234 envios" e "56 em andamento"; "1 envio" e "nenhum em andamento"; "nenhum
  envio" quando a empresa não mandou nada);
- nenhum erro de JavaScript (o rodar.py reprova qualquer um).
"""
import unicodedata

from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Início do banco: o filtro da fila (empresa e prazo) e a carteira sem rolar para o lado, de 1093 a "
             "1920 px")

# As larguras de tela conferidas (em pixels): 1366 e 1920 são as do pedido; 1093 e 1536 são as mesmas telas com o zoom
# de 125% do Windows (comum em notebook); 1280 fica no meio
LARGURAS_DE_TELA = [1093, 1280, 1366, 1536, 1920]
# A altura da janela nas medidas (não muda a largura da carteira)
ALTURA_DA_TELA = 900

# Os nomes compridos que o roteiro põe na carteira (variações escritas aqui; nenhuma vem de arquivo de teste): um com
# espaços, que quebra entre as palavras, e um sem espaço nenhum, que só pode quebrar no meio da palavra
NOME_COMPRIDO_COM_ESPACOS = ("Companhia Metropolitana de Serviços Hospitalares, Logística Integrada e Tecnologia da "
                             "Informação do Nordeste S.A.")
NOME_COMPRIDO_SEM_ESPACO = "ConstrutoraIncorporadoraEAdministradoraDeImoveisHorizonteAzulDoBrasilLtda"

# Os seletores do filtro e da fila
ESCOLHA_DA_EMPRESA = "[data-filtro-fila-empresa]"
BOTAO_DO_PRAZO = "[data-filtro-fila-prazo='{prazo}']"
ITENS_DA_FILA = "[data-fila-do-dia] li.item-fila:not(.item-fila-vazio)"
AVISO_DA_FILA = "[data-fila-do-dia] li.item-fila-vazio"
RESUMO_DA_FILA = "[data-resumo-da-fila]"

# O script que mede a carteira, o cartão da fila e a página: a largura do conteúdo e a largura visível de cada um
# (iguais quando nada rola para o lado)
MEDIDAS_DA_TELA = """() => {
  const caixa_da_carteira = document.querySelector('[data-tabela-carteira]');
  const cartao_da_fila = document.querySelector('[data-fila-do-dia]').closest('.painel-acompanhar');
  return {carteira_conteudo: caixa_da_carteira.scrollWidth, carteira_visivel: caixa_da_carteira.clientWidth,
          fila_conteudo: cartao_da_fila.scrollWidth, fila_visivel: cartao_da_fila.clientWidth,
          pagina_conteudo: document.documentElement.scrollWidth, pagina_visivel: document.documentElement.clientWidth};
}"""

# O script que diz se a fila terminou de carregar (a marca que o js/carregando_dados.js põe quando o dado chega)
FILA_CARREGADA = "() => document.querySelector('[data-fila-do-dia]').hasAttribute('data-dado-pronto')"


def preparar() -> dict:
    """Só os usuários de teste: as 6 empresas da carteira entram sozinhas no banco novo, todas sem carga."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    # Abre o banco temporário e cadastra o RH da Aurora e o especialista do banco
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def chave_de_ordem(nome: str) -> str:
    """O nome sem acentos e em minúsculas, para conferir a ordem alfabética como uma pessoa lê ("Á" junto do "A").

    Exemplo: "Atlântico Saúde" → "atlantico saude".
    """
    # NFD separa a letra do acento ("â" vira "a" + "^"); os acentos (marcas "Mn") ficam de fora
    letras = []
    for caractere in unicodedata.normalize("NFD", nome):
        if unicodedata.category(caractere) != "Mn":
            letras.append(caractere)
    return "".join(letras).lower()


def abrir_o_inicio(aba, endereco: str) -> None:
    """Abre o Início na largura comum de notebook e espera a fila chegar do servidor."""
    aba.set_viewport_size({"width": 1366, "height": ALTURA_DA_TELA})
    aba.goto(endereco + "/banco_inicio.html")
    aba.wait_for_function(FILA_CARREGADA, timeout=20000)


def numero_do_botao(aba, prazo: str) -> int:
    """O número entre parênteses de um botão do prazo. Ex.: "Passou do prazo (2)" → 2."""
    texto = aba.inner_text(f"[data-contagem-fila-prazo='{prazo}']").strip()
    return int(texto.strip("()"))


def conferir_que_cada_botao_mostra_o_seu_numero(aba, rotulo: str, conferir) -> None:
    """Clica em cada prazo e confere que a lista mostra exatamente o número escrito no botão."""
    for prazo in ("todos", "dentro", "passou"):
        esperado = numero_do_botao(aba, prazo)
        aba.click(BOTAO_DO_PRAZO.format(prazo=prazo))
        na_lista = aba.locator(ITENS_DA_FILA).count()
        ligado = aba.get_attribute(BOTAO_DO_PRAZO.format(prazo=prazo), "aria-pressed")
        conferir(f"{rotulo}: '{prazo}' mostra {na_lista} item(ns), o número do botão ({esperado}), e fica ligado",
                 na_lista == esperado and ligado == "true")
    # Volta para "Todos"
    aba.click(BOTAO_DO_PRAZO.format(prazo="todos"))


def conferir_as_larguras(aba, rotulo: str, conferir) -> None:
    """Em cada largura de tela, a carteira, a fila e a página não rolam para o lado."""
    for largura in LARGURAS_DE_TELA:
        aba.set_viewport_size({"width": largura, "height": ALTURA_DA_TELA})
        medidas = aba.evaluate(MEDIDAS_DA_TELA)
        cabe = (medidas["carteira_conteudo"] <= medidas["carteira_visivel"]
                and medidas["fila_conteudo"] <= medidas["fila_visivel"]
                and medidas["pagina_conteudo"] <= medidas["pagina_visivel"])
        conferir(f"{rotulo}, {largura} px: a carteira cabe sem rolar para o lado (conteúdo "
                 f"{medidas['carteira_conteudo']} px, visível {medidas['carteira_visivel']} px), e a fila "
                 f"({medidas['fila_conteudo']}/{medidas['fila_visivel']} px) e a página "
                 f"({medidas['pagina_conteudo']}/{medidas['pagina_visivel']} px) também", cabe)
    aba.set_viewport_size({"width": 1366, "height": ALTURA_DA_TELA})


def conferir_com_os_dados_reais(aba, endereco: str, conferir) -> None:
    """Parte 1: o banco novo (6 empresas sem carga): o filtro, a escolha da empresa e os prazos vazios."""
    abrir_o_inicio(aba, endereco)
    conferir("dados reais: o filtro da fila aparece em cima da lista", aba.locator("[data-filtro-da-fila]").is_visible())
    opcoes = []
    for texto in aba.locator(ESCOLHA_DA_EMPRESA + " option").all_inner_texts():
        opcoes.append(texto.strip())
    empresas = opcoes[1:]
    conferir(f"dados reais: 'Todas as empresas' e as 6 empresas em ordem alfabética (na tela: {opcoes})",
             opcoes[0] == "Todas as empresas" and len(empresas) == 6
             and empresas == sorted(empresas, key=chave_de_ordem))
    conferir("dados reais: começa em 'Todos', com os 6 itens e sem o resumo",
             aba.locator(ITENS_DA_FILA).count() == 6 and numero_do_botao(aba, "todos") == 6
             and aba.get_attribute(BOTAO_DO_PRAZO.format(prazo="todos"), "aria-pressed") == "true"
             and aba.locator(RESUMO_DA_FILA).is_hidden())
    # A primeira empresa da lista: só o item dela
    aba.select_option(ESCOLHA_DA_EMPRESA, index=1)
    titulos = aba.locator(ITENS_DA_FILA + " .item-fila-titulo").all_inner_texts()
    conferir(f"dados reais: a empresa '{empresas[0]}' deixa só o item dela (na tela: {titulos})",
             len(titulos) == 1 and empresas[0] in titulos[0]
             and aba.inner_text(RESUMO_DA_FILA).strip() == "Mostrando 1 de 6 itens.")
    # De volta a todas as empresas; os prazos ficam vazios (nenhum envio espera o banco)
    aba.select_option(ESCOLHA_DA_EMPRESA, value="")
    aba.click(BOTAO_DO_PRAZO.format(prazo="passou"))
    conferir("dados reais: 'Passou do prazo' fica vazio, com o aviso e 'Mostrando 0 de 6 itens.'",
             aba.locator(ITENS_DA_FILA).count() == 0 and numero_do_botao(aba, "passou") == 0
             and "Nada com este filtro" in aba.inner_text(AVISO_DA_FILA)
             and aba.inner_text(RESUMO_DA_FILA).strip() == "Mostrando 0 de 6 itens.")
    aba.click(BOTAO_DO_PRAZO.format(prazo="todos"))
    conferir_que_cada_botao_mostra_o_seu_numero(aba, "dados reais", conferir)
    conferir_as_larguras(aba, "dados reais", conferir)


def resposta_trocada(dados_reais: dict) -> dict:
    """A resposta do Início com a fila e a carteira trocadas pelo roteiro (envios que esperam o banco, nomes compridos e
    números grandes).

    Recebe: a resposta de verdade de /api/banco/inicio. Devolve: a resposta trocada, com as mesmas chaves.
    A fila: 2 envios que passaram do prazo (da 2ª e da 3ª empresa da carteira) e 1 dentro do prazo (da 2ª), antes dos
    itens de verdade (as empresas sem carga), como o servidor faz (os envios primeiro). Os envios seguem a regra do
    servidor: o que passou do prazo vem "urgente".
    """
    carteira = dados_reais["carteira"]
    segunda = carteira[1]
    terceira = carteira[2]
    # Os nomes compridos e os números grandes na carteira
    segunda["nome"] = NOME_COMPRIDO_COM_ESPACOS
    segunda["cidade"] = "São José dos Campos/SP"
    segunda["cadastrados"] = 123456
    segunda["envios"] = 1234
    segunda["em_andamento"] = 56
    segunda["situacao"] = {"texto": "Com pendência", "classe": "selo-atencao"}
    terceira["nome"] = NOME_COMPRIDO_SEM_ESPACO
    terceira["envios"] = 1
    terceira["em_andamento"] = 0
    # Os três envios que esperam a avaliação do banco
    envios = [
        {"titulo": "Avaliar o envio da " + segunda["nome"], "empresa_id": segunda["id"], "envio_id": "ROTEIRO-P1",
         "urgente": True, "detalhe": "Carga inicial · Passou do prazo de 1 dia útil"},
        {"titulo": "Avaliar o envio da " + segunda["nome"], "empresa_id": segunda["id"], "envio_id": "ROTEIRO-P2",
         "urgente": False, "detalhe": "Inclusão · Dentro do prazo de 1 dia útil"},
        {"titulo": "Avaliar o envio da " + terceira["nome"], "empresa_id": terceira["id"], "envio_id": "ROTEIRO-P3",
         "urgente": True, "detalhe": "Inclusão · Passou do prazo de 1 dia útil"},
    ]
    dados_reais["fila"] = envios + dados_reais["fila"]
    return dados_reais


def conferir_com_a_fila_trocada(aba, endereco: str, conferir) -> None:
    """Parte 2: a fila com envios nos dois prazos e as empresas de nome comprido (a resposta trocada pelo roteiro)."""

    def trocar_a_resposta(rota):
        """Busca a resposta de verdade no servidor e devolve a versão trocada pelo roteiro."""
        resposta = rota.fetch()
        rota.fulfill(response=resposta, json=resposta_trocada(resposta.json()))

    aba.route("**/api/banco/inicio", trocar_a_resposta)
    abrir_o_inicio(aba, endereco)
    conferir(f"fila trocada: 9 itens em 'Todos', 1 dentro do prazo e 2 que passaram (botões: "
             f"{numero_do_botao(aba, 'todos')}, {numero_do_botao(aba, 'dentro')}, {numero_do_botao(aba, 'passou')})",
             numero_do_botao(aba, "todos") == 9 and numero_do_botao(aba, "dentro") == 1
             and numero_do_botao(aba, "passou") == 2 and aba.locator(ITENS_DA_FILA).count() == 9)
    # "Passou do prazo": só os dois envios atrasados, na ordem da fila, com o botão "Avaliar"
    aba.click(BOTAO_DO_PRAZO.format(prazo="passou"))
    detalhes = aba.locator(ITENS_DA_FILA + " .item-fila-detalhe").all_inner_texts()
    botoes = aba.locator(ITENS_DA_FILA + " a").all_inner_texts()
    conferir(f"'Passou do prazo': só os 2 envios atrasados, com 'Avaliar' (na tela: {detalhes})",
             len(detalhes) == 2 and todos_contem(detalhes, "Passou do prazo") and botoes == ["Avaliar", "Avaliar"]
             and aba.inner_text(RESUMO_DA_FILA).strip() == "Mostrando 2 de 9 itens.")
    # "Dentro do prazo": só o envio no prazo
    aba.click(BOTAO_DO_PRAZO.format(prazo="dentro"))
    detalhes = aba.locator(ITENS_DA_FILA + " .item-fila-detalhe").all_inner_texts()
    conferir(f"'Dentro do prazo': só o envio no prazo (na tela: {detalhes})",
             len(detalhes) == 1 and "Dentro do prazo" in detalhes[0])
    # A empresa de nome comprido junto com o prazo: os números dos botões passam a ser os dela
    aba.select_option(ESCOLHA_DA_EMPRESA, label=NOME_COMPRIDO_COM_ESPACOS)
    conferir(f"a empresa e o prazo se combinam: a empresa de nome comprido tem 3 itens, 1 no prazo e 1 atrasado "
             f"(botões: {numero_do_botao(aba, 'todos')}, {numero_do_botao(aba, 'dentro')}, "
             f"{numero_do_botao(aba, 'passou')}), e 'Dentro do prazo' continua ligado com o envio dela",
             numero_do_botao(aba, "todos") == 3 and numero_do_botao(aba, "dentro") == 1
             and numero_do_botao(aba, "passou") == 1 and aba.locator(ITENS_DA_FILA).count() == 1
             and aba.inner_text(RESUMO_DA_FILA).strip() == "Mostrando 1 de 9 itens.")
    conferir_que_cada_botao_mostra_o_seu_numero(aba, "empresa de nome comprido", conferir)
    # A empresa de nome sem espaço: o envio atrasado dela
    aba.select_option(ESCOLHA_DA_EMPRESA, label=NOME_COMPRIDO_SEM_ESPACO)
    aba.click(BOTAO_DO_PRAZO.format(prazo="passou"))
    titulos = aba.locator(ITENS_DA_FILA + " .item-fila-titulo").all_inner_texts()
    conferir(f"a empresa de nome sem espaço: 'Passou do prazo' mostra o envio dela (na tela: {len(titulos)} item)",
             len(titulos) == 1 and NOME_COMPRIDO_SEM_ESPACO in titulos[0])
    # Tudo de volta: todas as empresas e todos os prazos; o resumo some
    aba.select_option(ESCOLHA_DA_EMPRESA, value="")
    aba.click(BOTAO_DO_PRAZO.format(prazo="todos"))
    conferir("com 'Todas as empresas' e 'Todos', os 9 itens voltam e o resumo some",
             aba.locator(ITENS_DA_FILA).count() == 9 and aba.locator(RESUMO_DA_FILA).is_hidden())
    conferir_que_cada_botao_mostra_o_seu_numero(aba, "fila trocada", conferir)
    conferir_a_coluna_de_envios(aba, conferir)
    conferir_as_larguras(aba, "nomes compridos e números grandes", conferir)
    aba.unroute("**/api/banco/inicio")


def todos_contem(textos: list[str], trecho: str) -> bool:
    """Diz se todos os textos da lista têm o trecho. Ex.: (["a · Passou do prazo"], "Passou do prazo") → True."""
    for texto in textos:
        if trecho not in texto:
            return False
    return True


def conferir_a_coluna_de_envios(aba, conferir) -> None:
    """A coluna "Envios" da carteira em duas linhas: quantos envios e, embaixo, quantos estão em andamento."""
    linhas = aba.locator("[data-corpo-carteira] tr")
    envios_da_segunda = linhas.nth(1).locator("td").nth(2).inner_text()
    envios_da_terceira = linhas.nth(2).locator("td").nth(2).inner_text()
    envios_da_primeira = linhas.nth(0).locator("td").nth(2).inner_text()
    conferir(f"a coluna 'Envios' em duas linhas: '{envios_da_segunda}', '{envios_da_terceira}' e '{envios_da_primeira}'",
             envios_da_segunda.split("\n") == ["1234 envios", "56 em andamento"]
             and envios_da_terceira.split("\n") == ["1 envio", "nenhum em andamento"]
             and envios_da_primeira.strip() == "nenhum envio")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Entra como especialista do banco e confere o filtro da fila e a largura da carteira."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_com_os_dados_reais(aba, endereco, conferir)
    conferir_com_a_fila_trocada(aba, endereco, conferir)
    aba.close()
