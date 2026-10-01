"""Limite de tentativas de login (ADR-110): a contagem dos erros, o bloqueio de 15 minutos e o acerto que zera.

Estes testes conferem o serviço (services/tentativas_de_login.py) com um "agora" fixo, sem esperar o relógio. A mesma
regra vista pela tela de login (a API) está em tests/test_protecoes_do_site.py.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services import auth, tentativas_de_login

# Um "agora" fixo, para os testes de horário darem sempre o mesmo resultado
AGORA = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo e vazio para cada teste."""
    return auth.conectar(tmp_path / "teste.db")


def errar_varias_vezes(conexao, login: str, vezes: int, a_partir_de: datetime) -> None:
    """Anota várias senhas erradas seguidas para o login, uma por minuto a partir do momento informado."""
    for numero_do_erro in range(vezes):
        tentativas_de_login.registrar_erro(conexao, login, agora=a_partir_de + timedelta(minutes=numero_do_erro))


def test_quatro_erros_nao_bloqueiam_e_o_quinto_bloqueia_por_15_minutos(conexao):
    """Até o 4º erro, o login continua livre; no 5º, fica bloqueado por 15 minutos a partir dele."""
    errar_varias_vezes(conexao, "empresa.aurora", 4, AGORA)
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=4)) == 0
    # O 5º erro, no minuto 4
    tentativas_de_login.registrar_erro(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=4))
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=4)) == 15
    # 14 minutos depois ainda falta 1; com 15, acabou
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=18)) == 1
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=19)) == 0


def test_os_minutos_que_faltam_sao_arredondados_para_cima(conexao):
    """Faltando 30 segundos, o aviso diz 1 minuto (nunca "tente em 0 minutos")."""
    errar_varias_vezes(conexao, "empresa.aurora", 5, AGORA)
    fim_do_bloqueio = AGORA + timedelta(minutes=4 + 15)
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora",
                                                   agora=fim_do_bloqueio - timedelta(seconds=30)) == 1


def test_erros_espalhados_por_mais_de_15_minutos_nao_somam(conexao):
    """A contagem vale 15 minutos a partir do primeiro erro: 4 erros hoje e 1 bem depois não bloqueiam."""
    errar_varias_vezes(conexao, "empresa.aurora", 4, AGORA)
    # O 5º erro, 16 minutos depois do primeiro: a contagem recomeça dele
    momento_do_quinto = AGORA + timedelta(minutes=16)
    tentativas_de_login.registrar_erro(conexao, "empresa.aurora", agora=momento_do_quinto)
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=momento_do_quinto) == 0


def test_login_certo_zera_a_contagem(conexao):
    """4 erros, um acerto e mais 4 erros: não bloqueia (a contagem voltou ao zero no acerto)."""
    errar_varias_vezes(conexao, "empresa.aurora", 4, AGORA)
    tentativas_de_login.registrar_acerto(conexao, "empresa.aurora")
    errar_varias_vezes(conexao, "empresa.aurora", 4, AGORA + timedelta(minutes=5))
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=9)) == 0


def test_erro_durante_o_bloqueio_nao_apaga_nem_estica_o_bloqueio(conexao):
    """Um erro anotado durante o bloqueio não o desfaz (seria uma porta dos fundos) nem o aumenta."""
    errar_varias_vezes(conexao, "empresa.aurora", 5, AGORA)
    # Fim do bloqueio: 15 minutos depois do 5º erro (minuto 4)
    fim_do_bloqueio = AGORA + timedelta(minutes=19)
    tentativas_de_login.registrar_erro(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=10))
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=10)) == 9
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=fim_do_bloqueio) == 0


def test_depois_do_bloqueio_a_pessoa_tem_de_novo_5_tentativas(conexao):
    """Acabado o bloqueio, o 1º erro seguinte não bloqueia de novo: a contagem recomeça."""
    errar_varias_vezes(conexao, "empresa.aurora", 5, AGORA)
    depois_do_bloqueio = AGORA + timedelta(minutes=20)
    tentativas_de_login.registrar_erro(conexao, "empresa.aurora", agora=depois_do_bloqueio)
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=depois_do_bloqueio) == 0


def test_cada_login_tem_a_sua_contagem(conexao):
    """Os erros de um login não bloqueiam outro."""
    errar_varias_vezes(conexao, "empresa.aurora", 5, AGORA)
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "especialista.banco", agora=AGORA + timedelta(minutes=5)) == 0


def test_registros_vencidos_sao_apagados_e_a_tabela_nao_cresce_sem_fim(conexao):
    """Quem tenta muitos logins inventados não enche o banco: as linhas vencidas somem no próximo erro anotado."""
    # 100 logins inventados, um erro cada
    for numero in range(100):
        tentativas_de_login.registrar_erro(conexao, f"inventado.{numero}", agora=AGORA)
    # Um erro 16 minutos depois: a limpeza apaga as 100 linhas vencidas e fica só a nova
    tentativas_de_login.registrar_erro(conexao, "outro.login", agora=AGORA + timedelta(minutes=16))
    linhas = conexao.execute("SELECT login FROM tentativas_de_login").fetchall()
    assert linhas == [("outro.login",)]


def test_bloqueio_valendo_nao_e_apagado_pela_limpeza(conexao):
    """A limpeza só apaga o que já não decide nada: um bloqueio ainda valendo fica."""
    errar_varias_vezes(conexao, "empresa.aurora", 5, AGORA)
    # 16 minutos depois do 1º erro, a contagem venceu, mas o bloqueio (até o minuto 19) ainda vale
    tentativas_de_login.registrar_erro(conexao, "outro.login", agora=AGORA + timedelta(minutes=16))
    assert tentativas_de_login.minutos_de_bloqueio(conexao, "empresa.aurora", agora=AGORA + timedelta(minutes=16)) == 3
