"""Testes da avaliação do fluxo de ponta a ponta (ADR-59).

Rodam a avaliação inteira (9 arquivos + cenário de falha) uma vez, num banco temporário, e conferem:
- todo arquivo chega a HOMOLOGADO e todo erro injetado num campo obrigatório é achado na linha certa, sem achado a
  mais (o de campo opcional não vira pendência, ADR-143);
- as inclusões vêm depois das cargas e reaproveitam o mapeamento;
- nenhuma etapa é refeita quando o fluxo é reaberto do ponto de salvamento;
- o provedor fora do ar para o arquivo, sem falso sucesso;
- os proxies de negócio batem com as decisões contadas.
"""
import json

import pytest

from eval import avaliacao_do_fluxo
from services import banco
from tests.apoio_do_parametro import erros_que_viram_pendencia


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


def busca_falsa(texto, k=3, **outros_argumentos):
    """RAG de mentira, sem depender do índice nem do modelo de embeddings."""
    return [{"fonte": f"Mapeamentos homologados › {texto}", "campo": None,
             "texto": f"Mapeamentos homologados › {texto}\nex."}]


@pytest.fixture(scope="module")
def resultado(tmp_path_factory):
    """A avaliação inteira, rodada uma vez num banco novo."""
    conexao = banco.conectar(tmp_path_factory.mktemp("fluxo") / "avaliacao.db")
    medido = avaliacao_do_fluxo.avaliar(conexao, busca=busca_falsa)
    conexao.close()
    return medido


def test_todos_os_arquivos_chegam_a_homologacao(resultado):
    """Os 9 arquivos terminam HOMOLOGADOS."""
    resumo = resultado["resumo"]
    assert resumo["arquivos"] == 9
    assert resumo["concluidos"] == 9
    for arquivo in resultado["arquivos"]:
        assert arquivo["status_final"] == "HOMOLOGADO"


def test_todo_erro_injetado_e_achado_e_nada_alem(resultado):
    """Cada erro do gabarito num campo obrigatório aparece na linha certa, e nenhum achado fica fora do gabarito.

    O erro num campo opcional não vira pendência (ADR-143): o gabarito continua o mesmo, e o filtro é o layout (a
    matrícula repetida da Vale Verde não é achada, porque a matrícula é opcional).
    """
    resumo = resultado["resumo"]
    assert resumo["erros_injetados"] > 0
    gabaritos = avaliacao_do_fluxo.carregar_gabaritos()
    for arquivo in resultado["arquivos"]:
        esperados = erros_que_viram_pendencia(gabaritos[arquivo["arquivo"]])
        assert arquivo["erros_achados"] == len(esperados), arquivo["arquivo"]
    assert resumo["achados_fora_do_gabarito"] == 0


def test_inclusoes_vem_depois_e_reaproveitam_o_mapeamento(resultado):
    """As cargas iniciais vêm antes; cada inclusão reaproveita colunas do mapeamento já aprovado."""
    tipos_na_ordem = []
    for arquivo in resultado["arquivos"]:
        tipos_na_ordem.append(arquivo["tipo_carga"])
        if arquivo["tipo_carga"] == "INCLUSAO":
            assert arquivo["colunas_reusadas"] > 0
    primeira_inclusao = tipos_na_ordem.index("INCLUSAO")
    assert "INCLUSAO" not in tipos_na_ordem[:primeira_inclusao]
    assert set(tipos_na_ordem[primeira_inclusao:]) == {"INCLUSAO"}


def test_retomar_do_ponto_de_salvamento_nao_refaz_etapas(resultado):
    """Toda decisão foi entregue a um fluxo reaberto, e o Interpretador rodou uma vez por arquivo."""
    resumo = resultado["resumo"]
    # Pelo menos o aceite e a homologação de cada arquivo
    assert resumo["retomadas"] >= 2 * resumo["arquivos"]
    assert resumo["etapas_refeitas_na_retomada"] == 0
    assert resumo["erros_por_etapa"] == {}


def test_provedor_fora_do_ar_para_o_arquivo_sem_falso_sucesso(resultado):
    """No cenário de falha, o fluxo para esperando "tentar de novo", com o erro na interpretação."""
    falha = resultado["cenario_de_falha"]
    assert falha["parou_em"] == "aguardar_nova_tentativa"
    assert falha["etapa_com_falha"] == "interpretar"
    assert falha["etapas_com_erro"] == ["interpretar"]
    assert falha["virou_sucesso"] is False


def test_proxies_de_negocio_batem_com_as_decisoes(resultado):
    """"Sem edição manual" = nenhum valor corrigido e nenhuma linha excluída; a soma bate com o resumo."""
    sem_edicao = 0
    for arquivo in resultado["arquivos"]:
        intervencoes = arquivo["intervencoes"]
        sem_edicao_esperado = intervencoes["valores_corrigidos"] == 0 and intervencoes["linhas_excluidas"] == 0
        assert arquivo["sem_edicao_manual"] == sem_edicao_esperado
        # Toda carga passa por um aceite e uma homologação feitos por pessoa
        assert intervencoes["aceite"] == 1 and intervencoes["homologacao"] == 1
        if arquivo["sem_edicao_manual"]:
            sem_edicao += 1
    assert resultado["resumo"]["homologados_sem_edicao_manual"] == sem_edicao


def test_cpf_errado_e_corrigido_pela_pessoa_e_nao_pela_ia(resultado):
    """Aurora: o CPF inválido só some com uma correção aprovada pela pessoa (valor corrigido = 1)."""
    aurora = None
    for arquivo in resultado["arquivos"]:
        if arquivo["arquivo"] == "aurora_carga_inicial":
            aurora = arquivo
    assert aurora["intervencoes"]["valores_corrigidos"] == 1
    assert aurora["sem_edicao_manual"] is False


def test_resultado_gravado_mostra_o_fluxo_completo():
    """O resultado gravado pelo script (usado no Painel) tem os 9 arquivos concluídos."""
    gravado = json.loads((avaliacao_do_fluxo.RAIZ / "data" / "avaliacao" / "resultados" / "fluxo.json")
                         .read_text(encoding="utf-8"))
    assert gravado["modo"] == "MOCK"
    assert gravado["resumo"]["concluidos"] == gravado["resumo"]["arquivos"] == 9
