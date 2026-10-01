"""Testes da tela "Acompanhamento dos agentes" (front/banco_agentes.html e o js dela), lendo os arquivos, sem navegador.

O que se prova aqui:
    - só o modelo real: a tela não tem mais o selo nem as linhas do modo simulado (MOCK), e o agente sem execução com o
      modelo real diz isso, sem enganar ("Sem execuções com o modelo real no período");
    - ocultos nesta versão (ADR-148), com o código guardado: a qualidade do Interpretador (o registro fixo do EXP-008),
      numa caixa <template>, e os quatro números de custo do alto, com "hidden" (o script ainda escreve neles);
    - a frase "Um registro por experimento, nunca sobrescrito" saiu;
    - com o cartão do teto oculto, a faixa do teto de custo passa a aparecer nesta tela, como nas outras;
    - os números dos Guardrails das KBs esperam o dado (a barra cinza), nunca mostram um zero antes da hora.
O roteiro de clique acompanhamento_dos_agentes confere o mesmo no Chrome, com os dados.
"""
import re

from api.principal import PASTA_DO_FRONT

# Um comentário do HTML inteiro (<!-- ... -->). O "?" pega o menor pedaço; re.DOTALL deixa o "." passar de linha
PADRAO_DO_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
# Uma caixa <template ...>...</template> inteira
PADRAO_DA_CAIXA = re.compile(r"<template\b[^>]*>.*?</template>", re.DOTALL)
# A abertura da seção dos números de custo do alto
PADRAO_DA_GRADE_DE_CUSTOS = re.compile(r'<section class="grade-numeros" aria-label="Custo e uso dos agentes"[^>]*>')


def html_da_pagina() -> str:
    """O HTML da página, sem os comentários (o que o navegador lê)."""
    texto = (PASTA_DO_FRONT / "banco_agentes.html").read_text(encoding="utf-8")
    return PADRAO_DO_COMENTARIO.sub("", texto)


def html_a_vista() -> str:
    """O HTML que o navegador desenha: sem os comentários e sem as caixas <template>."""
    return PADRAO_DA_CAIXA.sub("", html_da_pagina())


def codigo_do_script(nome: str) -> str:
    """O texto de um script da pasta front/js (ex.: "banco_agentes.js")."""
    return (PASTA_DO_FRONT / "js" / nome).read_text(encoding="utf-8")


def test_a_qualidade_do_interpretador_fica_numa_caixa_oculta():
    # Guardada na caixa, com a marca de oculto nesta versão: o código fica, para voltar rápido numa evolução
    caixas = PADRAO_DA_CAIXA.findall(html_da_pagina())
    caixa_da_qualidade = []
    for caixa in caixas:
        if 'data-oculto-nesta-versao="qualidade-do-interpretador"' in caixa:
            caixa_da_qualidade.append(caixa)
    assert len(caixa_da_qualidade) == 1
    assert 'id="titulo-qualidade"' in caixa_da_qualidade[0] and "EXP-008" in caixa_da_qualidade[0]
    # Fora da caixa, nada dela aparece
    assert 'id="titulo-qualidade"' not in html_a_vista()
    assert "Qualidade do Interpretador" not in html_a_vista()


def test_os_quatro_numeros_de_custo_ficam_ocultos_com_o_codigo():
    html = html_da_pagina()
    abertura = PADRAO_DA_GRADE_DE_CUSTOS.search(html)
    # A seção continua na página, com a marca e o "hidden" (o script ainda escreve nela)
    assert abertura is not None
    assert 'data-oculto-nesta-versao="custos-do-alto"' in abertura.group(0) and " hidden" in abertura.group(0)
    # Os quatro números continuam lá dentro, com os mesmos seletores que o script usa
    for seletor in ("data-teto-de-gasto", "data-custo-do-periodo", "data-link-ajustar-teto"):
        assert seletor in html
    assert "US$ 6,21" in html


def test_a_frase_do_registro_dos_experimentos_saiu():
    texto = (PASTA_DO_FRONT / "banco_agentes.html").read_text(encoding="utf-8")
    assert "nunca sobrescrito" not in texto
    # A linha do tempo continua
    assert "Linha do tempo dos experimentos" in html_a_vista()


def test_a_tela_nao_mostra_mais_o_modo_simulado():
    html = html_a_vista()
    script = codigo_do_script("banco_agentes.js")
    # Nem os exemplos do protótipo nem o script falam mais do modo simulado no cartão
    for texto in ("Simulada (MOCK)", "Simuladas (MOCK)", "Modelo real e simulado", "não medido (MOCK)"):
        assert texto not in html and texto not in script
    # O agente sem execução com o modelo real diz isso, sem enganar (nada de "Não trabalhou")
    assert "Sem execuções com o modelo real no período." in script
    assert "Ainda sem execuções com o modelo real." in script
    assert "Não trabalhou no período" not in script and "Ainda não trabalhou" not in script
    # A nota dos cartões explica o que fica de fora
    assert "as simuladas (MOCK) e os dados carregados sem os agentes não contam" in html


def test_o_custo_das_execucoes_diz_sem_modelo_nas_etapas_sem_ia():
    script = codigo_do_script("banco_agentes.js")
    assert 'const TEXTO_DA_ETAPA_SEM_MODELO = "sem modelo";' in script
    # O texto do período fala do custo por etapa (o custo do período está oculto)
    assert "os cartões, o custo por etapa e as execuções recentes" in script
    assert "os cartões, o custo por etapa e as execuções recentes" in html_a_vista()


def test_nada_fica_esperando_para_sempre_nos_numeros_ocultos():
    script = codigo_do_script("banco_agentes.js")
    # O teto de gasto (oculto) também sai da espera e vira "—" se o servidor falhar
    assert 'marcar_como_carregado(document.querySelector("[data-teto-de-gasto]"));' in script
    assert 'document.querySelector("[data-teto-de-gasto]").textContent = "—";' in script


def test_a_faixa_do_teto_aparece_nesta_tela():
    # Sem o cartão do teto à vista, a faixa amarela avisa quando os agentes estão pausados, como nas outras telas
    assert '<script src="js/aviso_do_teto_da_ia.js"></script>' in html_a_vista()


def test_os_numeros_dos_guardrails_das_kbs_esperam_o_dado():
    html = html_a_vista()
    for seletor in ("data-kbs-bloqueios", "data-kbs-avisos", "data-kbs-afetadas"):
        assert re.search(seletor + r" data-aguarda-dado>", html), seletor
    assert "data-tabela-achados-kbs data-aguarda-bloco" in html
    script = codigo_do_script("banco_agentes_kbs.js")
    # Os números vêm dos totais do servidor; sem resposta, "—" (nunca um zero inventado)
    assert "resposta.dados.totais" in script and "mostrar_dado_indisponivel" in script
