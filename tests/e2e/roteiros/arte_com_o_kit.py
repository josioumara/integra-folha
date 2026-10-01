"""Roteiro: o kit de marca mora na KB "Kit da marca" da empresa (ADR-115).

A KB do kit é a fonte única das cores, do logo e da escolha entre o próprio e o padrão: a aba "Kit
de endomarketing" da ficha da empresa saiu, e a guia do material mostra o "Kit em uso" só para ler.

O que ele confere:
- na guia do material, o "Kit em uso" aparece sem campo de edição, e o "Mudar o kit ou o logo" antigo saiu;
- o "Editar na KB →" abre a KB do kit da Aurora, com as amostras das cores da versão;
- no editor da versão nova: não há o campo do caminho do logo; um texto renomeado para .png é recusado na hora (a
  tela olha a assinatura do arquivo, não o nome); as cores digitadas viram amostras; o logo escolhido aparece na
  prévia, com "Tirar o logo"; o "Conferir na trava" não acusa "kit sem logo";
- salvo, o rascunho mostra o logo na janela da versão; publicado, o "Kit em uso" passa a "próprio da Aurora", verde e
  com o logo, sem recarregar a página;
- a arte do rascunho sai na cor do kit (um pixel da faixa) e com o logo desenhado (um pixel azul à direita);
- uma versão nova com "Tirar o logo", publicada, deixa o kit sem logo: o "Kit em uso" diz "sem logo", e a arte do
  rascunho aberto é redesenhada sem ele;
- a ficha da empresa tem 6 abas, sem a do kit, e o endereço antigo (?aba=kit) abre a Visão geral;
- nenhuma janela nativa do navegador (alert, confirm) aparece.
"""
import struct
import zlib

from tests.e2e.apoio import pasta_do_roteiro
from tests.e2e.roteiros.endomarketing_do_banco import abrir_endomarketing_do_banco, gerar_rascunho

DESCRICAO = "Kit na KB: o Kit em uso só para ler, o logo e as cores no editor da KB do kit, a arte e a ficha sem a aba"
# As cores do kit próprio que o roteiro grava na KB (verde e verde-escuro) e a principal em RGB, como o canvas devolve
COR_DO_KIT = "#1f7a4d"
COR_ESCURA_DO_KIT = "#14573a"
COR_DO_KIT_EM_RGB = [31, 122, 77]
# A cor do logo de teste (azul), em RGB
COR_DO_LOGO_EM_RGB = [26, 79, 214]
# Quanto esperar uma publicação (a primeira carrega o modelo de embeddings do catálogo; em milissegundos)
ESPERA_DA_PUBLICACAO = 60000


def criar_png_de_uma_cor(caminho, largura: int, altura: int, cor: list) -> None:
    """Grava um PNG de uma cor só (sem biblioteca de imagem), para servir de logo de teste.

    Recebe: o caminho do arquivo; a largura e a altura em pixels; a cor em RGB (ex.: [26, 79, 214]). Devolve: nada.
    Como um PNG é montado: a assinatura fixa do formato e três "pedaços" (cabeçalho, pixels comprimidos e fim), cada
    um com o tamanho, o nome, o conteúdo e um código de conferência (CRC).
    """
    def pedaco(nome: bytes, conteudo: bytes) -> bytes:
        """Um pedaço do PNG: tamanho, nome, conteúdo e o código de conferência."""
        conferencia = zlib.crc32(nome + conteudo) & 0xFFFFFFFF
        return struct.pack(">I", len(conteudo)) + nome + conteudo + struct.pack(">I", conferencia)

    # Cada linha de pixels começa com o byte 0 ("sem filtro") e repete a cor em toda a largura
    linha_de_pixels = b"\x00" + bytes(cor) * largura
    pixels = linha_de_pixels * altura
    # O cabeçalho: largura, altura, 8 bits por cor, tipo 2 (RGB), sem compressão especial, filtro e entrelaçamento
    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    assinatura_do_png = b"\x89PNG\r\n\x1a\n"
    conteudo = assinatura_do_png + pedaco(b"IHDR", cabecalho) + pedaco(b"IDAT", zlib.compress(pixels)) + pedaco(b"IEND", b"")
    caminho.write_bytes(conteudo)


def preparar() -> dict:
    """Os usuários de teste, o arquivo do logo (um PNG azul) e um arquivo falso (um texto com o nome .png).

    A KB do kit da Aurora já vem do projeto (data/kbs_endomarketing/EMP001/kit_da_marca.md) e entra publicada no
    banco novo; o roteiro faz as versões novas pela tela.
    """
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    pasta = pasta_do_roteiro()
    # O logo de teste: um quadrado azul de 64 × 64 pixels
    caminho_do_logo = pasta / "logo_aurora.png"
    criar_png_de_uma_cor(caminho_do_logo, 64, 64, COR_DO_LOGO_EM_RGB)
    # O arquivo falso: só texto, com o nome de imagem (a tela confere a assinatura, não o nome)
    caminho_do_falso = pasta / "logo_falso.png"
    caminho_do_falso.write_text("isto não é uma imagem", encoding="utf-8")
    return {"logo": str(caminho_do_logo), "falso": str(caminho_do_falso)}


def logo_desenhado_na_faixa(aba) -> bool:
    """Procura, na linha do meio da faixa de cima (da metade da arte para a direita), um pixel da cor do logo."""
    return aba.evaluate("""(cor_do_logo) => {
        const canvas = document.querySelector('[data-previa-arte]');
        const contexto = canvas.getContext('2d');
        const meio_da_faixa = Math.floor(canvas.height * 0.14 / 2);
        const linha = contexto.getImageData(0, meio_da_faixa, canvas.width, 1).data;
        for (let coluna = Math.floor(canvas.width / 2); coluna < canvas.width; coluna = coluna + 1) {
            const posicao = coluna * 4;
            if (linha[posicao] === cor_do_logo[0] && linha[posicao + 1] === cor_do_logo[1]
                && linha[posicao + 2] === cor_do_logo[2]) {
                return true;
            }
        }
        return false;
    }""", COR_DO_LOGO_EM_RGB)


def cor_do_alto_da_faixa(aba) -> list:
    """A cor de um pixel da faixa de cima da arte: no meio da largura e bem no alto (longe da marca e do logo)."""
    return aba.evaluate("""() => {
        const canvas = document.querySelector('[data-previa-arte]');
        const pixel = canvas.getContext('2d').getImageData(Math.floor(canvas.width / 2), 5, 1, 1).data;
        return [pixel[0], pixel[1], pixel[2]];
    }""")


def abrir_editor_da_versao_nova(aba) -> None:
    """Pelo "Editar na KB →" do Kit em uso, abre a KB do kit e o editor da versão nova."""
    aba.click("[data-editar-kit-na-kb]")
    aba.locator("#janela-kb[open]").wait_for(timeout=15000)
    aba.locator("[data-kb-botoes]").get_by_role("button", name="Editar (versão nova)").click()
    aba.locator("#janela-editor-kb[open]").wait_for(timeout=10000)


def salvar_no_editor(aba) -> None:
    """Clica em "Salvar rascunho" e espera o editor fechar e a janela da versão salva abrir."""
    aba.click("[data-editor-salvar]")
    aba.locator("#janela-editor-kb[open]").wait_for(state="detached", timeout=20000)
    aba.locator("#janela-kb[open]").wait_for(timeout=15000)


def publicar_rascunho_aberto(aba, conferir) -> None:
    """Publica o rascunho aberto na janela da KB e espera a janela mostrar essa versão publicada (ou o erro)."""
    versao = aba.evaluate("() => estado_das_kbs.kb_aberta.versao")
    linha = aba.locator("[data-kb-versoes] li", has_text="Rascunho v" + str(versao))
    linha.get_by_role("button", name="Publicar").click()
    aba.wait_for_function("""(versao) => (estado_das_kbs.kb_aberta.versao === versao
        && estado_das_kbs.kb_aberta.situacao === 'PUBLICADA') || !document.querySelector('[data-kb-erro]').hidden""",
                          arg=versao, timeout=ESPERA_DA_PUBLICACAO)
    conferir("a versão " + str(versao) + " do kit foi publicada (" + aba.inner_text("[data-kb-erro]") + ")",
             aba.locator("[data-kb-erro]").is_hidden())
    # Fecha a janela: a guia do material fica à vista de novo
    aba.click("#janela-kb .janela-cabecalho [data-fechar-janela]")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Troca as cores e o logo pela KB do kit, olha o Kit em uso e a arte, tira o logo e confere a ficha sem a aba."""
    aba = abrir_endomarketing_do_banco(navegador, endereco, erros_da_pagina)
    janelas_nativas = []

    def anotar_janela_nativa(janela) -> None:
        """Anota a mensagem da janela nativa e a fecha (para o roteiro não travar)."""
        janelas_nativas.append(janela.message)
        janela.dismiss()

    aba.on("dialog", anotar_janela_nativa)

    # 1. O Kit em uso, só para ler, e o botão antigo fora da tela
    aba.locator("[data-kit-em-uso]:not([hidden])").wait_for(timeout=20000)
    nome_do_kit = aba.inner_text("[data-kit-em-uso-nome]")
    conferir("o Kit em uso aparece na guia do material (" + nome_do_kit + ")", nome_do_kit.startswith("Kit em uso:"))
    conferir("o Kit em uso não tem campo de edição",
             aba.locator("[data-kit-em-uso] input, [data-kit-em-uso] select, [data-kit-em-uso] textarea").count() == 0)
    conferir("o botão antigo 'Mudar o kit ou o logo' saiu", aba.get_by_text("Mudar o kit ou o logo").count() == 0)

    # 2. "Editar na KB →" abre a KB do kit da Aurora, com as cores da versão
    aba.click("[data-editar-kit-na-kb]")
    aba.locator("#janela-kb[open]").wait_for(timeout=15000)
    # text_content: o texto do elemento como está no HTML (o CSS mostra o sobretítulo em maiúsculas)
    sobretitulo = aba.text_content("[data-kb-sobretitulo]")
    conferir("o link abre a KB do kit da marca (" + sobretitulo + ")", "Kit da marca" in sobretitulo)
    conferir("a janela da KB mostra as amostras das cores do kit",
             aba.locator("[data-kb-kit]:not([hidden]) [data-kb-kit-cores] span").count() > 0)

    # 3. O editor da versão nova: sem o caminho do logo, com o bloco do logo
    aba.locator("[data-kb-botoes]").get_by_role("button", name="Editar (versão nova)").click()
    aba.locator("#janela-editor-kb[open]").wait_for(timeout=10000)
    conferir("o editor não tem mais o campo do caminho do logo", aba.locator("[data-editor-campo='logo']").count() == 0)
    conferir("o editor do kit tem o bloco do logo", aba.locator("[data-logo-do-editor]").is_visible())

    # 4. Um texto renomeado para .png é recusado na hora
    aba.set_input_files("[data-arquivo-logo-do-editor]", dados["falso"])
    aba.locator("[data-erro-logo-do-editor]:not([hidden])").wait_for(timeout=10000)
    conferir("o arquivo falso é recusado (" + aba.inner_text("[data-erro-logo-do-editor]") + ")",
             "PNG ou JPEG" in aba.inner_text("[data-erro-logo-do-editor]"))

    # 5. A escolha, as cores (com as amostras) e o logo de verdade
    aba.select_option("[data-editor-campo='kit_escolhido']", "proprio")
    aba.fill("[data-editor-campo='cores']", COR_DO_KIT + ", " + COR_ESCURA_DO_KIT)
    conferir("as duas cores digitadas viram duas amostras", aba.locator("[data-amostras-do-editor] span").count() == 2)
    aba.set_input_files("[data-arquivo-logo-do-editor]", dados["logo"])
    aba.locator("[data-previa-logo-do-editor]:not([hidden])").wait_for(timeout=10000)
    conferir("a prévia do logo escolhido aparece, com o 'Tirar o logo' e sem erro",
             aba.locator("[data-tirar-logo-do-editor]").is_visible()
             and aba.locator("[data-erro-logo-do-editor]").is_hidden())

    # 6. A trava não acusa "kit sem logo" com o logo escolhido (ele vai junto ao salvar)
    aba.click("[data-editor-conferir]")
    aba.wait_for_function("""() => !document.querySelector('[data-editor-erro]').hidden
        || !document.querySelector('[data-editor-achados]').hidden""", timeout=15000)
    achados = aba.inner_text("[data-editor-achados]")
    conferir("a trava não fala de 'sem logo' (" + achados[:120] + ")", "sem logo" not in achados)

    # 7. Salvar: o rascunho abre com o logo; publicar aplica o kit na empresa
    salvar_no_editor(aba)
    aba.locator("[data-kb-kit-logo]:not([hidden])").wait_for(timeout=15000)
    conferir("a janela do rascunho mostra o logo desta versão, sem erro do logo",
             aba.locator("[data-kb-kit-logo]").is_visible() and aba.locator("[data-kb-erro]").is_hidden())
    publicar_rascunho_aberto(aba, conferir)

    # 8. O Kit em uso muda sozinho: próprio da Aurora, verde e com o logo
    aba.wait_for_function("""(cor) => document.querySelector('[data-kit-em-uso-detalhe]').innerText.includes(cor)
        && !document.querySelector('[data-kit-em-uso-logo]').hidden""", arg=COR_DO_KIT, timeout=20000)
    nome_do_kit = aba.inner_text("[data-kit-em-uso-nome]")
    conferir("o Kit em uso passa a 'próprio da Aurora' (" + nome_do_kit + ")", "próprio da Aurora" in nome_do_kit)

    # 9. A arte do rascunho: a faixa na cor do kit e o logo desenhado
    gerou = gerar_rascunho(aba, "comunicado", "whatsapp", ["Salário antecipado"])
    conferir("o rascunho foi gerado", gerou)
    if gerou:
        kit_visual = aba.inner_text("[data-kit-visual]")
        conferir("a tela diz o kit da Aurora, definido pelo banco (" + kit_visual + ")",
                 "Kit da Aurora" in kit_visual and "definido pelo banco" in kit_visual)
        cor = cor_do_alto_da_faixa(aba)
        conferir("a faixa da arte sai na cor do kit (" + str(cor) + ")", cor == COR_DO_KIT_EM_RGB)
        conferir("a arte anota que o logo entrou",
                 aba.get_attribute("[data-previa-arte]", "data-arte-com-logo") == "sim")
        conferir("o logo aparece desenhado na faixa (pixel azul à direita)", logo_desenhado_na_faixa(aba))

    # 10. Tirar o logo numa versão nova: o editor parte do logo da publicada
    abrir_editor_da_versao_nova(aba)
    aba.locator("[data-previa-logo-do-editor]:not([hidden])").wait_for(timeout=15000)
    conferir("o editor mostra o logo da versão publicada", aba.locator("[data-tirar-logo-do-editor]").is_visible())
    aba.click("[data-tirar-logo-do-editor]")
    conferir("depois de 'Tirar o logo', o editor diz 'Nenhum logo nesta versão'",
             aba.locator("[data-sem-logo-no-editor]").is_visible()
             and aba.locator("[data-previa-logo-do-editor]").is_hidden())
    salvar_no_editor(aba)
    aba.wait_for_function("() => document.querySelector('[data-kb-kit-texto]').innerText.includes('Sem logo')",
                          timeout=15000)
    conferir("o rascunho novo ficou sem logo", aba.locator("[data-kb-kit-logo]").is_hidden())
    publicar_rascunho_aberto(aba, conferir)

    # 11. O Kit em uso fica sem logo, e a arte do rascunho aberto é redesenhada sem ele
    aba.wait_for_function("() => document.querySelector('[data-kit-em-uso-detalhe]').innerText.includes('sem logo')",
                          timeout=20000)
    conferir("o Kit em uso diz 'sem logo' e não mostra imagem", aba.locator("[data-kit-em-uso-logo]").is_hidden())
    if gerou:
        aba.wait_for_function("() => document.querySelector('[data-previa-arte]').dataset.arteComLogo === 'nao'",
                              timeout=15000)
        conferir("a arte do rascunho aberto foi redesenhada sem o logo",
                 aba.get_attribute("[data-previa-arte]", "data-arte-com-logo") == "nao")

    # 12. A ficha da empresa não tem mais a aba do kit (e o endereço antigo abre a Visão geral)
    aba.goto(endereco + "/banco_empresas.html?empresa=EMP001&aba=kit")
    aba.locator("[data-ficha-empresa][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    conferir("a ficha tem 6 abas, sem a do kit",
             aba.locator("[data-aba-ficha]").count() == 6 and aba.locator("[data-aba-ficha='kit']").count() == 0)
    conferir("o endereço antigo (?aba=kit) abre a Visão geral",
             aba.get_attribute("[data-aba-ficha='visao']", "aria-selected") == "true")
    conferir("nenhuma janela nativa do navegador (" + str(janelas_nativas) + ")", janelas_nativas == [])
    aba.close()
