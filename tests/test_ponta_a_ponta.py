"""Teste de ponta a ponta em modo MOCK: as três trilhas da demo, pela API do front novo (ADR-108).

1. Empresa (Prisma): o arquivo passa pelo fluxo inteiro até a homologação, com as decisões tomadas pelo gabarito
   (é o mesmo fluxo em LangGraph que os botões da tela "Cadastrar funcionários" usam). Depois, o RH da Prisma entra
   pela API e vê o envio concluído e cadastrado.
2. Banco: a tela de Planejamento mostra os números do motor de planejamento (sem IA: o Consultor saiu, ADR-144).
3. Banco: a sub-aba Desempenho da IA (aba Telemetria) lista as execuções desse arquivo, sem nenhum CPF.

Antes, estas trilhas rodavam nas telas do Streamlit (AppTest); com a saída do Streamlit, rodam pelo TestClient do
FastAPI, o "navegador de mentira" que faz os pedidos direto na aplicação e guarda o cookie de login.
Roda no banco temporário dos testes (tests/conftest.py), o mesmo que a API abre.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from eval import avaliacao_do_fluxo
from models.contratos import Perfil
from services import auth, execucoes, planejamento, processamentos
from tests.test_fluxo_empresa import busca_falsa

# A empresa da trilha e o arquivo dela
EMPRESA_ID = "EMP005"
ARQUIVO = "prisma_carga_inicial"
# Os usuários desta trilha (nomes só deste arquivo, para não esbarrar em outros testes do mesmo banco)
LOGIN_DA_PRISMA = "ponta.prisma"
LOGIN_DO_BANCO = "ponta.banco"
# Senha dos usuários de teste (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


@pytest.fixture(scope="module", autouse=True)
def usuarios_da_trilha():
    """Cadastra o RH da Prisma e um especialista do banco no banco temporário, uma vez para este arquivo."""
    # Abre o banco temporário dos testes
    conexao = auth.conectar()
    # O RH da Prisma (perfil EMPRESA) e o especialista (perfil BANCO)
    auth.cadastrar_usuario(conexao, LOGIN_DA_PRISMA, SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_ID)
    auth.cadastrar_usuario(conexao, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()


@pytest.fixture(scope="module")
def processamento_id():
    """A trilha da empresa: o arquivo da Prisma do envio à homologação. Devolve o processamento."""
    conexao = auth.conectar()
    # O gabarito diz o que a empresa decide em cada pausa do fluxo
    gabaritos = avaliacao_do_fluxo.carregar_gabaritos()
    medido = avaliacao_do_fluxo.processar_arquivo(conexao, ARQUIVO, gabaritos[ARQUIVO],
                                                  avaliacao_do_fluxo.carregar_verdade(), busca=busca_falsa)
    # O arquivo precisa ter chegado ao fim do fluxo
    assert medido["status_final"] == "HOMOLOGADO"
    # O processamento do arquivo, pelo nome
    for perfil in processamentos.listar(conexao, EMPRESA_ID):
        if perfil.nome_arquivo == gabaritos[ARQUIVO]["arquivo"]:
            return perfil.processamento_id
    raise AssertionError("o arquivo da Prisma não foi registrado")


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    # Navegador novo, sem cookies
    navegador = TestClient(aplicacao)
    # Entra com a senha dos testes; o login precisa dar certo para o teste seguir
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200
    return navegador


def test_trilha_da_empresa_termina_com_o_envio_concluido_e_cadastrado(processamento_id):
    """O RH da Prisma vê, pela API, o envio concluído (fim do fluxo) e cadastrado em "Acompanhar cadastros"."""
    prisma = entrar(LOGIN_DA_PRISMA)
    # A leitura do envio (tela "Cadastrar funcionários"): o fluxo terminou
    leitura = prisma.get("/api/empresa/cadastro/" + processamento_id).json()
    assert leitura["terminou"] is True
    assert leitura["nome_da_etapa"] == "Concluído"
    # A lista de envios (tela "Acompanhar cadastros"), com a página maior para caber todos os envios da Prisma
    envios = prisma.get("/api/empresa/envios/pagina?quantidade=50").json()["envios"]
    # O envio desta trilha, pelo processamento
    envio_da_trilha = None
    for envio in envios:
        if envio["processamento_id"] == processamento_id:
            envio_da_trilha = envio
    # Ele aparece como cadastrado, com gente cadastrada
    assert envio_da_trilha["situacao"] == "Cadastrado"
    assert envio_da_trilha["cadastrados"] >= 1


def test_trilha_do_banco_mostra_os_numeros_do_motor(processamento_id):
    """A tela de Planejamento (sem filtro) mostra os mesmos números que o motor de planejamento calcula."""
    # Os números direto do serviço de planejamento
    conexao = auth.conectar()
    resumo = planejamento.resumir(conexao)
    indicadores = planejamento.indicadores(conexao)
    conexao.close()
    # Os mesmos números, pela API que a tela usa
    numeros = entrar(LOGIN_DO_BANCO).get("/api/banco/planejamento").json()
    assert numeros["indicadores"]["funcionarios_processados"] == indicadores["funcionarios_processados"]
    assert numeros["resumo"] == resumo and resumo["cadastrados"] == indicadores["funcionarios_processados"]
    # A Prisma entrou nos números
    assert indicadores["funcionarios_processados"] >= 1


def test_trilha_do_banco_ve_as_execucoes_do_arquivo_sem_cpf(processamento_id):
    """A sub-aba Desempenho da IA do banco lista as execuções; nenhum CPF do arquivo aparece no que a tela recebe.

    (Antes era o Painel Técnico do cientista; o perfil CIENTISTA saiu, ADR-78, e o banco tem a gestão completa.)
    """
    # As etapas que o fluxo registrou para este arquivo
    conexao = auth.conectar()
    etapas = []
    for execucao in execucoes.listar(conexao, processamento_id):
        etapas.append(execucao["etapa"])
    conexao.close()
    assert "aprovar_homologacao" in etapas and "liberar_planejamento" in etapas
    # O que a tela Desempenho da IA recebe da API
    resposta = entrar(LOGIN_DO_BANCO).get("/api/banco/telemetria/ia")
    assert resposta.status_code == 200
    assert resposta.json()["recentes"]
    # Nenhum CPF de funcionário da Prisma aparece na resposta
    verdade = avaliacao_do_fluxo.carregar_verdade()
    for funcionario_id in avaliacao_do_fluxo.carregar_gabaritos()[ARQUIVO]["funcionario_ids"]:
        assert verdade[funcionario_id]["cpf"] not in resposta.text
