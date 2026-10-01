"""Testes do bloco de avaliação: cabeçalhos de treino/prova, baseline B0 e métricas."""
import csv
import json
import random

import pytest

from baselines.baseline_mapper import CAMINHO_CALIBRACAO, BaselineMapper, ler_termos, normalizar
from eval.metricas import contar, intervalo_bootstrap, resumir
from scripts import calibrar_b0, gerar_cabecalhos
from scripts.gerar_cabecalhos import AMBIGUAS, EXTRAS, PASTA_AVALIACAO, PASTA_VOCAB, RAIZ


def _ler_jsonl(nome):
    """Os exemplos de um arquivo JSONL (um JSON por linha)."""
    exemplos = []
    with open(PASTA_AVALIACAO / nome, encoding="utf-8") as arquivo:
        for linha in arquivo:
            exemplos.append(json.loads(linha))
    return exemplos


def _termos(nome):
    """Os termos de um arquivo do vocabulário, normalizados."""
    termos = set()
    with open(PASTA_VOCAB / f"{nome}.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            termos.add(normalizar(linha["termo"]))
    return termos


@pytest.fixture(scope="module")
def conjuntos():
    """Gera os cabeçalhos e devolve (treino, teste)."""
    gerar_cabecalhos.main()
    return _ler_jsonl("cabecalhos_treino.jsonl"), _ler_jsonl("cabecalhos_teste.jsonl")


def test_tamanhos_dos_conjuntos(conjuntos):
    """1.500 exemplos de treino e 300 de prova."""
    treino, teste = conjuntos
    assert len(treino) == gerar_cabecalhos.N_TREINO
    assert len(teste) == gerar_cabecalhos.N_TESTE


def test_toda_coluna_tem_resposta_esperada(conjuntos):
    """Cada coluna de cada exemplo tem a resposta certa (sem os espaços sobrando)."""
    treino, teste = conjuntos
    for exemplo in treino + teste:
        colunas_sem_espacos = set()
        for coluna in exemplo["cabecalhos"]:
            colunas_sem_espacos.add(coluna.strip())
        assert colunas_sem_espacos == set(exemplo["esperado"])


def test_nada_da_prova_aparece_no_treino(conjuntos):
    """Nenhum termo, coluna ambígua ou extra do teste pode estar nos exemplos de treino."""
    treino, _ = conjuntos
    # O que só existe na prova: termos do teste e as ambíguas e extras do teste
    so_do_teste = _termos("teste") - _termos("treino")
    for coluna in AMBIGUAS["teste"] + EXTRAS["teste"]:
        so_do_teste.add(normalizar(coluna))
    # Todas as colunas usadas no treino
    colunas_do_treino = set()
    for exemplo in treino:
        for coluna in exemplo["cabecalhos"]:
            colunas_do_treino.add(normalizar(coluna))
    assert not colunas_do_treino & so_do_teste


def test_prova_usa_ambiguas_e_extras_so_do_teste(conjuntos):
    """As colunas ambíguas e extras da prova vêm só das listas do teste."""
    _, teste = conjuntos
    for exemplo in teste:
        for coluna, esperado in exemplo["esperado"].items():
            if esperado == "AMBIGUO":
                assert coluna in AMBIGUAS["teste"]
            if esperado == "NAO_MAPEADO":
                assert coluna in EXTRAS["teste"]


def test_geracao_reprodutivel(conjuntos):
    """Gerar de novo dá exatamente o mesmo arquivo."""
    antes = (PASTA_AVALIACAO / "cabecalhos_teste.jsonl").read_bytes()
    gerar_cabecalhos.main()
    assert (PASTA_AVALIACAO / "cabecalhos_teste.jsonl").read_bytes() == antes


def test_historico_so_com_vocabulario_de_treino(conjuntos):
    """O histórico de mapeamentos (base do RAG) usa só termos do treino."""
    with open(RAIZ / "data" / "synthetic" / "historico_mapeamentos.csv", encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert linhas
    termos_do_treino = _termos("treino")
    for linha in linhas:
        assert normalizar(linha["coluna_origem"]) in termos_do_treino


# ---------- Baseline B0 ----------

@pytest.fixture(scope="module")
def b0():
    """O B0 com a calibração gravada."""
    return BaselineMapper()


def test_b0_acerta_sinonimo_exato_do_treino(b0):
    """Um termo do treino, mesmo em maiúsculas e com espaços, vai para o campo certo."""
    with open(PASTA_VOCAB / "treino.csv", encoding="utf-8", newline="") as arquivo:
        primeira_linha = next(csv.DictReader(arquivo))
    resultado = b0.mapear_coluna(primeira_linha["termo"].upper() + "  ")
    assert resultado["status"] == "PROPOSTO" and resultado["campo"] == primeira_linha["campo"]


def test_b0_nao_mapeia_coluna_estranha():
    """Coluna sem parecido não é mapeada; erro de digitação ainda é reconhecido."""
    mapeador = BaselineMapper(termos=[("Nome do Funcionário", "nome")], comparador="ratio", limite=85)
    assert mapeador.mapear_coluna("Vaga Garagem")["status"] == "NAO_MAPEADO"
    # Erro de digitação
    assert mapeador.mapear_coluna("Nome do Funcionaro")["campo"] == "nome"


def test_b0_usa_a_calibracao_gravada(b0):
    """O B0 usa o comparador e o limite escolhidos na calibração."""
    calibracao = json.loads(CAMINHO_CALIBRACAO.read_text(encoding="utf-8"))["escolhida"]
    assert (b0.comparador, b0.limite) == (calibracao["comparador"], calibracao["limite"])


def test_calibracao_nao_usa_termos_da_prova():
    """A validação sai do TREINO: nenhum termo dela pode ser da prova."""
    ajuste, validacao = calibrar_b0.dividir_treino(ler_termos(PASTA_VOCAB / "treino.csv"), random.Random(1))
    termos_da_validacao = set()
    for termos_do_campo in validacao.values():
        for termo in termos_do_campo:
            termos_da_validacao.add(normalizar(termo))
    termos_do_ajuste = set()
    for termo, _ in ajuste:
        termos_do_ajuste.add(normalizar(termo))
    assert termos_da_validacao and not termos_da_validacao & (_termos("teste") - _termos("treino"))
    # E a validação não repete o que o B0 conhece
    assert not termos_da_validacao & termos_do_ajuste


def test_b0_devolve_uma_resposta_por_coluna(b0):
    """Uma resposta por coluna, na mesma ordem."""
    colunas = ["Nome", "CPF", "Vaga Garagem"]
    colunas_respondidas = []
    for resposta in b0.mapear(colunas):
        colunas_respondidas.append(resposta["coluna"])
    assert colunas_respondidas == colunas


# ---------- Métricas ----------

def _item(coluna, campo):
    """Uma resposta: PROPOSTO se tem campo, NAO_MAPEADO se não tem."""
    return {"coluna": coluna, "campo": campo, "status": "PROPOSTO" if campo else "NAO_MAPEADO"}


def test_metricas_contam_acertos_e_abstencoes():
    """Acurácia por campo, recall e precisão da abstenção num exemplo feito à mão."""
    exemplos = [{"esperado": {"A": "nome", "B": "cpf", "C": "AMBIGUO", "D": "NAO_MAPEADO"}}]
    previstos = [[_item("A", "nome"), _item("B", "rg"), _item("C", None), _item("D", "cargo")]]
    metricas = resumir(contar(exemplos, previstos))
    # Acertou A, errou B
    assert metricas["acuracia_por_campo"] == 0.5
    # Absteve em C, não em D
    assert metricas["abstencao_recall"] == 0.5
    # A única abstenção era devida
    assert metricas["abstencao_precisao"] == 1.0


def test_intervalo_bootstrap_contem_a_media():
    """Metade certa: o intervalo de confiança contém 50%."""
    exemplos = [{"esperado": {"A": "nome"}}] * 10 + [{"esperado": {"A": "cpf"}}] * 10
    previstos = [[_item("A", "nome")]] * 20
    minimo, maximo = intervalo_bootstrap(exemplos, previstos, repeticoes=500)
    assert minimo <= 0.5 <= maximo
    assert 0.0 <= minimo < maximo <= 1.0
