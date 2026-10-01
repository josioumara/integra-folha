"""As conversas do "Posso ajudar?" entre a empresa e o especialista do banco (ADR-69, passo 14).

O que estes testes provam:
- a empresa escreve e lê só a própria conversa; o banco vê todas, responde e marca como resolvida;
- mensagem nova reabre a conversa resolvida;
- o sinal (a "bolinha") conta as conversas abertas: sem resposta do especialista ou ainda não marcadas como
  respondidas; marcar como respondida fecha, mesmo com a última palavra da empresa;
- mensagem vazia ou longa demais é recusada;
- as rotas respeitam o perfil (empresa, banco, sem login) e a empresa vem da sessão.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, mensagens
from services.auth import Usuario

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Usuários de mentira para chamar o serviço direto
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")
RH_DA_HORIZONTE = Usuario(login="rh.horizonte", perfil=Perfil.EMPRESA, empresa_id="EMP002")
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, só deste teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def abertas_por_empresa(conexao) -> dict:
    """As conversas abertas no formato curto {empresa_id: sem_resposta}. Ex.: {"EMP001": True}."""
    abertas = {}
    for item in mensagens.empresas_com_conversa_aberta(conexao):
        abertas[item["empresa_id"]] = item["sem_resposta"]
    return abertas


def test_conversa_entre_a_empresa_e_o_banco(conexao):
    # Antes de escrever: conversa vazia, e o banco não vê nada
    assert mensagens.conversa_da_empresa(conexao, "EMP001")["mensagens"] == []
    assert mensagens.conversas_da_carteira(conexao) == []
    # A Aurora escreve, da tela de cadastro
    mensagens.mandar_mensagem(conexao, RH_DA_AURORA, "  A coluna Turno ficou de fora. Tudo bem?  ", "Cadastrar funcionários")
    conversa = mensagens.conversa_da_empresa(conexao, "EMP001")
    assert conversa["mensagens"][0]["texto"] == "A coluna Turno ficou de fora. Tudo bem?"
    assert conversa["mensagens"][0]["de"] == "empresa" and conversa["mensagens"][0]["autor"] == "rh.aurora"
    assert conversa["mensagens"][0]["contexto"] == "Cadastrar funcionários"
    # O banco vê a conversa, e ela está aberta e sem resposta
    assert [item["id"] for item in mensagens.conversas_da_carteira(conexao)] == ["EMP001"]
    assert abertas_por_empresa(conexao) == {"EMP001": True}
    # O banco responde: a conversa continua aberta (falta marcar como respondida), agora com resposta
    mensagens.mandar_mensagem(conexao, ESPECIALISTA, "Tudo bem: Turno não faz parte do layout.", empresa_id="EMP001")
    assert mensagens.conversa_da_empresa(conexao, "EMP001")["mensagens"][1]["de"] == "banco"
    assert abertas_por_empresa(conexao) == {"EMP001": False}
    # A Horizonte não vê a conversa da Aurora
    assert mensagens.conversa_da_empresa(conexao, "EMP002")["mensagens"] == []


def test_resolvida_e_reaberta_por_mensagem_nova(conexao):
    mensagens.mandar_mensagem(conexao, RH_DA_AURORA, "Dúvida rápida.")
    mensagens.marcar_resolvida(conexao, ESPECIALISTA, "EMP001")
    assert mensagens.conversa_da_empresa(conexao, "EMP001")["resolvida"] is True
    # Marcada como respondida: fechada, mesmo com a última palavra da empresa
    assert abertas_por_empresa(conexao) == {}
    # A empresa escreve de novo: a conversa reabre e volta a esperar o banco
    mensagens.mandar_mensagem(conexao, RH_DA_AURORA, "Mais uma dúvida.")
    assert mensagens.conversa_da_empresa(conexao, "EMP001")["resolvida"] is False
    assert abertas_por_empresa(conexao) == {"EMP001": True}
    # A empresa não marca como resolvida, e conversa sem mensagem não é resolvida
    with pytest.raises(PermissionError):
        mensagens.marcar_resolvida(conexao, RH_DA_AURORA, "EMP001")
    with pytest.raises(ValueError):
        mensagens.marcar_resolvida(conexao, ESPECIALISTA, "EMP004")


def test_mensagem_vazia_longa_e_empresa_errada_recusadas(conexao):
    with pytest.raises(ValueError):
        mensagens.mandar_mensagem(conexao, RH_DA_AURORA, "   ")
    with pytest.raises(ValueError):
        mensagens.mandar_mensagem(conexao, RH_DA_AURORA, "a" * (mensagens.TAMANHO_MAXIMO + 1))
    with pytest.raises(ValueError):
        mensagens.mandar_mensagem(conexao, ESPECIALISTA, "Olá", empresa_id="EMP999")
    # A empresa escreve sempre na própria conversa, mesmo que peça outra
    mensagens.mandar_mensagem(conexao, RH_DA_HORIZONTE, "Olá", empresa_id="EMP001")
    assert mensagens.conversa_da_empresa(conexao, "EMP001")["mensagens"] == []
    assert len(mensagens.conversa_da_empresa(conexao, "EMP002")["mensagens"]) == 1


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_das_mensagens(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um RH da Aurora, um da Horizonte e um especialista."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_mensagens.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao_do_teste.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_da_conversa_por_perfil(api_das_mensagens):
    rh = entrar("rh.aurora")
    especialista = entrar("especialista")
    anonimo = TestClient(aplicacao)
    # A empresa escreve e lê
    assert rh.post("/api/empresa/conversa", json={"texto": "Olá, banco!", "contexto": "Início"}).status_code == 200
    assert rh.get("/api/empresa/conversa").json()["mensagens"][0]["texto"] == "Olá, banco!"
    # O banco lê, responde e resolve
    assert especialista.get("/api/banco/conversas").json()[0]["id"] == "EMP001"
    assert especialista.post("/api/banco/conversas/EMP001", json={"texto": "Olá, Aurora!"}).status_code == 200
    assert especialista.post("/api/banco/conversas/EMP001/resolver").status_code == 200
    assert rh.get("/api/empresa/conversa").json()["resolvida"] is True
    # A Horizonte não vê a conversa da Aurora
    assert entrar("rh.horizonte").get("/api/empresa/conversa").json()["mensagens"] == []
    # Perfis trocados e sem login
    assert rh.get("/api/banco/conversas").status_code == 403
    assert rh.post("/api/banco/conversas/EMP001", json={"texto": "Oi"}).status_code == 403
    assert especialista.get("/api/empresa/conversa").status_code == 403
    assert anonimo.get("/api/empresa/conversa").status_code == 401
    assert anonimo.get("/api/banco/conversas").status_code == 401
    # Mensagem vazia: 400
    assert rh.post("/api/empresa/conversa", json={"texto": "  "}).status_code == 400


def gravar_mensagem(conexao, empresa_id: str, de: str, quando: str) -> None:
    """Grava uma mensagem com a hora escolhida (o serviço grava sempre a hora de agora)."""
    conexao.execute("INSERT INTO mensagens_de_ajuda (empresa_id, de, autor, contexto, texto, criado_em) "
                    "VALUES (?, ?, ?, '', 'texto', ?)", (empresa_id, de, de, quando))
    conexao.commit()


def test_prazo_de_um_dia_util():
    """ADR-94: o prazo é o mesmo horário do próximo dia útil; o fim de semana não conta."""
    from datetime import datetime, timezone
    quinta = datetime(2026, 9, 24, 15, tzinfo=timezone.utc)
    assert mensagens.prazo_de_um_dia_util(quinta) == datetime(2026, 9, 25, 15, tzinfo=timezone.utc)
    sexta = datetime(2026, 9, 25, 15, tzinfo=timezone.utc)
    assert mensagens.prazo_de_um_dia_util(sexta) == datetime(2026, 9, 28, 15, tzinfo=timezone.utc)
    sabado = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
    assert mensagens.prazo_de_um_dia_util(sabado) == datetime(2026, 9, 29, 0, tzinfo=timezone.utc)


def test_prazo_das_respostas_na_carteira(conexao):
    """Respondida no prazo, respondida fora do prazo e esperando atrasada; conversa resolvida não conta."""
    from datetime import datetime, timezone
    mensagens.conversa_da_empresa(conexao, "EMP001")
    # Aurora: pergunta na quinta 10h, duas mensagens seguidas (contam como uma vez), resposta na sexta 9h (no prazo)
    gravar_mensagem(conexao, "EMP001", "empresa", "2026-09-24T10:00:00+00:00")
    gravar_mensagem(conexao, "EMP001", "empresa", "2026-09-24T11:00:00+00:00")
    gravar_mensagem(conexao, "EMP001", "banco", "2026-09-25T09:00:00+00:00")
    # Horizonte: pergunta na segunda 10h, resposta na quarta 10h (fora do prazo); depois pergunta de novo na quarta
    gravar_mensagem(conexao, "EMP002", "empresa", "2026-09-21T10:00:00+00:00")
    gravar_mensagem(conexao, "EMP002", "banco", "2026-09-23T10:00:00+00:00")
    gravar_mensagem(conexao, "EMP002", "empresa", "2026-09-23T12:00:00+00:00")
    # Brisa: pergunta sem resposta, mas a conversa foi resolvida pelo banco (não conta como esperando)
    gravar_mensagem(conexao, "EMP003", "empresa", "2026-09-21T10:00:00+00:00")
    mensagens.marcar_resolvida(conexao, ESPECIALISTA, "EMP003")
    prazo = mensagens.prazo_das_respostas(conexao, agora=datetime(2026, 9, 25, 12, tzinfo=timezone.utc))
    assert prazo == {"respondidas": 2, "no_prazo": 1, "percentual_no_prazo": 50, "esperando": 1, "atrasadas": 1,
                     "atrasadas_por_empresa": ["EMP002"]}


def test_api_do_prazo_so_para_o_banco(api_das_mensagens):
    assert entrar("rh.aurora").get("/api/banco/conversas/prazo").status_code == 403
    resposta = entrar("especialista").get("/api/banco/conversas/prazo")
    assert resposta.status_code == 200 and resposta.json()["respondidas"] == 0


# ---------------- As conversas abertas: o sinal (a "bolinha") do menu, da aba Conversa e da Carteira ----------------

def test_conversas_abertas_pelo_criterio_do_sinal(conexao):
    """Aberta = tem mensagem e não foi marcada como respondida; a lista vem da mensagem mais recente para a mais antiga."""
    # Cria as tabelas: sem nenhuma mensagem, nada aberto
    mensagens.conversa_da_empresa(conexao, "EMP001")
    assert mensagens.empresas_com_conversa_aberta(conexao) == []
    # Aurora: pergunta e espera o especialista (aberta, sem resposta)
    gravar_mensagem(conexao, "EMP001", "empresa", "2026-09-28T10:00:00+00:00")
    # Horizonte: pergunta, o especialista responde e não marca (aberta, com resposta)
    gravar_mensagem(conexao, "EMP002", "empresa", "2026-09-29T10:00:00+00:00")
    gravar_mensagem(conexao, "EMP002", "banco", "2026-09-29T11:30:00+00:00")
    # Brisa: agradece e o especialista marca como respondida sem escrever (fechada, com a última palavra da empresa)
    gravar_mensagem(conexao, "EMP003", "empresa", "2026-09-30T09:00:00+00:00")
    mensagens.marcar_resolvida(conexao, ESPECIALISTA, "EMP003")
    # Uma empresa que não está na carteira não entra (a mesma regra da lista das conversas)
    gravar_mensagem(conexao, "EMP999", "empresa", "2026-09-30T12:00:00+00:00")
    assert mensagens.empresas_com_conversa_aberta(conexao) == [
        {"empresa_id": "EMP002", "sem_resposta": False, "ultima_mensagem_em": "2026-09-29T11:30:00+00:00"},
        {"empresa_id": "EMP001", "sem_resposta": True, "ultima_mensagem_em": "2026-09-28T10:00:00+00:00"},
    ]


def test_conversa_aberta_pelo_especialista_e_reaberta_pela_empresa(conexao):
    """O especialista pode começar a conversa (ela abre, com a última palavra dele); resolvida, a mensagem nova reabre."""
    # O especialista escreve primeiro para a Vale Verde, que nunca escreveu: a conversa abre, sem esperar por ele
    mensagens.mandar_mensagem(conexao, ESPECIALISTA, "Olá! Posso ajudar com o primeiro arquivo?", empresa_id="EMP004")
    assert abertas_por_empresa(conexao) == {"EMP004": False}
    # Marcada como respondida: fecha
    mensagens.marcar_resolvida(conexao, ESPECIALISTA, "EMP004")
    assert abertas_por_empresa(conexao) == {}
    # A empresa responde: reabre, agora esperando o especialista
    rh_da_vale_verde = Usuario(login="rh.valeverde", perfil=Perfil.EMPRESA, empresa_id="EMP004")
    mensagens.mandar_mensagem(conexao, rh_da_vale_verde, "Obrigada, vamos mandar amanhã.")
    assert abertas_por_empresa(conexao) == {"EMP004": True}
    # A última mensagem traz a data e a hora em que ela foi gravada
    ultima_gravada = mensagens.conversa_da_empresa(conexao, "EMP004")["mensagens"][-1]["quando"]
    assert mensagens.empresas_com_conversa_aberta(conexao)[0]["ultima_mensagem_em"] == ultima_gravada


def test_api_das_conversas_abertas_so_para_o_banco(api_das_mensagens):
    """A rota do sinal: o banco vê a lista e o total; a empresa recebe 403 (nunca vê as outras); sem login, 401."""
    rh = entrar("rh.aurora")
    especialista = entrar("especialista")
    rota = "/api/banco/conversas/abertas"
    # Nada aberto ainda
    assert especialista.get(rota).json() == {"empresas": [], "total": 0}
    # A Aurora pergunta: 1 aberta, esperando o especialista
    assert rh.post("/api/empresa/conversa", json={"texto": "Uma dúvida.", "contexto": "Início"}).status_code == 200
    resposta = especialista.get(rota).json()
    assert resposta["total"] == 1 and resposta["empresas"][0]["empresa_id"] == "EMP001"
    assert resposta["empresas"][0]["sem_resposta"] is True
    # O especialista responde: continua aberta, agora com resposta
    assert especialista.post("/api/banco/conversas/EMP001", json={"texto": "Respondido."}).status_code == 200
    resposta = especialista.get(rota).json()
    assert resposta["total"] == 1 and resposta["empresas"][0]["sem_resposta"] is False
    # Marcada como respondida: sai do sinal
    assert especialista.post("/api/banco/conversas/EMP001/resolver").status_code == 200
    assert especialista.get(rota).json() == {"empresas": [], "total": 0}
    # A empresa (qualquer uma) não vê a lista da carteira; sem login, nada
    assert rh.get(rota).status_code == 403
    assert entrar("rh.horizonte").get(rota).status_code == 403
    assert TestClient(aplicacao).get(rota).status_code == 401
