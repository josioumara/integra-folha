"""Servidor sem os índices do RAG (ex.: antes de rodar scripts/build_index.py): nada quebra.

Provam que:
- a busca avisa com um erro próprio (IndiceAusente) quando o índice não existe;
- o Endomarketing responde com uma mensagem clara, grava a execução como erro "IndiceAusente" e não
  guarda rascunho nenhum;
- o Assistente de Correção continua conversando, só que sem trechos de apoio.
"""

import pytest

from agents import assistente_correcao, endomarketing
from rag import busca as busca_rag
from services import auth, banco, execucoes
from tests.test_correcao import _achados_da_regra, _pendencia, busca_falsa, preparar_ate_a_validacao


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


def busca_sem_indice(*argumentos, **outros_argumentos):
    """Uma busca como a de um servidor novo: o índice ainda não existe."""
    raise busca_rag.IndiceAusente("O índice ainda não foi montado: rode scripts/build_index.py.")


def test_busca_sem_indice_avisa_com_erro_proprio(tmp_path):
    """Numa pasta de índices vazia, a busca no catálogo levanta IndiceAusente (e não um erro do ChromaDB)."""
    with pytest.raises(busca_rag.IndiceAusente, match="build_index"):
        busca_rag.buscar_beneficios("EMP001", "conta salário", pasta=tmp_path)


def test_endomarketing_sem_indice_avisa_e_nao_guarda_nada(tmp_path):
    """Sem o índice do catálogo: mensagem clara, execução com erro "IndiceAusente" e nenhum rascunho."""
    conexao = auth.conectar(tmp_path / "teste.db")
    resultado = endomarketing.gerar_material(conexao, "EMP001", "comunicado", "rh.aurora", busca=busca_sem_indice)
    assert resultado.situacao == endomarketing.INDISPONIVEL
    assert "ainda não está pronto" in resultado.mensagem
    assert resultado.material_id is None
    assert endomarketing.listar(conexao, "EMP001") == []
    ultima = execucoes.listar(conexao)[-1]
    assert ultima["status"] == execucoes.ERRO and ultima["tipo_erro"] == "IndiceAusente"
    conexao.close()


def test_assistente_sem_indice_continua_conversando(tmp_path, monkeypatch):
    """Sem o índice do layout, o Assistente responde a pergunta sobre a pendência, só que sem fontes do RAG."""
    # A preparação do arquivo (interpretação) usa a busca falsa; a conversa, a busca sem índice
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    conexao = banco.conectar(tmp_path / "teste.db")
    processamento_id = preparar_ate_a_validacao(conexao, "aurora_carga_inicial")
    cpf_invalido = _achados_da_regra(conexao, processamento_id, "CPF_INVALIDO")[0]
    resposta = assistente_correcao.conversar(conexao, processamento_id, "EMP001", _pendencia(cpf_invalido),
                                             "por que isso é um erro?", busca=busca_sem_indice)
    assert resposta.acao != "falha"
    assert not resposta.fontes
    conexao.close()


def test_build_que_falha_nao_deixa_indice_vazio(tmp_path, monkeypatch):
    """Se os vetores não puderem ser calculados (modelo não baixou), nenhum índice vazio fica para trás."""
    def modelo_que_nao_baixou(textos):
        """Como o fastembed quando o modelo não baixa."""
        raise ValueError("Could not load model from any source.")

    monkeypatch.setattr(busca_rag, "vetorizar", modelo_que_nao_baixou)
    trecho = busca_rag.Trecho("t1", "Campo cpf\nO CPF do funcionário", {"campo": "cpf"})
    with pytest.raises(ValueError, match="Could not load model"):
        busca_rag.gravar_colecao("colecao_teste", [trecho], pasta=tmp_path)
    assert not busca_rag.indice_disponivel("colecao_teste", pasta=tmp_path)
    nomes = []
    for colecao in busca_rag._abrir_banco_de_indices(tmp_path).list_collections():
        nomes.append(colecao.name)
    assert "colecao_teste" not in nomes


def test_indice_vazio_conta_como_indisponivel(tmp_path):
    """Uma coleção que existe mas não tem trechos não é "índice disponível"."""
    busca_rag._abrir_banco_de_indices(tmp_path).create_collection("colecao_vazia")
    assert not busca_rag.indice_disponivel("colecao_vazia", pasta=tmp_path)
