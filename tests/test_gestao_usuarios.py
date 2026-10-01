"""Gestão de usuários: desativar, redefinir, trocar a própria senha e migração do banco (ADR-32)."""
import sqlite3

import pytest

from models.contratos import Perfil
from services import auth


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo com um usuário da Horizonte."""
    conexao_do_teste = auth.conectar(tmp_path / "teste.db")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", "senha-forte", Perfil.EMPRESA, "EMP002")
    return conexao_do_teste


def test_usuario_desativado_nao_entra_e_reativado_volta(conexao):
    """Desativado não entra; reativado entra de novo com a mesma senha."""
    auth.definir_ativo(conexao, "rh.horizonte", False)
    assert auth.autenticar(conexao, "rh.horizonte", "senha-forte") is None
    auth.definir_ativo(conexao, "rh.horizonte", True)
    assert auth.autenticar(conexao, "rh.horizonte", "senha-forte") is not None


def test_banco_redefine_senha(conexao):
    """Depois de redefinida, só a senha nova funciona."""
    auth.redefinir_senha(conexao, "rh.horizonte", "nova-senha-123")
    assert auth.autenticar(conexao, "rh.horizonte", "senha-forte") is None
    assert auth.autenticar(conexao, "rh.horizonte", "nova-senha-123") is not None


def test_trocar_propria_senha_exige_a_senha_atual(conexao):
    """Para trocar a própria senha, é preciso saber a atual."""
    with pytest.raises(ValueError, match="senha atual"):
        auth.trocar_propria_senha(conexao, "rh.horizonte", "chute-errado", "nova-senha-123")
    auth.trocar_propria_senha(conexao, "rh.horizonte", "senha-forte", "nova-senha-123")
    assert auth.autenticar(conexao, "rh.horizonte", "nova-senha-123") is not None


def test_senha_curta_e_recusada(conexao):
    """Senha com menos de 8 caracteres é recusada."""
    with pytest.raises(ValueError, match="8 caracteres"):
        auth.cadastrar_usuario(conexao, "curta", "1234567", Perfil.BANCO)


def test_listagem_nunca_traz_o_hash(conexao):
    """A lista de usuários (que aparece na tela) não carrega o hash da senha."""
    usuario = auth.listar_usuarios(conexao)[0]
    assert not hasattr(usuario, "senha_hash")


@pytest.mark.somente_sqlite
def test_banco_antigo_da_fase_0_ganha_a_coluna_ativo_sem_perder_usuarios(tmp_path):
    """Banco criado antes da coluna "ativo": ao abrir, ganha a coluna e os usuários continuam lá."""
    caminho = tmp_path / "antigo.db"
    # Monta um banco no formato mais antigo
    antigo = sqlite3.connect(caminho)
    antigo.execute("CREATE TABLE usuarios (login TEXT PRIMARY KEY, senha_hash TEXT, perfil TEXT, empresa_id TEXT)")
    antigo.execute("INSERT INTO usuarios VALUES ('velho', 'x', 'BANCO', NULL)")
    antigo.commit()
    antigo.close()

    migrado = auth.conectar(caminho)
    logins = []
    for usuario in auth.listar_usuarios(migrado):
        logins.append(usuario.login)
    assert logins == ["velho"]
    assert auth.listar_usuarios(migrado)[0].ativo is True
