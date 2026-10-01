"""Apoio dos roteiros de clique: a conversa de um cartão de Acompanhar, que abre numa janela por cima da tela (ADR-138).

Para que serve: os cartões da lista das pendências são compactos, e a conversa com o Agente de validação (a pergunta,
as respostas rápidas, a caixa, os botões do grupo e o Desfazer) abre numa janela (um <dialog> com a marca
data-painel-da-conversa). Os roteiros que conversavam "dentro do cartão" abrem o cartão e usam a janela.

Uso:
    painel = abrir_a_conversa(aba, cartao)          # clica no "Abrir a conversa" e devolve o painel
    painel.locator("[data-caixa-da-conversa]").fill("O certo é ...")
"""

# A janela com a conversa aberta (front/acompanhar.html)
SELETOR_DO_PAINEL = "[data-painel-da-conversa]"


def painel_da_conversa(aba):
    """A janela com a conversa (esteja ela aberta ou não)."""
    return aba.locator(SELETOR_DO_PAINEL)


def fechar_a_conversa_aberta(aba) -> None:
    """Fecha a janela da conversa, se ela estiver aberta.

    Recebe: a aba. Devolve: nada. Por que: com a janela por cima da tela, a tela de trás não recebe cliques (é uma
    janela como as outras do portal); o roteiro fecha a conversa antes de clicar em outro cartão, num filtro ou na grade.
    No computador fecha pelo X; no celular, pelo "Voltar à lista".
    """
    janela = painel_da_conversa(aba)
    if not janela.is_visible():
        return
    # O X de dentro da janela (a conversa do "Posso ajudar?" tem outro X com a mesma marca)
    fechar = janela.locator("[data-fechar-conversa]")
    if fechar.is_visible():
        fechar.click()
    else:
        janela.locator("[data-voltar-a-lista]").click()
    janela.wait_for(state="hidden", timeout=10000)


def abrir_a_conversa(aba, cartao):
    """Abre na janela a conversa do cartão (das abertas ou das resolvidas) e devolve a janela.

    Recebe: a aba; o cartão (um locator de [data-pendencia] ou [data-resolvida]). Devolve: o locator da janela.
    Se a conversa de outro cartão estiver aberta, ela fecha antes (a janela fica por cima do cartão).
    """
    fechar_a_conversa_aberta(aba)
    cartao.locator("[data-abrir-conversa]").click()
    painel = painel_da_conversa(aba)
    painel.wait_for(timeout=10000)
    return painel
