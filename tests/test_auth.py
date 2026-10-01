"""Cadastro de usuários e login (ADR-32)."""
import pytest

from models.contratos import Perfil
from services import auth


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo e vazio para cada teste."""
    return auth.conectar(tmp_path / "teste.db")


def test_login_certo_devolve_perfil_e_empresa(conexao):
    """Login e senha certos: o sistema sabe o perfil e a empresa do usuário."""
    auth.cadastrar_usuario(conexao, "empresa.aurora", "senha-forte", Perfil.EMPRESA, "EMP001")
    usuario = auth.autenticar(conexao, "empresa.aurora", "senha-forte")
    assert usuario.perfil == Perfil.EMPRESA
    assert usuario.empresa_id == "EMP001"


def test_senha_errada_ou_usuario_inexistente_nao_entra(conexao):
    """Senha errada ou login que não existe: ninguém entra."""
    auth.cadastrar_usuario(conexao, "especialista.banco", "senha-forte", Perfil.BANCO)
    assert auth.autenticar(conexao, "especialista.banco", "errada") is None
    assert auth.autenticar(conexao, "ninguem", "senha-forte") is None


def test_senha_nunca_e_guardada_em_texto(conexao):
    """O banco guarda só o hash da senha, nunca a senha."""
    auth.cadastrar_usuario(conexao, "especialista.banco", "senha-forte", Perfil.BANCO)
    (senha_hash,) = conexao.execute("SELECT senha_hash FROM usuarios").fetchone()
    assert "senha-forte" not in senha_hash


def test_perfil_empresa_exige_empresa(conexao):
    """Usuário do perfil EMPRESA sem empresa é recusado."""
    with pytest.raises(ValueError):
        auth.cadastrar_usuario(conexao, "empresa.sem.empresa", "senha-forte", Perfil.EMPRESA)


def test_perfil_banco_nunca_fica_preso_a_uma_empresa(conexao):
    """Usuário do banco vê todas as empresas: a empresa informada no cadastro é ignorada."""
    auth.cadastrar_usuario(conexao, "especialista.banco", "senha-forte", Perfil.BANCO, "EMP001")
    assert auth.autenticar(conexao, "especialista.banco", "senha-forte").empresa_id is None



def test_usuario_de_perfil_que_nao_existe_mais_e_apagado_com_as_sessoes(conexao):
    """O perfil CIENTISTA saiu (ADR-78): um banco antigo com o usuário dele é limpo na preparação."""
    from services import sessoes
    auth.cadastrar_usuario(conexao, "rh.teste", "senha-forte", Perfil.EMPRESA, "EMP001")
    # Um usuário gravado antes, com um perfil que o sistema não conhece mais, e uma sessão dele
    conexao.execute("INSERT INTO usuarios (login, senha_hash, perfil, empresa_id, ativo) VALUES (?, ?, ?, ?, ?)",
                    ("cientista.dados", "hash-qualquer", "CIENTISTA", None, 1))
    conexao.commit()
    sessoes.criar_sessao(conexao, "cientista.dados")
    assert auth.remover_usuarios_de_perfis_extintos(conexao) == ["cientista.dados"]
    # A lista de usuários volta a funcionar, e a sessão dele sumiu
    logins = []
    for usuario in auth.listar_usuarios(conexao):
        logins.append(usuario.login)
    assert logins == ["rh.teste"]
    assert conexao.execute("SELECT COUNT(*) FROM sessoes WHERE login = ?", ("cientista.dados",)).fetchone()[0] == 0
    # Rodar de novo não apaga nada
    assert auth.remover_usuarios_de_perfis_extintos(conexao) == []


def test_senha_longa_demais_e_recusada_no_cadastro_e_so_errada_no_login(conexao):
    """O bcrypt só aceita 72 bytes: o cadastro recusa com mensagem clara, e o login com senha enorme é só "errado"
    (antes, virava erro 500 na tela de login)."""
    with pytest.raises(ValueError, match="no máximo 72"):
        auth.cadastrar_usuario(conexao, "senha.longa", "a" * 73, Perfil.BANCO)
    auth.cadastrar_usuario(conexao, "senha.normal", "senha-normal-123", Perfil.BANCO)
    assert auth.autenticar(conexao, "senha.normal", "a" * 500) is None
