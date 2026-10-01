"""Testes do "Baixar lista" de "Acompanhar cadastros" (ADR-155): o arquivo traz a grade que está na tela.

O que se prova aqui, pela rota POST /api/empresa/funcionarios/baixar, mandando o que a tela manda (o identificador de
download de cada pessoa que aparece com os filtros):
    - a empresa que só tem envios em andamento (ninguém cadastrado ainda) baixa a lista: antes, a tela mandava uma lista
      vazia, o servidor recusava e nada era baixado;
    - o arquivo tem as colunas certas, uma linha por pessoa da grade e a situação de cada uma (Pendente, Aguardando
      envio, Em análise, Cadastrado), com o filtro de situação valendo;
    - o download fica registrado com a quantidade de pessoas;
    - uma empresa nunca baixa as pessoas de outra, nem as que estão em andamento;
    - o identificador de quem estava em andamento não vale depois do cadastro (nunca traz outra pessoa);
    - sem login: 401; o perfil do banco: 403.
"""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import EstadoProcessamento, Perfil
from services import acompanhamento, auth, homologacao, processamentos
from tests.test_correcao import preparar_ate_a_validacao
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# A rota do download e a da lista que a tela mostra
ROTA_DO_DOWNLOAD = "/api/empresa/funcionarios/baixar"
ROTA_DA_LISTA = "/api/empresa/funcionarios"
# O cabeçalho que o arquivo tem de trazer, coluna por coluna, na ordem
CABECALHO_ESPERADO = ["Nome", "CPF", "Matrícula", "Cargo", "Unidade", "Admissão", "Salário", "Incluído em",
                      "Incluído por", "Situação", "Conta salário aberta em", "Código do banco", "Agência",
                      "Conta salário"]
# A posição da coluna do CPF e a da Situação no arquivo
COLUNA_DO_CPF = CABECALHO_ESPERADO.index("CPF")
COLUNA_DA_SITUACAO = CABECALHO_ESPERADO.index("Situação")


@pytest.fixture
def api_com_envios_em_andamento(tmp_path, monkeypatch, verdade):
    """A API apontada para um banco só deste teste.

    Os dados: a Horizonte (EMP002) só com a carga inicial em andamento (pendências; ninguém cadastrado), a Aurora
    (EMP001) com a carga cadastrada e uma inclusão em andamento, e um usuário de cada empresa e um do banco.
    Devolve {"inclusao_da_aurora": o processamento_id da inclusão da Aurora, "carga_da_horizonte": o da Horizonte}.
    """
    # O "conectar" original, guardado antes de trocar
    conectar_original = auth.conectar
    caminho = tmp_path / "api_baixar.db"
    # Toda conexão aberta pela API (e pelos serviços que usam auth.conectar) vai para o banco do teste
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao = conectar_original(caminho)
    # A Horizonte: o envio parou nas pendências (nenhuma pessoa cadastrada)
    carga_da_horizonte = preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    # A Aurora: a carga cadastrada e uma inclusão que ainda está com a empresa
    homologar(conexao, "aurora_carga_inicial", verdade)
    inclusao_da_aurora = preparar_ate_a_validacao(conexao, "aurora_inclusao")
    # Os usuários: o RH de cada empresa e o especialista do banco
    auth.cadastrar_usuario(conexao, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()
    return {"inclusao_da_aurora": inclusao_da_aurora, "carga_da_horizonte": carga_da_horizonte}


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def identificadores_que_a_tela_manda(lista: list[dict], situacao_escolhida: str = "") -> list[str]:
    """O que o botão "Baixar lista" manda: o identificador de download de cada pessoa que aparece com o filtro.

    Recebe: lista — a resposta de GET /api/empresa/funcionarios; situacao_escolhida — o filtro de situação ("" = todas).
    Devolve: os identificadores, na ordem da lista. Pessoa sem identificador fica de fora, como na tela.
    Exemplo: ([{"situacao": "Pendente", "id_para_baixar": "abc.linha3"}], "") → ["abc.linha3"].
    """
    identificadores = []
    for pessoa in lista:
        # O filtro de situação da tela: com uma escolhida, só quem está nela aparece
        if situacao_escolhida and pessoa["situacao"] != situacao_escolhida:
            continue
        # O identificador de download (a tela usa o mesmo campo)
        identificador = pessoa.get("id_para_baixar")
        if identificador:
            identificadores.append(identificador)
    return identificadores


def linhas_do_arquivo(resposta) -> list[list[str]]:
    """As linhas do CSV baixado, lidas como o Excel lê (separador ";", sem a marca do UTF-8 no começo)."""
    texto = resposta.content.decode("utf-8").lstrip("﻿")
    return list(csv.reader(io.StringIO(texto), delimiter=";"))


def test_empresa_so_com_envio_em_andamento_baixa_a_lista_da_grade(api_com_envios_em_andamento):
    """O defeito: a Horizonte ainda não tem ninguém cadastrado, a grade mostra as pessoas do envio e o arquivo sai."""
    horizonte = entrar("rh.horizonte")
    lista = horizonte.get(ROTA_DA_LISTA).json()
    # A grade tem gente, e ninguém dela está cadastrado (é o caso em que nada era baixado)
    assert lista
    assert all(pessoa["situacao"] in ("Pendente", "Aguardando envio") for pessoa in lista)
    # O botão manda a lista inteira (sem filtro): o arquivo sai, para o Excel, sem cópia no navegador
    resposta = horizonte.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores_que_a_tela_manda(lista)})
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.headers["cache-control"] == "no-store"
    linhas = linhas_do_arquivo(resposta)
    # As colunas certas, na ordem
    assert linhas[0] == CABECALHO_ESPERADO
    # Uma linha por pessoa da grade, com o mesmo CPF e a mesma situação que a tela mostra (comparados em pares, porque
    # uma pessoa do envio em andamento pode estar sem CPF)
    assert len(linhas) - 1 == len(lista)
    pares_da_tela = []
    for pessoa in lista:
        pares_da_tela.append((pessoa["cpf"], pessoa["situacao"]))
    pares_do_arquivo = []
    for linha in linhas[1:]:
        assert len(linha) == len(CABECALHO_ESPERADO)
        pares_do_arquivo.append((linha[COLUNA_DO_CPF], linha[COLUNA_DA_SITUACAO]))
    assert sorted(pares_do_arquivo) == sorted(pares_da_tela)
    # O download ficou registrado, com a quantidade de pessoas (a abertura da lista veio antes)
    conexao = auth.conectar()
    acessos = acompanhamento.acessos_da_empresa(conexao, "EMP002")
    conexao.close()
    assert (acessos[-1]["login"], acessos[-1]["tipo"], acessos[-1]["quantidade"]) == ("rh.horizonte", "DOWNLOAD",
                                                                                      len(lista))


def test_envio_mandado_ao_banco_baixa_as_pessoas_em_analise(api_com_envios_em_andamento):
    """Depois de mandado ao banco, as mesmas pessoas saem no arquivo como "Em análise"."""
    # O envio da Horizonte vai para o banco (as pessoas passam a "Em análise")
    conexao = auth.conectar()
    processamentos.atualizar_status(conexao, api_com_envios_em_andamento["carga_da_horizonte"],
                                    EstadoProcessamento.AGUARDANDO_BANCO)
    conexao.close()
    horizonte = entrar("rh.horizonte")
    lista = horizonte.get(ROTA_DA_LISTA).json()
    # O filtro "Em análise" da tela
    identificadores = identificadores_que_a_tela_manda(lista, "Em análise")
    assert identificadores
    resposta = horizonte.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores})
    assert resposta.status_code == 200, resposta.text
    linhas = linhas_do_arquivo(resposta)
    # Todas as linhas em análise, tantas quantas a tela mostra com o filtro
    assert len(linhas) - 1 == len(identificadores)
    assert all(linha[COLUNA_DA_SITUACAO] == "Em análise" for linha in linhas[1:])


def test_filtro_de_situacao_baixa_so_quem_aparece_na_grade(api_com_envios_em_andamento):
    """A Aurora tem cadastrados e uma inclusão em andamento: o arquivo segue o filtro, e sem filtro sai a grade inteira."""
    aurora = entrar("rh.aurora")
    lista = aurora.get(ROTA_DA_LISTA).json()
    # Sem filtro: todos da grade, cadastrados e em andamento
    todos = aurora.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores_que_a_tela_manda(lista)})
    assert todos.status_code == 200
    linhas_de_todos = linhas_do_arquivo(todos)
    assert len(linhas_de_todos) - 1 == len(lista)
    # As duas situações estão no arquivo
    situacoes_no_arquivo = set()
    for linha in linhas_de_todos[1:]:
        situacoes_no_arquivo.add(linha[COLUNA_DA_SITUACAO])
    assert {"Cadastrado", "Aguardando envio"} <= situacoes_no_arquivo
    # Com o filtro "Aguardando envio": só as pessoas da inclusão (antes, essa escolha não baixava nada)
    aguardando = identificadores_que_a_tela_manda(lista, "Aguardando envio")
    assert aguardando
    resposta = aurora.post(ROTA_DO_DOWNLOAD, json={"identificadores": aguardando})
    assert resposta.status_code == 200, resposta.text
    linhas = linhas_do_arquivo(resposta)
    assert len(linhas) - 1 == len(aguardando)
    assert all(linha[COLUNA_DA_SITUACAO] == "Aguardando envio" for linha in linhas[1:])


def test_uma_empresa_nunca_baixa_as_pessoas_da_outra(api_com_envios_em_andamento):
    """A Aurora mandando os identificadores da Horizonte (em andamento): recusado, sem nenhum CPF dela na resposta."""
    horizonte = entrar("rh.horizonte")
    lista_da_horizonte = horizonte.get(ROTA_DA_LISTA).json()
    identificadores_da_horizonte = identificadores_que_a_tela_manda(lista_da_horizonte)
    aurora = entrar("rh.aurora")
    resposta = aurora.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores_da_horizonte})
    # Nenhuma pessoa da Aurora foi pedida: recusado, com a frase para a pessoa
    assert resposta.status_code == 400
    assert resposta.json()["detail"]
    for pessoa in lista_da_horizonte:
        if pessoa["cpf"]:
            assert pessoa["cpf"] not in resposta.text
    # Misturando: as da Aurora saem e as da Horizonte são ignoradas
    lista_da_aurora = aurora.get(ROTA_DA_LISTA).json()
    identificadores_da_aurora = identificadores_que_a_tela_manda(lista_da_aurora)
    misturado = aurora.post(ROTA_DO_DOWNLOAD,
                            json={"identificadores": identificadores_da_aurora + identificadores_da_horizonte})
    assert misturado.status_code == 200
    assert len(linhas_do_arquivo(misturado)) - 1 == len(lista_da_aurora)
    for pessoa in lista_da_horizonte:
        if pessoa["cpf"]:
            assert pessoa["cpf"] not in misturado.text


def test_identificador_de_quem_estava_em_andamento_nao_vale_depois_do_cadastro(api_com_envios_em_andamento):
    """Uma tela antiga (aberta antes do cadastro) manda o identificador do envio em andamento: ninguém sai trocado."""
    aurora = entrar("rh.aurora")
    lista_de_antes = aurora.get(ROTA_DA_LISTA).json()
    identificadores_de_antes = identificadores_que_a_tela_manda(lista_de_antes, "Aguardando envio")
    assert identificadores_de_antes
    # O banco cadastra a inclusão: as pessoas passam a ter o identificador do arquivo final
    conexao = auth.conectar()
    homologacao.homologar(conexao, api_com_envios_em_andamento["inclusao_da_aurora"], "EMP001", "rh")
    conexao.close()
    # O identificador antigo não acha ninguém (nunca vira outra pessoa do arquivo final)
    resposta = aurora.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores_de_antes})
    assert resposta.status_code == 400
    # A tela atualizada manda os novos e o arquivo sai, com as pessoas cadastradas
    lista_de_agora = aurora.get(ROTA_DA_LISTA).json()
    resposta_nova = aurora.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores_que_a_tela_manda(lista_de_agora)})
    assert resposta_nova.status_code == 200
    assert len(linhas_do_arquivo(resposta_nova)) - 1 == len(lista_de_agora)


def test_download_sem_login_e_pelo_banco_e_recusado(api_com_envios_em_andamento):
    """Sem login: 401. O especialista do banco não usa a rota da empresa: 403."""
    horizonte = entrar("rh.horizonte")
    identificadores = identificadores_que_a_tela_manda(horizonte.get(ROTA_DA_LISTA).json())
    # Sem login
    assert TestClient(aplicacao).post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores}).status_code == 401
    # O perfil do banco
    especialista = entrar("especialista")
    assert especialista.post(ROTA_DO_DOWNLOAD, json={"identificadores": identificadores}).status_code == 403


def test_cada_pessoa_da_lista_tem_um_identificador_de_download_unico(api_com_envios_em_andamento):
    """Na lista da tela, todo mundo tem o identificador de download, sem repetir; o do cadastrado é o próprio id."""
    aurora = entrar("rh.aurora")
    lista = aurora.get(ROTA_DA_LISTA).json()
    identificadores = []
    for pessoa in lista:
        assert pessoa["id_para_baixar"]
        identificadores.append(pessoa["id_para_baixar"])
        # O cadastrado usa o mesmo id da ficha; quem está em andamento continua sem id (a ficha é só de cadastrados)
        if pessoa["situacao"] == "Cadastrado":
            assert pessoa["id_para_baixar"] == pessoa["id"]
        else:
            assert pessoa["id"] is None
    assert len(set(identificadores)) == len(identificadores)
