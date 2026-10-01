"""Spike: o fluxo pausa, sobrevive a um "reinício" e retoma sem refazer nada (ADR-15, ADR-39)."""
from langgraph.types import Command

from workflows.spike_grafo import abrir_checkpointer, configuracao, construir_grafo


def test_pausa_e_retoma_depois_de_reabrir_o_banco(tmp_path):
    """O fluxo para na aprovação, o "servidor reinicia" e, com a aprovação, termina sem repetir passos."""
    banco = tmp_path / "checkpoints.db"
    config = configuracao("proc-001")

    # 1ª "sessão": o fluxo roda até a pausa
    checkpointer_1 = abrir_checkpointer(banco)
    grafo_1 = construir_grafo(checkpointer_1)
    grafo_1.invoke({"processamento_id": "proc-001", "passos": [], "decisao": None}, config)
    estado = grafo_1.get_state(config)
    assert estado.next == ("aguardar_aprovacao",)
    assert estado.values["passos"] == ["preparar"]
    # Simula a página recarregada / o servidor reiniciado
    checkpointer_1.conn.close()

    # 2ª "sessão": conexão nova, mesmo arquivo; a pessoa aprova
    grafo_2 = construir_grafo(abrir_checkpointer(banco))
    # Continua pausado
    assert grafo_2.get_state(config).next == ("aguardar_aprovacao",)
    grafo_2.invoke(Command(resume="aprovado"), config)

    final = grafo_2.get_state(config)
    # Terminou
    assert final.next == ()
    assert final.values["decisao"] == "aprovado"
    # "preparar" rodou uma vez só: a retomada não refez o que já estava feito
    assert final.values["passos"] == ["preparar", "aguardar_aprovacao", "concluir"]


def test_processamentos_diferentes_nao_se_misturam(tmp_path):
    """Cada processamento tem a sua pausa: decidir um não mexe no outro."""
    grafo = construir_grafo(abrir_checkpointer(tmp_path / "checkpoints.db"))
    for processamento_id in ("proc-A", "proc-B"):
        grafo.invoke({"processamento_id": processamento_id, "passos": [], "decisao": None},
                     configuracao(processamento_id))
    grafo.invoke(Command(resume="rejeitado"), configuracao("proc-A"))

    assert grafo.get_state(configuracao("proc-A")).values["decisao"] == "rejeitado"
    assert grafo.get_state(configuracao("proc-B")).next == ("aguardar_aprovacao",)


def test_a_tela_encontra_a_pergunta_da_pausa(tmp_path):
    """A tela do spike lê a pergunta por este caminho; o teste garante que ele existe."""
    grafo = construir_grafo(abrir_checkpointer(tmp_path / "checkpoints.db"))
    config = configuracao("proc-001")
    grafo.invoke({"processamento_id": "proc-001", "passos": [], "decisao": None}, config)
    estado = grafo.get_state(config)
    assert estado.tasks[0].interrupts[0].value["pergunta"] == "Aprovar este processamento?"
