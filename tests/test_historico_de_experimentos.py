"""Testes do histórico de experimentos (ADR-66).

Provam que:
- cada experimento ganha o próximo número e nunca sobrescreve outro;
- um registro sem pergunta ou sem resultados é recusado;
- só as métricas medidas entram (nunca um número inventado) e "não medido" aparece escrito;
- o documento traz a linha do tempo e a evolução de recall e precisão do Interpretador;
- os registros do projeto estão completos, em sequência, e o docs/experimentos.md está em dia com eles.
"""
import pytest

from eval import historico_de_experimentos as historico
from scripts import gerar_historico_de_experimentos as gerador


def _experimento(titulo: str = "Teste de modelos") -> dict:
    """Um experimento mínimo e válido do Interpretador."""
    medida = {"acuracia_por_campo": 0.8, "abstencao_recall": 0.95, "abstencao_precisao": 0.5, "custo_usd": 1.0,
              "campo_que_nao_existe": 123}
    return {"titulo": titulo, "tipo": "interpretador", "pergunta": "Qual modelo usar?", "o_que_testamos": "Dois modelos",
            "amostra": "30 planilhas", "modo": "IA real",
            "resultados": [historico.resultado_do_interpretador("B3", "modelo-x", medida)],
            "leitura": "O modelo-x acertou 80%.", "custo_usd": None}


@pytest.fixture
def pasta_temporaria(tmp_path, monkeypatch):
    """Os registros dos testes vão para uma pasta temporária (os do projeto não são tocados)."""
    monkeypatch.setattr(historico, "PASTA_DOS_EXPERIMENTOS", tmp_path)
    return tmp_path


def test_cada_experimento_ganha_o_proximo_numero(pasta_temporaria):
    """EXP-001, depois EXP-002, com o título no nome do arquivo."""
    primeiro = historico.registrar(_experimento("Primeiro teste"))
    segundo = historico.registrar(_experimento("Segundo teste"))
    assert primeiro.name == "EXP-001_primeiro_teste.json"
    assert segundo.name == "EXP-002_segundo_teste.json"
    ids = []
    for registro in historico.listar():
        ids.append(registro["id"])
    assert ids == ["EXP-001", "EXP-002"]


def test_registro_nunca_sobrescreve_outro(pasta_temporaria, monkeypatch):
    """Se o arquivo com o próximo número já existir, o registro é recusado."""
    historico.registrar(_experimento("Igual"))
    monkeypatch.setattr(historico, "_proximo_numero", lambda: 1)
    with pytest.raises(historico.RegistroInvalido, match="não pode ser sobrescrito"):
        historico.registrar(_experimento("Igual"))


def test_registro_sem_pergunta_ou_resultados_e_recusado(pasta_temporaria):
    """Sem pergunta e sem resultados não há história para contar."""
    experimento = _experimento()
    experimento["pergunta"] = ""
    experimento["resultados"] = []
    with pytest.raises(historico.RegistroInvalido, match="pergunta, .*resultados"):
        historico.registrar(experimento)


def test_so_as_metricas_medidas_entram():
    """A medida estranha fica de fora; as medidas conhecidas entram como vieram."""
    resultado = historico.resultado_do_interpretador("B3", "modelo-x", {"acuracia_por_campo": 0.8, "outra": 1})
    assert resultado == {"nome": "B3", "modelo": "modelo-x", "metricas": {"acuracia_por_campo": 0.8}}


def test_documento_traz_linha_do_tempo_e_evolucao(pasta_temporaria):
    """A linha do tempo, a evolução do Interpretador em porcentagem e o custo não medido escrito por extenso."""
    historico.registrar(_experimento())
    documento = gerador.montar_documento()
    assert "| EXP-001 |" in documento and "Teste de modelos" in documento
    assert "| EXP-001 | B3 | `modelo-x` | 80,0% | 95,0% | 50,0% |" in documento
    assert "custo não medido" in documento


def test_registros_do_projeto_estao_completos_e_em_sequencia():
    """Os registros reais: todos com os campos obrigatórios e numerados sem buraco (fora o número reservado, que o
    docs/experimentos.md mostra como reservado até o registro dele chegar)."""
    registros = historico.listar()
    assert len(registros) >= 8
    registrados = set()
    for registro in registros:
        registrados.add(int(registro["id"].split("-")[1]))
    numero_esperado = 1
    for registro in registros:
        # O número reservado que ainda não tem registro fica de fora da sequência
        while numero_esperado in historico.NUMEROS_RESERVADOS and numero_esperado not in registrados:
            numero_esperado += 1
        assert registro["id"] == f"EXP-{numero_esperado:03d}"
        numero_esperado += 1
        for campo in historico.CAMPOS_OBRIGATORIOS:
            assert registro[campo]


def test_numero_reservado(pasta_temporaria, monkeypatch):
    """Com o 2 guardado, o experimento seguinte entra como EXP-003; o 2 entra depois, só pelo número dele."""
    monkeypatch.setattr(historico, "NUMEROS_RESERVADOS", {2: "Um experimento que ainda não juntou"})
    monkeypatch.setattr(gerador, "NUMEROS_RESERVADOS", {2: "Um experimento que ainda não juntou"})
    historico.registrar(_experimento("Primeiro teste"))
    terceiro = historico.registrar(_experimento("Terceiro teste"), numero=3)
    assert terceiro.name == "EXP-003_terceiro_teste.json"
    # A linha do tempo mostra o 2 como reservado, entre o 1 e o 3
    linhas = gerador.linha_do_tempo(historico.listar())
    assert linhas[2].startswith("| EXP-001") and linhas[3].startswith("| EXP-002 | — | Reservado:")
    assert linhas[4].startswith("| EXP-003")
    # Um número que já existe é recusado
    with pytest.raises(historico.RegistroInvalido, match="já é de outro experimento"):
        historico.registrar(_experimento("Outro"), numero=3)
    # Quando o reservado chega, ele entra no lugar dele e a linha "reservado" some
    historico.registrar(_experimento("Segundo teste"), numero=2)
    linhas = gerador.linha_do_tempo(historico.listar())
    assert "Reservado" not in "\n".join(linhas)


def test_documento_do_projeto_esta_em_dia_com_os_registros():
    """docs/experimentos.md é exatamente o que o gerador produz hoje (ninguém esqueceu de regenerar)."""
    gravado = gerador.CAMINHO_DO_DOCUMENTO.read_text(encoding="utf-8")
    assert gravado == gerador.montar_documento()
