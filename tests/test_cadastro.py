"""Testes de "Cadastrar funcionários" no novo front (ADR-69): services/cadastro.py e as rotas /api/empresa/cadastro/...

O que se prova aqui:
    - enviar o arquivo roda o fluxo até a IA propor o mapeamento (em MOCK, sem custo);
    - o aceite sem decidir a coluna ambígua não avança e explica o motivo;
    - do aceite à homologação, pelo fluxo em LangGraph;
    - descartar encerra sem cadastrar ninguém; reenvio idêntico não cria outro envio;
    - arquivo que não serve é recusado com a mensagem; outra empresa não mexe no envio.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, auditoria, auth, banco, cadastro, ingestao
from tests.test_correcao import ENVIOS, _escolhas_do_gabarito, _gabarito, busca_falsa
from workflows import fluxo_empresa
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def enviar(conexao, nome):
    """Envia um arquivo da demo pela porta do cadastro (como a tela faz). Devolve a leitura."""
    gabarito = _gabarito(nome)
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    return cadastro.enviar_arquivo(conexao, gabarito["empresa_id"], "rh.teste", conteudo, gabarito["arquivo"],
                                   busca=busca_falsa)


def test_enviar_roda_o_fluxo_ate_a_ia_propor_o_mapeamento(conexao):
    leitura = enviar(conexao, "aurora_carga_inicial")
    assert leitura["etapa"] == "aprovar_mapeamento"
    assert leitura["tipo"] == "Carga inicial" and leitura["linhas"] > 0
    assert leitura["colunas"] and all(coluna["situacao"] for coluna in leitura["colunas"])
    assert leitura["duplicado"] is False


def test_aceite_sem_decidir_a_coluna_ambigua_nao_avanca_e_explica(conexao):
    leitura = enviar(conexao, "atlantico_carga_inicial")
    # A IA pediu ajuda numa coluna
    assert any(coluna["precisa_decidir"] for coluna in leitura["colunas"])
    leitura = cadastro.aceitar_mapeamento(conexao, "EMP006", "rh.teste", leitura["processamento_id"], {},
                                          busca=busca_falsa)
    assert leitura["etapa"] == "aprovar_mapeamento"
    assert "Vencimentos" in leitura["erro"]


def test_do_aceite_a_homologacao_pelo_fluxo(conexao, verdade):
    # A carga inicial da Aurora já cadastrada: o próximo envio é inclusão
    homologar(conexao, "aurora_carga_inicial", verdade)
    antes = len(acompanhamento.funcionarios_da_empresa(conexao, "EMP001"))
    leitura = enviar(conexao, "aurora_inclusao")
    assert leitura["tipo"] == "Inclusão"
    processamento_id = leitura["processamento_id"]
    leitura = cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", processamento_id,
                                          _escolhas_do_gabarito(_gabarito("aurora_inclusao")), busca=busca_falsa)
    # Sem pendências: espera o clique final
    assert leitura["etapa"] == "aprovar_homologacao"
    # "Enviar ao banco": o envio espera a avaliação, e ninguém novo entra na lista ainda
    leitura = cadastro.homologar(conexao, "EMP001", "rh.teste", processamento_id)
    assert leitura["etapa"] == "avaliar_no_banco" and leitura["terminou"] is False
    assert len(acompanhamento.funcionarios_da_empresa(conexao, "EMP001")) == antes
    # O banco aprova: os funcionários da inclusão entram na lista
    fluxo_empresa.responder(conexao, processamento_id, "EMP001", "avaliar_no_banco",
                            {"acao": "aprovar", "usuario": "especialista"}, busca=busca_falsa)
    assert len(acompanhamento.funcionarios_da_empresa(conexao, "EMP001")) > antes


def test_homologar_com_pendencia_nao_cadastra(conexao):
    leitura = enviar(conexao, "aurora_carga_inicial")
    processamento_id = leitura["processamento_id"]
    leitura = cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", processamento_id,
                                          _escolhas_do_gabarito(_gabarito("aurora_carga_inicial")), busca=busca_falsa)
    # A Aurora tem um CPF inválido: a validação para na correção
    assert leitura["etapa"] == "aguardar_correcao"
    # O fluxo revalida, a pendência continua, e o clique é recusado com a explicação
    with pytest.raises(ValueError, match="Correção das pendências"):
        cadastro.homologar(conexao, "EMP001", "rh.teste", processamento_id)
    # Continua na correção; ninguém foi cadastrado
    assert cadastro.leitura_do_envio(conexao, "EMP001", processamento_id)["etapa"] == "aguardar_correcao"
    assert acompanhamento.funcionarios_da_empresa(conexao, "EMP001") == []


def test_descartar_encerra_sem_cadastrar(conexao):
    leitura = enviar(conexao, "horizonte_carga_inicial")
    processamento_id = leitura["processamento_id"]
    # Antes de descartar: o que se perde (a tela pede confirmação com isso); outra empresa não vê
    perdido = cadastro.o_que_se_perde(conexao, "EMP002", processamento_id)
    assert perdido == {"funcionarios": 50, "correcoes": 0}
    with pytest.raises(KeyError):
        cadastro.o_que_se_perde(conexao, "EMP001", processamento_id)
    leitura = cadastro.descartar(conexao, "EMP002", processamento_id, "rh.horizonte")
    assert leitura["terminou"] is True
    assert acompanhamento.envios_da_empresa(conexao, "EMP002")[0]["situacao"] == "Descartado"
    assert acompanhamento.funcionarios_da_empresa(conexao, "EMP002") == []
    # A trilha diz quem descartou e o que se perdeu (só quantidades)
    descartes = []
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "DESCARTADO_PELA_EMPRESA":
            descartes.append(evento["detalhe"])
    assert descartes == [{"por": "rh.horizonte", "funcionarios": 50, "correcoes": 0}]
    # A lista de envios mostra quem descartou e quando
    descarte = acompanhamento.envios_da_empresa(conexao, "EMP002")[0]["descarte"]
    assert descarte["por"] == "rh.horizonte" and descarte["quando"]


def test_envio_que_nao_foi_descartado_nao_tem_descarte(conexao):
    """Um envio em andamento não traz quem descartou (o campo fica vazio)."""
    enviar(conexao, "horizonte_carga_inicial")
    assert acompanhamento.envios_da_empresa(conexao, "EMP002")[0]["descarte"] is None


def test_reenvio_identico_nao_cria_outro_envio(conexao):
    primeira = enviar(conexao, "horizonte_carga_inicial")
    segunda = enviar(conexao, "horizonte_carga_inicial")
    assert segunda["duplicado"] is True
    assert segunda["processamento_id"] == primeira["processamento_id"]
    assert len(acompanhamento.envios_da_empresa(conexao, "EMP002")) == 1


def test_arquivo_que_nao_serve_e_recusado_com_mensagem(conexao):
    with pytest.raises(ingestao.ArquivoRecusado):
        cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", b"MZ\x90\x00programa", "planilha.exe")


def test_outra_empresa_nao_ve_nem_mexe_no_envio(conexao):
    leitura = enviar(conexao, "horizonte_carga_inicial")
    processamento_id = leitura["processamento_id"]
    with pytest.raises(KeyError):
        cadastro.leitura_do_envio(conexao, "EMP001", processamento_id)
    with pytest.raises(KeyError):
        cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.aurora", processamento_id, {}, busca=busca_falsa)
    with pytest.raises(KeyError):
        cadastro.descartar(conexao, "EMP001", processamento_id, "rh.aurora")


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_do_cadastro(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um usuário da Horizonte, um da Aurora e um do banco."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_cadastro.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao = conectar_original(caminho)
    auth.cadastrar_usuario(conexao, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_envia_le_e_descarta(api_do_cadastro):
    horizonte = entrar("rh.horizonte")
    gabarito = _gabarito("horizonte_carga_inicial")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    # Envio pelo formulário do navegador (multipart)
    resposta = horizonte.post("/api/empresa/cadastro/enviar", files={"arquivo": (gabarito["arquivo"], conteudo)})
    assert resposta.status_code == 200
    leitura = resposta.json()
    assert leitura["etapa"] == "aprovar_mapeamento" and leitura["colunas"]
    processamento_id = leitura["processamento_id"]
    # Ler de novo
    assert horizonte.get("/api/empresa/cadastro/" + processamento_id).json()["etapa"] == "aprovar_mapeamento"
    # A Aurora não vê nem descarta o envio da Horizonte
    aurora = entrar("rh.aurora")
    assert aurora.get("/api/empresa/cadastro/" + processamento_id).status_code == 404
    assert aurora.post("/api/empresa/cadastro/" + processamento_id + "/descartar").status_code == 404
    # Descartar
    assert horizonte.post("/api/empresa/cadastro/" + processamento_id + "/descartar").json()["terminou"] is True


def test_api_recusa_arquivo_que_nao_serve_e_outros_perfis(api_do_cadastro):
    horizonte = entrar("rh.horizonte")
    resposta = horizonte.post("/api/empresa/cadastro/enviar", files={"arquivo": ("planilha.exe", b"MZ\x90\x00x")})
    assert resposta.status_code == 400 and resposta.json()["detail"]
    especialista = entrar("especialista")
    assert especialista.post("/api/empresa/cadastro/enviar", files={"arquivo": ("a.csv", b"a;b\n1;2\n")}).status_code == 403
    assert TestClient(aplicacao).post("/api/empresa/cadastro/enviar", files={"arquivo": ("a.csv", b"a;b\n")}).status_code == 401


def test_lista_pendente_envia_ao_banco_tudo_o_que_esta_pronto(conexao, verdade):
    """Acompanhar cadastros: o envio sem pendência aparece como pronto e vai ao banco com "Enviar ao banco"."""
    homologar(conexao, "aurora_carga_inicial", verdade)
    leitura = enviar(conexao, "aurora_inclusao")
    processamento_id = leitura["processamento_id"]
    # Com as colunas ainda por aceitar, nada está pronto
    assert cadastro.envios_prontos_para_o_banco(conexao, "EMP001") == []
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", processamento_id,
                                _escolhas_do_gabarito(_gabarito("aurora_inclusao")), busca=busca_falsa)
    prontos = cadastro.envios_prontos_para_o_banco(conexao, "EMP001")
    assert [pronto["processamento_id"] for pronto in prontos] == [processamento_id]
    assert prontos[0]["pessoas"] == leitura["linhas"]
    # Sem marcar "Conferi a lista", não vai
    with pytest.raises(ValueError, match="Conferi a lista"):
        cadastro.enviar_prontos_ao_banco(conexao, "EMP001", "rh.teste", conferiu_a_lista=False)
    resultado = cadastro.enviar_prontos_ao_banco(conexao, "EMP001", "rh.teste", conferiu_a_lista=True)
    # Ninguém deste envio tinha ido ao banco antes: ninguém fica de fora (ADR-126)
    assert resultado == {"envios": 1, "pessoas": leitura["linhas"], "ficaram_de_fora": 0}
    # Foi para a avaliação do banco e saiu da lista de prontos
    assert cadastro.leitura_do_envio(conexao, "EMP001", processamento_id)["etapa"] == "avaliar_no_banco"
    assert cadastro.envios_prontos_para_o_banco(conexao, "EMP001") == []
    with pytest.raises(ValueError, match="Não há envio pronto"):
        cadastro.enviar_prontos_ao_banco(conexao, "EMP001", "rh.teste", conferiu_a_lista=True)


def test_envio_com_pendencia_nao_esta_pronto(conexao):
    leitura = enviar(conexao, "aurora_carga_inicial")
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", leitura["processamento_id"],
                                _escolhas_do_gabarito(_gabarito("aurora_carga_inicial")), busca=busca_falsa)
    # A Aurora tem um CPF inválido: fica fora da lista de prontos
    assert cadastro.envios_prontos_para_o_banco(conexao, "EMP001") == []
