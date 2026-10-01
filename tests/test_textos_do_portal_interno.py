"""Testes de três textos do Portal Interno: a tela fala com o especialista do banco, sem os termos de quem construiu.

Lê o HTML das páginas, sem os comentários e sem navegador, e confere:
    - a nota do modelo em uso (Acompanhamento dos agentes) começa com "Em uso:", sem "plano B" nem "hoje";
    - o título do EXP-011 (a linha do tempo dos experimentos) diz o resultado, sem falar da máquina de quem mediu;
    - a página de desvio da antiga tela "Benefícios e KBs" diz onde as KBs ficam, sem recado de mudança.
"""
import re

from api.principal import PASTA_DO_FRONT

# Um comentário do HTML inteiro (<!-- ... -->). O "?" pega o menor pedaço; re.DOTALL deixa o "." passar de linha
PADRAO_DO_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)


def texto_da_pagina(nome_da_pagina: str) -> str:
    """O HTML de uma página do front, sem os comentários: o que a tela mostra, e não o que o código explica.

    Recebe: o nome do arquivo (ex.: "banco_agentes.html"). Devolve: o HTML sem os comentários.
    """
    # Lê o arquivo da página, do jeito que o servidor entrega
    html = (PASTA_DO_FRONT / nome_da_pagina).read_text(encoding="utf-8")
    # Tira os comentários, que não aparecem na tela
    return PADRAO_DO_COMENTARIO.sub("", html)


def test_a_nota_do_modelo_em_uso_fala_so_do_modelo():
    """A nota do Acompanhamento dos agentes diz o modelo em uso, sem "plano B" nem "hoje"."""
    # O que a página do Acompanhamento dos agentes mostra
    html = texto_da_pagina("banco_agentes.html")
    # A nota começa com "Em uso:" e diz os dois modelos
    assert "<strong>Em uso:</strong> Claude Sonnet 4.6 no papel do modelo grande e Amazon Nova 2 Lite" in html
    # Nenhum termo do desenvolvimento na nota
    assert "Em uso hoje" not in html
    assert "(plano B, ADR-107)" not in html


def test_o_titulo_do_exp_011_diz_o_resultado_sem_a_maquina_de_quem_mediu():
    """Na linha do tempo dos experimentos, o EXP-011 diz o resultado do modelo local, sem "nesta máquina"."""
    # O que a página do Acompanhamento dos agentes mostra
    html = texto_da_pagina("banco_agentes.html")
    # O título, com o resultado no passado (é um experimento já feito)
    assert "<td>Modelo local: o dado não sai, mas a leitura não funcionou</td>" in html
    # A tela não fala do computador de quem mediu
    assert "nesta máquina" not in html


def test_o_desvio_da_antiga_tela_de_kbs_diz_onde_elas_ficam():
    """A página de desvio (banco_beneficios.html) diz onde as KBs ficam, sem recado de mudança."""
    # O que a página de desvio mostra, se o navegador não seguir sozinho
    html = texto_da_pagina("banco_beneficios.html")
    # O texto diz onde as KBs ficam, e o link para o Endomarketing continua
    assert "As KBs ficam nas guias do Endomarketing." in html
    assert 'href="banco_endomarketing.html?aba=regras"' in html
    # Sem o recado de mudança: quem abre a página não precisa saber onde as KBs ficavam
    assert "agora ficam" not in html
