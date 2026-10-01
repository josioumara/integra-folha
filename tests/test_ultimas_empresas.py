"""As listas de empresas da Carteira e do Endomarketing mostram só as últimas cadastradas.

A escolha das empresas que aparecem (as 8 últimas, ou as da busca) é da tela (front/js/escolha_de_empresa.js, a mesma
função nas duas) e tem o roteiro de clique lista_das_ultimas_empresas. O servidor entrega o que ela precisa, e estes
testes provam isso:
- services/empresas.datas_de_cadastro diz quando cada empresa entrou na carteira, e a cadastrada agora é a mais nova;
- a ficha de cada empresa (/api/banco/empresas) traz a data de cadastro;
- a lista do Endomarketing (/api/banco/endomarketing) traz a data de cadastro e todos os CNPJs da empresa (o
  principal primeiro, depois filiais e grupo), para a busca pelo CNPJ;
- as duas rotas são só do banco: 401 sem login e 403 para a empresa.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco
from services import empresas as cadastro_de_empresas
from services.auth import Usuario

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# O especialista do banco, para chamar o serviço direto
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
# Uma empresa nova, cadastrada no teste (os dígitos verificadores do CNPJ conferem)
EMPRESA_NOVA = {"nome": "Cedro Engenharia Ltda.", "setor": "Construção", "municipio": "Belo Horizonte", "uf": "MG",
                "cnpj": "11222333000181", "endereco_comercial": "Rua Exemplo, 100", "dominio_email": "cedro.com.br",
                "contrato_desde": "2026-09-01"}
# Uma filial da Aurora (mesma raiz 10433218, estabelecimento 0002)
FILIAL_DA_AURORA = "10433218000274"


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, com as 6 empresas da semente."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    cadastro_de_empresas.listar(conexao_do_teste)
    yield conexao_do_teste
    conexao_do_teste.close()


def test_datas_de_cadastro_diz_quando_cada_empresa_entrou(conexao):
    datas = cadastro_de_empresas.datas_de_cadastro(conexao)
    # As 6 da semente, cada uma com a data e a hora do cadastro (texto ISO)
    assert sorted(datas) == ["EMP001", "EMP002", "EMP003", "EMP004", "EMP005", "EMP006"]
    for data in datas.values():
        assert data and "T" in data
    # A empresa cadastrada agora é a mais nova (ou empata, no mesmo segundo, com a semente)
    nova = cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, EMPRESA_NOVA)
    datas_depois = cadastro_de_empresas.datas_de_cadastro(conexao)
    assert nova["empresa_id"] == "EMP007"
    assert datas_depois["EMP007"] >= max(datas.values())


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com o especialista, o RH da Aurora, a empresa nova e a filial."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    # A lista de empresas em memória é de outro banco (de outro teste): esquece
    cadastro_de_empresas.esquecer_lista_em_memoria()
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    cadastro_de_empresas.cadastrar(conexao_do_teste, ESPECIALISTA, EMPRESA_NOVA)
    cadastro_de_empresas.adicionar_cnpj(conexao_do_teste, ESPECIALISTA, "EMP001", FILIAL_DA_AURORA,
                                        cadastro_de_empresas.CNPJ_FILIAL)
    datas = cadastro_de_empresas.datas_de_cadastro(conexao_do_teste)
    conexao_do_teste.close()
    yield {"datas": datas}
    cadastro_de_empresas.esquecer_lista_em_memoria()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_as_fichas_da_carteira_trazem_a_data_de_cadastro(api):
    fichas = entrar("especialista").get("/api/banco/empresas").json()
    datas_das_fichas = {}
    for ficha in fichas:
        datas_das_fichas[ficha["id"]] = ficha["cadastrada_em"]
    # Todas as empresas da carteira, cada uma com a data do cadastro (a nova também)
    assert datas_das_fichas == api["datas"]
    assert "EMP007" in datas_das_fichas


def test_a_lista_do_endomarketing_traz_a_data_e_todos_os_cnpjs(api):
    lista = entrar("especialista").get("/api/banco/endomarketing").json()
    por_empresa = {}
    for empresa in lista:
        por_empresa[empresa["empresa_id"]] = empresa
    # A Aurora: o CNPJ principal primeiro e depois a filial registrada; a nova só com o dela
    assert por_empresa["EMP001"]["cnpjs"] == ["10433218000193", FILIAL_DA_AURORA]
    assert por_empresa["EMP007"]["cnpjs"] == [EMPRESA_NOVA["cnpj"]]
    for empresa_id, empresa in por_empresa.items():
        assert empresa["cadastrada_em"] == api["datas"][empresa_id]
        # Continua com os números de sempre da lista
        assert empresa["rascunhos"] == 0 and empresa["publicados"] == 0


@pytest.mark.parametrize("endereco", ["/api/banco/empresas", "/api/banco/endomarketing"])
def test_as_duas_listas_sao_so_do_banco(api, endereco):
    # Sem login: 401; a empresa: 403 (uma empresa nunca vê a carteira nem os CNPJs das outras)
    assert TestClient(aplicacao).get(endereco).status_code == 401
    assert entrar("rh.aurora").get(endereco).status_code == 403
