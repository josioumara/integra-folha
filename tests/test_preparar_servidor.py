"""Testes da preparação do servidor na subida (ADR-64).

Provam que o script gera só o que falta, nunca pergunta senha e só cria usuários com as três senhas
dos segredos. As etapas pesadas (gerar dados, montar índices) são trocadas por "gravadores" que só
anotam que foram chamadas.
"""
import pytest

from scripts import preparar_servidor
from services import auth


@pytest.fixture
def chamadas(monkeypatch):
    """Troca as etapas pesadas por gravadores e devolve a lista do que foi chamado."""
    registro = []

    def gerar_dados_de_mentira():
        """Anota que os dados seriam gerados."""
        registro.append("gerar_dados")

    def montar_indices_de_mentira():
        """Anota que os índices seriam montados."""
        registro.append("build_index")

    monkeypatch.setattr(preparar_servidor.gerar_dados, "main", gerar_dados_de_mentira)
    monkeypatch.setattr(preparar_servidor.build_index, "main", montar_indices_de_mentira)
    return registro


def _sem_senhas(monkeypatch):
    """Nenhuma senha nos segredos."""
    for _login, variavel_da_senha, _perfil, _empresa in preparar_servidor.criar_usuarios.USUARIOS_DEMO:
        monkeypatch.delenv(variavel_da_senha, raising=False)


def test_pasta_vazia_ou_ausente_precisa_gerar_dados(tmp_path):
    """Sem a pasta, ou com ela vazia, os dados precisam ser gerados; com um arquivo, não."""
    assert preparar_servidor.precisa_gerar_dados(tmp_path / "nao_existe")
    assert preparar_servidor.precisa_gerar_dados(tmp_path)
    (tmp_path / "aurora.xlsx").write_bytes(b"x")
    assert not preparar_servidor.precisa_gerar_dados(tmp_path)


def test_servidor_vazio_gera_dados_e_indices_sem_perguntar_senha(chamadas, monkeypatch):
    """Disco vazio e sem senhas: gera dados e índices, avisa que os usuários não foram criados e não trava."""
    monkeypatch.setattr(preparar_servidor, "precisa_gerar_dados", lambda: True)
    monkeypatch.setattr(preparar_servidor, "precisa_montar_indices", lambda: True)
    _sem_senhas(monkeypatch)
    # Se o script tentasse perguntar a senha, este getpass de mentira faria o teste falhar
    monkeypatch.setattr("getpass.getpass", _nao_pode_perguntar)
    feito = preparar_servidor.main()
    assert chamadas == ["gerar_dados", "build_index"]
    assert "usuários NÃO criados" in feito[2]


def _nao_pode_perguntar(*argumentos, **outros_argumentos):
    """No servidor não há ninguém para digitar: perguntar é um erro."""
    raise AssertionError("o servidor não pode perguntar senha")


def test_servidor_ja_pronto_nao_refaz_nada(chamadas, monkeypatch):
    """Com dados e índices já presentes, nada pesado roda de novo."""
    monkeypatch.setattr(preparar_servidor, "precisa_gerar_dados", lambda: False)
    monkeypatch.setattr(preparar_servidor, "precisa_montar_indices", lambda: False)
    _sem_senhas(monkeypatch)
    feito = preparar_servidor.main()
    assert chamadas == []
    assert feito[0] == "dados sintéticos já existiam" and feito[1] == "índices do RAG já existiam"


def test_faltando_uma_senha_nenhum_usuario_e_criado(monkeypatch):
    """Com só uma das duas senhas, o script não cria ninguém (a demo precisa dos dois perfis)."""
    _sem_senhas(monkeypatch)
    monkeypatch.setenv("SENHA_USUARIO_EMPRESA", "senha-da-empresa-1")
    assert preparar_servidor.senhas_dos_segredos() is None


def test_com_as_duas_senhas_os_usuarios_entram(chamadas, monkeypatch):
    """Com as duas senhas nos segredos, os dois usuários são criados e o login funciona."""
    monkeypatch.setattr(preparar_servidor, "precisa_gerar_dados", lambda: False)
    monkeypatch.setattr(preparar_servidor, "precisa_montar_indices", lambda: False)
    monkeypatch.setenv("SENHA_USUARIO_EMPRESA", "senha-da-empresa-1")
    monkeypatch.setenv("SENHA_USUARIO_BANCO", "senha-do-banco-1")
    feito = preparar_servidor.main()
    assert "criados com as senhas dos segredos" in feito[2]
    usuario = auth.autenticar(auth.conectar(), "especialista.banco", "senha-do-banco-1")
    assert usuario is not None and usuario.perfil.value == "BANCO"
