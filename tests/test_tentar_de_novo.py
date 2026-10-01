"""A rota "tentar de novo": retomar um envio que parou porque a IA foi pausada pelo teto de gasto (ADR-131).

O que se prova aqui (com variações: pausa do dia e do mês, e uma falha comum, que também para o envio):
    - o envio pausado fica guardado em "tentar de novo", sem contar como falha;
    - com o teto ainda atingido, tentar de novo devolve o recado e não mexe no fluxo (o envio continua guardado);
    - liberado o teto, o fluxo refaz a etapa que parou e segue até a próxima pausa (a proposta do mapeamento);
    - outra empresa não retoma o envio (404, mesmo com o teto atingido: o isolamento vem antes de tudo);
    - um envio em outra etapa não é "retomado" (400);
    - pela API: 503 com o recado da empresa, 404 para outra empresa, 200 com a leitura depois de liberar.
Tudo em MOCK, sem custo: o "teto atingido" é simulado.
"""
import pytest

from services import banco, cadastro, mapeamentos, teto_de_gasto
from tests.test_cadastro import api_do_cadastro, enviar, entrar  # noqa: F401 (a fixture da API)
from tests.test_correcao import ENVIOS, _gabarito

# O interpretador de verdade, guardado antes de qualquer troca
INTERPRETAR_DE_VERDADE = mapeamentos.interpretar_processamento


def parar_o_envio(monkeypatch, erro: Exception) -> None:
    """Troca o Interpretador por um que encontra o erro dado (a IA pausada pelo teto, ou outra falha)."""
    def interpretar_com_erro(*argumentos, **argumentos_nomeados):
        """O trabalho do Interpretador que não chega à IA."""
        raise erro
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", interpretar_com_erro)


def teto(monkeypatch, periodo: str | None) -> None:
    """Simula o teto: "dia" ou "mes" (atingido) ou None (livre)."""
    monkeypatch.setattr(teto_de_gasto, "teto_atingido", lambda: periodo)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste."""
    conexao_do_teste = banco.conectar(tmp_path / "tentar_de_novo.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.mark.parametrize("periodo", ["dia", "mes"])
def test_o_envio_pausado_espera_e_so_volta_com_o_teto_livre(conexao, monkeypatch, periodo):
    parar_o_envio(monkeypatch, teto_de_gasto.TetoDeGastoAtingido(periodo))
    leitura = enviar(conexao, "horizonte_carga_inicial")
    processamento_id = leitura["processamento_id"]
    # O envio ficou guardado, esperando a nova tentativa
    assert leitura["etapa"] == "aguardar_nova_tentativa"
    # Teto ainda atingido: o recado sobe, e o envio não sai do lugar
    teto(monkeypatch, periodo)
    with pytest.raises(teto_de_gasto.TetoDeGastoAtingido):
        cadastro.tentar_de_novo(conexao, "EMP002", processamento_id)
    assert cadastro.leitura_do_envio(conexao, "EMP002", processamento_id)["etapa"] == "aguardar_nova_tentativa"
    # Teto liberado (o dia virou ou o banco subiu o teto): o Interpretador trabalha e o envio segue para o aceite
    teto(monkeypatch, None)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    leitura = cadastro.tentar_de_novo(conexao, "EMP002", processamento_id)
    assert leitura["etapa"] == "aprovar_mapeamento" and leitura["colunas"]


def test_uma_falha_comum_tambem_pode_ser_retomada(conexao, monkeypatch):
    # Uma falha que não é o teto (ex.: o serviço caiu) também deixa o envio em "tentar de novo"
    parar_o_envio(monkeypatch, RuntimeError("serviço fora do ar"))
    processamento_id = enviar(conexao, "horizonte_carga_inicial")["processamento_id"]
    teto(monkeypatch, None)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    assert cadastro.tentar_de_novo(conexao, "EMP002", processamento_id)["etapa"] == "aprovar_mapeamento"


def test_outra_empresa_e_outra_etapa_nao_retomam(conexao, monkeypatch):
    parar_o_envio(monkeypatch, teto_de_gasto.TetoDeGastoAtingido("dia"))
    processamento_id = enviar(conexao, "horizonte_carga_inicial")["processamento_id"]
    # Outra empresa: "não encontrado", mesmo com o teto atingido (o isolamento vem antes do recado)
    teto(monkeypatch, "dia")
    with pytest.raises(KeyError):
        cadastro.tentar_de_novo(conexao, "EMP001", processamento_id)
    # Um envio que não está esperando uma nova tentativa (está no aceite): recusado com o motivo
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    outro_envio = enviar(conexao, "aurora_carga_inicial")["processamento_id"]
    teto(monkeypatch, None)
    with pytest.raises(ValueError, match="nova tentativa"):
        cadastro.tentar_de_novo(conexao, "EMP001", outro_envio)


def test_pela_api_503_com_o_recado_404_para_outra_empresa_e_200_ao_liberar(api_do_cadastro, monkeypatch):
    parar_o_envio(monkeypatch, teto_de_gasto.TetoDeGastoAtingido("mes"))
    horizonte = entrar("rh.horizonte")
    gabarito = _gabarito("horizonte_carga_inicial")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    leitura = horizonte.post("/api/empresa/cadastro/enviar", files={"arquivo": (gabarito["arquivo"], conteudo)}).json()
    endereco = "/api/empresa/cadastro/" + leitura["processamento_id"] + "/tentar_de_novo"
    # Teto atingido: 503 com o recado da empresa (que não manda clicar em nada)
    teto(monkeypatch, "mes")
    resposta = horizonte.post(endereco)
    assert resposta.status_code == 503 and resposta.json()["detail"] == teto_de_gasto.RECADO_PARA_A_EMPRESA
    # Outra empresa: 404
    assert entrar("rh.aurora").post(endereco).status_code == 404
    # Liberado: 200, com a leitura do envio já no aceite
    teto(monkeypatch, None)
    monkeypatch.setattr(mapeamentos, "interpretar_processamento", INTERPRETAR_DE_VERDADE)
    resposta = horizonte.post(endereco)
    assert resposta.status_code == 200 and resposta.json()["etapa"] == "aprovar_mapeamento"
