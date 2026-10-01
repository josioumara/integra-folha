"""Testes dos testes reais da trava das KBs (scripts/testar_trava_das_kbs.py) e dos totais da seção "Guardrails das
KBs" do Acompanhamento dos agentes (a rota GET /api/banco/kbs-endomarketing/achados).

O que se prova aqui:
    - cada caso do script acha a regra esperada, com a gravidade esperada, e os dois casos de controle passam sem
      achado nenhum (a trava não dá alarme falso);
    - nenhuma KB de teste é gravada nem publicada: só os achados ficam, com o autor do script;
    - rodar de novo não grava nada (sem --repetir), e o PostgreSQL só com --gravar-no-postgres;
    - o gasto com a IA é zero: a trava não chama modelo nenhum;
    - a rota dos achados traz os totais de TODOS os achados (a lista para nos 200 mais recentes), com o filtro por dono;
    - a rota é só do banco: sem login 401, empresa 403.
Cada teste usa um banco só dele (SQLite, numa pasta temporária).
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from scripts import testar_trava_das_kbs as script
from services import auth, banco, config, kbs_endomarketing

# Senha dos usuários de teste da rota
SENHA_DE_TESTE = "senha-de-teste-123"
# A rota dos achados da trava
ROTA_DOS_ACHADOS = "/api/banco/kbs-endomarketing/achados"


@pytest.fixture
def conexao(tmp_path):
    """Um banco vazio, só deste teste."""
    conexao_do_teste = banco.conectar(tmp_path / "trava.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture
def banco_do_script(tmp_path, monkeypatch):
    """O banco que o script abre (banco.conectar sem caminho) passa a ser um arquivo só deste teste.

    Devolve: uma função que abre esse mesmo banco, para o teste conferir o que ficou gravado.
    """
    conectar_original = banco.conectar
    caminho = tmp_path / "trava_do_script.db"
    # Toda conexão aberta sem caminho vai para o banco deste teste
    monkeypatch.setattr(banco, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    return lambda: conectar_original(caminho)


def achados_de_teste(conexao) -> list[dict]:
    """Os achados gravados com o id de uma KB de teste do script."""
    selecionados = []
    for achado in kbs_endomarketing.listar_achados(conexao, limite=script.LIMITE_DA_LEITURA_DOS_ACHADOS):
        if achado["kb_id"].startswith(script.COMECO_DO_ID_DE_TESTE):
            selecionados.append(achado)
    return selecionados


# ---------------- Os casos do script ----------------

def test_cada_caso_acha_a_regra_esperada_e_os_de_controle_passam(conexao):
    resultados = script.rodar_os_casos(conexao)
    casos = script.casos_de_teste()
    assert len(resultados) == len(casos) == 11
    for caso, resultado in zip(casos, resultados):
        # Todo caso deu o resultado esperado
        assert resultado["certo"], resultado
        # Os de controle não têm achado nenhum; os outros acham a regra esperada, com a gravidade esperada
        if caso["regra_esperada"] is None:
            assert resultado["regras"] == {} and resultado["achados_gravados"] == 0
        else:
            assert resultado["regras"][caso["regra_esperada"]] == caso["gravidade_esperada"]
    # As 9 regras da trava que o script testa aparecem (7 bloqueiam; 2 só avisam)
    regras_achadas = set()
    for resultado in resultados:
        regras_achadas.update(resultado["regras"])
    assert regras_achadas == {"Termo proibido", "Valor sem simulação", "Dado pessoal", "Ordem para o agente",
                              "Seções obrigatórias", "Ficha", "Vencida", "Categoria"}


def test_o_salvar_so_e_tentado_quando_a_trava_bloqueia_e_ela_recusa(conexao):
    for caso, resultado in zip(script.casos_de_teste(), script.rodar_os_casos(conexao)):
        # O "Salvar" só nos casos que bloqueiam, e sempre recusado; nos de aviso e nos de controle, nem tentado
        if caso["gravidade_esperada"] == kbs_endomarketing.BLOQUEIA:
            assert resultado["salvar_recusado"] is True
        else:
            assert resultado["salvar_recusado"] is None


def test_nenhuma_kb_de_teste_e_gravada_so_os_achados(conexao):
    script.rodar_os_casos(conexao)
    # Nenhuma KB com o id de teste existe (nem rascunho): a trava recusou toda gravação
    for resumo in kbs_endomarketing.listar(conexao):
        assert not resumo["kb_id"].startswith(script.COMECO_DO_ID_DE_TESTE)
    # Os achados ficaram: os do "Conferir" (VERIFICAR) e os do "Salvar" recusado (SALVAR), todos com o autor do script
    achados = achados_de_teste(conexao)
    momentos = set()
    for achado in achados:
        assert achado["feito_por"] == script.AUTOR
        momentos.add(achado["momento"])
    assert momentos == {kbs_endomarketing.VERIFICAR, kbs_endomarketing.SALVAR}
    # O número bate com o que o script contou
    assert len(achados) == 20


def test_rodar_de_novo_nao_grava_sem_repetir(banco_do_script, capsys):
    assert script.principal([]) == 0
    conexao = banco_do_script()
    primeira_vez = len(achados_de_teste(conexao))
    conexao.close()
    assert primeira_vez == 20
    # De novo, sem pedir: nada é gravado, e o aviso diz por quê
    assert script.principal([]) == 0
    assert "Nada foi gravado" in capsys.readouterr().out
    conexao = banco_do_script()
    assert len(achados_de_teste(conexao)) == primeira_vez
    conexao.close()
    # Com --repetir, grava de novo
    assert script.principal([script.OPCAO_DE_REPETIR]) == 0
    conexao = banco_do_script()
    assert len(achados_de_teste(conexao)) == 2 * primeira_vez
    conexao.close()


def test_o_gasto_com_a_ia_e_zero(banco_do_script, capsys):
    assert script.principal([]) == 0
    saida = capsys.readouterr().out
    # A trava não chamou modelo nenhum: zero chamadas e US$ 0,00
    assert "Chamadas à IA: 0." in saida and "Gasto com a IA: US$ 0,00" in saida
    # E o script rodou no modo MOCK (nada ali poderia gastar)
    assert config.MODO == "mock"


def test_postgres_so_com_a_opcao(monkeypatch, capsys):
    monkeypatch.setattr(config, "BANCO", "postgres")

    def conectar_proibido(caminho=None):
        """Se o script tentasse abrir o banco, o teste falharia aqui."""
        raise AssertionError("O script abriu o PostgreSQL sem a opção.")
    monkeypatch.setattr(banco, "conectar", conectar_proibido)
    # Sem a opção: recusa, sem abrir o banco
    assert script.principal([]) == 2
    assert script.OPCAO_DO_POSTGRES in capsys.readouterr().out


def test_opcao_desconhecida_mostra_o_uso(capsys):
    assert script.principal(["--outra-coisa"]) == 2
    assert "Uso:" in capsys.readouterr().out


def test_trecho_que_sumiu_da_kb_base_e_avisado():
    # Se a KB base mudar e o trecho de um caso sumir, o caso não pode continuar calado
    with pytest.raises(ValueError, match="não está na KB de teste"):
        script.trocar_trecho(script.KB_SEM_PROBLEMA, "um trecho que não existe", "outro")


# ---------------- Os totais da rota dos achados ----------------

@pytest.fixture
def api_do_banco(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um especialista e um RH. Devolve a conexão desse banco."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_trava.db"
    # Toda conexão da API vai para o banco deste teste
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    yield conexao_do_teste
    conexao_do_teste.close()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def gravar_achados(conexao, kb_id: str, dono: str, gravidade: str, quantos: int) -> None:
    """Grava direto na tabela `quantos` achados iguais de uma KB (o jeito que a trava grava)."""
    # Garante as tabelas das KBs (num banco novo, a primeira consulta as cria)
    kbs_endomarketing._preparar(conexao)
    achado = {"regra": "Termo proibido", "gravidade": gravidade, "detalhe": "teste", "trecho": ""}
    for _posicao in range(quantos):
        kbs_endomarketing._gravar_achados(conexao, kb_id, None, dono, kbs_endomarketing.VERIFICAR, [achado], "teste")


def test_os_totais_contam_todos_os_achados_e_nao_so_os_da_lista(api_do_banco):
    # 205 bloqueios da mesma KB do banco parceiro e 3 avisos de uma KB geral: mais do que os 200 da lista
    gravar_achados(api_do_banco, "SAN-BEN-X", kbs_endomarketing.DONO_SANTANDER, kbs_endomarketing.BLOQUEIA, 205)
    gravar_achados(api_do_banco, "GER-Y", kbs_endomarketing.DONO_GERAL, kbs_endomarketing.AVISO, 3)
    corpo = entrar("especialista").get(ROTA_DOS_ACHADOS).json()
    # A lista para nos 200 mais recentes; os totais contam os 208
    assert len(corpo["achados"]) == 200
    assert corpo["totais"] == {"bloqueios": 205, "avisos": 3, "kbs_com_achados": 2}


def test_os_totais_seguem_o_filtro_por_dono(api_do_banco):
    gravar_achados(api_do_banco, "SAN-BEN-X", kbs_endomarketing.DONO_SANTANDER, kbs_endomarketing.BLOQUEIA, 2)
    gravar_achados(api_do_banco, "GER-Y", kbs_endomarketing.DONO_GERAL, kbs_endomarketing.AVISO, 3)
    corpo = entrar("especialista").get(ROTA_DOS_ACHADOS + "?dono=GERAL").json()
    assert corpo["totais"] == {"bloqueios": 0, "avisos": 3, "kbs_com_achados": 1}
    assert len(corpo["achados"]) == 3


def test_os_totais_sem_achado_nenhum_sao_zero_de_verdade(api_do_banco):
    # Banco sem achado: os totais são zero (nada foi apontado), e a lista vem vazia
    corpo = entrar("especialista").get(ROTA_DOS_ACHADOS).json()
    assert corpo["achados"] == [] and corpo["totais"] == {"bloqueios": 0, "avisos": 0, "kbs_com_achados": 0}


def test_a_rota_dos_achados_e_so_do_banco(api_do_banco):
    # Sem login: 401; a empresa: 403
    assert TestClient(aplicacao).get(ROTA_DOS_ACHADOS).status_code == 401
    assert entrar("rh.aurora").get(ROTA_DOS_ACHADOS).status_code == 403
