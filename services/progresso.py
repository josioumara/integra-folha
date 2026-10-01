"""O progresso de um envio enquanto ele é lido: uma frase curta que a tela mostra ao vivo (ADR-95).

Para que serve: com a IA real, ler um Word em texto corrido leva dezenas de segundos. Em vez de só um cronômetro, a
tela mostra o que está acontecendo ("A IA está lendo 12 trecho(s) do texto", "A IA leu 5 de 12 trecho(s)"...).
Como funciona:
    1. a tela sorteia um código do pedido e o manda junto com o arquivo;
    2. enquanto o servidor lê, quem está trabalhando chama progresso.anotar("frase") — sem precisar receber nada;
    3. a tela pergunta, a cada segundo, a frase do pedido dela (GET .../progresso/{código}).

Como o código chega a quem anota sem mudar a assinatura de cada função: uma "variável de contexto" do Python
(contextvars). Ela é como um bilhete preso à tarefa em andamento: comecar() prende o bilhete, anotar() lê o bilhete e
escreve a frase, terminar() tira o bilhete. Fora de um pedido com código (testes, scripts), anotar() não faz nada.

As frases ficam só na memória do servidor, sem dado de ninguém (nunca um nome ou um CPF), e só quem enviou lê as
dele. Um servidor reiniciado esquece tudo, e a tela volta a mostrar só o cronômetro.
"""
import re
import threading
from contextvars import ContextVar

# O código do pedido da tarefa em andamento (o "bilhete"); None fora de um envio com código
_PEDIDO_ATUAL: ContextVar[str | None] = ContextVar("pedido_atual", default=None)
# As frases de cada pedido: {código: {"texto": frase, "dono": login}}
_FRASES: dict[str, dict] = {}
# A trava: duas leituras ao mesmo tempo não escrevem no dicionário juntas
_TRAVA = threading.Lock()
# Quantos pedidos ficam guardados no máximo (os mais antigos saem)
MAXIMO_DE_PEDIDOS_GUARDADOS = 200
# O formato do código que a tela manda: letras, números e traços (ex.: um UUID)
FORMATO_DO_CODIGO = re.compile(r"[A-Za-z0-9-]{8,64}")


def codigo_valido(codigo: str | None) -> bool:
    """True se o código do pedido tem o formato esperado (evita guardar qualquer texto que chegue)."""
    return bool(codigo) and FORMATO_DO_CODIGO.fullmatch(codigo) is not None


def comecar(codigo: str, dono: str):
    """Prende o código do pedido à tarefa em andamento e anota a primeira frase. Devolve o "bilhete" (para terminar).

    Recebe: o código (vindo da tela) e o login de quem enviou.
    """
    with _TRAVA:
        # Guarda no máximo MAXIMO_DE_PEDIDOS_GUARDADOS: sai o mais antigo
        if len(_FRASES) >= MAXIMO_DE_PEDIDOS_GUARDADOS:
            _FRASES.pop(next(iter(_FRASES)))
        _FRASES[codigo] = {"texto": "Recebi o arquivo.", "dono": dono}
    return _PEDIDO_ATUAL.set(codigo)


def anotar(texto: str) -> None:
    """Escreve a frase do momento no pedido em andamento. Fora de um pedido com código, não faz nada.

    Exemplo: progresso.anotar("A IA leu 5 de 12 trecho(s).").
    """
    codigo = _PEDIDO_ATUAL.get()
    if codigo is None:
        return
    with _TRAVA:
        if codigo in _FRASES:
            _FRASES[codigo]["texto"] = texto


def terminar(bilhete) -> None:
    """Tira o código do pedido da tarefa (a frase continua guardada até a tela ler a última)."""
    _PEDIDO_ATUAL.reset(bilhete)


def frase_do_pedido(codigo: str, dono: str) -> str | None:
    """A frase do momento de um pedido, só para quem enviou. Devolve None se o pedido não existe ou é de outro."""
    with _TRAVA:
        registro = _FRASES.get(codigo)
        if registro is None or registro["dono"] != dono:
            return None
        return registro["texto"]
