"""Cliente de LLM: modo MOCK, limite de custo e a pausa quando a IA real não responde (ADR-36 e ADR-145)."""
import pytest

from services import config, provedores_de_ia, teto_de_gasto
from services.llm_client import IAIndisponivel, LLMClient


def test_mock_devolve_resposta_registrada_sem_custo():
    """No MOCK, a resposta registrada para a tarefa volta, sem tokens medidos."""
    cliente = LLMClient(modo="mock", respostas_mock={"interpretar_colunas": '{"itens": []}'})
    resposta = cliente.gerar("interpretar_colunas", "prompt qualquer")
    assert resposta.texto == '{"itens": []}'
    assert resposta.modo == "mock"
    # "Não medido", nunca um número inventado
    assert resposta.tokens_entrada is None


def test_mock_sem_resposta_registrada_devolve_texto_padrao():
    """Tarefa sem resposta registrada: um texto padrão marcado como [MOCK]."""
    resposta = LLMClient(modo="mock").gerar("tarefa_nova", "prompt")
    assert resposta.texto.startswith("[MOCK]")


def test_modo_invalido_e_recusado():
    """Só existem os modos "mock" e "llm"."""
    with pytest.raises(ValueError):
        LLMClient(modo="producao")


def test_limite_de_chamadas_atingido_pausa_sem_simular():
    """Cota de chamadas esgotada: a IA pausa (IAIndisponivel, com o motivo), e nenhuma resposta simulada volta
    (ADR-145; antes, caía para o MOCK sem erro)."""
    cliente = LLMClient(modo="llm", limite_chamadas=1, mock_de_reserva=False)
    # A operação já gastou a cota
    cliente.chamadas_realizadas = 1
    with pytest.raises(IAIndisponivel) as pausa:
        cliente.gerar("interpretar_colunas", "prompt")
    assert "limite" in pausa.value.motivo


def test_limite_de_chamadas_com_o_mock_de_reserva_cai_para_a_simulacao():
    """Com o MOCK de reserva (só na máquina local), a cota esgotada cai para a simulação, como antes, e diz por quê."""
    cliente = LLMClient(modo="llm", limite_chamadas=1, mock_de_reserva=True)
    cliente.chamadas_realizadas = 1
    resposta = cliente.gerar("interpretar_colunas", "prompt")
    assert resposta.modo == "mock"
    assert "limite" in resposta.motivo_fallback


def test_falha_do_provedor_pausa_sem_simular(monkeypatch):
    """Provedor fora do ar: a IA pausa (IAIndisponivel), e o recado da exceção é o da pausa, sem o detalhe técnico."""
    cliente = LLMClient(modo="llm", mock_de_reserva=False)

    def provedor_fora_do_ar(*argumentos):
        """Simula o provedor sem responder, com um detalhe interno na mensagem."""
        raise ConnectionError("timeout em https://endereco-interno")

    monkeypatch.setattr(cliente, "_chamar_provedor", provedor_fora_do_ar)
    with pytest.raises(IAIndisponivel) as pausa:
        cliente.gerar("interpretar_colunas", "prompt")
    # O motivo técnico fica na exceção (para o registro); a mensagem é o recado, sem o endereço
    assert "falha no provedor" in pausa.value.motivo
    assert str(pausa.value) == teto_de_gasto.RECADO_PARA_A_EMPRESA
    assert "endereco-interno" not in str(pausa.value)


def test_falha_do_provedor_com_o_mock_de_reserva_cai_para_a_simulacao(monkeypatch):
    """Com o MOCK de reserva (só na máquina local), a falha do provedor cai para a simulação e registra o motivo."""
    cliente = LLMClient(modo="llm", mock_de_reserva=True)

    def provedor_fora_do_ar(*argumentos):
        """Simula o provedor sem responder."""
        raise ConnectionError("timeout")

    monkeypatch.setattr(cliente, "_chamar_provedor", provedor_fora_do_ar)
    resposta = cliente.gerar("interpretar_colunas", "prompt")
    assert resposta.modo == "mock"
    assert "falha no provedor" in resposta.motivo_fallback


def test_o_registro_do_servidor_diz_o_motivo_sem_o_detalhe_do_provedor(monkeypatch, caplog):
    """O registro do servidor guarda o que aconteceu: o limite da operação, ou só o TIPO do erro do provedor (a mensagem
    dele pode trazer endereços internos)."""
    caplog.set_level("WARNING", logger="services.llm_client")
    # O limite de chamadas da operação
    cliente = LLMClient(modo="llm", limite_chamadas=1, mock_de_reserva=False)
    cliente.chamadas_realizadas = 1
    with pytest.raises(IAIndisponivel):
        cliente.gerar("interpretar_colunas", "prompt")
    assert "limite de chamadas da operação atingido" in caplog.text

    def provedor_fora_do_ar(*argumentos):
        """Simula o provedor sem responder, com um endereço interno na mensagem."""
        raise ConnectionError("tempo esgotado em https://endereco-interno")

    # A falha do provedor: só o tipo do erro vai para o registro
    outro_cliente = LLMClient(modo="llm", mock_de_reserva=False)
    monkeypatch.setattr(outro_cliente, "_chamar_provedor", provedor_fora_do_ar)
    with pytest.raises(IAIndisponivel):
        outro_cliente.gerar("interpretar_colunas", "prompt")
    assert "falha no provedor (ConnectionError)" in caplog.text
    assert "endereco-interno" not in caplog.text


def test_sem_informar_o_cliente_segue_a_chave_do_env(monkeypatch):
    """Sem informar, o cliente segue a chave MOCK_DE_RESERVA do .env, lida na criação do cliente."""
    monkeypatch.setattr(config, "MOCK_DE_RESERVA", False)
    assert LLMClient(modo="llm").mock_de_reserva is False
    monkeypatch.setattr(config, "MOCK_DE_RESERVA", True)
    assert LLMClient(modo="llm").mock_de_reserva is True


def test_provedor_nao_escolhido_avisa_em_vez_de_esconder():
    """Sem modelo escolhido no .env, o modo "llm" avisa com erro (não finge que chamou)."""
    with pytest.raises(provedores_de_ia.ConfiguracaoDoProvedor):
        LLMClient(modo="llm").gerar("interpretar_colunas", "prompt")
