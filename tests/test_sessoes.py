"""Sessão lembrada por cookie: quando o ingresso vale e quando deixa de valer (ADR-40)."""
from datetime import datetime, timedelta, timezone

import pytest

from models.contratos import Perfil
from services import auth, sessoes

# Um "agora" fixo, para os testes de horário darem sempre o mesmo resultado
AGORA = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo com um usuário da Aurora."""
    conexao_do_teste = auth.conectar(tmp_path / "teste.db")
    auth.cadastrar_usuario(conexao_do_teste, "empresa.aurora", "senha-forte", Perfil.EMPRESA, "EMP001")
    return conexao_do_teste


def test_ingresso_valido_devolve_o_usuario_com_perfil_e_empresa(conexao):
    """Com o ingresso válido, o sistema sabe quem é o usuário, o perfil e a empresa."""
    ingresso = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    usuario = sessoes.validar_sessao(conexao, ingresso, agora=AGORA + timedelta(hours=1))
    assert usuario.login == "empresa.aurora"
    assert usuario.perfil == Perfil.EMPRESA
    assert usuario.empresa_id == "EMP001"


def test_ingresso_vence_em_8_horas(conexao):
    """Vale até 7h59; com 8 horas, vence."""
    ingresso = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    assert sessoes.validar_sessao(conexao, ingresso, agora=AGORA + timedelta(hours=7, minutes=59)) is not None
    assert sessoes.validar_sessao(conexao, ingresso, agora=AGORA + timedelta(hours=8)) is None


def test_sair_cancela_o_ingresso_mesmo_que_alguem_o_tenha_copiado(conexao):
    """Depois de "Sair", o mesmo ingresso não entra mais."""
    ingresso = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    sessoes.encerrar_sessao(conexao, ingresso)
    assert sessoes.validar_sessao(conexao, ingresso, agora=AGORA) is None


def test_usuario_desativado_perde_a_sessao_na_hora(conexao):
    """Desativar o usuário derruba a sessão aberta."""
    ingresso = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    auth.definir_ativo(conexao, "empresa.aurora", False)
    assert sessoes.validar_sessao(conexao, ingresso, agora=AGORA) is None


def test_senha_redefinida_derruba_todas_as_sessoes_do_usuario(conexao):
    """Senha redefinida: as sessões de todos os aparelhos caem."""
    ingresso_do_celular = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    ingresso_do_notebook = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    sessoes.encerrar_sessoes_do_usuario(conexao, "empresa.aurora")
    assert sessoes.validar_sessao(conexao, ingresso_do_celular, agora=AGORA) is None
    assert sessoes.validar_sessao(conexao, ingresso_do_notebook, agora=AGORA) is None


def test_ingresso_inventado_ou_vazio_nao_entra(conexao):
    """Ingresso inventado, nulo ou vazio: ninguém entra."""
    assert sessoes.validar_sessao(conexao, "ingresso-inventado", agora=AGORA) is None
    assert sessoes.validar_sessao(conexao, None, agora=AGORA) is None
    assert sessoes.validar_sessao(conexao, "", agora=AGORA) is None


def test_banco_guarda_so_o_hash_do_ingresso(conexao):
    """O banco guarda o hash, nunca o ingresso; e o ingresso é longo o bastante para não ser adivinhado."""
    ingresso = sessoes.criar_sessao(conexao, "empresa.aurora", agora=AGORA)
    (guardado,) = conexao.execute("SELECT token_hash FROM sessoes").fetchone()
    assert ingresso not in guardado
    # 32 bytes aleatórios em base64
    assert len(ingresso) >= 43


def test_cada_login_gera_um_ingresso_diferente(conexao):
    """Dois logins, dois ingressos diferentes."""
    assert sessoes.criar_sessao(conexao, "empresa.aurora") != sessoes.criar_sessao(conexao, "empresa.aurora")


def test_cookie_em_formato_estranho_e_recusado_sem_quebrar(conexao):
    """O cookie vem do navegador, ou seja, de fora: nunca confiar no formato."""
    for valor_estranho in (123, b"bytes", ["lista"], object()):
        assert sessoes.validar_sessao(conexao, valor_estranho, agora=AGORA) is None
