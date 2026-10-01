"""Roteiro: o "Lembrete para abrir a conta" pelo WhatsApp (ADR-93), gerado pelo banco (ADR-115).

O que ele confere, na aba Endomarketing do Portal Interno:
- a opção do lembrete diz que ele vai para toda a equipe;
- com o canal WhatsApp, o rascunho sai com no máximo 3 blocos, e o título fala com toda a equipe;
- a arte abre no molde do WhatsApp (cartão).
"""
from tests.e2e.roteiros.endomarketing_do_banco import abrir_endomarketing_do_banco, gerar_rascunho

DESCRICAO = "Lembrete de conta pelo WhatsApp: para toda a equipe, no máximo 3 blocos"


def preparar() -> dict:
    """Só os usuários de teste."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Escolhe o lembrete e o WhatsApp, gera e confere o rascunho."""
    aba = abrir_endomarketing_do_banco(navegador, endereco, erros_da_pagina)
    opcao = aba.locator("input[name='tipo-material'][value='lembrete_conta']")
    conferir("a opção do lembrete existe e diz 'toda a equipe'",
             opcao.count() == 1 and "toda a equipe" in (opcao.locator("xpath=ancestor::label[1]").get_attribute("title") or ""))
    # O WhatsApp diz na tela quantos trechos cabem
    canal = aba.locator("input[name='canal-material'][value='whatsapp']").locator("xpath=ancestor::label[1]")
    conferir("o canal WhatsApp diz o limite (" + canal.inner_text() + ")", "até 3 trechos" in canal.inner_text())
    gerou = gerar_rascunho(aba, "lembrete_conta", "whatsapp", ["Salário antecipado"])
    conferir("o rascunho foi gerado", gerou)
    if not gerou:
        conferir("aviso da tela: " + aba.inner_text("[data-avisos-material]")[:150], False)
        aba.close()
        return
    titulo = aba.inner_text("[data-titulo-material]")
    blocos = aba.locator("[data-corpo-material] .trecho-material").count()
    conferir("o título fala com toda a equipe (" + titulo + ")", "toda a equipe" in titulo)
    conferir("no WhatsApp, no máximo 3 blocos (" + str(blocos) + ")", 0 < blocos <= 3)
    molde = aba.get_attribute("[data-previa-arte]", "data-molde-desenhado")
    conferir("a arte abre no cartão para WhatsApp (" + str(molde) + ")", molde == "cartao")
    aba.close()
