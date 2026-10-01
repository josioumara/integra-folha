"""O kit de marca com a KB "Kit da marca" como fonte única.

O que estes testes provam:
- num banco novo, a KB do kit e a arte dizem o mesmo: a versão 1 da KB nasce com o logo.png da pasta, e a semente
  das empresas nasce com o kit dessa KB (a escolha, o texto, as cores e o logo), em qualquer ordem;
- o logo só se anexa a um RASCUNHO da KB do kit, e só PNG ou JPEG de verdade, até 500 KB (um texto renomeado para
  .png é recusado); a versão nova nasce com o logo da versão em que se baseia; a revisão leva o da publicada;
- a trava só avisa (regra "Logo") o kit próprio sem logo: não bloqueia;
- publicar a KB do kit aplica na empresa: a escolha, as cores e o logo da versão vão para a cópia que a arte lê;
- retirar a KB do kit volta a empresa ao padrão, e publicar a versão retirada de novo traz o kit de volta (nada se
  perde); a empresa que nunca teve KB do kit fica como está;
- o kit em uso (a prévia da tela de gerar o material) mostra o kit da arte e a versão da KB, sem nada de outra empresa;
- as rotas novas são só do BANCO (401 sem login, 403 para a empresa), e as rotas do kit que saíram dão 404 ou 405.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, endomarketing_do_banco, kbs_endomarketing, kbs_publicacao, kit_de_marca
from services import empresas as cadastro_de_empresas
from services import portal_do_banco
from services.auth import Usuario
from tests.test_empresas import dados_da_empresa_nova

ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")
SENHA_DE_TESTE = "senha-de-teste-123"
# A KB do kit da Aurora (a versão 1 sai de data/kbs_endomarketing/EMP001/kit_da_marca.md)
KIT_DA_AURORA = "EMP001-KIT-DA-MARCA"
# Imagens de teste: só a assinatura de cada formato e alguns bytes
PNG_NOVO = kit_de_marca.ASSINATURA_PNG + b"logo novo de teste"
JPEG_NOVO = kit_de_marca.ASSINATURA_JPEG + b"logo em jpeg de teste"
# As 5 cores da arte que o kit em uso devolve
CHAVES_DAS_CORES = {"cor_principal", "cor_escura", "cor_fundo", "cor_texto", "cor_apoio"}


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, só deste teste (as KBs da versão 1 e as empresas da semente entram na primeira consulta)."""
    conexao_do_teste = banco.conectar(tmp_path / "kit.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture
def sem_indice(monkeypatch):
    """Troca a reindexação (do catálogo e das KBs) por nada: estes testes não precisam do modelo de embeddings."""
    monkeypatch.setattr(portal_do_banco, "_reindexar_catalogo", lambda conexao_recebida: None)
    monkeypatch.setattr(kbs_publicacao, "_atualizar_kb_no_indice", lambda conexao_recebida, kb_id: True)


def logo_da_pasta(empresa_id: str = "EMP001") -> bytes:
    """O logo.png da pasta da empresa nos arquivos do projeto (o que a versão 1 da KB do kit recebe)."""
    return (kbs_endomarketing.PASTA_DAS_KBS / empresa_id / kbs_endomarketing.ARQUIVO_DO_LOGO_NA_PASTA).read_bytes()


def salvar_rascunho_do_kit(conexao, kit_escolhido: str = "proprio", cores: str = "#1f7a4d, #14573a") -> dict:
    """Grava uma versão nova (rascunho) da KB do kit da Aurora, como a tela faz, com a escolha e as cores pedidas.

    Devolve o que a gravação devolve: {kb_id, versao, situacao, achados}.
    """
    kit = kbs_endomarketing.obter(conexao, KIT_DA_AURORA)
    ficha = dict(kit["ficha"])
    ficha["kit_escolhido"] = kit_escolhido
    ficha["cores"] = cores
    return kbs_publicacao.salvar_kb(conexao, ESPECIALISTA, ficha, kit["corpo"], KIT_DA_AURORA)


def regras(achados: list[dict]) -> set:
    """Os nomes das regras que apareceram nos achados."""
    nomes = set()
    for achado in achados:
        nomes.add(achado["regra"])
    return nomes


# ---------------- Num banco novo, a KB e a arte dizem o mesmo ----------------

def test_banco_novo_a_kb_do_kit_e_a_arte_dizem_o_mesmo(conexao):
    # A versão 1 da KB do kit da Aurora: publicada, sem o antigo campo "logo", com o logo.png da pasta anexado
    kit = kbs_endomarketing.obter(conexao, KIT_DA_AURORA)
    assert (kit["versao"], kit["situacao"]) == (1, kbs_endomarketing.PUBLICADA) and "logo" not in kit["ficha"]
    assert kit["tem_logo"] and kit["endereco_do_logo"] == f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes/1/logo"
    assert kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, 1) == (logo_da_pasta(), kit_de_marca.TIPO_PNG)
    # A semente nasce com o kit dessa KB: a arte usa a escolha, as cores e o logo dela
    arte = endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")
    assert (arte["escolhido"], arte["cor_principal"], arte["cor_escura"]) == ("proprio", "#e8772e", "#8a3b12")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001") == (logo_da_pasta(),
                                                                                       kit_de_marca.TIPO_PNG)
    assert cadastro_de_empresas.obter(conexao, "EMP001")["kit_texto"].startswith("Aurora Alimentos, indústria")
    # O kit em uso aponta para a versão publicada da KB
    em_uso = kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, "EMP001")
    assert (em_uso["kb_id"], em_uso["kb_versao"], em_uso["tem_logo"]) == (KIT_DA_AURORA, 1, True)


def test_a_semente_nasce_com_o_kit_da_kb_em_qualquer_ordem(conexao):
    """A arte lida antes de qualquer KB ser carregada já sai com o kit da KB (a semente lê os mesmos arquivos)."""
    arte = endomarketing_do_banco.kit_da_empresa(conexao, "EMP002")
    assert (arte["escolhido"], arte["cor_principal"]) == ("proprio", "#0f5c8c")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP002")[0] == logo_da_pasta("EMP002")
    # Só depois a KB é carregada: ela diz o mesmo
    kit = kbs_endomarketing.obter(conexao, "EMP002-KIT-DA-MARCA")
    assert kbs_endomarketing.cores_do_kit(kit["ficha"])[0] == "#0f5c8c" and kit["tem_logo"]


# ---------------- O logo anexado à versão ----------------

def test_o_logo_so_entra_num_rascunho_e_so_imagem_de_verdade(conexao):
    versao = salvar_rascunho_do_kit(conexao)["versao"]
    # Um texto renomeado para .png, uma imagem grande demais e um arquivo vazio: recusados
    with pytest.raises(ValueError, match="PNG ou JPEG"):
        kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, versao, b"<svg>nao sou imagem</svg>")
    with pytest.raises(ValueError, match="500 KB"):
        kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, versao,
                                         PNG_NOVO + b"0" * kit_de_marca.LIMITE_DO_LOGO)
    with pytest.raises(ValueError, match="vazio"):
        kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, versao, b"")
    # PNG e JPEG de verdade valem; o novo substitui o anterior
    resposta = kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, versao, JPEG_NOVO)
    assert resposta == {"kb_id": KIT_DA_AURORA, "versao": versao, "tem_logo": True}
    assert kbs_publicacao.logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, versao) == (JPEG_NOVO, kit_de_marca.TIPO_JPEG)
    # A versão publicada não recebe logo (mudaria a arte sem publicar); uma KB que não é do kit, também não
    with pytest.raises(ValueError, match="rascunho"):
        kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, 1, PNG_NOVO)
    with pytest.raises(ValueError, match="kit da marca"):
        kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, "EMP001-BEN-CONSIGNADO", 1, PNG_NOVO)
    # Versão que não existe: KeyError (vira 404); a empresa não anexa nada
    with pytest.raises(KeyError):
        kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, 99, PNG_NOVO)
    with pytest.raises(PermissionError):
        kbs_publicacao.enviar_logo_da_kb(conexao, RH_DA_AURORA, KIT_DA_AURORA, versao, PNG_NOVO)
    # A versão publicada continua com o logo dela
    assert kbs_publicacao.logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, 1)[0] == logo_da_pasta()


def test_versao_nova_nasce_com_o_logo_da_anterior_e_so_o_rascunho_perde(conexao):
    logo_da_v1 = kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, 1)
    segunda = salvar_rascunho_do_kit(conexao)["versao"]
    # A versão nova nasce com o logo da última versão
    assert kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, segunda) == logo_da_v1
    # Trocado no rascunho, a versão seguinte já nasce com o novo
    kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, segunda, PNG_NOVO)
    terceira = salvar_rascunho_do_kit(conexao)["versao"]
    assert kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, terceira)[0] == PNG_NOVO
    # Tirado do rascunho: a versão fica sem logo; a versão 1 continua com o dela
    resposta = kbs_publicacao.tirar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, terceira)
    assert resposta == {"kb_id": KIT_DA_AURORA, "versao": terceira, "tem_logo": False}
    with pytest.raises(KeyError):
        kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, terceira)
    assert kbs_endomarketing.obter(conexao, KIT_DA_AURORA, terceira)["tem_logo"] is False
    assert kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, 1) == logo_da_v1
    # Tirar o logo da versão publicada: recusado
    with pytest.raises(ValueError, match="rascunho"):
        kbs_publicacao.tirar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, 1)


def test_revisar_leva_o_logo_da_versao_publicada(conexao, sem_indice):
    """A revisão da vigência parte da versão publicada: um rascunho mais novo, com outro logo, não conta."""
    rascunho = salvar_rascunho_do_kit(conexao)["versao"]
    kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, rascunho, PNG_NOVO)
    revisado = kbs_publicacao.revisar_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, "2099-12-31")
    assert revisado["kb"]["situacao"] == kbs_endomarketing.PUBLICADA
    nova = revisado["kb"]["versao"]
    assert kbs_endomarketing.imagem_do_logo(conexao, KIT_DA_AURORA, nova)[0] == logo_da_pasta()


def test_a_trava_so_avisa_o_kit_proprio_sem_logo(conexao, sem_indice):
    # Um rascunho sem logo: a versão seguinte herda "sem logo", e gravar só avisa
    segunda = salvar_rascunho_do_kit(conexao)["versao"]
    kbs_publicacao.tirar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, segunda)
    terceira = salvar_rascunho_do_kit(conexao)
    assert terceira["situacao"] == kbs_endomarketing.RASCUNHO and regras(terceira["achados"]) == {"Logo"}
    # O "Conferir" da tela conta o logo que a versão nova herdaria (o da última versão: nenhum)
    kit = kbs_endomarketing.obter(conexao, KIT_DA_AURORA, terceira["versao"])
    assert "Logo" in regras(kbs_publicacao.verificar_kb(conexao, ESPECIALISTA, kit["ficha"], kit["corpo"],
                                                         KIT_DA_AURORA))
    # Com o logo anexado, a publicação não avisa
    kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, terceira["versao"], PNG_NOVO)
    kbs_publicacao.publicar_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, terceira["versao"])
    for achado in kbs_endomarketing.listar_achados(conexao, "EMP001"):
        if achado["momento"] == kbs_endomarketing.PUBLICAR and achado["versao"] == terceira["versao"]:
            assert achado["regra"] != "Logo"
    # O kit padrão sem logo não avisa
    padrao = salvar_rascunho_do_kit(conexao, kit_escolhido="padrao")
    kbs_publicacao.tirar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, padrao["versao"])
    assert "Logo" not in regras(salvar_rascunho_do_kit(conexao, kit_escolhido="padrao")["achados"])


# ---------------- Publicar e retirar: o "aplicar na empresa" ----------------

def test_publicar_a_kb_do_kit_aplica_escolha_cores_e_logo_na_empresa(conexao, sem_indice):
    rascunho = salvar_rascunho_do_kit(conexao, cores="#1f7a4d, #14573a")["versao"]
    kbs_publicacao.enviar_logo_da_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, rascunho, PNG_NOVO)
    # O rascunho ainda não muda a arte
    assert endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")["cor_principal"] == "#e8772e"
    publicado = kbs_publicacao.publicar_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, rascunho)
    assert publicado["aplicacao"]["kit"] == {"aplicado": True, "kit_escolhido": "proprio", "kb_id": KIT_DA_AURORA,
                                             "versao": rascunho, "logo": True}
    # A arte passa a usar as cores e o logo da versão publicada
    arte = endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")
    assert (arte["cor_principal"], arte["cor_escura"]) == ("#1f7a4d", "#14573a")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001") == (PNG_NOVO, kit_de_marca.TIPO_PNG)
    # O kit em uso mostra o mesmo, com a versão da KB
    em_uso = kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, "EMP001")
    assert em_uso == {"escolhido": "proprio", "nome": "Kit da Aurora Alimentos Ltda.",
                      "cores": {"cor_principal": "#1f7a4d", "cor_escura": "#14573a", "cor_fundo": "#ffffff",
                                "cor_texto": "#222222", "cor_apoio": "#5c6366"},
                      "tem_logo": True, "endereco_do_logo": "/api/banco/empresas/EMP001/kit/logo",
                      "kb_id": KIT_DA_AURORA, "kb_versao": rascunho}
    # O padrão, publicado: a arte sai no padrão, e o logo guardado não entra
    padrao = salvar_rascunho_do_kit(conexao, kit_escolhido="padrao")["versao"]
    kbs_publicacao.publicar_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, padrao)
    em_uso = kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, "EMP001")
    assert (em_uso["escolhido"], em_uso["nome"], em_uso["tem_logo"], em_uso["endereco_do_logo"]) == (
        "padrao", "Padrão Santander", False, None)
    assert em_uso["cores"]["cor_principal"] == "#d62839" and em_uso["kb_versao"] == padrao
    # A Horizonte não mudou em nada (cada empresa só com o próprio kit)
    horizonte = kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, "EMP002")
    assert (horizonte["cores"]["cor_principal"], horizonte["kb_id"]) == ("#0f5c8c", "EMP002-KIT-DA-MARCA")
    assert set(horizonte["cores"]) == CHAVES_DAS_CORES


def test_retirar_volta_ao_padrao_e_publicar_de_novo_traz_o_kit(conexao, sem_indice):
    retirado = kbs_publicacao.retirar_kb(conexao, ESPECIALISTA, KIT_DA_AURORA)
    assert retirado["aplicacao"]["kit"] == {"aplicado": True, "kit_escolhido": "padrao", "kb_id": None,
                                            "versao": None, "logo": False}
    # A cópia que a arte lê voltou ao padrão: sem texto, sem cores e sem logo
    empresa = cadastro_de_empresas.obter(conexao, "EMP001")
    assert (empresa["kit_escolhido"], empresa["kit_texto"], empresa["kit_cores"]) == ("padrao", "", [])
    with pytest.raises(KeyError):
        endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001")
    em_uso = kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, "EMP001")
    assert (em_uso["escolhido"], em_uso["kb_id"], em_uso["kb_versao"], em_uso["tem_logo"]) == (
        "padrao", None, None, False)
    # Nada se perde: a versão retirada guarda as cores e o logo, e publicada de novo traz o kit de volta
    kbs_publicacao.publicar_kb(conexao, ESPECIALISTA, KIT_DA_AURORA, 1)
    assert endomarketing_do_banco.kit_da_empresa(conexao, "EMP001")["cor_principal"] == "#e8772e"
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001")[0] == logo_da_pasta()


def test_empresa_sem_kb_do_kit_fica_como_esta(conexao):
    """A empresa que ainda não tem KB do kit (o kit estava só no cadastro, antes da migração) não perde o kit."""
    empresa_id = cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova())["empresa_id"]
    cadastro_de_empresas.definir_kit(conexao, ESPECIALISTA, empresa_id, "proprio", "Logo azul", ["#123456"])
    resultado = kbs_publicacao.aplicar_o_kit(conexao, ESPECIALISTA, empresa_id)
    assert resultado["aplicado"] is False and "fica como está" in resultado["motivo"]
    assert cadastro_de_empresas.obter(conexao, empresa_id)["kit_cores"] == ["#123456"]
    # O kit em uso é o da arte, sem KB para editar
    em_uso = kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, empresa_id)
    assert (em_uso["escolhido"], em_uso["cores"]["cor_principal"], em_uso["kb_id"]) == ("proprio", "#123456", None)
    # Só o banco aplica e vê o kit em uso
    with pytest.raises(PermissionError):
        kbs_publicacao.aplicar_o_kit(conexao, RH_DA_AURORA, empresa_id)
    with pytest.raises(PermissionError):
        kbs_publicacao.kit_em_uso(conexao, RH_DA_AURORA, "EMP001")
    # Empresa que não existe: KeyError (vira 404)
    with pytest.raises(KeyError):
        kbs_publicacao.kit_em_uso(conexao, ESPECIALISTA, "EMP999")


def test_kit_novo_de_um_script_nasce_publicado_e_aplicado(conexao, sem_indice):
    """O caminho da migração e da carga da base viva: a KB do kit nova, já publicada, com o logo, e o kit aplicado."""
    empresa_id = cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova())["empresa_id"]
    resultado = kbs_publicacao.publicar_kit_novo(conexao, ESPECIALISTA, empresa_id, "proprio", "Logo azul da Cedro",
                                                 ["#123456", "#0a1b2c"], PNG_NOVO, "Teste")
    assert resultado["kb"]["kb_id"] == f"{empresa_id}-KIT-DA-MARCA" and resultado["kb"]["situacao"] == "PUBLICADA"
    assert resultado["kit"]["logo"] is True and resultado["indice_atualizado"] is True
    # A KB segue o modelo (passou na trava) e diz o kit; a arte usa o mesmo
    kit = kbs_endomarketing.obter(conexao, resultado["kb"]["kb_id"])
    assert kit["ficha"]["kit_escolhido"] == "proprio" and kbs_endomarketing.cores_do_kit(kit["ficha"]) == [
        "#123456", "#0a1b2c"]
    assert kbs_endomarketing.texto_da_secao(kit["corpo"], "Identidade") == "Logo azul da Cedro"
    arte = endomarketing_do_banco.kit_da_empresa(conexao, empresa_id)
    assert (arte["cor_principal"], arte["cor_escura"], arte["tem_logo"]) == ("#123456", "#0a1b2c", True)
    # Um kit próprio sem nenhuma cor não passa na trava (e nada é gravado para a empresa)
    outra = cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova(12))["empresa_id"]
    with pytest.raises(kbs_endomarketing.TravaBloqueou):
        kbs_publicacao.publicar_kit_novo(conexao, ESPECIALISTA, outra, "proprio", "Sem cor", [], None, "Teste")
    assert cadastro_de_empresas.obter(conexao, outra)["kit_escolhido"] == "padrao"


# ---------------- As rotas ----------------

@pytest.fixture
def api(tmp_path, monkeypatch, sem_indice):
    """A API apontada para um banco só deste teste, com um especialista e um RH da Aurora."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_kit.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def arquivo(conteudo: bytes, nome: str = "logo.png", tipo: str = "image/png") -> dict:
    """O campo "arquivo" de um envio multipart, como o navegador manda."""
    return {"arquivo": (nome, conteudo, tipo)}


def test_api_do_logo_da_kb_anexa_mostra_e_tira(api):
    especialista = entrar("especialista")
    # A KB do kit traz o logo da versão mostrada
    kit = especialista.get(f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}").json()
    assert kit["tem_logo"] and kit["endereco_do_logo"] == f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes/1/logo"
    # Um rascunho pela rota de sempre (a ficha sem "logo"): ele nasce com o logo da versão anterior
    ficha = kit["ficha"]
    ficha["cores"] = "#1f7a4d"
    criado = especialista.post(f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes",
                               json={"ficha": ficha, "corpo": kit["corpo"]}).json()
    rota_do_logo = f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes/{criado['versao']}/logo"
    assert especialista.get(rota_do_logo).content == logo_da_pasta()
    # Um arquivo falso: 400, com o motivo para a pessoa
    recusado = especialista.post(rota_do_logo, files=arquivo(b"texto qualquer"))
    assert recusado.status_code == 400 and "PNG ou JPEG" in recusado.json()["detail"]
    # Um JPEG de verdade: anexado, e a prévia mostra a imagem com o tipo certo
    enviado = especialista.post(rota_do_logo, files=arquivo(JPEG_NOVO, "logo.jpg", "image/jpeg"))
    assert enviado.status_code == 200
    assert enviado.json() == {"kb_id": KIT_DA_AURORA, "versao": criado["versao"], "tem_logo": True}
    previa = especialista.get(rota_do_logo)
    assert previa.content == JPEG_NOVO and previa.headers["content-type"] == "image/jpeg"
    # Tirar: a versão fica sem logo (404)
    assert especialista.delete(rota_do_logo).json() == {"kb_id": KIT_DA_AURORA, "versao": criado["versao"],
                                                         "tem_logo": False}
    assert especialista.get(rota_do_logo).status_code == 404
    # A versão publicada não recebe nem perde o logo (400); versão que não existe: 404
    da_publicada = f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes/1/logo"
    assert especialista.post(da_publicada, files=arquivo(PNG_NOVO)).status_code == 400
    assert especialista.delete(da_publicada).status_code == 400
    assert especialista.get(f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes/99/logo").status_code == 404
    # Uma KB que não é do kit: 400
    assert especialista.get("/api/banco/kbs-endomarketing/EMP001-BEN-CONSIGNADO/versoes/1/logo").status_code == 400


def test_api_do_kit_em_uso(api):
    especialista = entrar("especialista")
    em_uso = especialista.get("/api/banco/empresas/EMP001/kit_em_uso").json()
    assert (em_uso["escolhido"], em_uso["kb_id"], em_uso["kb_versao"]) == ("proprio", KIT_DA_AURORA, 1)
    assert set(em_uso["cores"]) == CHAVES_DAS_CORES and em_uso["tem_logo"] is True
    # O endereço do logo em uso abre a imagem (a mesma rota que a arte usa)
    assert especialista.get(em_uso["endereco_do_logo"]).content == logo_da_pasta()
    # Empresa que não existe: 404
    assert especialista.get("/api/banco/empresas/EMP999/kit_em_uso").status_code == 404


def test_rotas_novas_do_kit_sao_so_do_banco(api):
    rh = entrar("rh.aurora")
    anonimo = TestClient(aplicacao)
    rota_do_logo = f"/api/banco/kbs-endomarketing/{KIT_DA_AURORA}/versoes/1/logo"
    for rota in ("/api/banco/empresas/EMP001/kit_em_uso", rota_do_logo):
        assert rh.get(rota).status_code == 403, rota
        assert anonimo.get(rota).status_code == 401, rota
    assert rh.post(rota_do_logo, files=arquivo(PNG_NOVO)).status_code == 403
    assert rh.delete(rota_do_logo).status_code == 403
    assert anonimo.post(rota_do_logo, files=arquivo(PNG_NOVO)).status_code == 401
    assert anonimo.delete(rota_do_logo).status_code == 401


def test_as_rotas_do_kit_que_sairam(api):
    especialista = entrar("especialista")
    # A gravação direta do kit no cadastro e a subida e a retirada do logo saíram (o GET do logo fica)
    direto = especialista.post("/api/banco/empresas/EMP001/kit", json={"escolhido": "padrao", "texto": "", "cores": []})
    assert direto.status_code in (404, 405)
    assert especialista.post("/api/banco/empresas/EMP001/kit/logo", files=arquivo(PNG_NOVO)).status_code == 405
    assert especialista.delete("/api/banco/empresas/EMP001/kit/logo").status_code == 405
    # O kit da Aurora não mudou
    em_uso = especialista.get("/api/banco/empresas/EMP001/kit_em_uso").json()
    assert (em_uso["escolhido"], em_uso["cores"]["cor_principal"]) == ("proprio", "#e8772e")
    assert especialista.get("/api/banco/empresas/EMP001/kit/logo").content == logo_da_pasta()
