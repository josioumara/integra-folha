"""O joinha nas respostas dos agentes: o voto, as regras e os números do Acompanhamento dos agentes (ADR-151).

O que estes testes provam (com a IA simulada, sem custo):
- a resposta da conversa (e a da confirmação) traz a posição do balão, e as Resolvidas trazem a posição de cada balão:
  é por ela que o joinha diz qual resposta recebeu o voto;
- um voto por pessoa em cada resposta: mudar de ideia troca o voto, sem somar dois; retirar o voto apaga a linha; duas
  pessoas do mesmo RH votam cada uma por si;
- só a resposta do agente recebe o joinha (nem a fala da pessoa, nem a pergunta que abre o cartão); a referência fora
  do formato e o voto fora da regra são recusados; o comentário fica só no joinha para baixo, com até 200 letras;
- a pergunta da leitura recebe o joinha do Agente Leitor (ou do Conferidor, pelo começo do texto dele);
- o banco vota no material do Endomarketing da empresa aberta, e só nele;
- a empresa só vota (e só vê os votos) nos envios dela: o de outra empresa é "não encontrado";
- os números da tela do banco: a satisfação por agente, o período pelas datas de Brasília (as duas pontas contam), a
  tendência de 12 semanas até o fim do período, a comparação com votos bastantes, nunca um zero inventado, e nenhum
  login nem texto de comentário;
- as rotas: 401 sem login, 403 para o outro perfil, 404 para o envio de outra empresa, 400 para a data errada;
- a tela usa os mesmos tipos, votos, limites e semanas do servidor, toda página com a conversa carrega o joinha, e a
  seção fica no Acompanhamento dos agentes (e não nos Indicadores).
A tela (o joinha nos balões e no material, o comentário à vista e a seção do Acompanhamento dos agentes) tem o roteiro
de clique opiniao_dos_agentes.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agents import conferidor_da_leitura, endomarketing
from api.principal import aplicacao
from models.contratos import Perfil
from services import assistente_na_tela, auth, cadastro, conversas_das_pendencias, opiniao_dos_agentes
from services import empresas as cadastro_de_empresas
from tests.apoio_do_parametro import marcar_como_obrigatorios
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import (EMPRESA, ESCOLHAS_DO_ARQUIVO, LOGIN, arquivo_com_casdo,  # noqa: F401
                                            conexao, envio, representante, usar_busca_falsa)
from tests.test_perguntas_da_ia import LINHA_DA_BEATRIZ, enviar_e_aceitar

# Senha dos usuários de teste das rotas
SENHA_DE_TESTE = "senha-de-teste-123"
# A pasta do front, para conferir que a tela usa os mesmos nomes e limites do servidor
PASTA_DO_FRONT = Path(__file__).resolve().parent.parent / "front"
# Os scripts do joinha (o componente e a seção do banco)
SCRIPTS_DO_JOINHA = {"js/opiniao_dos_agentes.js", "js/banco_opiniao_dos_agentes.js"}
# Uma declaração no nível de cima de um script (sem espaço antes): função, const, let, var ou class, com o nome
DECLARACAO_GLOBAL = re.compile(r"^(?:async\s+)?function\s+(\w+)\s*\(|^(?:const|let|var|class)\s+(\w+)", re.MULTILINE)
# Quem vota nos testes do serviço: duas pessoas do RH da Aurora, uma da Brisa e o especialista do banco
RH_DA_AURORA = SimpleNamespace(login=LOGIN, empresa_id=EMPRESA, perfil=Perfil.EMPRESA)
OUTRA_PESSOA_DA_AURORA = SimpleNamespace(login="rh.aurora.2", empresa_id=EMPRESA, perfil=Perfil.EMPRESA)
RH_DA_BRISA = SimpleNamespace(login="rh.brisa", empresa_id="EMP003", perfil=Perfil.EMPRESA)
ESPECIALISTA = SimpleNamespace(login="especialista", empresa_id=None, perfil=Perfil.BANCO)
# O momento das contas da satisfação: quarta-feira, 30/09/2026, 15h no horário universal (12h em Brasília)
AGORA = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)


def pendencia_da_noiva(conexao) -> dict:
    """A pendência de quem veio sozinha com "Noiva" (não está num grupo)."""
    from services import acompanhamento
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["valor_lido"] == "Noiva":
            return pendencia
    raise AssertionError("o envio devia ter a pendência da Noiva")


def conversar(conexao, envio_id: str, pendencia: dict, mensagem: str, em_grupo: bool = False) -> dict:
    """Uma rodada da conversa com o Agente de validação sobre a pendência."""
    return assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio_id, pendencia["regra_id"], pendencia["linha"],
                                        mensagem, em_grupo=em_grupo)


def referencia_da_resposta(resposta: dict) -> str:
    """A referência do joinha de uma resposta da conversa: a chave e a posição. Ex.: "a1b2|...|estado_civil|2"."""
    return f"{resposta['chave']}|{resposta['ordem']}"


def votar_na_resposta(conexao, usuario, referencia: str, voto: str | None, comentario: str | None = None) -> dict:
    """O joinha de uma pessoa da empresa numa resposta da conversa."""
    return opiniao_dos_agentes.votar_como_empresa(conexao, usuario, opiniao_dos_agentes.TIPO_RESPOSTA_DA_CONVERSA,
                                                  referencia, voto, comentario)


def linhas_da_tabela(conexao) -> list[tuple]:
    """Todas as opiniões guardadas: (login, agente, voto, comentario, empresa_id)."""
    # A tabela nasce no primeiro voto; quando todos foram recusados, ela ainda não existe
    opiniao_dos_agentes._preparar(conexao)
    return list(conexao.execute("SELECT login, agente, voto, comentario, empresa_id FROM opinioes_dos_agentes "
                                "ORDER BY login"))


def gravar_material(conexao, material_id: str, empresa_id: str) -> None:
    """Grava direto na tabela um rascunho do Endomarketing da empresa (o texto não importa aqui)."""
    endomarketing._preparar(conexao)
    conexao.execute("INSERT INTO materiais_endomarketing (material_id, empresa_id, tipo, conteudo, status, modelo, "
                    "versao_prompt, criado_em, criado_por) VALUES (?, ?, 'comunicado', '{}', 'RASCUNHO', 'mock', 'v', "
                    "'2026-09-30T12:00:00+00:00', 'especialista')", (material_id, empresa_id))
    conexao.commit()


# ---------------- A posição da resposta ----------------

def test_a_resposta_da_conversa_traz_a_posicao_do_balao(conexao, envio):
    pendencia = pendencia_da_noiva(conexao)
    # A pergunta (0), a fala da pessoa (1) e a resposta do agente (2)
    primeira = conversar(conexao, envio, pendencia, "Por que isso é um problema?")
    assert primeira["ordem"] == 2
    # A rodada seguinte continua a conta: a fala da pessoa (3) e a resposta (4)
    segunda = conversar(conexao, envio, pendencia, "Solteiro")
    assert segunda["ordem"] == 4
    # A posição aponta mesmo para a resposta do agente guardada
    balao = conversas_das_pendencias.balao_guardado(conexao, envio, segunda["chave"], segunda["ordem"])
    assert balao == {"quem": "ia", "pergunta": False}


def test_a_confirmacao_tambem_traz_a_posicao_e_recebe_o_joinha(conexao, envio):
    pendencia = pendencia_da_noiva(conexao)
    resposta = conversar(conexao, envio, pendencia, "não cadastrar esta pessoa")
    confirmada = assistente_na_tela.confirmar_retirada(conexao, EMPRESA, LOGIN, envio,
                                                       resposta["confirmacao"]["correcao_id"], True)
    # A pergunta (0), a fala (1), a pergunta de confirmação (2), a escolha (3) e a resposta (4)
    assert confirmada["ordem"] == 4
    opiniao = votar_na_resposta(conexao, RH_DA_AURORA, f"{resposta['chave']}|{confirmada['ordem']}", "para_cima")
    assert opiniao["agente"] == "agente_de_validacao" and opiniao["voto"] == "para_cima"


def test_as_resolvidas_trazem_a_posicao_de_cada_balao(conexao, envio):
    conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro")
    resolvida = conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA)[0]
    posicoes = []
    for balao in resolvida["conversa"]:
        posicoes.append(balao["ordem"])
    assert posicoes == [0, 1, 2]


# ---------------- O voto na resposta da conversa ----------------

def test_mudar_de_ideia_troca_o_voto_sem_somar_dois(conexao, envio):
    referencia = referencia_da_resposta(conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro"))
    votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_cima")
    opiniao = votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_baixo", "Não era isso que eu queria.")
    # Uma linha só, com o voto e o comentário novos
    assert linhas_da_tabela(conexao) == [(LOGIN, "agente_de_validacao", "para_baixo",
                                          "Não era isso que eu queria.", EMPRESA)]
    assert opiniao == {"tipo": "resposta_da_conversa", "referencia": referencia, "agente": "agente_de_validacao",
                       "nome_do_agente": "Agente de validação", "voto": "para_baixo",
                       "comentario": "Não era isso que eu queria."}
    # A tela do banco conta um voto, e não dois
    numeros = opiniao_dos_agentes.satisfacao_dos_agentes(conexao)
    assert numeros["total"]["votos"] == 1 and numeros["total"]["para_baixo"] == 1


def test_retirar_o_voto_apaga_a_linha(conexao, envio):
    referencia = referencia_da_resposta(conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro"))
    votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_cima")
    opiniao = votar_na_resposta(conexao, RH_DA_AURORA, referencia, None)
    assert opiniao["voto"] is None and opiniao["comentario"] is None
    assert linhas_da_tabela(conexao) == []
    assert opiniao_dos_agentes.opinioes_do_envio(conexao, RH_DA_AURORA, envio) == []


def test_duas_pessoas_do_mesmo_rh_votam_cada_uma_por_si(conexao, envio):
    referencia = referencia_da_resposta(conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro"))
    votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_cima")
    votar_na_resposta(conexao, OUTRA_PESSOA_DA_AURORA, referencia, "para_baixo")
    # Cada pessoa vê o seu voto, e a tela do banco conta os dois
    minhas = opiniao_dos_agentes.opinioes_do_envio(conexao, RH_DA_AURORA, envio)
    da_colega = opiniao_dos_agentes.opinioes_do_envio(conexao, OUTRA_PESSOA_DA_AURORA, envio)
    assert [opiniao["voto"] for opiniao in minhas] == ["para_cima"]
    assert [opiniao["voto"] for opiniao in da_colega] == ["para_baixo"]
    assert opiniao_dos_agentes.satisfacao_dos_agentes(conexao)["total"]["votos"] == 2


def test_o_joinha_vale_na_conversa_do_grupo(conexao, envio):
    resposta = conversar(conexao, envio, representante(conexao), 'Sim, use "Casado" para as 3', em_grupo=True)
    assert resposta["chave"].startswith("grupo|")
    opiniao = votar_na_resposta(conexao, RH_DA_AURORA, referencia_da_resposta(resposta), "para_cima")
    assert opiniao["agente"] == "agente_de_validacao"
    # O voto fica preso ao envio do grupo: a tela o encontra de novo pelo envio
    assert len(opiniao_dos_agentes.opinioes_do_envio(conexao, RH_DA_AURORA, envio)) == 1


def test_so_a_resposta_do_agente_recebe_o_joinha(conexao, envio):
    resposta = conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro")
    chave = resposta["chave"]
    # A pergunta que abre o cartão (0) e a fala da pessoa (1) não recebem o joinha
    for posicao in (0, 1):
        with pytest.raises(ValueError):
            votar_na_resposta(conexao, RH_DA_AURORA, f"{chave}|{posicao}", "para_cima")
    # Uma posição que não existe: "não encontrado"
    with pytest.raises(KeyError):
        votar_na_resposta(conexao, RH_DA_AURORA, f"{chave}|99", "para_cima")
    # A referência sem a posição, ou com uma posição que não é número
    for referencia_errada in ("sem-barra", f"{chave}|x", f"{chave}|-1", f"{chave}|²"):
        with pytest.raises(ValueError):
            votar_na_resposta(conexao, RH_DA_AURORA, referencia_errada, "para_cima")
    assert linhas_da_tabela(conexao) == []


def test_o_voto_e_o_tipo_fora_da_regra_sao_recusados(conexao, envio):
    referencia = referencia_da_resposta(conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro"))
    with pytest.raises(ValueError):
        votar_na_resposta(conexao, RH_DA_AURORA, referencia, "talvez")
    # A empresa não vota no material do Endomarketing (é do banco)
    with pytest.raises(ValueError):
        opiniao_dos_agentes.votar_como_empresa(conexao, RH_DA_AURORA, "material_do_endomarketing", "m1", "para_cima")
    assert linhas_da_tabela(conexao) == []


def test_o_comentario_fica_so_no_joinha_para_baixo_e_ate_200_letras(conexao, envio):
    referencia = referencia_da_resposta(conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro"))
    # No joinha para cima, o comentário não fica
    assert votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_cima", "Ótimo")["comentario"] is None
    # Só espaços viram "sem comentário"; as pontas saem
    assert votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_baixo", "   ")["comentario"] is None
    assert votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_baixo", "  Faltou.  ")["comentario"] == "Faltou."
    # 200 letras cabem; 201, não (e o voto de antes continua)
    assert votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_baixo", "a" * 200)["comentario"] == "a" * 200
    with pytest.raises(ValueError):
        votar_na_resposta(conexao, RH_DA_AURORA, referencia, "para_baixo", "a" * 201)
    assert linhas_da_tabela(conexao)[0][3] == "a" * 200


def test_a_empresa_so_vota_e_so_ve_os_votos_nos_envios_dela(conexao, envio):
    referencia = referencia_da_resposta(conversar(conexao, envio, pendencia_da_noiva(conexao), "Solteiro"))
    # A Brisa não vota na conversa da Aurora, nem vê os votos daquele envio ("não encontrado")
    with pytest.raises(KeyError):
        votar_na_resposta(conexao, RH_DA_BRISA, referencia, "para_cima")
    with pytest.raises(KeyError):
        opiniao_dos_agentes.opinioes_do_envio(conexao, RH_DA_BRISA, envio)
    assert linhas_da_tabela(conexao) == []


# ---------------- A pergunta da leitura ----------------

def test_a_pergunta_do_leitor_recebe_o_joinha(conexao):
    envio_do_word = enviar_e_aceitar(conexao)
    # A pergunta do Agente Leitor sobre o CPF da Beatriz (linha 4 da tabela montada)
    referencia = f"{envio_do_word}|{LINHA_DA_BEATRIZ}|cpf"
    opiniao = opiniao_dos_agentes.votar_como_empresa(conexao, RH_DA_AURORA, "pergunta_da_leitura", referencia,
                                                     "para_cima")
    assert opiniao["agente"] == "leitor" and opiniao["nome_do_agente"] == "Agente Leitor"
    assert opiniao_dos_agentes.opinioes_do_envio(conexao, RH_DA_AURORA, envio_do_word)[0]["referencia"] == referencia
    # Uma linha ou um campo sem pergunta: "não encontrado"; a referência fora do formato: recusada
    with pytest.raises(KeyError):
        opiniao_dos_agentes.votar_como_empresa(conexao, RH_DA_AURORA, "pergunta_da_leitura",
                                               f"{envio_do_word}|{LINHA_DA_BEATRIZ}|nome_completo", "para_cima")
    for referencia_errada in (f"{envio_do_word}|4", f"{envio_do_word}|x|cpf", f"{envio_do_word}|4|cpf|a"):
        with pytest.raises(ValueError):
            opiniao_dos_agentes.votar_como_empresa(conexao, RH_DA_AURORA, "pergunta_da_leitura", referencia_errada,
                                                   "para_cima")
    # Outra empresa não vota na pergunta da Aurora
    with pytest.raises(KeyError):
        opiniao_dos_agentes.votar_como_empresa(conexao, RH_DA_BRISA, "pergunta_da_leitura", referencia, "para_cima")


def test_quem_fez_a_pergunta_da_leitura():
    # O Conferidor começa sempre do mesmo jeito (o de hoje e o da primeira versão); o resto é do Leitor
    assert opiniao_dos_agentes.agente_da_pergunta(conferidor_da_leitura.INICIO_DA_PERGUNTA + "no documento está "
                                                  "01/02/2020, mas ficou 01/02/2021. Qual é o certo?") == "conferidor"
    assert opiniao_dos_agentes.agente_da_pergunta(conferidor_da_leitura.INICIO_DA_PERGUNTA_DA_V1 + "a data") == \
        "conferidor"
    assert opiniao_dos_agentes.agente_da_pergunta("Não achei o CPF de Beatriz no texto. Qual é?") == "leitor"
    # O mesmo começo no meio da frase não é do Conferidor
    assert opiniao_dos_agentes.agente_da_pergunta("Por favor, " + conferidor_da_leitura.INICIO_DA_PERGUNTA) == "leitor"


# ---------------- O material do Endomarketing ----------------

def test_o_banco_vota_no_material_da_empresa_aberta(conexao):
    gravar_material(conexao, "m-aurora", "EMP001")
    opiniao = opiniao_dos_agentes.votar_como_banco(conexao, ESPECIALISTA, "EMP001", "material_do_endomarketing",
                                                   "m-aurora", "para_baixo", "O texto ficou longo.")
    assert opiniao["agente"] == "endomarketing" and opiniao["comentario"] == "O texto ficou longo."
    assert linhas_da_tabela(conexao) == [("especialista", "endomarketing", "para_baixo", "O texto ficou longo.",
                                          "EMP001")]
    # Os votos do especialista na Aurora; na Horizonte, nenhum
    assert len(opiniao_dos_agentes.opinioes_dos_materiais(conexao, ESPECIALISTA, "EMP001")) == 1
    assert opiniao_dos_agentes.opinioes_dos_materiais(conexao, ESPECIALISTA, "EMP002") == []
    # O material da Aurora pedido pela Horizonte é "não encontrado"; o banco não vota na conversa da empresa
    with pytest.raises(KeyError):
        opiniao_dos_agentes.votar_como_banco(conexao, ESPECIALISTA, "EMP002", "material_do_endomarketing",
                                             "m-aurora", "para_cima")
    with pytest.raises(ValueError):
        opiniao_dos_agentes.votar_como_banco(conexao, ESPECIALISTA, "EMP001", "resposta_da_conversa", "x|2",
                                             "para_cima")


# ---------------- A satisfação no Acompanhamento dos agentes ----------------

def gravar_opiniao(conexao, agente: str, voto: str, empresa_id: str, quando: datetime, numero: int,
                   comentario: str | None = None) -> None:
    """Grava direto uma opinião (como a carga dos dados de demonstração faz), com a data informada."""
    opiniao_dos_agentes._preparar(conexao)
    opiniao_dos_agentes.gravar(conexao, {
        "tipo": "resposta_da_conversa", "referencia": f"teste|{agente}|{numero}", "login": "rh.teste",
        "agente": agente, "perfil": "EMPRESA", "empresa_id": empresa_id, "processamento_id": None, "voto": voto,
        "comentario": comentario, "origem": opiniao_dos_agentes.ORIGEM_DA_TELA,
        "quando": quando.isoformat(timespec="seconds")})
    conexao.commit()


@pytest.fixture
def opinioes_de_exemplo(conexao):
    """Votos em datas e empresas diferentes (a Aurora é de SP; a Horizonte, de MG).

    - Agente de validação, Aurora: 3 para cima ontem e 1 para baixo, com comentário, 8 dias atrás;
    - Agente Leitor, Horizonte: 1 para cima 40 dias atrás (fora dos 30 dias, dentro dos 90);
    - Agente de Endomarketing, Aurora: 1 para baixo 200 dias atrás (só "desde o começo");
    - Agente Conferidor, Aurora: 1 para cima no domingo, 27/09, às 22h de Brasília (segunda, 01h, no horário universal).
    """
    cadastro_de_empresas.esquecer_lista_em_memoria()
    for numero in range(3):
        gravar_opiniao(conexao, "agente_de_validacao", "para_cima", "EMP001", AGORA - timedelta(days=1), numero)
    gravar_opiniao(conexao, "agente_de_validacao", "para_baixo", "EMP001", AGORA - timedelta(days=8), 3,
                   "Um comentário que nunca vai para o banco.")
    gravar_opiniao(conexao, "leitor", "para_cima", "EMP002", AGORA - timedelta(days=40), 4)
    gravar_opiniao(conexao, "endomarketing", "para_baixo", "EMP001", AGORA - timedelta(days=200), 5)
    gravar_opiniao(conexao, "conferidor", "para_cima", "EMP001", datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc), 6)
    return conexao


def do_agente(numeros: dict, agente: str) -> dict:
    """Os números de um agente na resposta que a tela do banco recebe."""
    for numeros_do_agente in numeros["agentes"]:
        if numeros_do_agente["agente"] == agente:
            return numeros_do_agente
    raise KeyError(agente)


def satisfacao(conexao, de: str = "", ate: str = "") -> dict:
    """Os números que a tela do banco recebe, no período pedido, com o momento fixo dos testes."""
    return opiniao_dos_agentes.satisfacao_dos_agentes(conexao, de=de, ate=ate, agora=AGORA)


def test_a_satisfacao_por_agente_no_periodo(opinioes_de_exemplo):
    numeros = satisfacao(opinioes_de_exemplo, de="2026-09-01", ate="2026-09-30")
    # Os quatro agentes, sempre na mesma ordem
    assert [agente["agente"] for agente in numeros["agentes"]] == ["agente_de_validacao", "leitor", "conferidor",
                                                                   "endomarketing"]
    validacao = do_agente(numeros, "agente_de_validacao")
    assert (validacao["votos"], validacao["para_cima"], validacao["para_baixo"]) == (4, 3, 1)
    assert validacao["satisfacao"] == 75.0 and validacao["com_comentario"] == 1
    assert validacao["nome"] == "Agente de validação" and validacao["o_que_faz"]
    # Sem voto no período: satisfação vazia, nunca um zero inventado
    assert do_agente(numeros, "leitor")["votos"] == 0 and do_agente(numeros, "leitor")["satisfacao"] is None
    # O total do período: a validação e o Conferidor
    assert numeros["total"] == {"votos": 5, "para_cima": 4, "para_baixo": 1, "com_comentario": 1, "satisfacao": 80.0}
    assert numeros["periodo"] == {"de": "2026-09-01", "ate": "2026-09-30"}


def test_o_periodo_pelas_datas_de_brasilia_e_o_tudo(opinioes_de_exemplo):
    # Desde 03/07: entra o Leitor, de 21/08
    em_90_dias = satisfacao(opinioes_de_exemplo, de="2026-07-03", ate="2026-09-30")
    assert do_agente(em_90_dias, "leitor")["satisfacao"] == 100.0 and em_90_dias["total"]["votos"] == 6
    # Sem as datas (o "Tudo"): todos, até o de 200 dias atrás. Um voto para baixo de um só é 0% de verdade
    desde_o_comeco = satisfacao(opinioes_de_exemplo)
    assert do_agente(desde_o_comeco, "endomarketing")["satisfacao"] == 0.0 and desde_o_comeco["total"]["votos"] == 7
    # As duas pontas contam, pelo dia de Brasília: o voto do Conferidor foi no domingo, 27/09, às 22h daqui
    assert do_agente(satisfacao(opinioes_de_exemplo, "2026-09-27", "2026-09-27"), "conferidor")["votos"] == 1
    assert do_agente(satisfacao(opinioes_de_exemplo, "2026-09-28", "2026-09-30"), "conferidor")["votos"] == 0
    # Só o começo, ou só o fim
    assert satisfacao(opinioes_de_exemplo, de="2026-09-29")["total"]["votos"] == 3
    assert satisfacao(opinioes_de_exemplo, ate="2026-08-31")["total"]["votos"] == 2
    # A data que não existe, fora do formato ou o começo depois do fim: recusados
    for de, ate in (("2026-13-01", ""), ("", "30/09/2026"), ("2026-09-30", "2026-09-01")):
        with pytest.raises(ValueError):
            satisfacao(opinioes_de_exemplo, de, ate)


def test_a_tendencia_tem_12_semanas_ate_o_fim_do_periodo_e_a_semana_vira_em_brasilia(opinioes_de_exemplo):
    numeros = satisfacao(opinioes_de_exemplo)
    # As 12 segundas-feiras, da mais antiga até a da semana de agora (quarta, 30/09 → segunda, 28/09)
    assert len(numeros["semanas"]) == 12
    assert numeros["semanas"][0] == "2026-07-13" and numeros["semanas"][-1] == "2026-09-28"
    tendencia = do_agente(numeros, "agente_de_validacao")["tendencia"]
    assert tendencia[-1] == {"semana": "2026-09-28", "votos": 3, "para_cima": 3, "satisfacao": 100.0}
    assert tendencia[-2] == {"semana": "2026-09-21", "votos": 1, "para_cima": 0, "satisfacao": 0.0}
    # Semana sem voto: satisfação vazia
    assert tendencia[0]["votos"] == 0 and tendencia[0]["satisfacao"] is None
    # O voto de domingo às 22h de Brasília fica na semana de 21/09, mesmo sendo segunda no horário universal
    conferidor = do_agente(numeros, "conferidor")["tendencia"]
    assert conferidor[-2]["votos"] == 1 and conferidor[-1]["votos"] == 0
    # Com o fim do período em 31/08, a linha termina na semana dele (segunda, 31/08), e o voto do Leitor (sexta, 21/08)
    # fica na semana de 17/08
    em_agosto = satisfacao(opinioes_de_exemplo, ate="2026-08-31")
    assert em_agosto["semanas"][0] == "2026-06-15" and em_agosto["semanas"][-1] == "2026-08-31"
    assert do_agente(em_agosto, "leitor")["tendencia"][-3] == {"semana": "2026-08-17", "votos": 1, "para_cima": 1,
                                                               "satisfacao": 100.0}


def test_a_comparacao_junta_4_semanas_de_cada_ponta_e_pede_votos_bastantes(opinioes_de_exemplo):
    # Sem voto nas 4 primeiras semanas: não há o que comparar (nunca uma subida inventada)
    numeros = satisfacao(opinioes_de_exemplo)
    assert do_agente(numeros, "agente_de_validacao")["comparacao"] == {
        "no_comeco": None, "no_fim": 75.0, "votos_no_comeco": 0, "votos_no_fim": 4, "diferenca": None}
    # Na primeira semana (13/07), 2 para cima e 3 para baixo (40%); no fim, mais 1 para cima (4 de 5, 80%)
    votos_do_comeco = ["para_cima", "para_cima", "para_baixo", "para_baixo", "para_baixo"]
    for numero, voto in enumerate(votos_do_comeco):
        gravar_opiniao(opinioes_de_exemplo, "agente_de_validacao", voto, "EMP001", AGORA - timedelta(days=77),
                       10 + numero)
    gravar_opiniao(opinioes_de_exemplo, "agente_de_validacao", "para_cima", "EMP001", AGORA - timedelta(days=2), 20)
    numeros = satisfacao(opinioes_de_exemplo)
    assert do_agente(numeros, "agente_de_validacao")["comparacao"] == {
        "no_comeco": 40.0, "no_fim": 80.0, "votos_no_comeco": 5, "votos_no_fim": 5, "diferenca": 40.0}
    # Uma ponta com menos votos que o mínimo: as duas satisfações aparecem, mas a diferença não (seria acaso)
    for numero in range(5):
        gravar_opiniao(opinioes_de_exemplo, "conferidor", "para_baixo", "EMP001", AGORA - timedelta(days=77),
                       30 + numero)
    conferidor = do_agente(satisfacao(opinioes_de_exemplo), "conferidor")
    assert conferidor["comparacao"] == {"no_comeco": 0.0, "no_fim": 100.0, "votos_no_comeco": 5, "votos_no_fim": 1,
                                        "diferenca": None}
    # As semanas se juntam pelos votos, e não pela média das porcentagens: 4 de 10, e não (100% + 33%) ÷ 2
    semanas = [{"votos": 1, "para_cima": 1}, {"votos": 9, "para_cima": 3}]
    assert opiniao_dos_agentes._contagem_das_semanas(semanas) == (10, 4)


def test_a_tela_do_banco_nunca_recebe_quem_votou_nem_o_comentario(opinioes_de_exemplo):
    em_texto = json.dumps(satisfacao(opinioes_de_exemplo), ensure_ascii=False)
    assert "rh.teste" not in em_texto and "nunca vai para o banco" not in em_texto
    assert "teste|" not in em_texto


# ---------------- A tela bate com o servidor ----------------

def ler_do_front(caminho_relativo: str) -> str:
    """O conteúdo de um arquivo do front, como texto. Ex.: ler_do_front("js/opiniao_dos_agentes.js")."""
    return (PASTA_DO_FRONT / caminho_relativo).read_text(encoding="utf-8")


def test_toda_pagina_com_a_conversa_carrega_o_joinha():
    # Os ganchos do joinha ficam no js/assistente_de_correcao.js: a página que carrega a conversa sem o joinha quebraria
    paginas_com_a_conversa = []
    for pagina in sorted(PASTA_DO_FRONT.glob("*.html")):
        html = pagina.read_text(encoding="utf-8")
        # A tag que carrega a conversa (o nome do arquivo também aparece nos comentários da página)
        if '<script src="js/assistente_de_correcao.js">' not in html:
            continue
        paginas_com_a_conversa.append(pagina.name)
        # O joinha logo depois da conversa, e a aparência dele
        assert html.index('<script src="js/opiniao_dos_agentes.js">') > \
            html.index('<script src="js/assistente_de_correcao.js">'), pagina.name
        assert '<link rel="stylesheet" href="css/opiniao_dos_agentes.css">' in html, pagina.name
    assert paginas_com_a_conversa == ["acompanhar.html", "cadastrar.html"]


def test_os_tipos_os_votos_e_os_limites_da_tela_sao_os_do_servidor():
    tela = ler_do_front("js/opiniao_dos_agentes.js")
    assert f'const TIPO_RESPOSTA_DA_CONVERSA = "{opiniao_dos_agentes.TIPO_RESPOSTA_DA_CONVERSA}";' in tela
    assert f'const TIPO_PERGUNTA_DA_LEITURA = "{opiniao_dos_agentes.TIPO_PERGUNTA_DA_LEITURA}";' in tela
    assert f'const TIPO_MATERIAL_DO_ENDOMARKETING = "{opiniao_dos_agentes.TIPO_MATERIAL_DO_ENDOMARKETING}";' in tela
    assert f'const VOTO_PARA_CIMA = "{opiniao_dos_agentes.PARA_CIMA}";' in tela
    assert f'const VOTO_PARA_BAIXO = "{opiniao_dos_agentes.PARA_BAIXO}";' in tela
    assert f"const TAMANHO_MAXIMO_DO_COMENTARIO_DO_JOINHA = {opiniao_dos_agentes.TAMANHO_MAXIMO_DO_COMENTARIO};" in tela
    # A regra das perguntas da leitura e o começo da chave do grupo: os mesmos do servidor
    from services import validador
    assert f'const REGRA_DA_PERGUNTA_DA_LEITURA = "{validador.PREFIXO_DA_PERGUNTA_DA_IA}";' in tela
    assert f'const COMECO_DA_CHAVE_DO_GRUPO = "{conversas_das_pendencias.PREFIXO_DO_GRUPO}";' in tela
    # As semanas da seção do Acompanhamento dos agentes
    secao_do_banco = ler_do_front("js/banco_opiniao_dos_agentes.js")
    assert f"const SEMANAS_DA_TENDENCIA_NA_TELA = {opiniao_dos_agentes.SEMANAS_DA_TENDENCIA};" in secao_do_banco
    assert f"const SEMANAS_DA_COMPARACAO_NA_TELA = {opiniao_dos_agentes.SEMANAS_DA_COMPARACAO};" in secao_do_banco
    assert (f"const MINIMO_DE_VOTOS_PARA_COMPARAR_NA_TELA = {opiniao_dos_agentes.MINIMO_DE_VOTOS_PARA_COMPARAR};"
            in secao_do_banco)


def test_a_secao_fica_no_acompanhamento_dos_agentes_e_nao_nos_indicadores():
    agentes = ler_do_front("banco_agentes.html")
    # A seção vem logo depois dos cartões do trabalho de cada agente
    assert "data-parte-opinioes" in agentes
    assert agentes.index('id="titulo-agentes"') < agentes.index("data-parte-opinioes")
    # O script da seção roda depois do da tela, que guarda o período do alto
    assert agentes.index('<script src="js/banco_agentes.js">') < \
        agentes.index('<script src="js/banco_opiniao_dos_agentes.js">')
    assert '<link rel="stylesheet" href="css/opiniao_dos_agentes.css">' in agentes
    # Nos Indicadores, a seção não existe
    indicadores = ler_do_front("banco_indicadores.html")
    assert "banco_opiniao_dos_agentes.js" not in indicadores and "data-cartoes-das-opinioes" not in indicadores


def nomes_globais(texto_do_script: str) -> set:
    """Os nomes que um script declara no nível de cima (funções, const, let, var e class)."""
    nomes = set()
    for achado in DECLARACAO_GLOBAL.finditer(texto_do_script):
        # O nome vem no primeiro grupo (função) ou no segundo (const, let, var ou class)
        nomes.add(achado.group(1) or achado.group(2))
    return nomes


def test_os_scripts_do_joinha_nao_repetem_nomes_dos_outros_scripts_da_pagina():
    # No navegador, os scripts da mesma página dividem os nomes: uma função repetida substitui a outra (e um const
    # repetido quebra a página). Em cada página com os scripts do joinha, nenhum nome deles se repete
    paginas_com_o_joinha = []
    for pagina in sorted(PASTA_DO_FRONT.glob("*.html")):
        # Os scripts que rodam: os de dentro das caixas <template> não rodam
        html = re.sub(r"<template[\s\S]*?</template>", "", pagina.read_text(encoding="utf-8"))
        scripts = re.findall(r'<script src="(js/[^"]+)"', html)
        if not SCRIPTS_DO_JOINHA.intersection(scripts):
            continue
        paginas_com_o_joinha.append(pagina.name)
        donos_de_cada_nome = {}
        for script in scripts:
            for nome in nomes_globais(ler_do_front(script)):
                if nome not in donos_de_cada_nome:
                    donos_de_cada_nome[nome] = []
                donos_de_cada_nome[nome].append(script)
        for nome, donos in donos_de_cada_nome.items():
            if SCRIPTS_DO_JOINHA.intersection(donos):
                assert len(donos) == 1, f"{pagina.name}: o nome {nome} está em {donos}"
    assert paginas_com_o_joinha == ["acompanhar.html", "banco_agentes.html", "banco_endomarketing.html",
                                    "cadastrar.html"]


def test_o_lugar_do_joinha_no_material():
    endomarketing = ler_do_front("banco_endomarketing.html")
    assert "data-opiniao-do-rascunho" in endomarketing and "data-opiniao-da-janela-material" in endomarketing
    # O joinha carrega antes do script da aba, que o chama (as tags, e não os comentários da página)
    assert endomarketing.index('<script src="js/opiniao_dos_agentes.js">') < \
        endomarketing.index('<script src="js/banco_endomarketing.js">')


# ---------------- As rotas ----------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste: a Aurora conversou com o agente, e há um rascunho dela.

    Devolve: {envio, referencia (a da resposta do agente)}.
    """
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    cadastro_de_empresas.esquecer_lista_em_memoria()
    conexao_do_teste = conectar_original(caminho)
    # O estado civil é opcional no layout: o parâmetro deste teste o marca como obrigatório (ADR-143)
    marcar_como_obrigatorios(conexao_do_teste, "estado_civil")
    leitura = cadastro.enviar_arquivo(conexao_do_teste, EMPRESA, LOGIN, arquivo_com_casdo(), "estado_civil.csv",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao_do_teste, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS_DO_ARQUIVO,
                                busca=busca_falsa)
    resposta = conversar(conexao_do_teste, leitura["processamento_id"], pendencia_da_noiva(conexao_do_teste), "Solteiro")
    gravar_material(conexao_do_teste, "m-aurora", "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao_do_teste.close()
    yield {"envio": leitura["processamento_id"], "referencia": referencia_da_resposta(resposta)}
    cadastro_de_empresas.esquecer_lista_em_memoria()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def voto_na_resposta(referencia: str, voto: str | None, comentario: str | None = None) -> dict:
    """O corpo do pedido do joinha numa resposta da conversa."""
    return {"tipo": "resposta_da_conversa", "referencia": referencia, "voto": voto, "comentario": comentario}


def test_as_rotas_pedem_login(api):
    sem_login = TestClient(aplicacao)
    assert sem_login.post("/api/empresa/opinioes", json=voto_na_resposta(api["referencia"], "para_cima")).status_code \
        == 401
    assert sem_login.get("/api/empresa/opinioes", params={"envio": api["envio"]}).status_code == 401
    assert sem_login.post("/api/banco/empresas/EMP001/opinioes", json={}).status_code == 401
    assert sem_login.get("/api/banco/empresas/EMP001/opinioes").status_code == 401
    assert sem_login.get("/api/banco/telemetria/opinioes").status_code == 401


def test_cada_rota_e_so_do_seu_perfil(api):
    da_empresa = entrar("rh.aurora")
    assert da_empresa.get("/api/banco/telemetria/opinioes").status_code == 403
    assert da_empresa.get("/api/banco/empresas/EMP001/opinioes").status_code == 403
    material = {"tipo": "material_do_endomarketing", "referencia": "m-aurora", "voto": "para_cima"}
    assert da_empresa.post("/api/banco/empresas/EMP001/opinioes", json=material).status_code == 403
    do_banco = entrar("especialista")
    assert do_banco.post("/api/empresa/opinioes", json=voto_na_resposta(api["referencia"], "para_cima")).status_code \
        == 403
    assert do_banco.get("/api/empresa/opinioes", params={"envio": api["envio"]}).status_code == 403


def test_a_empresa_vota_e_ve_so_os_seus_votos(api):
    da_aurora = entrar("rh.aurora")
    votou = da_aurora.post("/api/empresa/opinioes", json=voto_na_resposta(api["referencia"], "para_baixo", "Faltou."))
    assert votou.status_code == 200 and votou.json()["voto"] == "para_baixo" and votou.json()["comentario"] == "Faltou."
    minhas = da_aurora.get("/api/empresa/opinioes", params={"envio": api["envio"]})
    assert minhas.status_code == 200 and [opiniao["referencia"] for opiniao in minhas.json()["opinioes"]] == \
        [api["referencia"]]
    # A Brisa não vota nem vê nada do envio da Aurora: "não encontrado", sem dizer se existe
    da_brisa = entrar("rh.brisa")
    assert da_brisa.post("/api/empresa/opinioes", json=voto_na_resposta(api["referencia"], "para_cima")).status_code \
        == 404
    assert da_brisa.get("/api/empresa/opinioes", params={"envio": api["envio"]}).status_code == 404
    # Voto fora da regra: 400, com a frase para a pessoa
    errado = da_aurora.post("/api/empresa/opinioes", json=voto_na_resposta(api["referencia"], "talvez"))
    assert errado.status_code == 400 and "joinha" in errado.json()["detail"]


def test_o_banco_vota_no_material_e_le_so_numeros(api):
    do_banco = entrar("especialista")
    material = {"tipo": "material_do_endomarketing", "referencia": "m-aurora", "voto": "para_cima"}
    assert do_banco.post("/api/banco/empresas/EMP001/opinioes", json=material).status_code == 200
    assert do_banco.post("/api/banco/empresas/EMP002/opinioes", json=material).status_code == 404
    meus = do_banco.get("/api/banco/empresas/EMP001/opinioes")
    assert meus.status_code == 200 and meus.json()["opinioes"][0]["voto"] == "para_cima"
    # A Aurora também vota (na conversa): a tela do banco soma os dois agentes, só com números
    entrar("rh.aurora").post("/api/empresa/opinioes", json=voto_na_resposta(api["referencia"], "para_baixo", "Faltou."))
    numeros = do_banco.get("/api/banco/telemetria/opinioes")
    assert numeros.status_code == 200
    assert numeros.json()["total"]["votos"] == 2 and numeros.json()["total"]["com_comentario"] == 1
    em_texto = numeros.text
    assert "rh.aurora" not in em_texto and "especialista" not in em_texto and "Faltou." not in em_texto
    # Um período antigo, sem votos, e a data errada
    em_janeiro = do_banco.get("/api/banco/telemetria/opinioes", params={"de": "2026-01-01", "ate": "2026-01-31"})
    assert em_janeiro.status_code == 200 and em_janeiro.json()["total"]["votos"] == 0
    assert do_banco.get("/api/banco/telemetria/opinioes", params={"de": "31/01/2026"}).status_code == 400
