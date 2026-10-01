"""Roteiro: a arte no formato do canal e fiel ao texto do material (ADR-87), na aba Endomarketing do Portal Interno
(ADR-115; só a arte do canal escolhido).

O que ele confere, depois de o especialista gerar um material em cada canal (IA simulada):
- não há mais a escolha do molde: aparece só a arte do canal do rascunho, no tamanho dele (e-mail → banner
  1200 × 400; mural → cartaz A4 1240 × 1754; WhatsApp → imagem quadrada 1080 × 1080), e a tela diz o formato;
- o título da arte é o título do material; a frase é o texto de um bloco; o rodapé é a fonte desse bloco; fora isso,
  só a marca (e a assinatura) do kit. Nenhum texto novo aparece na imagem;
- "Abrir rascunho" num rascunho de outro canal troca a arte para o formato daquele canal;
- a arte não escreve o nome do canal entre parênteses: um título "... (E-mail)" aparece na arte sem o parêntese;
- a arte tem o texto no rótulo de acessibilidade.
"""
from tests.e2e.roteiros.endomarketing_do_banco import abrir_endomarketing_do_banco, esperar_arte_no_molde, gerar_rascunho

DESCRICAO = "Arte no formato do canal e fiel ao texto: só a arte do canal, sem o canal entre parênteses na imagem"
# A marca do kit (o único texto da arte que não vem do material, fora a assinatura do kit próprio)
MARCA_DO_KIT = "Santander"
# O benefício do catálogo da Aurora que entra nos materiais
BENEFICIO = "Salário antecipado"
# Cada canal: o molde da arte e o tamanho real da imagem (largura, altura), em pixels
FORMATO_DO_CANAL = {
    "email": ("email", 1200, 400),
    "mural": ("cartaz", 1240, 1754),
    "whatsapp": ("cartao", 1080, 1080),
}


def preparar() -> dict:
    """Só os usuários de teste."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def textos_fora_do_material(aba) -> list:
    """Os textos da arte que NÃO vêm do material aberto (a lista vazia quer dizer: arte fiel).

    Compara o que a arte anotou (data-textos-da-arte) com o título, os blocos e as fontes do rascunho na tela, do jeito
    que vão para a arte: sem o nome do canal entre parênteses (texto_sem_o_canal, do js/arte_do_material.js).
    """
    return aba.evaluate("""(marca) => {
        const textos = JSON.parse(document.querySelector('[data-previa-arte]').dataset.textosDaArte);
        const material = estado_do_endomarketing.rascunho;
        const permitidos = new Set([marca, texto_sem_o_canal(material.titulo)]);
        const assinatura = estado_do_endomarketing.dados.kit.assinatura;
        if (assinatura) {
            permitidos.add(assinatura);
        }
        for (const bloco of material.blocos) {
            permitidos.add(texto_sem_o_canal(bloco.texto));
            permitidos.add(texto_sem_o_canal('Fonte: ' + bloco.fontes.join('; ')));
        }
        return textos.filter(texto => !permitidos.has(texto));
    }""", MARCA_DO_KIT)


def tamanho_da_arte(aba) -> list:
    """O tamanho real da imagem da prévia: [largura, altura], em pixels."""
    return aba.evaluate("() => [document.querySelector('[data-previa-arte]').width,"
                        " document.querySelector('[data-previa-arte]').height]")


def textos_da_arte(aba) -> list:
    """Tudo o que a arte anotou que escreveu (data-textos-da-arte)."""
    return aba.evaluate("() => JSON.parse(document.querySelector('[data-previa-arte]').dataset.textosDaArte)")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Gera um material em cada canal e confere a arte; abre de novo o do e-mail; confere o título com o canal."""
    aba = abrir_endomarketing_do_banco(navegador, endereco, erros_da_pagina)
    conferir("não há mais a escolha do molde (só a arte do canal)", aba.locator("[data-modelo-arte]").count() == 0)

    # 1. Um rascunho em cada canal: a arte tem o formato do canal e o texto do material
    rascunhos_por_canal = {}
    for canal, (molde, largura, altura) in FORMATO_DO_CANAL.items():
        # O benefício é marcado só na primeira vez: a caixa continua marcada (um segundo clique a desmarcaria)
        beneficios = []
        if not rascunhos_por_canal:
            beneficios = [BENEFICIO]
        gerou = gerar_rascunho(aba, "comunicado", canal, beneficios)
        conferir(canal + ": o rascunho foi gerado (" + aba.inner_text("[data-titulo-material]")[:80] + ")", gerou)
        if not gerou:
            continue
        rascunhos_por_canal[canal] = aba.evaluate("() => estado_do_endomarketing.rascunho.material_id")
        esperar_arte_no_molde(aba, molde)
        tamanho = tamanho_da_arte(aba)
        conferir(canal + ": a arte tem o formato do canal (" + str(tamanho) + ")", tamanho == [largura, altura])
        formato = aba.inner_text("[data-formato-da-arte]")
        conferir(canal + ": a tela diz o formato (" + formato + ")", str(largura) + " × " + str(altura) in formato)
        fora = textos_fora_do_material(aba)
        conferir(canal + ": todo texto da arte vem do material (" + str(fora) + ")", fora == [])

    # 2. "Abrir rascunho" no do e-mail (a arte aberta é a do último canal): a arte volta a ser o banner
    if "email" in rascunhos_por_canal and len(rascunhos_por_canal) > 1:
        linha = aba.locator("[data-lista-materiais] [data-material-id='" + rascunhos_por_canal["email"] + "']")
        linha.get_by_role("button", name="Abrir rascunho").click()
        esperar_arte_no_molde(aba, "email")
        tamanho = tamanho_da_arte(aba)
        conferir("'Abrir rascunho' do e-mail troca a arte para o banner (" + str(tamanho) + ")", tamanho == [1200, 400])

    # 3. Um título com o canal entre parênteses: a arte o escreve sem o parêntese
    if rascunhos_por_canal:
        titulo = aba.evaluate("() => estado_do_endomarketing.rascunho.titulo")
        molde_aberto = aba.evaluate("() => estado_do_endomarketing.molde")
        # Só a memória da tela muda (nada é gravado): o título ganha "(E-mail)" e a arte é desenhada de novo
        aba.evaluate("""() => {
            estado_do_endomarketing.rascunho.titulo = estado_do_endomarketing.rascunho.titulo + ' (E-mail)';
            desenhar_arte_do_rascunho();
        }""")
        esperar_arte_no_molde(aba, molde_aberto)
        textos = textos_da_arte(aba)
        com_o_canal = [texto for texto in textos if "(E-mail)" in texto]
        conferir("a arte não escreve o canal entre parênteses (" + str(com_o_canal) + ")", com_o_canal == [])
        conferir("o título continua na arte, sem o parêntese", titulo in textos)

    rotulo = aba.get_attribute("[data-previa-arte]", "aria-label")
    conferir("a arte tem o texto no rótulo de acessibilidade", rotulo.startswith("Prévia da arte: " + MARCA_DO_KIT))
    aba.close()
