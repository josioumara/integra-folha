"""Testes do congelamento da avaliação e da acurácia por campo (ADR-58).

Provam que:
- a prova gravada no Git está exatamente como foi congelada;
- a impressão digital não muda só porque o Windows grava o fim de linha diferente;
- qualquer mudança (alterar, remover ou criar um arquivo da prova) é percebida e para a medição;
- a acurácia por campo soma exatamente o mesmo que a acurácia geral.
"""
import json

import pytest

from eval import congelamento
from eval.metricas import acuracia_de_cada_campo, contar


def test_a_prova_do_repositorio_esta_como_foi_congelada():
    """Nenhum arquivo da prova, dos gabaritos ou das métricas mudou depois do congelamento."""
    assert congelamento.conferir() == []


def test_a_foto_cobre_prova_gabaritos_e_metricas():
    """A foto inclui a prova do Interpretador, cada gabarito e o código das métricas."""
    caminhos = congelamento.arquivos_da_prova()
    assert "data/avaliacao/cabecalhos_teste.jsonl" in caminhos
    assert "eval/metricas.py" in caminhos
    assert "data/golden/aurora_carga_inicial.json" in caminhos


def test_impressao_digital_ignora_o_fim_de_linha_do_windows(tmp_path):
    """O mesmo texto com CRLF (Windows) e com LF (Linux) tem a mesma impressão digital."""
    arquivo_windows = tmp_path / "windows.txt"
    arquivo_linux = tmp_path / "linux.txt"
    arquivo_windows.write_bytes(b"linha 1\r\nlinha 2\r\n")
    arquivo_linux.write_bytes(b"linha 1\nlinha 2\n")
    assert congelamento.impressao_digital(arquivo_windows) == congelamento.impressao_digital(arquivo_linux)


def test_diferencas_percebe_arquivo_alterado_removido_e_novo():
    """Cada tipo de mudança aparece numa frase própria."""
    foto_gravada = {"a.json": "111", "b.json": "222"}
    foto_atual = {"a.json": "999", "c.json": "333"}
    mudancas = congelamento.diferencas(foto_gravada, foto_atual)
    assert "alterado: a.json" in mudancas
    assert "removido: b.json" in mudancas
    assert "novo, não congelado: c.json" in mudancas


def test_prova_alterada_para_a_medicao(tmp_path, monkeypatch):
    """Se a foto gravada não bate com os arquivos de hoje, a medição se recusa a rodar."""
    # Uma foto gravada com a impressão digital das métricas adulterada
    foto = congelamento.fotografar()
    foto["eval/metricas.py"] = "0" * 64
    caminho_falso = tmp_path / "congelamento.json"
    caminho_falso.write_text(json.dumps({"data": "2026-09-24", "motivo": "teste", "arquivos": foto}),
                             encoding="utf-8")
    monkeypatch.setattr(congelamento, "CAMINHO_DO_CONGELAMENTO", caminho_falso)
    with pytest.raises(congelamento.AvaliacaoAlterada, match="alterado: eval/metricas.py"):
        congelamento.exigir_prova_congelada()


def test_sem_congelamento_nao_se_mede(tmp_path, monkeypatch):
    """Sem foto gravada, a medição também não roda."""
    monkeypatch.setattr(congelamento, "CAMINHO_DO_CONGELAMENTO", tmp_path / "nao_existe.json")
    with pytest.raises(congelamento.AvaliacaoAlterada, match="ainda não foi congelada"):
        congelamento.exigir_prova_congelada()


def test_congelar_exige_motivo():
    """Recongelar sem dizer o motivo é recusado (e nada é gravado)."""
    with pytest.raises(ValueError, match="motivo"):
        congelamento.congelar("   ")


def _item(coluna, campo):
    """Uma resposta do mapeador: campo proposto, ou pendência quando o campo é AMBIGUO/NAO_MAPEADO."""
    if campo in ("AMBIGUO", "NAO_MAPEADO"):
        return {"coluna": coluna, "status": campo, "campo": None}
    return {"coluna": coluna, "status": "PROPOSTO", "campo": campo}


def test_acuracia_de_cada_campo_do_pior_para_o_melhor():
    """Cada campo tem as suas colunas e acertos; os difíceis vêm primeiro; pendências ficam de fora."""
    exemplos = [
        {"esperado": {"CPF": "cpf", "Salário": "valor_renda", "Proventos": "AMBIGUO"}},
        {"esperado": {"Documento": "cpf", "Remuneração": "valor_renda"}},
    ]
    previstos = [
        [_item("CPF", "cpf"), _item("Salário", "valor_renda"), _item("Proventos", "valor_renda")],
        [_item("Documento", "cpf"), _item("Remuneração", "NAO_MAPEADO")],
    ]
    linhas = acuracia_de_cada_campo(exemplos, previstos)
    # valor_renda: 1 de 2 (pior, vem primeiro); cpf: 2 de 2
    assert linhas[0] == {"campo": "valor_renda", "colunas": 2, "acertos": 1, "acuracia": 0.5}
    assert linhas[1] == {"campo": "cpf", "colunas": 2, "acertos": 2, "acuracia": 1.0}
    # "Proventos" devia virar pendência: não conta em campo nenhum
    assert len(linhas) == 2


def test_acuracia_por_campo_soma_o_mesmo_que_a_geral():
    """No resultado gravado do B0, a soma por campo bate com as contagens gerais."""
    resultado = json.loads((congelamento.RAIZ / "data" / "avaliacao" / "resultados" / "B0.json")
                           .read_text(encoding="utf-8"))
    total_de_colunas = 0
    total_de_acertos = 0
    for linha in resultado["acuracia_de_cada_campo"]:
        total_de_colunas += linha["colunas"]
        total_de_acertos += linha["acertos"]
    assert total_de_colunas == resultado["n_colunas_com_campo"]
    assert total_de_acertos / total_de_colunas == pytest.approx(resultado["acuracia_por_campo"])


def test_contar_e_por_campo_concordam_num_exemplo():
    """A mesma planilha contada pelos dois jeitos dá o mesmo total de acertos."""
    exemplos = [{"esperado": {"A": "cpf", "B": "matricula"}}]
    previstos = [[_item("A", "cpf"), _item("B", "cpf")]]
    contagem = contar(exemplos, previstos)
    soma_de_acertos = 0
    for linha in acuracia_de_cada_campo(exemplos, previstos):
        soma_de_acertos += linha["acertos"]
    assert soma_de_acertos == contagem["campos_certos"] == 1
