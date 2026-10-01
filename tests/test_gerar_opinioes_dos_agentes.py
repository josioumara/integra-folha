"""Os dados de demonstração do joinha (scripts/gerar_opinioes_dos_agentes.py; ADR-151).

O que estes testes provam (sem IA e sem o banco de todos):
- a carga usa só as empresas que existem no banco, avisa as que faltaram e nunca inventa uma;
- quem vota: o RH da empresa (validação, Leitor e Conferidor) e o banco (Endomarketing); empresa sem RH só recebe os
  votos do banco;
- tudo com a origem "carga sintética", a referência "sintetico|...", as datas nos últimos 90 dias e o comentário só no
  joinha para baixo;
- a semente é fixa: a mesma carga, no mesmo momento, dá os mesmos votos; rodar de novo não duplica nada;
- o --remover e a nova carga tiram só a carga sintética (o voto dado na tela fica);
- as taxas são diferentes por agente (a do Agente de validação sobe com o tempo), e o volume da base viva é plausível;
- o PostgreSQL de todos só com a confirmação de propósito.
"""
from datetime import datetime, timedelta, timezone

import pytest

from models.contratos import Perfil
from scripts import gerar_opinioes_dos_agentes as carga
from services import auth, opiniao_dos_agentes
from services import empresas as cadastro_de_empresas

# O momento da carga nos testes: quarta-feira, 30/09/2026, 15h no horário universal
AGORA = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)
# Uma senha qualquer para os usuários de teste (ninguém entra: a carga só lê os logins)
SENHA_DE_TESTE = "senha-de-teste-123"


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, com as 6 empresas da semente, dois logins do RH da Aurora, um da Horizonte e o do banco."""
    cadastro_de_empresas.esquecer_lista_em_memoria()
    # auth.conectar abre o banco já com a tabela dos usuários
    conexao_do_teste = auth.conectar(tmp_path / "teste.db")
    cadastro_de_empresas.listar(conexao_do_teste)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora.2", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    yield conexao_do_teste
    conexao_do_teste.close()
    cadastro_de_empresas.esquecer_lista_em_memoria()


def linhas(conexao) -> list[tuple]:
    """Todas as opiniões, em ordem: (referencia, login, agente, perfil, empresa, voto, comentario, origem, data)."""
    return list(conexao.execute("SELECT referencia, login, agente, perfil, empresa_id, voto, comentario, origem, "
                                "atualizado_em FROM opinioes_dos_agentes ORDER BY referencia, login"))


def test_a_carga_usa_so_as_empresas_do_banco_e_quem_pode_votar(conexao):
    resumo = carga.carregar(conexao, ["EMP001", "EMP002", "EMP003", "EMP099"], agora=AGORA)
    assert resumo["empresas"] == ["EMP001", "EMP002", "EMP003"] and resumo["faltaram"] == ["EMP099"]
    assert resumo["total"] == len(linhas(conexao)) == sum(resumo["votos"].values())
    for referencia, login, agente, perfil, empresa_id, voto, comentario, origem, data in linhas(conexao):
        # O Endomarketing é do banco; os outros, do RH da própria empresa
        if agente == "endomarketing":
            assert (login, perfil) == ("especialista", "BANCO")
        else:
            assert perfil == "EMPRESA" and (empresa_id, login) in {("EMP001", "rh.aurora"),
                                                                   ("EMP001", "rh.aurora.2"),
                                                                   ("EMP002", "rh.horizonte")}
        # A Brisa (EMP003) não tem RH: só os votos do banco
        if empresa_id == "EMP003":
            assert agente == "endomarketing"
        assert origem == opiniao_dos_agentes.ORIGEM_DA_CARGA_SINTETICA
        assert referencia.startswith(f"sintetico|{agente}|{empresa_id}|")
        # O comentário só no joinha para baixo
        assert comentario is None or voto == "para_baixo"
        # Nos últimos 90 dias (e nunca no futuro)
        momento = datetime.fromisoformat(data)
        assert AGORA - timedelta(days=91) <= momento <= AGORA


def test_a_semente_e_fixa_e_rodar_de_novo_nao_duplica(conexao):
    carga.carregar(conexao, ["EMP001", "EMP002"], agora=AGORA)
    primeira = linhas(conexao)
    carga.carregar(conexao, ["EMP001", "EMP002"], agora=AGORA)
    assert linhas(conexao) == primeira
    # A lista de empresas não muda os votos de uma empresa (cada uma tem o seu sorteio)
    carga.carregar(conexao, ["EMP002"], agora=AGORA)
    so_da_horizonte = []
    for linha in primeira:
        if linha[4] == "EMP002":
            so_da_horizonte.append(linha)
    assert linhas(conexao) == so_da_horizonte


def test_remover_e_a_nova_carga_tiram_so_a_carga_sintetica(conexao):
    opiniao_dos_agentes._preparar(conexao)
    opiniao_dos_agentes.gravar(conexao, {
        "tipo": "resposta_da_conversa", "referencia": "envio|REGRA|2|cpf|2", "login": "rh.aurora",
        "agente": "agente_de_validacao", "perfil": "EMPRESA", "empresa_id": "EMP001", "processamento_id": "envio",
        "voto": "para_cima", "comentario": None, "origem": opiniao_dos_agentes.ORIGEM_DA_TELA,
        "quando": AGORA.isoformat(timespec="seconds")})
    conexao.commit()
    carga.carregar(conexao, ["EMP001"], agora=AGORA)
    carga.carregar(conexao, ["EMP001"], agora=AGORA)
    assert opiniao_dos_agentes.quantas_da_carga_sintetica(conexao) > 0
    opiniao_dos_agentes.remover_carga_sintetica(conexao)
    # Sobra só o voto da tela
    assert [linha[0] for linha in linhas(conexao)] == ["envio|REGRA|2|cpf|2"]


def test_a_taxa_do_agente_de_validacao_sobe_com_o_tempo():
    assert carga.taxa_do_dia("agente_de_validacao", 90) == pytest.approx(0.70)
    assert carga.taxa_do_dia("agente_de_validacao", 45) == pytest.approx(0.79)
    assert carga.taxa_do_dia("agente_de_validacao", 0) == pytest.approx(0.88)
    assert carga.taxa_do_dia("conferidor", 10) == pytest.approx(0.60)


def satisfacao(opinioes: list[dict]) -> float:
    """A % de votos para cima numa lista de opiniões."""
    para_cima = 0
    for opiniao in opinioes:
        if opiniao["voto"] == "para_cima":
            para_cima = para_cima + 1
    return 100 * para_cima / len(opinioes)


def test_as_taxas_sao_diferentes_por_agente_e_o_volume_e_plausivel():
    # Muitas empresas de mentira (sem banco): as taxas aparecem nos números
    por_agente = {"agente_de_validacao": [], "leitor": [], "conferidor": [], "endomarketing": []}
    for numero in range(200):
        for opiniao in carga.opinioes_da_empresa(f"TESTE{numero}", ["rh"], "banco", AGORA):
            por_agente[opiniao["agente"]].append(opiniao)
    # O Conferidor abaixo do Leitor, e o Leitor abaixo do Endomarketing
    assert satisfacao(por_agente["conferidor"]) < satisfacao(por_agente["leitor"]) < \
        satisfacao(por_agente["endomarketing"])
    # O Agente de validação melhora: os votos do último mês acima dos de 60 a 90 dias atrás
    recentes = []
    antigos = []
    for opiniao in por_agente["agente_de_validacao"]:
        momento = datetime.fromisoformat(opiniao["quando"])
        if momento >= AGORA - timedelta(days=30):
            recentes.append(opiniao)
        elif momento < AGORA - timedelta(days=60):
            antigos.append(opiniao)
    assert satisfacao(recentes) > satisfacao(antigos) + 5
    # A base viva (22 empresas, um RH cada): algumas centenas de votos, como no contrato (~600)
    total_da_base_viva = 0
    for empresa_id in carga.empresas_da_base_viva():
        total_da_base_viva = total_da_base_viva + len(carga.opinioes_da_empresa(empresa_id, ["rh"], "banco", AGORA))
    assert len(carga.empresas_da_base_viva()) == 22
    assert 400 <= total_da_base_viva <= 800


def test_o_postgres_de_todos_so_com_a_confirmacao():
    with pytest.raises(carga.CargaRecusada):
        carga.conferir_o_banco("postgres", False)
    # Com a confirmação de propósito, ou no SQLite, segue
    carga.conferir_o_banco("postgres", True)
    carga.conferir_o_banco("sqlite", False)
