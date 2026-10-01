"""Roteiro: as KBs de endomarketing (ADR-125) nas guias do Endomarketing do Portal Interno.

A antiga tela "Benefícios e KBs" foi aposentada: as KBs ficam nas guias "Base
de Conhecimento" (as da empresa) e "Regras gerais" (diretrizes gerais e Santander), e não há mais "Aplicar na
empresa" (publicar já atualiza a vitrine, o agente e o kit, sem mensagem).

O que ele confere:
- o endereço antigo (banco_beneficios.html?dono=EMP001) leva à guia Base de Conhecimento da Aurora;
- a guia Regras gerais mostra as 7 diretrizes gerais e, no Santander, a prateleira com a aba Benefícios primeiro;
- na Aurora, a aba Benefícios (6) aparece, não há botão "Aplicar", e a janela de um benefício mostra as seções e a
  marca "simulação";
- uma KB nova com um termo proibido é barrada pela trava ("Conferir na trava" mostra o achado);
- corrigida, a KB é salva como rascunho e NÃO aparece na vitrine da empresa;
- publicada, ela aparece na vitrine da empresa sozinha (o aviso não fala de "aplicar");
- retirada (com a confirmação numa janela da própria página), ela some da vitrine;
- a seção "Guardrails das KBs" do Acompanhamento dos agentes mostra o termo proibido que a trava apontou;
- a empresa não abre o endereço antigo nem o Endomarketing do banco (é levada para a página inicial dela);
- nenhuma janela nativa do navegador (alert, confirm) aparece.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = "KBs nas guias do Endomarketing: endereço antigo, regras gerais, trava, rascunho, vitrine, retirar e guardrails"
# O título da KB criada pelo roteiro
TITULO_DA_KB_NOVA = "Vale-cultura digital"
# O corpo da KB nova: primeiro com um termo proibido ("taxa zero"), depois corrigido
CORPO_COM_TERMO_PROIBIDO = """# Vale-cultura digital

## Resumo
Crédito mensal para cinema e livros, com taxa zero.

## Como funciona
O crédito cai no cartão todo mês.

## Quem pode usar
Todo o time da Aurora.

## Como contratar
Pelo aplicativo do banco.

## Condições
- Crédito de R$ 50 por mês (simulação).

## Mensagem principal
Cultura no seu mês.

## O que não dizer
- Que é dinheiro.
"""
CORPO_CORRIGIDO = CORPO_COM_TERMO_PROIBIDO.replace(", com taxa zero.", ", sem tarifa por 12 meses (simulação).")


def preparar() -> dict:
    """Só os usuários de teste: as KBs do projeto entram sozinhas no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def titulos_da_vitrine(aba, endereco: str) -> str:
    """Abre a vitrine "Benefícios do seu time" da empresa e devolve o texto dos cartões."""
    aba.goto(endereco + "/beneficios.html")
    aba.locator("[data-grade-beneficios][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    return aba.inner_text("[data-grade-beneficios]")


def abrir_guia(aba, guia: str) -> None:
    """Clica na guia ("base", "regras" ou "material") e, nas das KBs, espera a lista delas chegar."""
    aba.click("#botao-guia-" + guia)
    if guia != "material":
        aba.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Consulta, cria com a trava, publica, confere na vitrine, retira e confere a Telemetria."""
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    janelas_nativas = []

    def anotar_janela_nativa(janela) -> None:
        """Anota a mensagem da janela nativa e a fecha (para o roteiro não travar)."""
        janelas_nativas.append(janela.message)
        janela.dismiss()

    banco.on("dialog", anotar_janela_nativa)

    # 1. O endereço antigo leva à guia Base de Conhecimento da Aurora, com a aba Endomarketing marcada
    banco.goto(endereco + "/banco_beneficios.html?dono=EMP001")
    banco.wait_for_url("**/banco_endomarketing.html?empresa=EMP001&aba=base", timeout=10000)
    banco.locator("[data-area-da-empresa]:not([hidden])").wait_for(timeout=20000)
    banco.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    conferir("o endereço antigo abre a Base de Conhecimento da Aurora, com a aba Endomarketing marcada (5 abas)",
             banco.inner_text(".abas-banco .aba-ativa").strip() == "Endomarketing"
             and banco.locator(".abas-banco .aba").count() == 5
             and banco.get_attribute("#botao-guia-base", "aria-selected") == "true")

    # 2. A guia Regras gerais: as 7 diretrizes gerais e, no Santander, a prateleira (Benefícios primeiro)
    abrir_guia(banco, "regras")
    conferir("a guia Regras gerais abre nas diretrizes gerais, com as 7 KBs gerais",
             banco.locator("[data-escolha-das-regras]").is_visible()
             and banco.locator("[data-lista-kbs] li").count() == 7)
    banco.click("[data-dono-das-regras='SANTANDER']")
    banco.locator("[data-lista-kbs][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    conferir("no Santander, a primeira aba é a dos Benefícios (a prateleira)",
             banco.locator("[data-abas-tipos] button").first.inner_text().startswith("Benefícios")
             and banco.locator("[data-lista-kbs] li").count() > 0)
    conferir("a Base de Conhecimento e as Regras gerais não têm o botão 'Aplicar'",
             banco.locator("[data-aplicar-na-empresa]").count() == 0
             and banco.locator("[data-ultima-aplicacao]").count() == 0)

    # 3. De volta à Aurora: a aba dos benefícios e a janela de um benefício
    abrir_guia(banco, "base")
    conferir("a Aurora tem a aba Benefícios com 6", banco.locator("[data-abas-tipos] button",
                                                                    has_text="Benefícios (6)").count() == 1)
    banco.locator("[data-lista-kbs] li", has_text="Crédito consignado").get_by_role("button", name="Abrir").click()
    banco.locator("#janela-kb[open]").wait_for(timeout=10000)
    texto_da_janela = banco.inner_text("#janela-kb")
    conferir("a janela mostra as seções e a marca de simulação",
             "Condições" in texto_da_janela and "simulação" in texto_da_janela and "Versões" in texto_da_janela)
    banco.click("#janela-kb .janela-cabecalho [data-fechar-janela]")

    # 4. KB nova com termo proibido: a trava aponta
    banco.click("[data-nova-kb]")
    banco.locator("#janela-editor-kb[open]").wait_for(timeout=10000)
    banco.select_option('[data-editor-campo="tipo"]', "beneficio")
    banco.fill('[data-editor-campo="titulo"]', TITULO_DA_KB_NOVA)
    banco.fill('[data-editor-campo="vigencia_inicio"]', "2026-01-01")
    banco.fill('[data-editor-campo="vigencia_fim"]', "2099-12-31")
    banco.fill("[data-editor-corpo]", CORPO_COM_TERMO_PROIBIDO)
    banco.click("[data-editor-conferir]")
    banco.locator("[data-editor-achados]:not([hidden])").wait_for(timeout=10000)
    conferir("a trava aponta o termo proibido 'taxa zero'",
             "taxa zero" in banco.inner_text("[data-editor-achados]"))
    banco.click("[data-editor-salvar]")
    banco.locator("[data-editor-erro]:not([hidden])").wait_for(timeout=10000)
    conferir("salvar com o termo proibido é bloqueado", "bloqueou" in banco.inner_text("[data-editor-erro]"))

    # 5. Corrigida: vira rascunho, e a empresa ainda não vê
    banco.fill("[data-editor-corpo]", CORPO_CORRIGIDO)
    banco.click("[data-editor-salvar]")
    banco.locator("#janela-kb[open]").wait_for(timeout=15000)
    conferir("salvo como rascunho v1", "Rascunho v1" in banco.inner_text("[data-aviso-kbs]"))
    empresa = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    conferir("o rascunho não aparece na vitrine da empresa",
             TITULO_DA_KB_NOVA not in titulos_da_vitrine(empresa, endereco))

    # 6. Publicar: aparece na vitrine, sozinha
    banco.locator("[data-kb-versoes] li", has_text="Rascunho v1").get_by_role("button", name="Publicar").click()
    # A primeira publicação carrega o modelo de embeddings (para o catálogo do agente): pode levar alguns segundos
    banco.wait_for_function("""() => document.querySelector('[data-aviso-kbs-texto]').innerText.includes('publicada')
        || !document.querySelector('[data-kb-erro]').hidden""", timeout=60000)
    conferir("publicar não deu erro (" + banco.inner_text("[data-kb-erro]") + ")",
             banco.locator("[data-kb-erro]").is_hidden())
    conferir("o aviso não fala de aplicar (a atualização da empresa é transparente)",
             "plica" not in banco.inner_text("[data-aviso-kbs]"))
    conferir("publicada, a KB aparece na vitrine da empresa",
             TITULO_DA_KB_NOVA in titulos_da_vitrine(empresa, endereco))

    # 7. Retirar (confirmação na janela da página): some da vitrine
    banco.locator("#janela-kb[open]").wait_for(timeout=10000)
    banco.locator("[data-kb-botoes]").get_by_role("button", name="Retirar").click()
    banco.locator("#janela-confirmacao-kb[open]").wait_for(timeout=10000)
    banco.click("#janela-confirmacao-kb [data-confirmar-acao]")
    banco.locator("#janela-confirmacao-kb[open]").wait_for(state="detached", timeout=15000)
    conferir("retirada, a KB some da vitrine da empresa",
             TITULO_DA_KB_NOVA not in titulos_da_vitrine(empresa, endereco))

    # 8. O Acompanhamento dos agentes mostra o que a trava apontou
    banco.goto(endereco + "/banco_agentes.html")
    banco.locator("[data-corpo-achados-kbs] tr").first.wait_for(timeout=15000)
    conferir("a seção 'Guardrails das KBs' mostra o termo proibido",
             "Termo proibido" in banco.inner_text("[data-corpo-achados-kbs]"))

    # 9. A empresa não abre o endereço antigo nem o Endomarketing do banco
    empresa.goto(endereco + "/banco_beneficios.html")
    conferir("a empresa é levada para a página inicial dela (endereço antigo)", "banco_" not in empresa.url)
    empresa.goto(endereco + "/banco_endomarketing.html?aba=regras")
    conferir("a empresa é levada para a página inicial dela (Endomarketing do banco)", "banco_" not in empresa.url)
    conferir("nenhuma janela nativa do navegador (" + str(janelas_nativas) + ")", janelas_nativas == [])
    empresa.close()
    banco.close()
