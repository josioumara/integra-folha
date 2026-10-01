"""Testes da conversa guardada no servidor e da lista "Resolvidas" (ADR-120).

O que estes testes provam (com a IA simulada, sem custo):
- cada rodada da conversa fica guardada: a pergunta que a pessoa viu (1º balão), o que ela escreveu e a resposta do
  agente com o que mudou; a resposta da conversa traz a chave, a mesma da tela;
- "Resolvidas" traz a conversa cuja mudança ainda vale e cuja pendência saiu: de quem, o campo, o resumo, quem e
  quando, e os balões; a pendência ainda em aberto, a conversa sem mudança e a mudança desfeita ficam de fora;
- o Desfazer marca o balão como "Desfeito" e conta na conversa o que voltou;
- a troca do grupo entra como UMA resolvida, com a quantidade de pessoas;
- a confirmação de "não cadastrar" entra na conversa (a escolha e a resposta), e a pergunta fica decidida;
- envio descartado sai de "Resolvidas"; outra empresa não vê nada;
- a rota GET /api/empresa/pendencias/resolvidas: 401 sem login, 403 para o banco, cada empresa só a sua.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, assistente_na_tela, auth, cadastro, conversas_das_pendencias
from tests.apoio_do_parametro import marcar_como_obrigatorios
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import (EMPRESA, ESCOLHAS_DO_ARQUIVO, LOGIN, arquivo_com_casdo,  # noqa: F401
                                            conexao, envio, representante, usar_busca_falsa)

# Senha dos usuários de teste da rota
SENHA_DE_TESTE = "senha-de-teste-123"


def pendencia_da_noiva(conexao) -> dict:
    """A pendência de quem veio sozinha com "Noiva" (não está num grupo)."""
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["valor_lido"] == "Noiva":
            return pendencia
    raise AssertionError("o envio devia ter a pendência da Noiva")


def conversar(conexao, envio_id: str, pendencia: dict, mensagem: str, em_grupo: bool = False) -> dict:
    """Uma rodada da conversa sobre a pendência."""
    return assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio_id, pendencia["regra_id"], pendencia["linha"],
                                        mensagem, em_grupo=em_grupo)


def test_a_conversa_fica_guardada_e_a_resolvida_vem_com_ela(conexao, envio):
    pendencia = pendencia_da_noiva(conexao)
    resposta = conversar(conexao, envio, pendencia, "Solteiro")
    # A chave é a mesma da tela: envio, regra e linha
    assert resposta["chave"] == f"{envio}|VALOR_NAO_CONVERTIDO|{pendencia['linha']}|estado_civil"
    resolvidas = conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA)
    assert len(resolvidas) == 1
    resolvida = resolvidas[0]
    assert resolvida["chave"] == resposta["chave"] and resolvida["processamento_id"] == envio
    assert resolvida["titulo"] == 'Ajuste na informação "Estado civil" de Davi Melo' and resolvida["quantidade"] == 1
    assert resolvida["nome_do_campo"] == pendencia["nome_do_campo"]
    assert resolvida["resumo"] == "Estado civil: Noiva → Solteiro"
    assert resolvida["resolvida_por"] == LOGIN and resolvida["resolvida_em"]
    # Os balões: a pergunta que a pessoa viu, o que ela escreveu e a resposta com o que mudou
    conversa = resolvida["conversa"]
    assert [balao["quem"] for balao in conversa] == ["ia", "empresa", "ia"]
    assert conversa[0]["pergunta"] is True and conversa[0]["texto"] == pendencia["pergunta"]
    assert conversa[1]["texto"] == "Solteiro"
    assert conversa[2]["texto"] == resposta["mensagem"] and '"Noiva" para "Solteiro"' in conversa[2]["texto"]
    assert conversa[2]["aplicado"]["desfazer"] == resposta["aplicado"]["desfazer"]
    assert conversa[2]["aplicado"]["desfeito"] is False


def test_pendencia_em_aberto_e_conversa_sem_mudanca_nao_sao_resolvidas(conexao, envio):
    pendencia = pendencia_da_noiva(conexao)
    # Só uma pergunta: a conversa fica guardada, mas nada foi resolvido
    conversar(conexao, envio, pendencia, "Por que isso é um problema?")
    assert conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA) == []
    guardadas = conversas_das_pendencias.conversas_do_envio(conexao, envio)
    assert len(guardadas[f"{envio}|VALOR_NAO_CONVERTIDO|{pendencia['linha']}|estado_civil"]["baloes"]) == 3


def test_desfazer_tira_das_resolvidas_e_fica_na_conversa(conexao, envio):
    pendencia = pendencia_da_noiva(conexao)
    resposta = conversar(conexao, envio, pendencia, "Solteiro")
    desfazer = resposta["aplicado"]["desfazer"]
    desfeito = assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, desfazer["tipo"], desfazer["id"])
    # A pendência voltou: não é mais uma resolvida
    assert conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA) == []
    # Na conversa: o balão da mudança marcado como desfeito e o que voltou, como fala do agente
    baloes = conversas_das_pendencias.conversas_do_envio(conexao, envio)[resposta["chave"]]["baloes"]
    assert baloes[2]["aplicado"]["desfeito"] is True
    assert baloes[-1]["quem"] == "ia" and baloes[-1]["texto"] == desfeito["resumo"]
    # Resolvida de novo: volta para a lista, com a conversa inteira
    conversar(conexao, envio, pendencia_da_noiva(conexao), "Casado")
    resolvidas = conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA)
    assert len(resolvidas) == 1 and resolvidas[0]["resumo"] == "Estado civil: Noiva → Casado"
    assert len(resolvidas[0]["conversa"]) == 6


def test_a_troca_do_grupo_e_uma_resolvida_so(conexao, envio):
    pendencia = representante(conexao)
    resposta = conversar(conexao, envio, pendencia, 'Sim, use "Casado" para as 3', em_grupo=True)
    assert resposta["chave"] == f"grupo|{envio}|estado_civil|casdo"
    resolvidas = conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA)
    assert len(resolvidas) == 1
    assert resolvidas[0]["chave"] == resposta["chave"] and resolvidas[0]["quantidade"] == 3
    assert resolvidas[0]["titulo"] == 'Ajuste na informação "Estado civil" de 3 pessoas'
    assert resolvidas[0]["conversa"][0]["texto"] == pendencia["grupo"]["pergunta"]


def test_a_confirmacao_de_nao_cadastrar_entra_na_conversa(conexao, envio):
    pendencia = pendencia_da_noiva(conexao)
    resposta = conversar(conexao, envio, pendencia, "não cadastrar esta pessoa")
    assistente_na_tela.confirmar_retirada(conexao, EMPRESA, LOGIN, envio, resposta["confirmacao"]["correcao_id"], True)
    resolvida = conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA)[0]
    textos = [balao["texto"] for balao in resolvida["conversa"]]
    assert textos[1] == "não cadastrar esta pessoa" and textos[3] == "Sim, não cadastrar"
    assert textos[4].startswith("Pronto: tirei Davi Melo")
    # A pergunta de confirmação ficou decidida (os botões não voltam ao reabrir)
    assert resolvida["conversa"][2]["confirmacao"]["decidida"] is True


def test_envio_descartado_e_outra_empresa_nao_mostram_resolvidas(conexao, envio):
    conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro")
    assert conversas_das_pendencias.resolvidas_da_empresa(conexao, "EMP003") == []
    cadastro.descartar(conexao, EMPRESA, envio, LOGIN)
    assert conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA) == []


# ---------------- A rota ----------------

@pytest.fixture
def api_das_resolvidas(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com uma pendência da Aurora já resolvida pela conversa."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    # O estado civil é opcional no layout: o parâmetro deste teste o marca como obrigatório (ADR-143)
    marcar_como_obrigatorios(conexao_do_teste, "estado_civil")
    leitura = cadastro.enviar_arquivo(conexao_do_teste, EMPRESA, LOGIN, arquivo_com_casdo(), "estado_civil.csv",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao_do_teste, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS_DO_ARQUIVO,
                                busca=busca_falsa)
    conversar(conexao_do_teste, leitura["processamento_id"], pendencia_da_noiva(conexao_do_teste), "Solteiro")
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao_do_teste.close()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_a_rota_das_resolvidas_e_so_da_empresa_dona(api_das_resolvidas):
    endereco = "/api/empresa/pendencias/resolvidas"
    # A dona vê a sua resolvida, com a conversa
    resposta = entrar("rh.aurora").get(endereco)
    assert resposta.status_code == 200 and len(resposta.json()) == 1
    assert resposta.json()[0]["conversa"][1]["texto"] == "Solteiro"
    # Sem login, o banco (fora do perfil) e outra empresa (lista vazia)
    assert TestClient(aplicacao).get(endereco).status_code == 401
    assert entrar("especialista").get(endereco).status_code == 403
    outra = entrar("rh.brisa").get(endereco)
    assert outra.status_code == 200 and outra.json() == []


# ---------------- A mesma regra em vários campos ----------------

def test_a_mesma_regra_em_campos_diferentes_nao_se_mistura(conexao, envio):
    """O arquivo sem várias colunas obrigatórias: cada campo tem a sua pendência, a sua pergunta e a sua conversa, e o
    valor respondido no cartão da UF vai só para a UF (antes, os cartões dividiam tudo e o valor podia ir para a
    matrícula). O outro campo é o sexo, obrigatório desde o ADR-128."""
    from services import correcoes, perguntas_das_pendencias
    sem_coluna = {}
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == "OBRIGATORIO_SEM_COLUNA":
            sem_coluna[pendencia["campo"]] = pendencia
    assert "uf_comercial" in sem_coluna and "sexo" in sem_coluna
    # A pergunta guardada de um campo não aparece no cartão do outro
    chave_da_uf = perguntas_das_pendencias.chave_da_pendencia("OBRIGATORIO_SEM_COLUNA", None, None, "uf_comercial")
    chave_do_sexo = perguntas_das_pendencias.chave_da_pendencia("OBRIGATORIO_SEM_COLUNA", None, None, "sexo")
    assert chave_da_uf != chave_do_sexo
    perguntas_das_pendencias._guardar(conexao, envio, {chave_da_uf: "Pergunta só da UF?"}, "teste")
    perguntas = {}
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == "OBRIGATORIO_SEM_COLUNA":
            perguntas[pendencia["campo"]] = pendencia["pergunta"]
    assert perguntas["uf_comercial"] == "Pergunta só da UF?" and perguntas["sexo"] != "Pergunta só da UF?"
    # A resposta curta no cartão da UF ("SP") vale para a UF de todos, e só para ela
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, "OBRIGATORIO_SEM_COLUNA", None, "SP",
                                            campo="uf_comercial")
    assert resposta["chave"] == f"{envio}|OBRIGATORIO_SEM_COLUNA|null|uf_comercial"
    assert resposta["aplicado"] is not None
    campos_trocados = {correcao.campo for correcao in correcoes.listar(conexao, envio, "APLICADA")}
    assert campos_trocados == {"uf_comercial"}
    # O sexo continua pendente, com a conversa dele vazia
    restantes = [pendencia["campo"] for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA)
                 if pendencia["regra_id"] == "OBRIGATORIO_SEM_COLUNA"]
    assert "sexo" in restantes and "uf_comercial" not in restantes
    guardadas = conversas_das_pendencias.conversas_do_envio(conexao, envio)
    assert f"{envio}|OBRIGATORIO_SEM_COLUNA|null|sexo" not in guardadas


def test_conversa_gravada_com_a_chave_antiga_nao_quebra_as_resolvidas(conexao, envio):
    """Antes de o campo entrar na chave, a chave era "<envio>|<regra>|<linha>". Uma conversa guardada assim
    não pode derrubar a lista das resolvidas: ela é lida como "qualquer campo daquela regra e linha"."""
    pendencia = pendencia_da_noiva(conexao)
    chave_antiga = f"{envio}|VALOR_NAO_CONVERTIDO|{pendencia['linha']}"
    abertura = {"titulo": "Davi Melo", "nome_do_campo": "Estado civil", "quantidade": 1, "pergunta": "Qual é?"}
    # Uma conversa antiga, ainda com a pendência em aberto: não é resolvida, e nada quebra
    conversas_das_pendencias.registrar(conexao, envio, chave_antiga, abertura,
                                       [conversas_das_pendencias.fala("empresa", "Solteiro"),
                                        conversas_das_pendencias.fala("ia", "Pronto: ...",
                                                                      aplicado={"resumo": "x", "desfazer": None})],
                                       LOGIN)
    assert conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA) == []
    # Resolvida a pendência (pela conversa nova), a antiga também sai do "em aberto" e aparece
    conversar(conexao, envio, pendencia, "Solteiro")
    chaves = {resolvida["chave"] for resolvida in conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA)}
    assert chave_antiga in chaves
