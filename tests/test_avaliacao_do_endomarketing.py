"""Testes da avaliação do Agente de Endomarketing (ADR-61).

Com a busca de teste por palavras (sem índice nem modelo de embeddings), provam que:
- todo material de toda empresa sai com blocos que passam na conferência e só com fontes da empresa;
- destaque que o catálogo da empresa não traz é avisado, sem citar a outra empresa que o traz;
- destaque que o catálogo traz aparece citando a seção certa;
- todo bloco adulterado (número trocado, fonte inventada, fonte de outra empresa) é barrado e todo
  bloco original é mantido.
A medição com a busca REAL fica no script (scripts/avaliar_endomarketing.py) e no ADR-61.
"""
import json

import pytest

from eval import avaliacao_do_endomarketing
from services import auth
from tests.test_endomarketing import busca_por_palavras


@pytest.fixture(scope="module")
def resultado(tmp_path_factory):
    """A avaliação inteira com a busca por palavras, num banco novo com o catálogo inicial."""
    conexao = auth.conectar(tmp_path_factory.mktemp("endomarketing") / "avaliacao.db")
    medido = avaliacao_do_endomarketing.avaliar(conexao, busca=busca_por_palavras(conexao))
    conexao.close()
    return medido


def test_todo_material_sai_fiel_e_so_com_fontes_da_empresa(resultado):
    """18 materiais (6 empresas x 3 tipos), fidelidade 100% e nenhuma fonte de outra empresa."""
    resumo = resultado["resumo"]
    assert resumo["materiais"] == 18
    assert resumo["materiais_gerados"] == 18
    assert resumo["fidelidade"] == 1.0
    assert resumo["fontes_de_outra_empresa"] == 0


def test_destaque_fora_do_catalogo_e_avisado_sem_citar_a_outra_empresa(resultado):
    """Com a busca sem resultado, o pedido avisa e não cita a empresa que tem o assunto."""
    for destaque in resultado["destaques"]:
        if destaque["tipo"] == "fora_do_catalogo":
            assert destaque["avisou"] is True
            assert destaque["citou_fora"] is False


def test_destaque_no_catalogo_e_achado_na_secao_certa(resultado):
    """O assunto que o catálogo traz aparece num bloco que cita a seção dele, sem aviso."""
    assert resultado["resumo"]["destaques_no_catalogo"] == "4 de 4"


def test_guardrail_de_saida_barra_toda_adulteracao_e_mantem_os_originais(resultado):
    """Número trocado, fonte inventada e fonte de outra empresa: todos barrados; originais: todos mantidos."""
    adulteracoes = resultado["adulteracoes"]
    assert adulteracoes["originais"] > 0
    assert adulteracoes["originais_mantidos"] == adulteracoes["originais"]
    for tipo in ("numero_trocado", "fonte_inventada", "fonte_de_outra_empresa"):
        assert adulteracoes[tipo]["total"] > 0
        assert adulteracoes[tipo]["barrados"] == adulteracoes[tipo]["total"]


def test_fonte_de_outra_empresa_e_mesmo_de_outra_empresa(tmp_path):
    """A fonte usada na adulteração existe no catálogo, mas não no da empresa do material."""
    conexao = auth.conectar(tmp_path / "teste.db")
    trechos = avaliacao_do_endomarketing.trechos_por_empresa(conexao)
    conexao.close()
    fonte = avaliacao_do_endomarketing.fonte_de_outra_empresa(trechos, "EMP001")
    fontes_da_aurora = set()
    for trecho in trechos["EMP001"]:
        fontes_da_aurora.add(trecho["fonte"])
    assert fonte not in fontes_da_aurora


def test_resultado_gravado_com_a_busca_real_registra_o_limite_da_distancia():
    """O resultado do script (busca real) registra que nenhuma distância separa "tem" de "não tem"."""
    gravado = json.loads((avaliacao_do_endomarketing.CAMINHO_DOS_CASOS.parent / "resultados" / "endomarketing.json")
                         .read_text(encoding="utf-8"))
    distancias = gravado["distancias_de_destaque"]
    assert distancias["existe_limite_que_separa"] is False
    assert distancias["maior_quando_tem"] >= distancias["menor_quando_nao_tem"]
    assert gravado["resumo"]["fontes_de_outra_empresa"] == 0
