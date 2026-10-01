"""Aba Endomarketing do Portal Interno: o banco gera, confere e publica; a empresa só baixa (ADR-115).

O que estes testes provam:
- a arte usa o kit que o banco definiu: padrão, ou o próprio com as cores, a assinatura e o logo (T19);
- o logo só entra se for PNG ou JPEG de verdade (assinatura do arquivo) e com até 500 KB; a arte, PNG até 2 MB;
- o logo da empresa só se mostra por aqui: subir e tirar saíram (o logo muda na KB do kit, a fonte única);
- o especialista gera com os benefícios que marcou, publica com a arte, e a empresa passa a ver; retirado, some;
- o kit de boas-vindas só se liga a uma inclusão da própria empresa;
- as rotas do banco são só do perfil BANCO (a empresa recebe 403; quem não entrou, 401).
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, empresas, endomarketing_do_banco, kit_de_marca
from services.auth import Usuario
from services.permissoes import AcessoNegado
from tests.test_endomarketing import busca_por_palavras
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# O especialista do banco e o RH da Aurora, para chamar os serviços direto
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")
# Imagens de teste: só a assinatura de cada formato e alguns bytes
PNG_DE_TESTE = kit_de_marca.ASSINATURA_PNG + b"imagem de teste"
JPEG_DE_TESTE = kit_de_marca.ASSINATURA_JPEG + b"imagem de teste"


@pytest.fixture
def conexao(tmp_path, monkeypatch):
    """Um banco novo, só deste teste, com a busca do catálogo por palavras (sem depender do índice do RAG)."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    busca = busca_por_palavras(conexao_do_teste)

    def buscar_beneficios(empresa_id, consulta, dia=None, k=2):
        """A mesma assinatura da busca do RAG; o dia não importa no teste."""
        return busca(empresa_id, consulta, k=k)
    monkeypatch.setattr("rag.busca.buscar_beneficios", buscar_beneficios)
    yield conexao_do_teste
    conexao_do_teste.close()


# ---------------- O kit de marca ----------------

def test_t19_arte_usa_o_kit_que_o_banco_definiu(conexao):
    """T19: sem kit próprio, a arte sai no padrão; com kit próprio, nas cores, com a assinatura e o logo da empresa.

    A 1ª cor gravada pelo banco é a principal (a faixa); a 2ª, a do rodapé; com uma cor só, o rodapé é ela escurecida.
    O logo só entra no kit próprio. Cada empresa recebe só o próprio kit. O kit aqui é a cópia derivada, que o
    "aplicar na empresa" grava a partir da KB do kit publicada (tests/test_kit_na_kb.py prova esse caminho).
    """
    # A Aurora no kit padrão, com um logo guardado: o logo fica guardado, mas não vai para a arte
    empresas.definir_kit(conexao, ESPECIALISTA, "EMP001", "padrao", "", [])
    kit_de_marca.gravar_logo(conexao, "EMP001", PNG_DE_TESTE, "especialista")
    padrao = endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")
    assert padrao["escolhido"] == "padrao" and padrao["cor_principal"] == "#d62839" and padrao["assinatura"] == ""
    assert padrao["tem_logo"] is True and padrao["endereco_do_logo"] is None
    # Kit próprio com duas cores: o logo entra na arte
    empresas.definir_kit(conexao, ESPECIALISTA, "EMP001", "proprio", "Logo verde da Aurora", ["#1f7a4d", "#14573a"])
    proprio = endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")
    assert (proprio["escolhido"], proprio["cor_principal"], proprio["cor_escura"]) == ("proprio", "#1f7a4d", "#14573a")
    assert proprio["assinatura"] == "Aurora Alimentos Ltda."
    assert proprio["endereco_do_logo"] == "/api/banco/empresas/EMP001/kit/logo"
    # Uma cor só: o rodapé é a mesma cor, mais escura
    empresas.definir_kit(conexao, ESPECIALISTA, "EMP001", "proprio", "Logo verde da Aurora", ["#1f7a4d"])
    assert endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")["cor_escura"] == "#155535"
    # A Horizonte continua com o kit dela (o da KB do kit dela), sem nada da Aurora
    horizonte = endomarketing_do_banco.kit_da_empresa(conexao, "EMP002")
    assert horizonte["cor_principal"] == "#0f5c8c"
    assert horizonte["assinatura"] == empresas.obter(conexao, "EMP002")["nome"]
    assert horizonte["endereco_do_logo"] == "/api/banco/empresas/EMP002/kit/logo"
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP002")[0] != PNG_DE_TESTE


def test_logo_so_png_ou_jpeg_de_verdade_e_ate_500_kb(conexao):
    """A conferência olha a assinatura do arquivo: texto renomeado para .png é recusado; grande demais também."""
    # A semente das empresas entra primeiro (ela nasce com o logo da KB do kit, que este teste troca depois)
    empresas.listar(conexao)
    with pytest.raises(ValueError, match="PNG ou JPEG"):
        kit_de_marca.gravar_logo(conexao, "EMP001", b"<svg>nao sou imagem</svg>", "especialista")
    with pytest.raises(ValueError, match="500 KB"):
        kit_de_marca.gravar_logo(conexao, "EMP001", PNG_DE_TESTE + b"0" * kit_de_marca.LIMITE_DO_LOGO, "especialista")
    with pytest.raises(ValueError, match="vazio"):
        kit_de_marca.gravar_logo(conexao, "EMP001", b"", "especialista")
    # JPEG vale; o novo substitui o anterior; tirar apaga
    kit_de_marca.gravar_logo(conexao, "EMP001", JPEG_DE_TESTE, "especialista")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001") == (JPEG_DE_TESTE, "image/jpeg")
    kit_de_marca.tirar_logo(conexao, "EMP001")
    with pytest.raises(KeyError):
        endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001")
    # A empresa não vê o logo pelo serviço do banco
    with pytest.raises(AcessoNegado):
        endomarketing_do_banco.logo_da_empresa(conexao, RH_DA_AURORA, "EMP001")


def test_arte_so_png_de_verdade_e_ate_2_mb():
    """A arte que a tela manda ao publicar é conferida antes de ser guardada."""
    kit_de_marca.conferir_arte(PNG_DE_TESTE)
    with pytest.raises(ValueError, match="PNG"):
        kit_de_marca.conferir_arte(JPEG_DE_TESTE)
    with pytest.raises(ValueError, match="2 MB"):
        kit_de_marca.conferir_arte(PNG_DE_TESTE + b"0" * kit_de_marca.LIMITE_DA_ARTE)


# ---------------- Gerar, publicar e retirar ----------------

def test_tela_da_empresa_traz_kit_beneficios_sugestoes_e_materiais(conexao):
    """O que a aba mostra: os benefícios da própria empresa (sem o atendimento), os tipos, os canais e os materiais."""
    tela = endomarketing_do_banco.tela_da_empresa(conexao, ESPECIALISTA, "EMP001")
    titulos = []
    for beneficio in tela["beneficios"]:
        titulos.append(beneficio["titulo"])
    assert "Conta salário" in titulos and "Canais de dúvidas" not in titulos
    assert tela["empresa"]["nome"] == "Aurora Alimentos Ltda." and tela["materiais"] == []
    assert {"chave": "whatsapp", "nome": "WhatsApp", "maximo_de_blocos": 3} in tela["canais"]
    assert tela["sugestoes"]["sem_conta"] == {"quantidade": 0, "texto": "0"}
    # A empresa não abre a aba do banco; empresa que não existe: KeyError (404)
    with pytest.raises(AcessoNegado):
        endomarketing_do_banco.tela_da_empresa(conexao, RH_DA_AURORA, "EMP001")
    with pytest.raises(KeyError):
        endomarketing_do_banco.tela_da_empresa(conexao, ESPECIALISTA, "EMP999")


def test_especialista_gera_publica_com_arte_e_retira(conexao):
    """O ciclo inteiro pelo serviço do banco: rascunho → publicado (com arte) → retirado, com quem fez cada passo."""
    gerado = endomarketing_do_banco.gerar_material(conexao, ESPECIALISTA, "EMP001", "comunicado", "whatsapp",
                                                   ["Conta salário"])
    assert gerado["situacao"] == "GERADO"
    material = gerado["material"]
    assert material["status"] == "RASCUNHO" and material["nome_do_status"] == "Rascunho"
    assert material["beneficios"] == ["Conta salário"] and material["canal"] == "whatsapp"
    assert material["criado_por"] == "especialista" and len(material["blocos"]) <= 3
    publicado = endomarketing_do_banco.publicar_material(conexao, ESPECIALISTA, "EMP001", material["material_id"],
                                                         PNG_DE_TESTE)
    assert publicado["status"] == "PUBLICADO" and publicado["tem_arte"] is True
    assert publicado["publicado_por"] == "especialista"
    assert endomarketing_do_banco.arte_do_material(conexao, ESPECIALISTA, "EMP001",
                                                   material["material_id"]) == PNG_DE_TESTE
    retirado = endomarketing_do_banco.retirar_material(conexao, ESPECIALISTA, "EMP001", material["material_id"])
    assert retirado["status"] == "RETIRADO" and retirado["nome_do_status"] == "Retirado da empresa"
    # A lista do seletor conta os rascunhos e os publicados de cada empresa
    for empresa in endomarketing_do_banco.empresas_do_endomarketing(conexao, ESPECIALISTA):
        if empresa["empresa_id"] == "EMP001":
            assert (empresa["rascunhos"], empresa["publicados"]) == (0, 0)


def test_arte_invalida_nao_publica(conexao):
    """Uma "arte" que não é PNG é recusada, e o material continua rascunho."""
    gerado = endomarketing_do_banco.gerar_material(conexao, ESPECIALISTA, "EMP001", "faq", "email",
                                                   ["Crédito consignado"])
    with pytest.raises(ValueError, match="PNG"):
        endomarketing_do_banco.publicar_material(conexao, ESPECIALISTA, "EMP001", gerado["material_id"],
                                                 b"<html>nao sou png</html>")
    assert endomarketing_do_banco.tela_da_empresa(conexao, ESPECIALISTA, "EMP001")["materiais"][0]["status"] == \
        "RASCUNHO"


def test_kit_de_boas_vindas_so_para_inclusao_da_propria_empresa(conexao, verdade):
    """A inclusão da Aurora vira sugestão; o kit não se liga a ela num material da Horizonte; gerado, a sugestão some."""
    homologar(conexao, "aurora_carga_inicial", verdade)
    inclusao = homologar(conexao, "aurora_inclusao", verdade)
    sugestoes = endomarketing_do_banco.tela_da_empresa(conexao, ESPECIALISTA, "EMP001")["sugestoes"]
    processamentos_sugeridos = []
    for kit in sugestoes["kits"]:
        processamentos_sugeridos.append(kit["processamento_id"])
    assert processamentos_sugeridos == [inclusao]
    with pytest.raises(ValueError, match="kit de boas-vindas"):
        endomarketing_do_banco.gerar_material(conexao, ESPECIALISTA, "EMP002", "kit_boas_vindas", "email",
                                              ["Conta salário"], processamento_id=inclusao)
    gerado = endomarketing_do_banco.gerar_material(conexao, ESPECIALISTA, "EMP001", "kit_boas_vindas", "email",
                                                   ["Conta salário"], processamento_id=inclusao)
    assert gerado["situacao"] == "GERADO"
    assert endomarketing_do_banco.tela_da_empresa(conexao, ESPECIALISTA, "EMP001")["sugestoes"]["kits"] == []


# ---------------- As rotas da API ----------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um especialista, um RH da Aurora e um da Horizonte."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_endomarketing.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    busca = busca_por_palavras(conexao_do_teste)

    def buscar_beneficios(empresa_id, consulta, dia=None, k=2):
        """A mesma assinatura da busca do RAG; o dia não importa no teste."""
        return busca(empresa_id, consulta, k=k)
    monkeypatch.setattr("rag.busca.buscar_beneficios", buscar_beneficios)
    conexao_do_teste.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_do_banco_gera_publica_e_a_empresa_baixa(api):
    """Pela API: o banco gera com benefícios, publica com a arte (multipart); a Aurora vê e baixa; retirado, some."""
    especialista = entrar("especialista")
    rota_da_empresa = "/api/banco/empresas/EMP001/endomarketing"
    assert especialista.get(rota_da_empresa).json()["beneficios"]
    # Sem benefício marcado: 400 com a mensagem para a pessoa
    sem_beneficio = especialista.post(rota_da_empresa + "/gerar", json={"tipo": "faq", "beneficios": []})
    assert sem_beneficio.status_code == 400 and "benefício" in sem_beneficio.json()["detail"]
    gerado = especialista.post(rota_da_empresa + "/gerar", json={"tipo": "faq", "canal": "mural",
                                                                   "beneficios": ["Conta salário"]}).json()
    material_id = gerado["material_id"]
    rh = entrar("rh.aurora")
    # Rascunho: a empresa ainda não vê
    assert rh.get("/api/empresa/endomarketing").json() == []
    publicado = especialista.post(rota_da_empresa + "/" + material_id + "/publicar",
                                  files={"arte": ("arte.png", PNG_DE_TESTE, "image/png")})
    assert publicado.status_code == 200 and publicado.json()["status"] == "PUBLICADO"
    assert rh.get("/api/empresa/endomarketing").json()[0]["material_id"] == material_id
    assert rh.get("/api/empresa/endomarketing/" + material_id + "/arte").content == PNG_DE_TESTE
    # Publicar de novo: 400; material da Aurora pela rota da Horizonte: 404
    assert especialista.post(rota_da_empresa + "/" + material_id + "/publicar").status_code == 400
    assert especialista.post("/api/banco/empresas/EMP002/endomarketing/" + material_id + "/retirar").status_code == 404
    assert especialista.post(rota_da_empresa + "/" + material_id + "/retirar").status_code == 200
    assert rh.get("/api/empresa/endomarketing").json() == []


def test_api_do_logo_da_empresa_so_mostra(api):
    """O logo da empresa só se mostra por esta rota (a cópia da KB do kit): subir e tirar por aqui saíram (405)."""
    especialista = entrar("especialista")
    rota_do_logo = "/api/banco/empresas/EMP001/kit/logo"
    # A Aurora nasce com o logo da KB do kit dela (o logo.png da pasta da empresa)
    previa = especialista.get(rota_do_logo)
    assert previa.status_code == 200 and previa.headers["content-type"] == "image/png"
    # Subir e tirar o logo por aqui saíram: o logo muda na KB do kit
    subir = especialista.post(rota_do_logo, files={"arquivo": ("logo.png", PNG_DE_TESTE, "image/png")})
    assert subir.status_code == 405
    assert especialista.delete(rota_do_logo).status_code == 405
    # O logo continua o mesmo
    assert especialista.get(rota_do_logo).content == previa.content


def test_rotas_do_endomarketing_do_banco_sao_so_do_banco(api):
    """A empresa recebe 403 e quem não entrou, 401, em todas as rotas do endomarketing do banco."""
    rh = entrar("rh.aurora")
    anonimo = TestClient(aplicacao)
    for rota in ["/api/banco/endomarketing", "/api/banco/empresas/EMP001/endomarketing",
                 "/api/banco/empresas/EMP001/kit/logo", "/api/banco/empresas/EMP001/kit_em_uso",
                 "/api/banco/empresas/EMP001/endomarketing/abc/arte"]:
        assert rh.get(rota).status_code == 403
        assert anonimo.get(rota).status_code == 401
    for rota in ["/api/banco/empresas/EMP001/endomarketing/gerar", "/api/banco/empresas/EMP001/endomarketing/abc/publicar",
                 "/api/banco/empresas/EMP001/endomarketing/abc/retirar"]:
        assert rh.post(rota, json={"tipo": "faq", "beneficios": ["Conta salário"]}).status_code == 403
