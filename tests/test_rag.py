"""Testes do RAG: cortes dos trechos, isolamento entre empresas, vigência e as 10 consultas de cada índice.

Os índices são montados numa pasta temporária, com o banco de teste, e usam o modelo de embeddings
local (storage/modelos/; baixado na primeira vez).
"""
import json
from datetime import date
from pathlib import Path

import pytest

from rag import busca
from rag.trechos import LIMITE_CARACTERES, trechos_catalogo
from scripts import build_index
from scripts.avaliar_rag import acertou

# As consultas de teste e o dia usado para a vigência do catálogo
RAIZ = Path(__file__).resolve().parent.parent
CONSULTAS = json.loads((RAIZ / "data" / "avaliacao" / "consultas_rag.json").read_text(encoding="utf-8"))
DIA = date.fromisoformat(CONSULTAS["dia"])


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    """Monta os dois índices numa pasta temporária (uma vez para o arquivo todo)."""
    raiz = tmp_path_factory.mktemp("rag")
    quantidades = build_index.main(caminho_banco=raiz / "teste.db", pasta=raiz / "indices")
    # Layout: 45 campos + 20 regras + 182 mapeamentos (cnpj_grupo e os seus 3 nomes de treino entraram no ADR-77; a
    # regra "Informação de cada pessoa ou igual para todos" entrou no ADR-124; a regra "Mínimo e máximo do parâmetro",
    # no ADR-128);
    # catálogo: 34 trechos (31 + 3 benefícios novos da Aurora); nenhum aprovado
    assert quantidades == {busca.COLECAO_LAYOUT: 45 + 20 + 182, busca.COLECAO_CATALOGO: 34,
                           busca.COLECAO_APROVADOS: 0}
    return raiz / "indices"


def _todos(pasta, colecao):
    """Todos os trechos gravados numa coleção."""
    return busca._abrir_banco_de_indices(pasta).get_collection(colecao).get()


def _nome_da_consulta(consulta: dict) -> str:
    """O nome do caso de teste: o começo da pergunta."""
    return consulta["pergunta"][:40]


def _consultas_conhecidas_do_layout() -> list[dict]:
    """As consultas do layout que têm resposta."""
    conhecidas = []
    for consulta in CONSULTAS["layout"]:
        if consulta["tipo"] == "conhecida":
            conhecidas.append(consulta)
    return conhecidas


def _algum_acerto(consulta: dict, resultados: list[dict]) -> bool:
    """True se algum trecho devolvido é a resposta certa da consulta."""
    for resultado in resultados:
        if acertou(consulta, resultado):
            return True
    return False


# ---------- Cortes ----------

def test_todo_trecho_comeca_pelo_caminho_de_origem(pasta):
    """Cada trecho começa pela fonte (ex.: "Layout v1 › cpf"), para a resposta poder citá-la."""
    for colecao in (busca.COLECAO_LAYOUT, busca.COLECAO_CATALOGO):
        dados = _todos(pasta, colecao)
        for texto, metadados in zip(dados["documents"], dados["metadatas"]):
            assert texto.startswith(metadados["fonte"])


def test_o_exemplo_do_parametro_entra_no_indice_tambem_no_dado_pessoal(pasta):
    """O exemplo de cada campo ajuda a IA a reconhecer o dado, inclusive o do CPF (ADR-101)."""
    textos_do_layout = _todos(pasta, busca.COLECAO_LAYOUT)["documents"]
    trecho_do_cpf = ""
    for texto in textos_do_layout:
        if "Campo cpf " in texto:
            trecho_do_cpf = texto
    assert "Exemplo: 12345678909." in trecho_do_cpf


def test_o_trecho_de_cada_campo_diz_se_ele_pode_ser_igual_para_todos(pasta):
    """A marcação "Pode ser igual para todos" do parâmetro entra no texto que a IA lê:
    o CPF é de cada pessoa; o CNPJ do empregador pode ser o mesmo para todos (dado da empresa)."""
    dados = _todos(pasta, busca.COLECAO_LAYOUT)
    # O trecho de cada campo do parâmetro (as regras e os mapeamentos ficam de fora)
    trecho_por_campo = {}
    for texto, metadados in zip(dados["documents"], dados["metadatas"]):
        if metadados.get("tipo_trecho") == "campo":
            trecho_por_campo[metadados["campo"]] = texto
    assert "É de cada pessoa: nunca é o mesmo para todos os funcionários do arquivo." in trecho_por_campo["cpf"]
    assert "Pode ser o mesmo para todos os funcionários do arquivo (dado da empresa)." in \
        trecho_por_campo["cnpj_empregador"]


def test_secao_longa_e_dividida_repetindo_o_titulo():
    """Seção grande vira vários trechos, todos com o título e dentro do limite de tamanho."""
    # Cerca de 360 caracteres
    paragrafo = "Condição especial do produto. " * 12
    documento = {"empresa_id": "EMP999", "titulo": "Pacote de teste", "versao": 1, "vigencia_inicio": "2026-01-01",
                 "vigencia_fim": "2026-12-31",
                 "conteudo_md": f"# Pacote\n\n## Produto grande\n{paragrafo}\n\n{paragrafo}\n\n{paragrafo}\n"}
    trechos = trechos_catalogo([documento])
    assert len(trechos) > 1
    for trecho in trechos:
        assert trecho.texto.startswith("Pacote de teste v1 › Produto grande")
        assert len(trecho.texto) <= LIMITE_CARACTERES + 60


# ---------- Isolamento e vigência ----------

def test_busca_no_catalogo_exige_empresa(pasta):
    """Sem empresa, a busca no catálogo é recusada (nunca busca em todas)."""
    with pytest.raises(ValueError):
        busca.buscar_beneficios("", "conta salário", dia=DIA, pasta=pasta)


@pytest.mark.parametrize("empresa", ["EMP001", "EMP002", "EMP003", "EMP004", "EMP005", "EMP006"])
def test_cada_empresa_so_recebe_o_proprio_catalogo(pasta, empresa):
    """Mesmo pedindo muitos trechos, só voltam os da própria empresa."""
    resultados = busca.buscar_beneficios(empresa, "quais são os benefícios e a conta salário?", dia=DIA,
                                         k=10, distancia_maxima=2, pasta=pasta)
    empresas_devolvidas = set()
    for resultado in resultados:
        empresas_devolvidas.add(resultado["empresa_id"])
    assert resultados and empresas_devolvidas == {empresa}


def test_documento_fora_da_vigencia_nao_volta(pasta):
    """O pacote da Horizonte começa em 2026-03-01: em fevereiro, nada dele pode voltar."""
    resultados = busca.buscar_beneficios("EMP002", "adiantamento salarial", dia=date(2026, 2, 15),
                                         distancia_maxima=2, pasta=pasta)
    assert resultados == []


# ---------- As 10 consultas de cada índice ----------

@pytest.mark.parametrize("consulta", CONSULTAS["catalogo"], ids=_nome_da_consulta)
def test_consultas_do_catalogo(pasta, consulta):
    """Pergunta com resposta acha o trecho certo; sem resposta, não inventa; de outra empresa, nada vaza."""
    resultados = busca.buscar_beneficios(consulta["empresa_id"], consulta["pergunta"], dia=DIA, pasta=pasta)
    if consulta["tipo"] == "conhecida":
        assert _algum_acerto(consulta, resultados)
    elif consulta["tipo"] == "sem_resposta":
        # Admite a ausência de evidência em vez de devolver algo qualquer
        assert resultados == []
    else:
        # Pede dado de outra empresa: nada dela pode voltar
        for resultado in resultados:
            assert resultado["empresa_id"] == consulta["empresa_id"]


@pytest.mark.parametrize("consulta", _consultas_conhecidas_do_layout(), ids=_nome_da_consulta)
def test_consultas_do_layout(pasta, consulta):
    """Cada pergunta sobre o layout acha o trecho certo."""
    resultados = busca.search_rules(consulta["pergunta"], pasta=pasta)
    assert _algum_acerto(consulta, resultados)


def test_layout_devolve_um_trecho_por_campo(pasta):
    """A busca não devolve dois trechos do mesmo campo (dá espaço para outras fontes)."""
    resultados = busca.search_rules("salário do funcionário", pasta=pasta)
    chaves = []
    for resultado in resultados:
        chaves.append(resultado["campo"] or resultado["fonte"])
    assert len(chaves) == len(set(chaves))
