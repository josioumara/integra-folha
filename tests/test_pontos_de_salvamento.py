"""Pontos de salvamento dos envios: guardados para sempre (ADR-71 revisto).

O que estes testes provam:
- depois de o banco aprovar, o ponto de salvamento do envio continua guardado (nada o apaga);
- se o ponto se perder mesmo assim (ex.: um banco restaurado sem ele), o envio continua "concluído" nas telas e o
  fluxo NUNCA recomeça do zero;
- envio encerrado pela empresa (descartado) mostra o motivo, lido da auditoria, mesmo sem o ponto.
"""
from models.contratos import EstadoProcessamento
from services import avaliacao_do_banco, cadastro, processamentos
from tests.test_avaliacao_do_banco import ESPECIALISTA, enviar_a_aurora_ao_banco
from tests.test_fluxo_empresa import conexao, gerar_envios, iniciar, receber, verdade  # noqa: F401
from workflows import fluxo_empresa as fluxo


def ponto_existe(conexao, processamento_id: str) -> bool:
    """True se o envio ainda tem ponto de salvamento no LangGraph."""
    checkpointer = fluxo.abrir_checkpointer(conexao)
    return checkpointer.get_tuple({"configurable": {"thread_id": processamento_id}}) is not None


def perder_o_ponto(conexao, processamento_id: str) -> None:
    """Simula um ponto de salvamento perdido (ex.: banco restaurado sem ele): apaga a "thread" do LangGraph."""
    fluxo.abrir_checkpointer(conexao).delete_thread(processamento_id)


def homologar_a_aurora(conexao, verdade) -> str:
    """A Aurora envia e o banco aprova. Devolve o processamento_id."""
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, True)
    return processamento_id


def test_ponto_de_salvamento_fica_guardado_depois_do_fim(conexao, verdade):
    """Guardado para sempre: mostra exatamente onde cada envio parou, mesmo meses depois."""
    processamento_id = homologar_a_aurora(conexao, verdade)
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.HOMOLOGADO
    assert ponto_existe(conexao, processamento_id)


def test_ponto_perdido_o_envio_continua_concluido_e_nao_recomeca(conexao, verdade):
    processamento_id = homologar_a_aurora(conexao, verdade)
    perder_o_ponto(conexao, processamento_id)
    situacao = fluxo.situacao(conexao, processamento_id)
    assert situacao["iniciado"] and situacao["terminou"] and situacao["etapa_atual"] is None
    assert situacao["estado"]["status"] == "HOMOLOGADO" and situacao["estado"]["ponto_de_salvamento_apagado"]
    # Pedir para iniciar de novo não recomeça: nenhum ponto novo, a situação continua HOMOLOGADO
    fluxo.iniciar(conexao, processamento_id, "EMP001")
    assert not ponto_existe(conexao, processamento_id)
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.HOMOLOGADO
    # A leitura do envio (novo front) mostra "Concluído"
    assert cadastro.leitura_do_envio(conexao, "EMP001", processamento_id)["nome_da_etapa"] == "Concluído"


def test_envio_descartado_mostra_o_motivo_mesmo_sem_o_ponto(conexao):
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    cadastro.descartar(conexao, empresa_id, processamento_id, "rh")
    motivo_antes = fluxo.situacao(conexao, processamento_id)["estado"]["motivo_da_rejeicao"]
    assert motivo_antes  # o descarte grava um código de motivo
    perder_o_ponto(conexao, processamento_id)
    situacao = fluxo.situacao(conexao, processamento_id)
    assert situacao["terminou"] and situacao["estado"]["status"] == "REJEITADO"
    assert situacao["estado"]["motivo_da_rejeicao"] == motivo_antes
