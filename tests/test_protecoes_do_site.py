"""Proteções do site na API (ADR-110): limite de tentativas de login, cabeçalhos de proteção do navegador e limite
do tamanho do pedido na entrada.

Usa o TestClient do FastAPI (um "navegador de mentira", sem ligar servidor) e o banco temporário dos testes
(tests/conftest.py). Cada teste de login usa um usuário próprio, para a contagem de erros de um não atrapalhar outro.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.principal import MENSAGEM_LOGIN_RECUSADO, PASTA_DO_FRONT, aplicacao
from models.contratos import Perfil
from services import auth, cadastro, config, tentativas_de_login

# Senha usada pelos usuários de teste (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"
# Uma senha errada qualquer
SENHA_ERRADA = "senha-errada-999"
# Os usuários deste arquivo: um por teste de login, todos da Aurora
LOGINS_DE_TESTE = ("limite.bloqueio", "limite.acerto", "limite.comparacao", "limite.fim", "limite.envio")


@pytest.fixture(scope="module", autouse=True)
def usuarios_de_teste():
    """Cadastra os usuários deste arquivo no banco temporário, uma vez."""
    conexao = auth.conectar()
    for login in LOGINS_DE_TESTE:
        auth.cadastrar_usuario(conexao, login, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao.close()


def tentar_entrar(login: str, senha: str):
    """Tenta entrar com um navegador novo e devolve a resposta da API."""
    return TestClient(aplicacao).post("/api/entrar", json={"usuario": login, "senha": senha})


# ---------------- 1. Limite de tentativas de login ----------------

def test_quinta_senha_errada_bloqueia_e_nem_a_senha_certa_entra_durante_o_bloqueio():
    """As 4 primeiras recebem a mensagem de sempre; a 5ª já avisa o bloqueio; depois, nem a senha certa entra."""
    for _tentativa in range(4):
        resposta = tentar_entrar("limite.bloqueio", SENHA_ERRADA)
        assert resposta.status_code == 401
        assert resposta.json()["detail"] == MENSAGEM_LOGIN_RECUSADO
    # A 5ª senha errada: 429 ("muitos pedidos"), com os minutos que faltam
    quinta = tentar_entrar("limite.bloqueio", SENHA_ERRADA)
    assert quinta.status_code == 429
    assert "Tente de novo em 15 minutos." in quinta.json()["detail"]
    # O cabeçalho Retry-After diz ao navegador quando tentar (em segundos)
    assert quinta.headers["retry-after"] == str(15 * 60)
    # Com a senha CERTA, durante o bloqueio: recusada do mesmo jeito, sem cookie
    certa = tentar_entrar("limite.bloqueio", SENHA_DE_TESTE)
    assert certa.status_code == 429
    assert "set-cookie" not in certa.headers


def test_bloqueio_de_login_inexistente_e_igual_ao_de_login_que_existe():
    """O aviso de bloqueio não revela se o usuário existe: um login inventado recebe a mesma resposta (ADR-69)."""
    respostas = {}
    for login in ("limite.comparacao", "login.que.nao.existe"):
        for _tentativa in range(4):
            assert tentar_entrar(login, SENHA_ERRADA).status_code == 401
        respostas[login] = tentar_entrar(login, SENHA_ERRADA)
    existente = respostas["limite.comparacao"]
    inexistente = respostas["login.que.nao.existe"]
    assert existente.status_code == inexistente.status_code == 429
    assert existente.json() == inexistente.json()


def test_login_certo_zera_a_contagem_de_erros():
    """4 erros, um login certo e mais 4 erros: nada é bloqueado."""
    for _tentativa in range(4):
        assert tentar_entrar("limite.acerto", SENHA_ERRADA).status_code == 401
    assert tentar_entrar("limite.acerto", SENHA_DE_TESTE).status_code == 200
    for _tentativa in range(4):
        assert tentar_entrar("limite.acerto", SENHA_ERRADA).status_code == 401
    assert tentar_entrar("limite.acerto", SENHA_DE_TESTE).status_code == 200


def test_acabado_o_bloqueio_a_senha_certa_entra(monkeypatch):
    """Passados os 15 minutos, a pessoa entra com a senha certa."""
    for _tentativa in range(5):
        tentar_entrar("limite.fim", SENHA_ERRADA)
    assert tentar_entrar("limite.fim", SENHA_DE_TESTE).status_code == 429
    # O relógio do serviço anda 16 minutos
    daqui_a_16_minutos = datetime.now(timezone.utc) + timedelta(minutes=16)
    monkeypatch.setattr(tentativas_de_login, "_agora", lambda: daqui_a_16_minutos)
    assert tentar_entrar("limite.fim", SENHA_DE_TESTE).status_code == 200


def test_login_gigante_e_recusado_pelo_formato():
    """O login digitado vai para a tabela de tentativas: mais de 200 letras é recusado antes (422)."""
    assert tentar_entrar("x" * 201, SENHA_ERRADA).status_code == 422


# ---------------- 2. Cabeçalhos de proteção do navegador ----------------

# Os cabeçalhos que toda resposta tem de trazer, com o valor exato
CABECALHOS_DE_PROTECAO = {
    "x-frame-options": "SAMEORIGIN",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
}


def test_toda_resposta_traz_os_cabecalhos_de_protecao():
    """Página pública, desvio para o login, erro da API, css, js e endereço que não existe: todos com os cabeçalhos."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    enderecos = ("/login.html", "/", "/home.html", "/api/eu", "/css/estilos.css", "/js/login.js", "/nao_existe.txt")
    for endereco in enderecos:
        resposta = navegador.get(endereco)
        for nome, valor in CABECALHOS_DE_PROTECAO.items():
            assert resposta.headers.get(nome) == valor, (endereco, nome)
        assert "content-security-policy" in resposta.headers, endereco
        # Em http (a máquina local), o HSTS não vale e não vai
        assert "strict-transport-security" not in resposta.headers, endereco


def test_hsts_so_quando_a_conexao_e_https():
    """Em https, o navegador recebe a ordem de usar sempre https (por 1 ano)."""
    resposta = TestClient(aplicacao, base_url="https://testserver").get("/login.html")
    assert resposta.headers["strict-transport-security"] == "max-age=31536000"


def test_politica_de_conteudo_so_deixa_rodar_script_do_proprio_site():
    """A CSP: script só de arquivo do site (nada inline, nada de eval), quadro só do próprio site, sem plugins."""
    politica = TestClient(aplicacao).get("/login.html").headers["content-security-policy"]
    diretivas = {}
    for diretiva in politica.split(";"):
        partes = diretiva.split()
        diretivas[partes[0]] = partes[1:]
    assert diretivas["default-src"] == ["'self'"]
    assert diretivas["script-src"] == ["'self'"]
    assert diretivas["frame-ancestors"] == ["'self'"]
    assert diretivas["object-src"] == ["'none'"]
    assert "'unsafe-inline'" not in diretivas["style-src"]
    assert "'unsafe-eval'" not in politica


def test_as_paginas_do_front_cabem_na_politica_de_conteudo():
    """Nenhuma página tem script escrito dentro dela, evento inline (onclick=...) ou bloco <style>; tudo o que vem de
    fora é do Google Fonts. Se alguém acrescentar algo assim, a tela quebraria no navegador: este teste avisa antes.
    """
    for pagina in sorted(PASTA_DO_FRONT.glob("*.html")):
        conteudo = pagina.read_text(encoding="utf-8")
        # Todo <script> tem src (arquivo do site)
        for etiqueta in re.findall(r"<script\b[^>]*>", conteudo):
            assert "src=" in etiqueta, (pagina.name, etiqueta)
        # Nenhum evento escrito no HTML (onclick="...", onload="...")
        assert re.search(r"\son[a-z]+\s*=\s*[\"']", conteudo) is None, pagina.name
        # Nenhum bloco <style>
        assert "<style" not in conteudo, pagina.name
        # Todo endereço de fora carregado pela página (src= ou href=) é do Google Fonts (liberado na política)
        for endereco in re.findall(r"(?:src|href)\s*=\s*[\"'](https?://[^\"']+)", conteudo):
            assert endereco.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com")), (pagina.name,
                                                                                                         endereco)


def test_arquivos_do_front_saem_com_o_tipo_certo():
    """Com o nosniff, o navegador só roda .js marcado como JavaScript e só usa .css marcado como CSS."""
    navegador = TestClient(aplicacao)
    assert "javascript" in navegador.get("/js/login.js").headers["content-type"]
    assert navegador.get("/css/estilos.css").headers["content-type"].startswith("text/css")


# ---------------- 3. Limite do tamanho do pedido na entrada ----------------

@pytest.fixture
def limite_de_1_mb(monkeypatch):
    """Baixa o limite do arquivo para 1 MB nestes testes (menos bytes para montar)."""
    monkeypatch.setattr(config, "LIMITE_UPLOAD_MB", 1)


@pytest.fixture
def envio_que_nao_pode_ser_lido(monkeypatch):
    """Troca a leitura do envio por uma que reprova o teste: se ela for chamada, o arquivo grande passou."""

    def leitura_proibida(*_argumentos, **_opcoes):
        raise AssertionError("O arquivo grande chegou à leitura")

    monkeypatch.setattr(cadastro, "enviar_arquivo", leitura_proibida)


def test_pedido_maior_que_o_limite_e_recusado_na_porta_com_a_mensagem_de_sempre(limite_de_1_mb,
                                                                                envio_que_nao_pode_ser_lido):
    """2 MB com limite de 1 MB: 413 com "Arquivo maior que o limite de 1 MB.", sem chegar à rota (nem ao login)."""
    arquivo_grande = b"a;b\n" + b"x" * (2 * 1024 * 1024)
    resposta = TestClient(aplicacao).post("/api/empresa/cadastro/enviar", files={"arquivo": ("grande.csv",
                                                                                            arquivo_grande)})
    assert resposta.status_code == 413
    assert resposta.json()["detail"] == "Arquivo maior que o limite de 1 MB."


def test_arquivo_que_passa_do_limite_por_pouco_e_recusado_ao_ler(limite_de_1_mb, envio_que_nao_pode_ser_lido):
    """1 MB + 10 bytes cabe na folga do formulário, mas a leitura para no limite e recusa com a mesma mensagem."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": "limite.envio", "senha": SENHA_DE_TESTE}).status_code == 200
    arquivo_quase = b"x" * (1024 * 1024 + 10)
    resposta = navegador.post("/api/empresa/cadastro/enviar", files={"arquivo": ("quase.csv", arquivo_quase)})
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Arquivo maior que o limite de 1 MB."


def test_pedido_sem_o_tamanho_declarado_e_recusado():
    """Conteúdo "em pedaços" (sem Content-Length) não dá para conferir antes: recusado com 411."""

    def pedacos():
        yield b"a;b\n"
        yield b"1;2\n"

    resposta = TestClient(aplicacao).post("/api/empresa/cadastro/enviar", content=pedacos(),
                                          headers={"content-type": "text/csv"})
    assert resposta.status_code == 411


def test_pedido_dentro_do_limite_segue_normalmente():
    """O limite não atrapalha o pedido comum: o login (pequeno) passa e a API responde normalmente."""
    assert tentar_entrar("limite.envio", SENHA_DE_TESTE).status_code == 200
