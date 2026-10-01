"""O cabeçalho das telas e a troca da própria senha pelo novo front (ADR-69, passo 19).

O que estes testes provam:
- as iniciais saem do login; o papel diz a empresa (RH) ou "Especialista do banco";
- o sino de avisos saiu do cabeçalho, e o número das conversas também (ele vem das conversas
  abertas, GET /api/banco/conversas/abertas, testado em tests/test_mensagens.py);
- a troca da própria senha pede a senha atual, a confirmação igual e o tamanho mínimo; depois, a nova senha entra;
- sem login, o cabeçalho e a troca de senha dão 401.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, cabecalho

SENHA_DE_TESTE = "senha-de-teste-123"


def test_iniciais_do_login():
    assert cabecalho.iniciais("marina.costa@aurora.com.br") == "MC"
    assert cabecalho.iniciais("teste.banco") == "TB"
    assert cabecalho.iniciais("rh@cedroeng.com.br") == "RH"


@pytest.fixture
def api_do_cabecalho(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um usuário de cada perfil."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_cabecalho.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao = conectar_original(caminho)
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()


def entrar(login, senha=SENHA_DE_TESTE):
    """Um navegador de mentira logado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": senha}).status_code == 200
    return navegador


def test_cabecalho_por_perfil(api_do_cabecalho):
    empresa = entrar("rh.aurora").get("/api/cabecalho").json()
    assert empresa["papel"].startswith("RH · Aurora") and empresa["iniciais"] == "RA" and "avisos" not in empresa
    # O nome da empresa sozinho (a arte do endomarketing usa)
    assert empresa["nome_da_empresa"].startswith("Aurora")
    banco = entrar("especialista").get("/api/cabecalho").json()
    assert banco["papel"] == "Especialista do banco"
    # O número das conversas saiu do cabeçalho: o sinal do menu vem de /api/banco/conversas/abertas
    assert "mensagens_sem_resposta" not in banco
    assert banco["nome_da_empresa"] is None
    assert TestClient(aplicacao).get("/api/cabecalho").status_code == 401


def test_trocar_a_propria_senha(api_do_cabecalho):
    rh = entrar("rh.aurora")
    rota = "/api/minha-senha"
    # Confirmação diferente, senha atual errada e senha curta: recusadas
    assert rh.post(rota, json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "nova-senha-123", "confirmacao": "outra"}).status_code == 400
    assert rh.post(rota, json={"senha_atual": "errada", "nova_senha": "nova-senha-123", "confirmacao": "nova-senha-123"}).status_code == 400
    assert rh.post(rota, json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "curta", "confirmacao": "curta"}).status_code == 400
    # Certo: a nova senha entra, a antiga não
    assert rh.post(rota, json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "nova-senha-123", "confirmacao": "nova-senha-123"}).status_code == 200
    assert TestClient(aplicacao).post("/api/entrar", json={"usuario": "rh.aurora", "senha": SENHA_DE_TESTE}).status_code == 401
    entrar("rh.aurora", "nova-senha-123")
    assert TestClient(aplicacao).post(rota, json={"senha_atual": "x", "nova_senha": "y", "confirmacao": "y"}).status_code == 401
