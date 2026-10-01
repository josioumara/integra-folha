"""A página "Teto de gasto da IA" e a retomada automática dos envios pausados pelo teto (ADR-139).

O que se prova aqui (tudo em MOCK, sem custo; o gasto é somado direto na tabela do dia):
    - a situação num banco novo: tetos iniciais, IA funcionando, nada esperando, histórico vazio;
    - o ajuste grava o teto pela função do teto e registra no histórico (de → para, quem, quando), aceitando a
      vírgula do português;
    - as recusas (com variações: negativo, zero, texto, vazio, NaN, infinito, acima do máximo, período desconhecido,
      o mesmo valor), sem gravar nada no histórico;
    - os avisos: o teto novo não passa do gasto de hoje (ou do mês), e o teto do dia maior que o do mês;
    - "pausada desde": a primeira chamada barrada no período, sem contar as de antes de um ajuste;
    - subir o teto com a IA pausada libera na hora, sem reiniciar nada;
    - só os envios parados PELO TETO voltam sozinhos; o parado por outra falha continua esperando o clique;
    - a retomada para se o teto for atingido de novo, segue depois de um envio que quebra e não roda duas ao mesmo
      tempo;
    - o recado do envio pausado aponta o botão "Tentar de novo";
    - pela API: 401 sem login, 403 para a empresa, só o número de envios (nenhuma empresa), 400 com o motivo e a
      retomada em segundo plano depois de subir o teto;
    - a retomada periódica liga uma vez só, e só na partida do servidor.
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

from api import principal
from services import auth, banco, cadastro, execucoes, mapeamentos, pagina_do_teto_da_ia, teto_de_gasto
from tests.test_cadastro import api_do_cadastro, enviar, entrar  # noqa: F401 (a fixture da API)
from tests.test_tentar_de_novo import INTERPRETAR_DE_VERDADE, parar_o_envio, teto


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste."""
    conexao_do_teste = banco.conectar(tmp_path / "pagina_do_teto.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def gastar(conexao, valor_usd: float, dias_atras: int = 0) -> None:
    """Soma um gasto com IA no dia de hoje (ou alguns dias antes, no calendário de Brasília)."""
    dia = teto_de_gasto.hoje_em_brasilia() - timedelta(days=dias_atras)
    teto_de_gasto.somar_no_dia(conexao, valor_usd, dia)


def pausar_uma_chamada(conexao, identificador: str = "PROC-X", momento: datetime | None = None) -> datetime:
    """Grava uma chamada barrada pelo teto (como o agente grava na pausa). Devolve o momento dela."""
    momento = momento or datetime.now(timezone.utc)
    execucoes.registrar_pausa_pelo_teto(conexao, identificador, "EMP002", "interpretar", "Interpretador", momento)
    return momento


# ---------------- A situação ----------------

def test_a_situacao_num_banco_novo(conexao):
    situacao = pagina_do_teto_da_ia.situacao_da_pagina(conexao)
    assert (situacao["teto_dia_usd"], situacao["teto_mes_usd"]) == (20.0, 20.0)
    assert situacao["atingido"] is None and situacao["pausada_desde"] is None and situacao["volta_quando"] is None
    assert situacao["envios_esperando"] == 0 and situacao["historico"] == []
    assert situacao["ultimas_mudancas"] == {"dia": None, "mes": None}
    assert situacao["teto_maximo_usd"] == teto_de_gasto.TETO_MAXIMO_USD


# ---------------- O ajuste ----------------

@pytest.mark.parametrize("valor_digitado, valor_gravado", [(35, 35.0), ("25,50", 25.5), (" 12.75 ", 12.75)])
def test_o_ajuste_grava_e_registra_no_historico(conexao, valor_digitado, valor_gravado):
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "dia", valor_digitado)
    assert situacao["teto_dia_usd"] == valor_gravado and teto_de_gasto.ler_tetos(conexao)["dia"] == valor_gravado
    # O histórico guarda o de antes (o inicial), o novo e quem mudou
    mudanca = situacao["historico"][0]
    assert (mudanca["periodo"], mudanca["valor_antigo_usd"], mudanca["valor_novo_usd"], mudanca["alterado_por"]) == \
        ("dia", 20.0, valor_gravado, "especialista")
    # A última mudança do dia aparece; a do mês continua no valor inicial
    assert situacao["ultimas_mudancas"]["dia"]["alterado_por"] == "especialista"
    assert situacao["ultimas_mudancas"]["mes"] is None
    # Uma segunda mudança entra por cima, com o valor anterior certo
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "outra.pessoa", "dia", 40)
    assert [linha["valor_antigo_usd"] for linha in situacao["historico"]] == [valor_gravado, 20.0]


@pytest.mark.parametrize("periodo, valor, motivo", [
    ("dia", -5, "maior que zero"),
    ("mes", 0, "maior que zero"),
    ("dia", "vinte", "número"),
    ("dia", "", "número"),
    ("dia", "nan", "número"),
    ("mes", math.inf, "número"),
    ("dia", 1000.01, "máximo"),
    ("dia", True, "número"),
    ("dia", None, "número"),
    ("semana", 10, "Período desconhecido"),
    ("dia", 20, "nada mudou"),
])
def test_as_recusas_nao_gravam_nada(conexao, periodo, valor, motivo):
    with pytest.raises(ValueError, match=motivo):
        pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", periodo, valor)
    # Nada mudou: nem o teto, nem o histórico
    assert teto_de_gasto.ler_tetos(conexao) == {"dia": 20.0, "mes": 20.0}
    assert pagina_do_teto_da_ia.situacao_da_pagina(conexao)["historico"] == []


def test_avisa_quando_o_teto_novo_nao_passa_do_gasto(conexao):
    gastar(conexao, 7.2)
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "dia", 5)
    assert situacao["atingido"] == "dia" and situacao["ia_liberada"] is False
    assert any("não passa do gasto de hoje" in aviso and "meia-noite" in aviso for aviso in situacao["avisos"])
    # O mês: gasto espalhado por dias (dentro do mesmo mês, quando dá), teto do mês abaixo da soma
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "mes", 7)
    assert any("não passa do gasto do mês" in aviso for aviso in situacao["avisos"])


def test_avisa_quando_o_teto_do_dia_passa_do_do_mes(conexao):
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "dia", 50)
    assert any("maior que o do mês" in aviso for aviso in situacao["avisos"])
    # Um teto do dia abaixo do do mês: nenhum aviso
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "dia", 10)
    assert situacao["avisos"] == []


def test_subir_o_teto_com_a_ia_pausada_libera_na_hora(conexao):
    gastar(conexao, 25)
    assert teto_de_gasto.periodo_atingido(conexao) == "dia"
    pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "mes", 100)
    situacao = pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "dia", 30)
    # A mesma conferência que o cliente de IA faz antes de cada chamada já deixa passar (sem reiniciar nada)
    assert situacao["atingido"] is None and situacao["ia_liberada"] is True
    assert teto_de_gasto.periodo_atingido(conexao) is None


# ---------------- Desde quando ----------------

def test_pausada_desde_a_primeira_chamada_barrada(conexao):
    gastar(conexao, 21)
    # Atingido, mas ninguém chamou a IA ainda: não há "desde"
    situacao = pagina_do_teto_da_ia.situacao_da_pagina(conexao)
    assert situacao["atingido"] == "dia" and situacao["pausada_desde"] is None
    assert "meia-noite" in situacao["volta_quando"]
    # Duas chamadas barradas: vale a primeira
    primeira = pausar_uma_chamada(conexao)
    pausar_uma_chamada(conexao, momento=primeira + timedelta(minutes=5))
    desde = pagina_do_teto_da_ia.situacao_da_pagina(conexao)["pausada_desde"]
    assert datetime.fromisoformat(desde) == primeira.replace(microsecond=primeira.microsecond // 1000 * 1000)


def test_uma_pausa_de_antes_do_ajuste_nao_conta(conexao):
    gastar(conexao, 21)
    # Uma chamada barrada antes de alguém mudar o teto (a pausa daquela vez já acabou)
    pausar_uma_chamada(conexao, momento=datetime.now(timezone.utc) - timedelta(seconds=30))
    pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "mes", 100)
    # O teto do dia (20) continua atingido, mas ninguém chamou a IA depois da mudança
    assert pagina_do_teto_da_ia.situacao_da_pagina(conexao)["pausada_desde"] is None


def test_a_pausa_do_mes_volta_no_dia_primeiro(conexao):
    gastar(conexao, 21)
    pagina_do_teto_da_ia.ajustar_teto(conexao, "especialista", "dia", 100)
    situacao = pagina_do_teto_da_ia.situacao_da_pagina(conexao)
    assert situacao["atingido"] == "mes" and "dia 1º" in situacao["volta_quando"]


# ---------------- A retomada ----------------

def envio_pausado(conexao, monkeypatch, nome: str = "horizonte_carga_inicial") -> str:
    """Um envio parado pelo teto (a IA pausada no Interpretador). Devolve o processamento_id."""
    parar_o_envio(monkeypatch, teto_de_gasto.TetoDeGastoAtingido("dia"))
    return enviar(conexao, nome)["processamento_id"]


def etapa(conexao, empresa_id: str, processamento_id: str) -> str:
    """A etapa em que o envio está agora."""
    return cadastro.leitura_do_envio(conexao, empresa_id, processamento_id)["etapa"]


def test_so_os_envios_parados_pelo_teto_voltam_sozinhos(conexao, monkeypatch):
    pausado_pelo_teto = envio_pausado(conexao, monkeypatch)
    # Outro envio, de outra empresa, parado por uma falha comum (não é o teto)
    parar_o_envio(monkeypatch, RuntimeError("serviço fora do ar"))
    parado_por_falha = enviar(conexao, "aurora_carga_inicial")["processamento_id"]
    esperando = pagina_do_teto_da_ia.envios_pausados_pelo_teto(conexao)
    assert esperando == [{"processamento_id": pausado_pelo_teto, "empresa_id": "EMP002"}]
    # O recado do envio pausado aponta o botão "Tentar de novo"
    leitura = cadastro.leitura_do_envio(conexao, "EMP002", pausado_pelo_teto)
    assert leitura["erro"] == teto_de_gasto.RECADO_DO_ENVIO_PAUSADO and "Tentar de novo" in leitura["erro"]
    # A IA voltou: só o pausado pelo teto é retomado
    teto(monkeypatch, None)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    assert pagina_do_teto_da_ia.retomar_envios_pausados(conexao) == 1
    assert etapa(conexao, "EMP002", pausado_pelo_teto) == "aprovar_mapeamento"
    assert etapa(conexao, "EMP001", parado_por_falha) == "aguardar_nova_tentativa"
    assert pagina_do_teto_da_ia.situacao_da_pagina(conexao)["envios_esperando"] == 0


def test_com_o_teto_atingido_nada_volta(conexao, monkeypatch):
    processamento_id = envio_pausado(conexao, monkeypatch)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    # O gasto do dia passou do teto: a retomada nem tenta
    gastar(conexao, 21)
    assert pagina_do_teto_da_ia.retomar_envios_pausados(conexao) == 0
    assert etapa(conexao, "EMP002", processamento_id) == "aguardar_nova_tentativa"
    assert pagina_do_teto_da_ia.situacao_da_pagina(conexao)["envios_esperando"] == 1


def test_a_retomada_para_quando_o_teto_e_atingido_no_meio(conexao, monkeypatch):
    primeiro = envio_pausado(conexao, monkeypatch)
    segundo = envio_pausado(conexao, monkeypatch, "aurora_carga_inicial")
    # A conferência da retomada deixa passar, mas a do envio encontra o teto atingido (outro pedido gastou no meio)
    teto(monkeypatch, "mes")
    assert pagina_do_teto_da_ia.retomar_envios_pausados(conexao) == 0
    assert etapa(conexao, "EMP002", primeiro) == etapa(conexao, "EMP001", segundo) == "aguardar_nova_tentativa"


def test_um_envio_que_quebra_nao_para_os_outros(conexao, monkeypatch):
    primeiro = envio_pausado(conexao, monkeypatch)
    segundo = envio_pausado(conexao, monkeypatch, "aurora_carga_inicial")
    tentar_de_verdade = cadastro.tentar_de_novo

    def tentar_quebrando_o_primeiro(conexao_da_retomada, empresa_id, processamento_id):
        """O primeiro envio quebra por outro motivo; o segundo segue normal."""
        if processamento_id == primeiro:
            raise RuntimeError("quebrou")
        return tentar_de_verdade(conexao_da_retomada, empresa_id, processamento_id)
    monkeypatch.setattr(cadastro, "tentar_de_novo", tentar_quebrando_o_primeiro)
    teto(monkeypatch, None)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    assert pagina_do_teto_da_ia.retomar_envios_pausados(conexao) == 1
    assert etapa(conexao, "EMP001", segundo) == "aprovar_mapeamento"


def test_duas_retomadas_nao_rodam_juntas(conexao, monkeypatch):
    envio_pausado(conexao, monkeypatch)
    teto(monkeypatch, None)
    # Outra retomada está com a trava: esta não faz nada
    pagina_do_teto_da_ia.trava_da_retomada.acquire()
    try:
        assert pagina_do_teto_da_ia.retomar_envios_pausados(conexao) == 0
    finally:
        pagina_do_teto_da_ia.trava_da_retomada.release()


def test_a_retomada_em_segundo_plano_nunca_derruba_nada():
    def banco_fora_do_ar():
        """A conexão que não abre."""
        raise ConnectionError("fora do ar")
    assert pagina_do_teto_da_ia.retomar_com_conexao_nova(banco_fora_do_ar) == 0


def test_a_retomada_periodica_liga_uma_vez_e_so_na_partida(monkeypatch):
    linhas_criadas = []

    class LinhaDeFundoFalsa:
        """No lugar da linha de fundo de verdade (que rodaria para sempre durante os testes)."""

        def __init__(self, **argumentos):
            linhas_criadas.append(argumentos)

        def start(self):
            """Não roda nada."""

    monkeypatch.setattr(pagina_do_teto_da_ia.threading, "Thread", LinhaDeFundoFalsa)
    monkeypatch.setitem(pagina_do_teto_da_ia.retomada_periodica, "ligada", False)
    assert pagina_do_teto_da_ia.ligar_retomada_periodica(auth.conectar) is True
    assert pagina_do_teto_da_ia.ligar_retomada_periodica(auth.conectar) is False
    assert len(linhas_criadas) == 1 and linhas_criadas[0]["daemon"] is True
    assert linhas_criadas[0]["args"][1] == pagina_do_teto_da_ia.INTERVALO_DA_RETOMADA_S
    # Ligada na partida do servidor (a lista do que roda quando ele liga), e não ao importar
    assert principal.ligar_a_retomada_do_teto in principal.aplicacao.router.on_startup


# ---------------- Pela API ----------------

ROTAS_DO_TETO = [("get", "/api/banco/teto_da_ia"), ("get", "/api/banco/teto_da_ia/aviso"),
                 ("post", "/api/banco/teto_da_ia")]


@pytest.mark.parametrize("metodo, endereco", ROTAS_DO_TETO)
def test_api_so_para_o_banco(api_do_cadastro, metodo, endereco):
    from fastapi.testclient import TestClient
    sem_login = TestClient(principal.aplicacao)
    empresa = entrar("rh.horizonte")
    if metodo == "post":
        # O POST leva um teto novo no corpo
        corpo = {"periodo": "dia", "valor_usd": 30}
        resposta_sem_login = sem_login.post(endereco, json=corpo)
        resposta_da_empresa = empresa.post(endereco, json=corpo)
    else:
        resposta_sem_login = sem_login.get(endereco)
        resposta_da_empresa = empresa.get(endereco)
    # Sem login: 401; a empresa: 403 (e nada foi gravado)
    assert resposta_sem_login.status_code == 401
    assert resposta_da_empresa.status_code == 403
    assert teto_de_gasto.ler_tetos(auth.conectar()) == {"dia": 20.0, "mes": 20.0}


def test_api_mostra_ajusta_recusa_e_retoma(api_do_cadastro, monkeypatch):
    # Um envio da Horizonte parado pelo teto
    parar_o_envio(monkeypatch, teto_de_gasto.TetoDeGastoAtingido("dia"))
    horizonte = entrar("rh.horizonte")
    leitura = enviar(auth.conectar(), "horizonte_carga_inicial")
    processamento_id = leitura["processamento_id"]
    especialista = entrar("especialista")
    # A página: só o número de envios esperando, nenhuma empresa
    resposta = especialista.get("/api/banco/teto_da_ia")
    assert resposta.status_code == 200 and resposta.json()["envios_esperando"] == 1
    assert "EMP002" not in resposta.text and processamento_id not in resposta.text
    assert especialista.get("/api/banco/teto_da_ia/aviso").json() == {"atingido": None}
    # Um valor negativo: 400 com o motivo
    resposta = especialista.post("/api/banco/teto_da_ia", json={"periodo": "dia", "valor_usd": -1})
    assert resposta.status_code == 400 and "maior que zero" in resposta.json()["detail"]
    # Subir o teto: grava com quem mudou e, depois da resposta, o envio volta sozinho para a análise
    teto(monkeypatch, None)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    resposta = especialista.post("/api/banco/teto_da_ia", json={"periodo": "dia", "valor_usd": "30,00"})
    dados = resposta.json()
    assert resposta.status_code == 200 and dados["teto_dia_usd"] == 30.0 and dados["ia_liberada"] is True
    assert dados["historico"][0]["alterado_por"] == "especialista"
    assert horizonte.get("/api/empresa/cadastro/" + processamento_id).json()["etapa"] == "aprovar_mapeamento"
    assert especialista.get("/api/banco/teto_da_ia").json()["envios_esperando"] == 0


def test_api_aviso_com_o_teto_atingido(api_do_cadastro):
    gastar(auth.conectar(), 20)
    assert entrar("especialista").get("/api/banco/teto_da_ia/aviso").json() == {"atingido": "dia"}
