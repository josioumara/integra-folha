"""Roteiro: a tela Endomarketing do banco em duas seções, com a empresa em primeiro lugar.

O que ele confere:
- sem empresa escolhida, a página mostra só a faixa "Escolha a empresa" (busca e lista) e nada embaixo;
- nenhuma empresa abre sozinha;
- a busca filtra a lista pelo nome;
- escolhida a empresa, a faixa se recolhe no nome dela, com "Trocar empresa", e embaixo aparecem duas guias (como as
  dos Indicadores), nesta ordem: "Base de Conhecimento" (aberta) e "Material para Comunicação" (as guias poupam
  rolar a tela das KBs até os materiais);
- a guia escolhida e a empresa ficam no endereço, e o F5 volta nelas;
- a Base de Conhecimento traz as KBs da empresa, com os Benefícios numa aba própria (a primeira, já aberta, só com
  benefícios) e as outras KBs nas abas seguintes;
- "Nova KB" abre o editor já com a empresa (travada) e o tipo "Benefício";
- uma versão nova aparece em "Aguardando publicação" com quem salvou, a data e a hora; "Visualizar" abre ela e
  "Publicar" a publica e a tira da lista;
- "Histórico anterior (N)" abre as versões antigas congeladas (faixa de gelo, selo "Congelada", sem ações), com a
  navegação "‹ Versão mais antiga", "Versão mais recente ›" e "Voltar à versão atual";
- não há mais "Aplicar na empresa": publicar já atualiza a empresa, sem mensagem, e a guia do material continua
  oferecendo os benefícios do catálogo;
- "Trocar empresa" traz a lista de volta; outra empresa troca o nome e as KBs;
- a guia "Regras gerais" mostra as mesmas regras para qualquer empresa (as 7 diretrizes gerais), e a KB nova
  dali já vem com o dono "GERAL", travado;
- nenhuma janela nativa do navegador (alert, confirm) aparece.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Endomarketing do banco: empresa primeiro, nada sem empresa, Base de Conhecimento e Material para Comunicação"


def preparar() -> dict:
    """Só os usuários de teste: as empresas e as KBs do projeto entram sozinhas no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def posicao_vertical(aba, seletor: str) -> float:
    """Devolve a altura (em pixels, do topo da página) em que o elemento começa."""
    return aba.locator(seletor).bounding_box()["y"]


def escolher_empresa(aba, nome: str) -> None:
    """Clica na empresa da lista do topo e espera a faixa se recolher no nome dela e a Base de Conhecimento chegar."""
    aba.locator("[data-lista-empresas-endomarketing] button", has_text=nome).click()
    aba.wait_for_function("(nome) => document.querySelector('[data-nome-da-empresa]').innerText.includes(nome)",
                          arg=nome, timeout=10000)
    aba.locator("[data-area-da-empresa]:not([hidden])").wait_for(timeout=20000)
    aba.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)


def abrir_kb_da_lista(aba, titulo: str) -> None:
    """Na lista das KBs (aba aberta), clica em "Abrir" na KB com esse título e espera a janela."""
    aba.locator("[data-lista-kbs] li", has_text=titulo).get_by_role("button", name="Abrir").click()
    aba.locator("#janela-kb[open]").wait_for(timeout=10000)


def criar_versao_nova(aba, titulo: str, origem: str) -> None:
    """Abre a KB, clica em "Editar (versão nova)", troca a origem, salva o rascunho e fecha a janela da versão salva.

    Recebe: a aba; o título da KB; o texto novo da origem (a mudança da versão). Devolve: nada.
    """
    abrir_kb_da_lista(aba, titulo)
    aba.locator("[data-kb-botoes] button", has_text="Editar (versão nova)").click()
    aba.locator("#janela-editor-kb[open]").wait_for(timeout=10000)
    aba.fill('[data-editor-campo="origem"]', origem)
    aba.click("[data-editor-salvar]")
    # Salva, a janela da KB abre na versão nova (rascunho); fecha para voltar à guia
    aba.locator("#janela-editor-kb:not([open])").wait_for(state="attached", timeout=20000)
    aba.locator("#janela-kb[open]").wait_for(timeout=20000)
    aba.click("#janela-kb .janela-cabecalho [data-fechar-janela]")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre sem empresa, busca, escolhe, confere as guias, a aba dos Benefícios, o editor, o histórico e trocar."""
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    janelas_nativas = []

    def anotar_janela_nativa(janela) -> None:
        """Anota a mensagem da janela nativa e a fecha (para o roteiro não travar)."""
        janelas_nativas.append(janela.message)
        janela.dismiss()

    banco.on("dialog", anotar_janela_nativa)

    # 1. Sem empresa: só a faixa de escolha; nada embaixo, e nenhuma empresa abre sozinha
    banco.goto(endereco + "/banco_endomarketing.html")
    banco.locator("[data-lista-empresas-endomarketing][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    banco.wait_for_timeout(1500)
    conferir("sem empresa, a faixa 'Escolha a empresa' aparece com a lista",
             banco.locator("[data-escolha-da-empresa]").is_visible()
             and banco.locator("[data-lista-empresas-endomarketing] button").count() >= 2)
    conferir("sem empresa, nada aparece embaixo (nem as seções nem o aviso do material)",
             banco.locator("[data-area-da-empresa]").is_hidden()
             and banco.locator("[data-empresa-escolhida]").is_hidden()
             and banco.locator(".aviso-so-o-publicado").is_hidden())

    # 2. A busca filtra pelo nome
    banco.fill("[data-busca-endomarketing]", "auro")
    conferir("a busca 'auro' deixa só a Aurora na lista",
             banco.locator("[data-lista-empresas-endomarketing] button").count() == 1
             and "Aurora" in banco.inner_text("[data-lista-empresas-endomarketing]"))
    banco.fill("[data-busca-endomarketing]", "")

    # 3. Escolhida a Aurora: a faixa se recolhe e as três guias aparecem, nesta ordem
    escolher_empresa(banco, "Aurora")
    conferir("a faixa mostra só a Aurora, com os números e 'Trocar empresa'",
             banco.locator("[data-escolha-da-empresa]").is_hidden()
             and banco.locator("[data-empresa-escolhida]").is_visible()
             and "publicado" in banco.inner_text("[data-resumo-da-empresa-escolhida]")
             and banco.locator("[data-trocar-empresa]").is_visible())
    guias = banco.locator("[data-guia-endomarketing]").all_inner_texts()
    conferir("embaixo, as guias 'Base de Conhecimento', 'Regras gerais' e 'Material para Comunicação' (" +
             " | ".join(guias) + ")",
             [guia.strip() for guia in guias] == ["Base de Conhecimento", "Regras gerais", "Material para Comunicação"])
    conferir("a empresa vem antes das guias",
             posicao_vertical(banco, "[data-empresa-escolhida]") < posicao_vertical(banco, ".guias-endomarketing"))
    conferir("abre na guia Base de Conhecimento, e o material fica escondido (sem rolar a tela até ele)",
             banco.get_attribute("#botao-guia-base", "aria-selected") == "true"
             and banco.locator("#base-de-conhecimento").is_visible()
             and banco.locator("#material-para-comunicacao").is_hidden())

    # 3.1 A guia do material: troca o conteúdo, e o endereço guarda a empresa e a guia (o F5 volta nelas)
    banco.click("#botao-guia-material")
    conferir("a guia Material para Comunicação mostra o aviso, o formulário e os materiais, e esconde as KBs",
             banco.locator("#material-para-comunicacao .aviso-so-o-publicado").is_visible()
             and banco.locator("[data-gerar-material]").is_visible()
             and banco.locator("#materiais").is_visible()
             and banco.locator("#base-de-conhecimento").is_hidden())
    conferir("o endereço guarda a empresa e a guia (" + banco.url + ")",
             "empresa=EMP001" in banco.url and "aba=material" in banco.url)
    banco.reload()
    banco.locator("[data-area-da-empresa]:not([hidden])").wait_for(timeout=20000)
    conferir("depois do F5, a Aurora e a guia do material continuam abertas",
             "Aurora" in banco.inner_text("[data-nome-da-empresa]")
             and banco.locator("#material-para-comunicacao").is_visible()
             and banco.locator("#base-de-conhecimento").is_hidden())
    banco.click("#botao-guia-base")
    banco.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)

    # 4. Base de Conhecimento: os Benefícios numa aba própria, a primeira e já aberta
    abas = banco.locator("[data-abas-tipos] button")
    conferir("a primeira aba é 'Benefícios (6)' e está aberta (" + abas.first.inner_text() + ")",
             abas.first.inner_text() == "Benefícios (6)" and abas.first.get_attribute("aria-selected") == "true")
    conferir("as outras KBs da empresa têm abas próprias, e 'Todas' é a última",
             abas.count() >= 3 and abas.last.inner_text().startswith("Todas"))
    detalhes = banco.locator("[data-lista-kbs] .item-fila-detalhe").all_inner_texts()
    conferir("a aba dos Benefícios lista só os 6 benefícios",
             len(detalhes) == 6 and all(detalhe.startswith("Benefício") for detalhe in detalhes))
    abas.nth(1).click()
    detalhes_da_outra_aba = banco.locator("[data-lista-kbs] .item-fila-detalhe").all_inner_texts()
    conferir("a segunda aba mostra outro tipo de KB",
             len(detalhes_da_outra_aba) > 0 and not detalhes_da_outra_aba[0].startswith("Benefício"))
    abas.first.click()

    # 5. "Nova KB": o editor já vem com a empresa (travada) e o tipo Benefício
    banco.click("[data-nova-kb]")
    banco.locator("#janela-editor-kb[open]").wait_for(timeout=10000)
    conferir("o editor vem com a Aurora travada e o tipo Benefício",
             banco.input_value('[data-editor-campo="dono"]') == "EMP001"
             and banco.locator('[data-editor-campo="dono"]').is_disabled()
             and banco.input_value('[data-editor-campo="tipo"]') == "beneficio")
    banco.click("#janela-editor-kb .janela-cabecalho [data-fechar-janela]")

    # 5.1 Aguardando publicação e o histórico congelado
    conferir("sem versão nova, 'Aguardando publicação' diz que não há nenhuma",
             banco.locator("[data-sem-aguardando]").is_visible()
             and banco.inner_text("[data-contador-aguardando]") == "0")
    criar_versao_nova(banco, "Crédito consignado", "Revisão 1 do roteiro")
    linha_aguardando = banco.locator("[data-lista-aguardando] li", has_text="Crédito consignado")
    registro = linha_aguardando.inner_text() if linha_aguardando.count() == 1 else ""
    conferir("a versão nova aparece em 'Aguardando publicação', com quem salvou, a data e a hora (" +
             registro.replace("\n", " | ") + ")",
             "versão 2" in registro and "Salva por teste.banco em" in registro and " às " in registro
             and banco.inner_text("[data-contador-aguardando]") == "1")
    linha_aguardando.get_by_role("button", name="Visualizar").click()
    banco.locator("#janela-kb[open]").wait_for(timeout=10000)
    conferir("'Visualizar' abre a versão nova (rascunho v2), sem o gelo",
             "Rascunho v2" in banco.inner_text("[data-kb-selos]")
             and "janela-kb-congelada" not in (banco.get_attribute("#janela-kb", "class") or ""))
    banco.click("#janela-kb .janela-cabecalho [data-fechar-janela]")
    linha_aguardando.get_by_role("button", name="Publicar").click()
    banco.locator("[data-lista-aguardando] li").first.wait_for(state="detached", timeout=20000)
    conferir("'Publicar' publica a versão 2 e ela sai da lista",
             "Versão 2 publicada" in banco.inner_text("[data-aviso-kbs]")
             and banco.locator("#janela-kb[open]").count() == 0
             and banco.locator("[data-sem-aguardando]").is_visible())
    # Uma terceira versão, para o histórico ter duas versões antigas para navegar
    criar_versao_nova(banco, "Crédito consignado", "Revisão 2 do roteiro")
    banco.locator("[data-lista-aguardando] li", has_text="Crédito consignado").get_by_role("button", name="Publicar").click()
    banco.locator("[data-lista-aguardando] li").first.wait_for(state="detached", timeout=20000)

    # O histórico anterior: abre a mais recente das antigas, congelada, e navega até a mais antiga e de volta
    abrir_kb_da_lista(banco, "Crédito consignado")
    conferir("a versão atual (v3) tem o botão 'Histórico anterior (2)'",
             banco.locator("[data-kb-historico]").inner_text() == "Histórico anterior (2)")
    banco.click("[data-kb-historico]")
    banco.wait_for_function("() => document.querySelector('#janela-kb').classList.contains('janela-kb-congelada')",
                            timeout=10000)
    texto_da_faixa = banco.inner_text("[data-kb-congelada-texto]")
    conferir("a versão 2 abre congelada: faixa de gelo, selo 'Congelada' e sem nenhuma ação (" + texto_da_faixa[:90] + ")",
             texto_da_faixa.startswith("Versão 2 congelada (1 de 2")
             and "Substituída pela versão 3" in texto_da_faixa
             and "Congelada" in banco.inner_text("[data-kb-selos]")
             and banco.locator("[data-kb-botoes] button").count() == 0)
    conferir("na lista das versões, as antigas não têm 'Publicar'",
             banco.locator(".versao-da-kb-congelada").count() == 2
             and banco.locator(".versao-da-kb-congelada").get_by_role("button", name="Publicar").count() == 0)
    banco.get_by_role("button", name="‹ Versão mais antiga").click()
    banco.wait_for_function("() => document.querySelector('[data-kb-congelada-texto]').innerText.startsWith('Versão 1')",
                            timeout=10000)
    conferir("'‹ Versão mais antiga' vai para a versão 1 (2 de 2), sem outra mais antiga",
             "(2 de 2" in banco.inner_text("[data-kb-congelada-texto]")
             and banco.get_by_role("button", name="‹ Versão mais antiga").count() == 0)
    banco.get_by_role("button", name="Versão mais recente ›").click()
    banco.wait_for_function("() => document.querySelector('[data-kb-congelada-texto]').innerText.startsWith('Versão 2')",
                            timeout=10000)
    banco.get_by_role("button", name="Voltar à versão atual").click()
    banco.wait_for_function("() => !document.querySelector('#janela-kb').classList.contains('janela-kb-congelada')",
                            timeout=10000)
    conferir("'Voltar à versão atual' mostra a v3 publicada, sem o gelo e com as ações",
             "Publicada v3" in banco.inner_text("[data-kb-selos]")
             and banco.locator("[data-kb-congelada]").is_hidden()
             and banco.locator("[data-kb-botoes] button", has_text="Editar (versão nova)").count() == 1)
    banco.click("#janela-kb .janela-cabecalho [data-fechar-janela]")

    # 6. Sem "Aplicar na empresa": publicar já atualizou a empresa, sem mensagem sobre isso
    conferir("não há botão 'Aplicar na empresa' nem a linha da última aplicação",
             banco.locator("[data-aplicar-na-empresa]").count() == 0
             and banco.locator("[data-ultima-aplicacao]").count() == 0)
    conferir("o aviso da publicação não fala de aplicar (" + banco.inner_text("[data-aviso-kbs]") + ")",
             "plica" not in banco.inner_text("[data-aviso-kbs]"))
    banco.click("#botao-guia-material")
    conferir("depois de publicar, a guia do material oferece os benefícios do catálogo",
             banco.locator("input[name='beneficio-material']").count() > 0)
    banco.click("#botao-guia-base")
    banco.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)

    # 7. "Trocar empresa": a lista volta; outra empresa troca o nome e as KBs
    banco.click("[data-trocar-empresa]")
    conferir("'Trocar empresa' traz a busca e a lista de volta",
             banco.locator("[data-escolha-da-empresa]").is_visible())
    outra = banco.locator("[data-lista-empresas-endomarketing] button").nth(1)
    nome_da_outra = outra.locator(".botao-envio-fila-empresa").inner_text()
    escolher_empresa(banco, nome_da_outra)
    conferir("a faixa mostra a outra empresa (" + nome_da_outra + ")",
             banco.inner_text("[data-nome-da-empresa]") == nome_da_outra
             and banco.locator("[data-escolha-da-empresa]").is_hidden())
    conferir("a Base de Conhecimento abre de novo na aba dos Benefícios",
             banco.locator("[data-abas-tipos] button").first.inner_text().startswith("Benefícios"))

    # 8. A guia Regras gerais: as mesmas regras em qualquer empresa, e a KB nova já com o dono GERAL
    banco.click("#botao-guia-regras")
    banco.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    conferir("na outra empresa, a guia Regras gerais mostra as 7 diretrizes gerais, e a empresa continua no topo",
             banco.locator("[data-lista-kbs] li").count() == 7
             and "todas as empresas" in banco.inner_text("[data-descricao-dono]")
             and banco.inner_text("[data-nome-da-empresa]") == nome_da_outra)
    conferir("o endereço guarda a guia Regras gerais", "aba=regras" in banco.url)
    banco.click("[data-nova-kb]")
    banco.locator("#janela-editor-kb[open]").wait_for(timeout=10000)
    conferir("a KB nova das Regras gerais vem com o dono GERAL, travado",
             banco.input_value('[data-editor-campo="dono"]') == "GERAL"
             and banco.locator('[data-editor-campo="dono"]').is_disabled())
    banco.click("#janela-editor-kb .janela-cabecalho [data-fechar-janela]")

    conferir("nenhuma janela nativa do navegador apareceu", len(janelas_nativas) == 0)
