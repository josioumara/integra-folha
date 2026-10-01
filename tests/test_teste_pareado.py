"""Testes das contas do teste pareado (eval/teste_pareado.py): McNemar exato, bootstrap pareado, Holm e acurácia por
dólar. Os números esperados foram conferidos à mão (a distribuição binomial com 50%)."""
import pytest

from eval import teste_pareado


def test_mcnemar_exato_nos_casos_conferidos_a_mao():
    # 30 × 2: P(X <= 2) com n = 32 é (1 + 32 + 496) / 2^32; o bilateral é o dobro
    assert teste_pareado.mcnemar_exato(30, 2) == pytest.approx(2 * 529 / 2 ** 32)
    # 17 × 15: bem equilibrado, pode ser sorte
    assert 0.8 < teste_pareado.mcnemar_exato(17, 15) < 0.9
    # Sem discordância, não há o que testar
    assert teste_pareado.mcnemar_exato(0, 0) == 1.0
    # Tudo para um lado com poucos itens: 5 × 0 → 2 × (1/32) = 0,0625 (ainda não passa de 0,05)
    assert teste_pareado.mcnemar_exato(0, 5) == pytest.approx(0.0625)
    # Nunca passa de 1
    assert teste_pareado.mcnemar_exato(3, 3) == 1.0


def test_contar_discordantes():
    pares = [(True, True), (False, True), (False, True), (True, False), (False, False)]
    assert teste_pareado.contar_discordantes(pares) == {"os_dois": 1, "so_o_primeiro": 1, "so_o_segundo": 2,
                                                        "nenhum": 1}


def test_bootstrap_pareado_da_a_diferenca_e_um_intervalo_em_volta():
    # 5 grupos iguais: o segundo acerta 2 itens a mais de 10 em cada um → diferença 0,20, intervalo em cima dela
    grupo = [(True, True)] * 6 + [(False, True)] * 2 + [(False, False)] * 2
    resultado = teste_pareado.bootstrap_pareado([grupo] * 5)
    assert resultado["diferenca"] == pytest.approx(0.2)
    assert resultado["ic_95_baixo"] == pytest.approx(0.2) and resultado["ic_95_alto"] == pytest.approx(0.2)
    assert resultado["grupos"] == 5 and resultado["itens"] == 50


def test_bootstrap_pareado_com_grupos_diferentes_abre_o_intervalo():
    ganha = [(False, True)] * 10
    empata = [(True, True)] * 10
    resultado = teste_pareado.bootstrap_pareado([ganha, empata, empata, ganha, empata])
    assert resultado["diferenca"] == pytest.approx(0.4)
    assert resultado["ic_95_baixo"] < 0.4 < resultado["ic_95_alto"]
    # O mesmo sorteio (a mesma semente) dá o mesmo intervalo
    assert teste_pareado.bootstrap_pareado([ganha, empata, empata, ganha, empata]) == resultado


def test_bootstrap_sem_grupos():
    resultado = teste_pareado.bootstrap_pareado([])
    assert resultado["diferenca"] == 0.0 and resultado["grupos"] == 0


def test_correcao_de_holm():
    ajustados = teste_pareado.correcao_de_holm({"T1": 0.01, "T2": 0.04, "T3": 0.30})
    assert ajustados == pytest.approx({"T1": 0.03, "T2": 0.08, "T3": 0.30})
    # Um ajustado nunca fica menor que o anterior: B daria 0,042, mas fica com os 0,06 do A
    ajustados = teste_pareado.correcao_de_holm({"A": 0.02, "B": 0.021, "C": 0.9})
    assert ajustados == pytest.approx({"A": 0.06, "B": 0.06, "C": 0.9})
    # E nunca passa de 1
    assert teste_pareado.correcao_de_holm({"A": 0.6, "B": 0.7}) == pytest.approx({"A": 1.0, "B": 1.0})


def test_acuracia_por_dolar():
    assert teste_pareado.acuracia_por_dolar(0.829, 1.51) == pytest.approx(0.549, abs=0.001)
    # Sem custo, a divisão não tem sentido
    assert teste_pareado.acuracia_por_dolar(0.9, 0.0) is None
