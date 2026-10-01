"""A avaliação dos envios pelo especialista do banco (ADR-69, passo 15).

O que estes testes provam:
- o envio que a empresa manda ao banco aparece na fila, com a trilha, os alertas confirmados e as pessoas com o
  CPF inteiro (o especialista tem autorização contratual); ninguém é cadastrado antes da aprovação;
- devolver exige motivo; devolvido, a empresa vê o motivo, ajusta e envia de novo; aprovado, os funcionários
  ficam cadastrados e o envio sai da fila de espera;
- só o perfil BANCO avalia (a empresa e quem não entrou são barrados, também pelas rotas).
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import EstadoProcessamento, Perfil
from services import acompanhamento, auth, avaliacao_do_banco, homologacao, processamentos
from services.auth import Usuario
from tests.test_correcao import busca_falsa
from tests.test_fluxo_empresa import (aprovar, conexao, corrigir_cpf_da_aurora, gerar_envios, iniciar,  # noqa: F401
                                      receber, verdade)
from workflows import fluxo_empresa as fluxo

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Usuários de mentira para chamar o serviço direto
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")


def enviar_a_aurora_ao_banco(conexao, verdade) -> str:
    """A Aurora corrige a única pendência e envia a carga inicial ao banco. Devolve o processamento_id."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao", {"acao": "homologar", "usuario": "rh"},
                    busca=busca_falsa)
    return processamento_id


def test_envio_na_fila_com_trilha_alertas_e_pessoas_com_cpf_inteiro(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    fila = avaliacao_do_banco.fila_de_envios(conexao, ESPECIALISTA)
    assert [envio["id"] for envio in fila] == [processamento_id]
    envio = fila[0]
    assert envio["situacao"] == "aguardando" and "Aurora" in envio["empresa"] and envio["prazo"]["texto"]
    assert "enviada por rh" in envio["trilha"][0] and len(envio["trilha"]) >= 3
    # As pessoas do envio, com o CPF inteiro e formatado; ninguém cadastrado ainda
    pessoas = avaliacao_do_banco.pessoas_do_envio(conexao, ESPECIALISTA, processamento_id)
    assert len(pessoas) > 0
    for pessoa in pessoas:
        assert len(pessoa["cpf"]) == 14 and "*" not in pessoa["cpf"] and pessoa["nome"]
    # A grade do especialista (ADR-111): cada pessoa traz todos os campos do parâmetro vigente, o CPF formatado
    campos_do_parametro = acompanhamento.campos_para_a_empresa(conexao)
    for pessoa in pessoas:
        assert list(pessoa["campos"]) == campos_do_parametro
        assert pessoa["campos"]["cpf"] == pessoa["cpf"] and pessoa["campos"]["nome_completo"] == pessoa["nome"]
    # Quem do banco abriu a lista fica registrado nos acessos da empresa (sem o CPF)
    acesso = acompanhamento.acessos_da_empresa(conexao, "EMP001")[-1]
    assert (acesso["login"], acesso["tipo"], acesso["quantidade"]) == (ESPECIALISTA.login, "LISTA", len(pessoas))
    assert homologacao.obter(conexao, processamento_id) is None
    assert avaliacao_do_banco.envios_esperando_o_banco(conexao) == 1


def test_devolver_com_motivo_reenviar_e_aprovar(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    # Sem motivo, não devolve
    with pytest.raises(ValueError):
        avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, False, "  ")
    # Devolvido: a empresa vê o motivo em Acompanhar
    devolvido = avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, False,
                                           "Confirme o salário da linha 5.")
    assert devolvido["situacao"] == "devolvido" and "Confirme o salário" in devolvido["resultado"]
    envio_da_empresa = acompanhamento.envios_da_empresa(conexao, "EMP001")[0]
    assert envio_da_empresa["situacao"] == "Devolvido pelo banco"
    assert envio_da_empresa["motivo_da_devolucao"] == "Confirme o salário da linha 5."
    # Avaliar de novo, sem a empresa reenviar, não vale
    with pytest.raises(ValueError):
        avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, True)
    # A empresa envia de novo e o banco aprova: cadastrados
    fluxo.responder(conexao, processamento_id, "EMP001", "aprovar_homologacao", {"acao": "homologar", "usuario": "rh"},
                    busca=busca_falsa)
    aprovado = avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, True)
    assert aprovado["situacao"] == "aprovado" and "especialista" in aprovado["resultado"]
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.HOMOLOGADO
    assert homologacao.obter(conexao, processamento_id)["homologado_por"] == "especialista"
    assert avaliacao_do_banco.envios_esperando_o_banco(conexao) == 0
    # A linha do tempo da empresa mostra o envio ao banco e o cadastro
    etapas = acompanhamento.envios_da_empresa(conexao, "EMP001")[0]["linha_do_tempo"]
    # As 6 etapas, na ordem do caminho do envio; até a aprovação, todas feitas
    assert [etapa["nome"] for etapa in etapas] == ["Arquivo carregado", "Lido pelos agentes", "Conferido por você",
                                                   "Enviado ao banco", "Aprovação das contas enviadas",
                                                   "Contas abertas"]
    for etapa in etapas[:-1]:
        assert etapa["feito"]
    # As contas só vêm com o arquivo semanal do banco: ainda por fazer
    assert etapas[-1]["atual"] and not etapas[-1]["feito"]


def test_so_o_banco_avalia(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    with pytest.raises(PermissionError):
        avaliacao_do_banco.fila_de_envios(conexao, RH_DA_AURORA)
    with pytest.raises(PermissionError):
        avaliacao_do_banco.avaliar(conexao, RH_DA_AURORA, processamento_id, True)
    with pytest.raises(PermissionError):
        avaliacao_do_banco.pessoas_do_envio(conexao, RH_DA_AURORA, processamento_id)
    # Envio que não existe
    with pytest.raises(KeyError):
        avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, "nao-existe", True)


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_da_avaliacao(tmp_path, monkeypatch, verdade):
    """A API apontada para um banco só deste teste, com a Aurora já enviada ao banco."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_avaliacao.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    processamento_id = enviar_a_aurora_ao_banco(conexao_do_teste, verdade)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()
    return processamento_id


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_da_avaliacao_por_perfil(api_da_avaliacao):
    processamento_id = api_da_avaliacao
    especialista = entrar("especialista")
    rh = entrar("rh.aurora")
    anonimo = TestClient(aplicacao)
    assert especialista.get("/api/banco/envios").json()[0]["id"] == processamento_id
    assert especialista.get("/api/banco/envios/" + processamento_id + "/pessoas").status_code == 200
    rota = "/api/banco/envios/" + processamento_id + "/avaliar"
    # A empresa e quem não entrou não avaliam
    assert rh.post(rota, json={"aprovar": True}).status_code == 403
    assert rh.get("/api/banco/envios").status_code == 403
    assert anonimo.get("/api/banco/envios").status_code == 401
    # Devolver sem motivo: 400; aprovar: 200 e sai da espera
    assert especialista.post(rota, json={"aprovar": False, "motivo": ""}).status_code == 400
    resposta = especialista.post(rota, json={"aprovar": True})
    assert resposta.status_code == 200 and resposta.json()["situacao"] == "aprovado"
    assert especialista.get("/api/banco/envios/nao-existe/pessoas").status_code == 404
