"""Spike de pausa e retomada (ADR-15, ADR-39).

"Spike" é um experimento pequeno para responder uma dúvida técnica arriscada antes de construir de
verdade. Aqui a dúvida era: o fluxo consegue PARAR esperando uma pessoa decidir e CONTINUAR depois,
mesmo que a página seja recarregada ou o servidor reinicie, sem refazer o que já foi feito?

O fluxo tem três passos:
    preparar  ->  aguardar_aprovacao (pausa)  ->  concluir

O estado do fluxo fica gravado num arquivo SQLite (o "checkpointer", um ponto de salvamento). É o mesmo
padrão que as Fases 7 e 8 usam para o aceite do mapeamento e a homologação.
"""
import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class EstadoSpike(TypedDict):
    """O que o fluxo guarda enquanto anda (e o que fica salvo nos pontos de parada)."""

    processamento_id: str   # o identificador do processamento
    passos: list[str]       # os passos que já rodaram, na ordem (para provar que nada se repete)
    decisao: str | None     # a resposta da pessoa ("aprovado" ou "rejeitado")


def preparar(estado: EstadoSpike) -> dict:
    """Primeiro passo: só anota que rodou."""
    return {"passos": estado["passos"] + ["preparar"]}


def aguardar_aprovacao(estado: EstadoSpike) -> dict:
    """Segundo passo: PAUSA o fluxo e espera a pessoa responder."""
    # interrupt() para o fluxo aqui e manda a pergunta para a tela.
    # Quando a pessoa responde, o LangGraph roda este passo de novo desde o começo, e desta vez o
    # interrupt() devolve a resposta. Por isso nada que mude dados pode vir ANTES do interrupt().
    decisao = interrupt({"pergunta": "Aprovar este processamento?"})
    # Guarda a decisão e anota que o passo rodou
    return {"decisao": decisao, "passos": estado["passos"] + ["aguardar_aprovacao"]}


def concluir(estado: EstadoSpike) -> dict:
    """Terceiro passo: só anota que rodou."""
    return {"passos": estado["passos"] + ["concluir"]}


def abrir_checkpointer(caminho: Path) -> SqliteSaver:
    """Abre o arquivo SQLite onde ficam os pontos de parada do fluxo."""
    # Cria a pasta, se ainda não existir
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: a API atende cada pedido numa "thread" (linha de execução) diferente
    return SqliteSaver(sqlite3.connect(caminho, check_same_thread=False))


def construir_grafo(checkpointer: SqliteSaver):
    """Monta o fluxo: os três passos e a ordem entre eles."""
    grafo = StateGraph(EstadoSpike)
    # Os passos ("nós" do grafo)
    grafo.add_node("preparar", preparar)
    grafo.add_node("aguardar_aprovacao", aguardar_aprovacao)
    grafo.add_node("concluir", concluir)
    # A ordem ("arestas"): início -> preparar -> aguardar -> concluir -> fim
    grafo.add_edge(START, "preparar")
    grafo.add_edge("preparar", "aguardar_aprovacao")
    grafo.add_edge("aguardar_aprovacao", "concluir")
    grafo.add_edge("concluir", END)
    # "Compila" o fluxo com o ponto de salvamento
    return grafo.compile(checkpointer=checkpointer)


def configuracao(processamento_id: str) -> dict:
    """Cada processamento tem a sua própria linha do tempo no ponto de salvamento (o "thread_id")."""
    return {"configurable": {"thread_id": processamento_id}}
