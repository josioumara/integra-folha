"""Os CNPJs de filiais e do grupo e a regra do CNPJ no envio (ADR-77).

O que estes testes provam:
- o banco cadastra CNPJs de filiais (mesma raiz da sede) e do grupo (outra raiz), conferidos, e tira quando quiser;
- a regra do CNPJ: principal, filial ou registrado passa; desconhecido repetido em 2 ou mais funcionários vira a
  pergunta "é do grupo?" (alerta); desconhecido num funcionário só bloqueia (provável erro de digitação);
- a empresa confirma uma vez: o CNPJ entra sozinho no cadastro, o alerta sai de todos e não volta a ser perguntado;
- só o perfil BANCO cadastra e tira CNPJs (também pelas rotas).
"""
import random
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil, carregar_layout
from services import acompanhamento, auth, banco, correcoes, validador
from services import empresas as cadastro_de_empresas
from services.auth import Usuario
from services.documentos import gerar_cnpj
from services.validador import ALERTA, BLOQUEANTE, REGRA_CNPJ_DO_GRUPO
from tests.test_correcao import busca_falsa, preparar_ate_a_validacao
from tests.test_validador import normalizacao_de, registro

# O CNPJ principal da Aurora (EMP001) e uma filial dela (mesma raiz 10433218, estabelecimento 0002)
CNPJ_DA_AURORA = "10433218000193"
SENHA_DE_TESTE = "senha-de-teste-123"
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")
CAMPOS = carregar_layout()


def cnpj_de_outra_raiz(semente: int) -> str:
    """Um CNPJ válido sorteado, com raiz diferente da Aurora (serve de "empresa do grupo")."""
    sorteador = random.Random(semente)
    cnpj = gerar_cnpj(sorteador)
    # Na chance rara de sair a mesma raiz, sorteia de novo
    while cnpj[:8] == CNPJ_DA_AURORA[:8]:
        cnpj = gerar_cnpj(sorteador)
    return cnpj


def filial_da_aurora() -> str:
    """Um CNPJ válido de filial da Aurora: a mesma raiz, estabelecimento 0002, dígitos verificadores calculados."""
    from services.documentos import cnpj_valido
    # Procura os dois dígitos finais que fecham a conta (só um par é válido)
    for final in range(100):
        candidato = CNPJ_DA_AURORA[:8] + "0002" + str(final).zfill(2)
        if cnpj_valido(candidato):
            return candidato
    raise AssertionError("Não achei a filial")


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


@pytest.fixture(autouse=True)
def preparar(monkeypatch):
    """Cada teste começa sem a lista de empresas em memória e sem depender do índice do RAG."""
    cadastro_de_empresas.esquecer_lista_em_memoria()
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    yield
    cadastro_de_empresas.esquecer_lista_em_memoria()


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, só deste teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


# ---------------- O cadastro dos CNPJs ----------------

def test_banco_cadastra_filial_e_grupo_conferidos(conexao):
    """Filial com a mesma raiz e grupo com outra raiz entram; os erros voltam com o motivo."""
    grupo = cnpj_de_outra_raiz(1)
    cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", filial_da_aurora(), "FILIAL")
    lista = cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", grupo, "GRUPO")
    assert [(item["tipo"], item["origem"]) for item in lista] == [("FILIAL", "BANCO"), ("GRUPO", "BANCO")]
    # Os motivos de recusa
    casos = [(CNPJ_DA_AURORA, "FILIAL", "principal"), (grupo, "FILIAL", "8 primeiros"),
             (filial_da_aurora(), "GRUPO", "filial"), ("11111111111111", "GRUPO", "dígitos"),
             (grupo, "GRUPO", "já está")]
    for cnpj, tipo, motivo in casos:
        with pytest.raises(ValueError, match=motivo):
            cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", cnpj, tipo)
    # Tirar
    lista = cadastro_de_empresas.remover_cnpj(conexao, ESPECIALISTA, "EMP001", grupo)
    assert [item["tipo"] for item in lista] == ["FILIAL"]
    with pytest.raises(KeyError):
        cadastro_de_empresas.remover_cnpj(conexao, ESPECIALISTA, "EMP001", grupo)


def test_so_o_banco_cadastra_cnpj(conexao):
    """A empresa não cadastra CNPJ pela aba do banco (só confirmando no envio)."""
    with pytest.raises(PermissionError):
        cadastro_de_empresas.adicionar_cnpj(conexao, RH_DA_AURORA, "EMP001", cnpj_de_outra_raiz(2), "GRUPO")


# ---------------- A regra do CNPJ no Validador ----------------

def _achados_de_cnpj(relatorio) -> list[tuple]:
    """(regra, severidade, linha) dos achados de CNPJ."""
    achados = []
    for achado in relatorio.achados:
        if achado.regra_id.startswith("CNPJ"):
            achados.append((achado.regra_id, achado.severidade, achado.linha))
    return achados


def test_regra_do_cnpj():
    """Principal e filial passam; desconhecido repetido pergunta; desconhecido sozinho bloqueia; registrado passa."""
    grupo, digitado_errado = cnpj_de_outra_raiz(3), cnpj_de_outra_raiz(4)
    pessoas = [registro(_linha=2, cnpj_empregador=CNPJ_DA_AURORA), registro(_linha=3, cnpj_empregador=filial_da_aurora()),
               registro(_linha=4, cnpj_empregador=grupo), registro(_linha=5, cnpj_empregador=grupo),
               registro(_linha=6, cnpj_empregador=digitado_errado)]
    sem_cadastro = {"principal": CNPJ_DA_AURORA, "registrados": []}
    relatorio = validador.validar(normalizacao_de(*pessoas), CAMPOS, "EMP001", cnpjs_da_empresa=sem_cadastro)
    assert _achados_de_cnpj(relatorio) == [(REGRA_CNPJ_DO_GRUPO, ALERTA, 4), (REGRA_CNPJ_DO_GRUPO, ALERTA, 5),
                                           ("CNPJ_DE_OUTRA_EMPRESA", BLOQUEANTE, 6)]
    # Com o grupo no cadastro, só o digitado errado continua
    com_grupo = {"principal": CNPJ_DA_AURORA, "registrados": [grupo]}
    relatorio = validador.validar(normalizacao_de(*pessoas), CAMPOS, "EMP001", cnpjs_da_empresa=com_grupo)
    assert _achados_de_cnpj(relatorio) == [("CNPJ_DE_OUTRA_EMPRESA", BLOQUEANTE, 6)]


# ---------------- A confirmação da empresa ----------------

def test_empresa_confirma_uma_vez_e_nao_pergunta_de_novo(conexao):
    """Dois funcionários com o CNPJ do grupo: confirmar um tira o alerta dos dois e o CNPJ entra no cadastro."""
    processamento_id = preparar_ate_a_validacao(conexao, "aurora_carga_inicial")
    grupo = cnpj_de_outra_raiz(5)
    registros = correcoes.dados_atuais(conexao, processamento_id).registros
    linhas = [registros[0]["_linha"], registros[1]["_linha"], registros[2]["_linha"]]
    # A empresa põe o CNPJ do grupo em dois funcionários
    for linha in linhas[:2]:
        acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, linha, "cnpj_empregador",
                                          grupo, "Empregado pela empresa do grupo")
    alertas = [achado for achado in validador.obter(conexao, processamento_id).achados
               if achado.regra_id == REGRA_CNPJ_DO_GRUPO]
    assert sorted(achado.linha for achado in alertas) == linhas[:2]
    assert "É de uma empresa do seu grupo?" in alertas[0].mensagem
    # "Sim, é do nosso grupo" em um deles
    acompanhamento.confirmar_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, REGRA_CNPJ_DO_GRUPO,
                                       linhas[0], "É da Aurora Participações, do nosso grupo")
    assert _regras_do_envio(conexao, processamento_id).isdisjoint({REGRA_CNPJ_DO_GRUPO, "CNPJ_DE_OUTRA_EMPRESA"})
    registrado = cadastro_de_empresas.cnpjs_da_empresa(conexao, "EMP001")
    assert [(item["cnpj"], item["tipo"], item["origem"], item["registrado_por"]) for item in registrado] == [
        (grupo, "GRUPO", "EMPRESA", "rh.aurora")]
    # Um terceiro funcionário com o mesmo CNPJ: já conhecido, nada a perguntar
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, linhas[2], "cnpj_empregador",
                                      grupo, "Também é da empresa do grupo")
    assert _regras_do_envio(conexao, processamento_id).isdisjoint({REGRA_CNPJ_DO_GRUPO, "CNPJ_DE_OUTRA_EMPRESA"})


def _regras_do_envio(conexao, processamento_id: str) -> set:
    """As regras com achados no último relatório do envio."""
    regras = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        regras.add(achado.regra_id)
    return regras


# ---------------- As rotas ----------------

@pytest.fixture
def api_dos_cnpjs(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um especialista e um RH."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_cnpjs.db"
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


def test_rotas_dos_cnpjs(api_dos_cnpjs):
    """O especialista cadastra, vê na ficha e tira; a empresa recebe 403; erro volta com o motivo (400)."""
    especialista = entrar("especialista")
    rh = entrar("rh.aurora")
    grupo = cnpj_de_outra_raiz(6)
    pedido = {"cnpj": grupo, "tipo": "GRUPO"}
    assert rh.post("/api/banco/empresas/EMP001/cnpjs", json=pedido).status_code == 403
    resposta = especialista.post("/api/banco/empresas/EMP001/cnpjs", json=pedido)
    assert resposta.status_code == 200 and resposta.json()[0]["cnpj"] == grupo
    assert especialista.post("/api/banco/empresas/EMP001/cnpjs", json=pedido).status_code == 400
    ficha = [empresa for empresa in especialista.get("/api/banco/empresas").json() if empresa["id"] == "EMP001"][0]
    assert ficha["outros_cnpjs"][0]["cnpj"] == grupo
    assert especialista.delete("/api/banco/empresas/EMP001/cnpjs/" + grupo).status_code == 200
    assert especialista.delete("/api/banco/empresas/EMP001/cnpjs/" + grupo).status_code == 404
