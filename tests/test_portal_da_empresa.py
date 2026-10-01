"""Portal Empresa no novo front: Início, Benefícios do time e Endomarketing com dados reais (ADR-69, passo 13).

O que estes testes provam:
- o Início mostra o nome, os números e a etapa da jornada da empresa de quem entrou (sem nenhum funcionário);
- os Benefícios vêm só das KBs publicadas da própria empresa (ADR-125), separados em benefícios e atendimento, sem
  marcas de Markdown;
- o Endomarketing da empresa é só a lista do que o BANCO publicou (ADR-115): rascunho, descartado, retirado e o
  aprovado no modelo antigo não aparecem; a arte só sai publicada e da própria empresa; as rotas de gerar e aprovar
  saíram;
- as rotas são só do perfil EMPRESA, e a empresa vem sempre da sessão.
"""
import pytest
from fastapi.testclient import TestClient

from agents import endomarketing
from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, portal_da_empresa
from tests.test_endomarketing import busca_por_palavras
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Uma "imagem" PNG de teste: só a assinatura do formato e alguns bytes
PNG_DE_TESTE = b"\x89PNG\r\n\x1a\n" + b"arte de teste"


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, só deste teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


# ---------------- Início ----------------

def test_inicio_da_empresa_antes_e_depois_da_carga_inicial(conexao, verdade):
    # Antes de qualquer envio: nenhuma carga inicial
    antes = portal_da_empresa.inicio_da_empresa(conexao, "EMP001")
    assert "Aurora" in antes["empresa"] and antes["jornada"]["carga_inicial"] is None
    assert antes["numeros"]["cadastrados"] == 0
    # Depois da carga inicial cadastrada: a etapa e o número de cadastrados
    homologar(conexao, "aurora_carga_inicial", verdade)
    depois = portal_da_empresa.inicio_da_empresa(conexao, "EMP001")
    assert depois["jornada"]["carga_inicial"]["cadastrados"] == depois["numeros"]["cadastrados"] > 0
    assert depois["jornada"]["inclusoes"] == {"envios": 0, "cadastrados": 0}
    assert depois["linhas_para_corrigir"] == 0
    # O 2º cartão: a carga já foi cadastrada, ninguém em análise pelo banco
    assert depois["numeros"]["pessoas_em_analise"] == 0
    # Sem conta: os Cadastrados que ainda aguardam o retorno do banco (a conta única, ADR-123): todos, sem arquivo
    cadastrados = depois["numeros"]["cadastrados"]
    assert depois["sem_conta"] == {"quantidade": cadastrados, "texto": str(cadastrados)}


# ---------------- Benefícios ----------------

def test_beneficios_vem_das_kbs_publicadas_da_propria_empresa(conexao):
    beneficios = portal_da_empresa.beneficios_da_empresa(conexao, "EMP001")
    titulos = [secao["titulo"] for secao in beneficios["beneficios"]]
    assert "Crédito consignado" in titulos and "Onde consultar" not in titulos
    # O atendimento vai para o quadro de ajuda
    assert [secao["titulo"] for secao in beneficios["atendimento"]] == ["Onde consultar", "Canais de dúvidas"]
    # Texto sem as marcas de negrito do Markdown, e com a fonte (a KB do benefício e a versão dela)
    for secao in beneficios["beneficios"]:
        assert "**" not in secao["texto"] and secao["versao"] == 1 and secao["documento"] == secao["titulo"]
    # A fonte do atendimento é a KB de atendimento da Aurora
    assert beneficios["atendimento"][0]["documento"] == "Canais de atendimento Aurora"
    # A Horizonte não vê as KBs da Aurora ("Salário antecipado" só existe na Aurora)
    da_horizonte = portal_da_empresa.beneficios_da_empresa(conexao, "EMP002")
    assert "Salário antecipado" in titulos
    for secao in da_horizonte["beneficios"]:
        assert secao["titulo"] != "Salário antecipado"
    for secao in da_horizonte["atendimento"]:
        assert "Aurora" not in secao["documento"]


# ---------------- Endomarketing: a empresa só vê o que o banco publicou (ADR-115) ----------------

def _material_da_aurora(conexao, status_final: str | None = None) -> str:
    """Gera um rascunho da Aurora (como o banco faria) e o leva à situação pedida. Devolve o material_id."""
    resultado = endomarketing.gerar_material(conexao, "EMP001", "comunicado", "especialista.banco",
                                             beneficios=["Conta salário"], busca=busca_por_palavras(conexao))
    if status_final == endomarketing.PUBLICADO:
        endomarketing.publicar(conexao, "EMP001", resultado.material_id, "especialista.banco", PNG_DE_TESTE)
    if status_final == endomarketing.DESCARTADO:
        endomarketing.descartar(conexao, "EMP001", resultado.material_id, "especialista.banco")
    return resultado.material_id


def test_empresa_so_ve_o_que_o_banco_publicou(conexao):
    """Rascunho e descartado não aparecem; o publicado aparece com o texto e a arte, sem os dados internos."""
    _material_da_aurora(conexao)
    _material_da_aurora(conexao, endomarketing.DESCARTADO)
    publicado = _material_da_aurora(conexao, endomarketing.PUBLICADO)
    materiais = portal_da_empresa.materiais_da_empresa(conexao, "EMP001")
    assert [material["material_id"] for material in materiais] == [publicado]
    assert materiais[0]["tem_arte"] is True and materiais[0]["blocos"] and materiais[0]["publicado_em"]
    assert materiais[0]["nome_do_tipo"] == "Comunicado interno" and materiais[0]["nome_do_canal"] == "E-mail"
    # Quem gerou, o modelo e as observações ficam só no banco
    for campo in ("criado_por", "modelo", "observacoes", "status"):
        assert campo not in materiais[0]
    # A Horizonte não vê o material da Aurora
    assert portal_da_empresa.materiais_da_empresa(conexao, "EMP002") == []


def test_arte_so_sai_publicada_e_da_propria_empresa(conexao):
    """A arte do publicado sai para a Aurora; retirado deixa de sair; a Horizonte nunca acha (KeyError → 404)."""
    publicado = _material_da_aurora(conexao, endomarketing.PUBLICADO)
    assert portal_da_empresa.arte_do_material(conexao, "EMP001", publicado) == PNG_DE_TESTE
    with pytest.raises(KeyError):
        portal_da_empresa.arte_do_material(conexao, "EMP002", publicado)
    endomarketing.retirar(conexao, "EMP001", publicado, "especialista.banco")
    with pytest.raises(KeyError):
        portal_da_empresa.arte_do_material(conexao, "EMP001", publicado)
    assert portal_da_empresa.materiais_da_empresa(conexao, "EMP001") == []


def test_material_aprovado_pela_empresa_no_modelo_antigo_nao_aparece_mais(conexao):
    """Antes do ADR-115 a empresa aprovava o próprio rascunho; esses materiais não foram validados pelo banco."""
    material_id = _material_da_aurora(conexao)
    conexao.execute("UPDATE materiais_endomarketing SET status = 'APROVADO' WHERE material_id = ?", (material_id,))
    conexao.commit()
    assert portal_da_empresa.materiais_da_empresa(conexao, "EMP001") == []


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_da_empresa(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um RH da Aurora, um da Horizonte e um especialista."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_empresa.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    busca = busca_por_palavras(conexao_do_teste)

    def buscar_beneficios(empresa_id, consulta, dia=None, k=2):
        """A mesma assinatura da busca do RAG; o dia não importa no teste."""
        return busca(empresa_id, consulta, k=k)
    monkeypatch.setattr("rag.busca.buscar_beneficios", buscar_beneficios)
    yield conexao_do_teste
    conexao_do_teste.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_inicio_beneficios_e_materiais_da_empresa(api_da_empresa):
    """A empresa lista e baixa a arte do que foi publicado; a Horizonte recebe 404 na arte da Aurora."""
    publicado = _material_da_aurora(api_da_empresa, endomarketing.PUBLICADO)
    rh = entrar("rh.aurora")
    assert "Aurora" in rh.get("/api/empresa/inicio").json()["empresa"]
    assert rh.get("/api/empresa/beneficios").json()["beneficios"]
    assert rh.get("/api/empresa/endomarketing").json()[0]["material_id"] == publicado
    arte = rh.get("/api/empresa/endomarketing/" + publicado + "/arte")
    assert arte.status_code == 200 and arte.content == PNG_DE_TESTE
    assert arte.headers["content-type"] == "image/png" and "attachment" in arte.headers["content-disposition"]
    assert entrar("rh.horizonte").get("/api/empresa/endomarketing/" + publicado + "/arte").status_code == 404


def test_api_da_empresa_nao_gera_nem_aprova_material(api_da_empresa):
    """ADR-115: as rotas antigas de gerar, aprovar, sugestões e kit não existem mais para a empresa."""
    rh = entrar("rh.aurora")
    assert rh.post("/api/empresa/endomarketing/gerar", json={"tipo": "faq"}).status_code in (404, 405)
    assert rh.post("/api/empresa/endomarketing/abc/decidir", json={"aprovar": True}).status_code in (404, 405)
    assert rh.get("/api/empresa/endomarketing/sugestoes").status_code == 404
    assert rh.get("/api/empresa/endomarketing/kit").status_code == 404


def test_api_da_empresa_recusa_o_banco_e_quem_nao_entrou(api_da_empresa):
    especialista = entrar("especialista")
    anonimo = TestClient(aplicacao)
    for rota in ["/api/empresa/inicio", "/api/empresa/beneficios", "/api/empresa/endomarketing",
                 "/api/empresa/endomarketing/abc/arte"]:
        assert especialista.get(rota).status_code == 403
        assert anonimo.get(rota).status_code == 401
