"""Roteiro: o banco gera, a empresa comunica (ADR-115) — do rascunho no Portal Interno até a lista da empresa.

O que ele confere:
- a aba Endomarketing do Portal Interno diz "A empresa só vê o que você publicar";
- sem nenhum benefício marcado, a tela pede "pelo menos um" e não chama a IA;
- com dois benefícios marcados, o rascunho sai (IA simulada) com os blocos e as fontes, e entra na lista como Rascunho;
- antes de publicar, a empresa NÃO vê o material; depois de "Publicar para a empresa", vê e baixa o texto e a arte;
- a arte publicada é uma só, a do canal do rascunho (no e-mail, o banner 1200 × 400);
- "Retirar da empresa" pede a confirmação numa janela da própria página (nunca o confirm() do navegador) e o material
  some da lista da empresa.

As funções de apoio do começo (abrir a aba do banco, marcar as escolhas, gerar) também são usadas pelos roteiros
arte_fiel_ao_texto, arte_com_o_kit e lembrete_no_whatsapp.
"""
from pathlib import Path

from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = "Endomarketing do banco: gerar com os benefícios escolhidos, publicar, a empresa baixar e o banco retirar"
# Os dois benefícios do catálogo da Aurora que entram no material
BENEFICIOS_ESCOLHIDOS = ["Salário antecipado", "Crédito consignado"]
# Quanto esperar a IA simulada escrever (em milissegundos)
ESPERA_DO_RASCUNHO = 60000


# ---------------- Apoio (usado também por outros roteiros) ----------------

def abrir_endomarketing_do_banco(navegador, endereco: str, erros_da_pagina: list, empresa_id: str = "EMP001"):
    """Entra como especialista, abre a aba Endomarketing na empresa pedida e espera o formulário ficar pronto.

    Recebe: o navegador; o endereço do servidor; a lista dos erros de JavaScript; o código da empresa.
    Devolve: a aba do navegador.
    """
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    # A guia "Material para Comunicação" (a primeira guia é a Base de Conhecimento)
    aba.goto(endereco + "/banco_endomarketing.html?empresa=" + empresa_id + "&aba=material")
    # A área da empresa aparece quando os dados dela chegam (kit, catálogo, tipos, canais e materiais)
    aba.locator("[data-area-da-empresa]:not([hidden])").wait_for(timeout=20000)
    aba.locator("input[name='beneficio-material']").first.wait_for(state="attached", timeout=20000)
    return aba


def marcar_opcao(aba, nome_do_grupo: str, valor: str) -> None:
    """Clica no cartão (ou na pílula) de uma opção: a bolinha de marcar fica escondida, como para quem usa a tela.

    Recebe: a aba; o name do grupo (ex.: "canal-material"); o value da opção (ex.: "whatsapp"). Devolve: nada.
    """
    opcao = aba.locator("input[name='" + nome_do_grupo + "'][value='" + valor + "']")
    opcao.locator("xpath=ancestor::label[1]").click()


def gerar_rascunho(aba, tipo: str, canal: str, beneficios: list) -> bool:
    """Marca o tipo, o canal e os benefícios, clica em "Gerar rascunho" e espera o rascunho e a arte.

    Recebe: a aba; a chave do tipo; a chave do canal; os títulos dos benefícios.
    Devolve: True se o rascunho saiu e a arte foi desenhada; False se a tela disse que não gerou.
    """
    marcar_opcao(aba, "tipo-material", tipo)
    marcar_opcao(aba, "canal-material", canal)
    for beneficio in beneficios:
        marcar_opcao(aba, "beneficio-material", beneficio)
    aba.click("[data-gerar-material]")
    # Espera a arte ficar pronta (rascunho gerado) ou o aviso de que não gerou
    aba.wait_for_function("""() => document.querySelector('[data-previa-arte]').dataset.moldeDesenhado
        || document.querySelector('[data-titulo-material]').innerText.includes('não foi gerado')""",
                          timeout=ESPERA_DO_RASCUNHO)
    return aba.evaluate("() => estado_do_endomarketing.rascunho !== null")


def esperar_arte_no_molde(aba, molde: str) -> None:
    """Espera a arte da prévia terminar de ser desenhada no molde pedido (ex.: "cartaz")."""
    aba.wait_for_function("(molde) => document.querySelector('[data-previa-arte]').dataset.moldeDesenhado === molde",
                          arg=molde, timeout=15000)


def abrir_materiais_da_empresa(navegador, endereco: str, erros_da_pagina: list):
    """Entra como o RH da Aurora e abre "Materiais de endomarketing", esperando a lista carregar. Devolve a aba."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    recarregar_materiais_da_empresa(aba, endereco)
    return aba


def recarregar_materiais_da_empresa(aba, endereco: str) -> None:
    """Abre (de novo) a lista de materiais da empresa e espera: ou um material, ou o aviso de lista vazia."""
    aba.goto(endereco + "/endomarketing.html")
    aba.wait_for_function("""() => document.querySelector('[data-lista-materiais] article')
        || (document.querySelector('[data-sem-materiais]') && !document.querySelector('[data-sem-materiais]').hidden)""",
                          timeout=20000)


# ---------------- O roteiro ----------------

def preparar() -> dict:
    """Só os usuários de teste: o catálogo da Aurora entra sozinho no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Gera e publica no banco, confere na empresa, retira no banco e confere de novo na empresa."""
    banco = abrir_endomarketing_do_banco(navegador, endereco, erros_da_pagina)
    # Qualquer janela nativa do navegador (alert, confirm) reprova: a tela usa as janelas dela
    janelas_nativas = []

    def anotar_janela_nativa(janela) -> None:
        """Anota a mensagem da janela nativa e a fecha (para o roteiro não travar)."""
        janelas_nativas.append(janela.message)
        janela.dismiss()

    banco.on("dialog", anotar_janela_nativa)
    conferir("a tela diz que a empresa só vê o que for publicado",
             "A empresa só vê o que você publicar" in banco.inner_text(".aviso-so-o-publicado"))

    # 1. Sem benefício marcado: a tela pede pelo menos um e não gera
    banco.click("[data-gerar-material]")
    conferir("sem benefício, a tela pede 'Marque pelo menos um benefício'",
             banco.locator("[data-erro-beneficios]").is_visible())
    conferir("sem benefício, nenhum rascunho aparece", banco.locator("[data-rascunho]").is_hidden())

    # 2. Com dois benefícios: o rascunho sai com blocos, fontes e os benefícios no resumo
    gerou = gerar_rascunho(banco, "comunicado", "email", BENEFICIOS_ESCOLHIDOS)
    conferir("o rascunho foi gerado (" + banco.inner_text("[data-titulo-material]")[:80] + ")", gerou)
    if not gerou:
        conferir("aviso da tela: " + banco.inner_text("[data-avisos-material]")[:150], False)
        banco.close()
        return
    material_id = banco.evaluate("() => estado_do_endomarketing.rascunho.material_id")
    titulo = banco.evaluate("() => estado_do_endomarketing.rascunho.titulo")
    resumo = banco.inner_text("[data-resumo-material]")
    conferir("o resumo traz os dois benefícios escolhidos (" + resumo[:120] + ")",
             BENEFICIOS_ESCOLHIDOS[0] in resumo and BENEFICIOS_ESCOLHIDOS[1] in resumo)
    blocos = banco.locator("[data-corpo-material] .trecho-material")
    fontes = banco.locator("[data-corpo-material] .fonte-trecho")
    conferir("cada bloco tem a fonte (" + str(blocos.count()) + " blocos)",
             blocos.count() > 0 and fontes.count() == blocos.count())
    conferir("não há edição livre do texto",
             banco.locator("[data-corpo-material] [contenteditable='true']").count() == 0)
    linha_do_material = banco.locator("[data-lista-materiais] [data-material-id='" + material_id + "']")
    linha_do_material.wait_for(timeout=10000)
    conferir("o material entra na lista como Rascunho",
             linha_do_material.locator("[data-selo-da-situacao]").inner_text() == "Rascunho")

    # 3. Antes de publicar, a empresa não vê
    empresa = abrir_materiais_da_empresa(navegador, endereco, erros_da_pagina)
    conferir("antes de publicar, a empresa não vê o rascunho",
             empresa.locator("[data-material='" + material_id + "']").count() == 0)

    # 4. Publicar para a empresa (com a arte)
    banco.click("[data-publicar-material]")
    banco.locator("[data-aviso-endomarketing]:not([hidden])").wait_for(timeout=20000)
    conferir("o aviso diz que a empresa já vê o material",
             "Publicado para a" in banco.inner_text("[data-aviso-endomarketing]"))
    linha_do_material = banco.locator("[data-lista-materiais] [data-material-id='" + material_id + "']")
    conferir("na lista do banco, a situação vira 'Publicado para a empresa'",
             linha_do_material.locator("[data-selo-da-situacao]").inner_text() == "Publicado para a empresa")
    conferir("o publicado tem 'Baixar arte' (a arte foi junto)",
             linha_do_material.get_by_role("button", name="Baixar arte").count() == 1)
    conferir("o rascunho fechou depois de publicar", banco.locator("[data-rascunho]").is_hidden())
    # "Ver" abre a janela com o texto e a arte publicada (a imagem carrega de verdade)
    linha_do_material.get_by_role("button", name="Ver", exact=True).click()
    banco.locator("#janela-material[open]").wait_for(timeout=10000)
    banco.wait_for_function("() => document.querySelector('[data-janela-material-arte]').complete", timeout=10000)
    largura_da_arte = banco.evaluate("() => document.querySelector('[data-janela-material-arte]').naturalWidth")
    conferir("'Ver' mostra o texto e a arte publicada (" + str(largura_da_arte) + " px)",
             titulo in banco.inner_text("#janela-material") and largura_da_arte > 0)
    # A arte publicada é a do canal do rascunho: o material é do e-mail, então vai o banner
    altura_da_arte = banco.evaluate("() => document.querySelector('[data-janela-material-arte]').naturalHeight")
    conferir("a arte publicada é a do canal, o banner do e-mail (" + str(largura_da_arte) + " × " + str(altura_da_arte)
             + ")", [largura_da_arte, altura_da_arte] == [1200, 400])
    banco.click("#janela-material .janela-botoes [data-fechar-janela]")

    # 5. A empresa vê e baixa o texto e a arte
    recarregar_materiais_da_empresa(empresa, endereco)
    cartao_da_empresa = empresa.locator("[data-material='" + material_id + "']")
    conferir("depois de publicar, a empresa vê o material", cartao_da_empresa.count() == 1)
    if cartao_da_empresa.count() == 1:
        with empresa.expect_download(timeout=15000) as espera_do_texto:
            cartao_da_empresa.get_by_role("button", name="Baixar texto").click()
        texto_baixado = Path(espera_do_texto.value.path()).read_text(encoding="utf-8")
        conferir("a empresa baixa o texto, com o título (" + espera_do_texto.value.suggested_filename + ")",
                 titulo in texto_baixado)
        with empresa.expect_download(timeout=15000) as espera_da_arte:
            cartao_da_empresa.get_by_role("button", name="Baixar arte").click()
        arte_baixada = Path(espera_da_arte.value.path()).read_bytes()
        conferir("a empresa baixa a arte em PNG (" + str(len(arte_baixada)) + " bytes)",
                 arte_baixada[:8] == b"\x89PNG\r\n\x1a\n")

    # 6. O banco retira: a confirmação é uma janela da própria página
    linha_do_material.locator("[data-retirar-material]").click()
    banco.locator("#janela-confirmacao[open]").wait_for(timeout=10000)
    conferir("retirar pede a confirmação na janela da página",
             "Retirar da empresa?" in banco.inner_text("#janela-confirmacao"))
    banco.click("#janela-confirmacao [data-confirmar-acao]")
    banco.locator("#janela-confirmacao[open]").wait_for(state="detached", timeout=15000)
    linha_do_material = banco.locator("[data-lista-materiais] [data-material-id='" + material_id + "']")
    conferir("na lista do banco, a situação vira 'Retirado da empresa'",
             linha_do_material.locator("[data-selo-da-situacao]").inner_text() == "Retirado da empresa")
    # O filtro "Retirados" mostra só o retirado
    banco.click("[data-filtro-situacao='RETIRADO']")
    conferir("o filtro Retirados mostra só o material retirado",
             banco.locator("[data-lista-materiais] article").count() == 1)
    conferir("nenhuma janela nativa do navegador (" + str(janelas_nativas) + ")", janelas_nativas == [])

    # 7. A empresa deixa de ver
    recarregar_materiais_da_empresa(empresa, endereco)
    conferir("depois de retirar, o material some da empresa",
             empresa.locator("[data-material='" + material_id + "']").count() == 0)
    empresa.close()
    banco.close()
