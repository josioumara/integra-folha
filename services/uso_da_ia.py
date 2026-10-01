"""Uso da IA de cada execução: quantas chamadas, quantos tokens e quanto custou (ADR-131).

Para que serve: a tabela execucoes_agentes (services/execucoes.py) tem as colunas de tokens e de custo, mas elas
ficavam vazias, porque quem grava a execução não via as chamadas feitas lá dentro do agente. Este arquivo junta as
duas pontas:
- o cliente de IA (services/llm_client.py) ANOTA cada resposta aqui;
- quem grava a execução ABRE uma medição antes do trabalho e, no fim, entrega o que ela somou ao registrar.

Analogia: é o taxímetro. Quem começa a corrida liga o taxímetro (medir()); cada chamada à IA soma no taxímetro que
estiver ligado; no fim da corrida, o valor vai para o recibo (a linha da execução).

Como a medição sabe de qual execução é a chamada: pela "variável de contexto" (contextvars) do Python. Cada pedido
feito à API roda no seu próprio contexto; por isso duas empresas usando a aplicação ao mesmo tempo nunca somam no
taxímetro uma da outra. Uma medição aberta dentro de outra é independente: a de fora não conta o que a de dentro
mediu (cada execução paga só as suas chamadas, e nada é somado duas vezes).

Quando o agente já tem a resposta na mão (uma chamada só, ou chamadas em outra linha de execução, como no Leitor),
ele usa Uso.da_resposta e soma direto, sem a medição.

Nada pessoal entra aqui: só números (chamadas, tokens, custo).
"""
import contextvars
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Uso:
    """O uso da IA somado numa execução.

    Tokens e custo ficam None ("não medido") até alguma chamada ser medida: o painel nunca mostra um zero inventado.
    Ex.: 2 chamadas reais → Uso(chamadas=2, tokens_entrada=3100, tokens_saida=420, custo_usd=0.0161).
    """

    chamadas: int = 0                   # quantas vezes a IA foi chamada (real ou simulada)
    tokens_entrada: int | None = None   # tamanho dos pedidos, somado; None = nenhuma chamada medida
    tokens_saida: int | None = None     # tamanho das respostas, somado
    custo_usd: float | None = None      # custo somado, em dólares
    # Por que a IA real não respondeu (a 1ª queda para o MOCK: teto, limite, provedor fora); None = não caiu
    motivo_da_queda: str | None = None
    # A trava deixa duas linhas de execução somarem no mesmo uso sem perder conta (ex.: a chamada com tempo limite)
    _trava: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def da_resposta(cls, resposta) -> "Uso":
        """O uso de uma resposta só do cliente de IA.

        Recebe: a resposta (RespostaLLM) ou None. Devolve: um Uso com essa chamada; sem resposta, um uso vazio.
        Ex.: uma resposta de 1000 tokens de entrada e US$ 0,01 → Uso(chamadas=1, tokens_entrada=1000, custo_usd=0.01).
        """
        # Começa vazio ("não medido")
        uso = cls()
        # Com resposta, soma a chamada dela
        if resposta is not None:
            uso.somar_resposta(resposta)
        return uso

    def somar_resposta(self, resposta) -> None:
        """Soma uma resposta do cliente de IA neste uso.

        Recebe: a resposta (RespostaLLM). Devolve: nada; conta a chamada e soma os tokens e o custo que foram medidos.
        """
        # A trava: duas linhas de execução somando ao mesmo tempo não perdem conta
        with self._trava:
            # Toda resposta é uma chamada, real ou simulada
            self.chamadas += 1
            # Resposta simulada COM motivo = a IA real deveria ter respondido e não respondeu (no MOCK puro, sem motivo)
            if resposta.motivo_fallback and self.motivo_da_queda is None:
                self.motivo_da_queda = resposta.motivo_fallback
            # Soma só o que foi medido (None = "não medido" não vira zero)
            self.tokens_entrada = _somar_medido(self.tokens_entrada, resposta.tokens_entrada)
            self.tokens_saida = _somar_medido(self.tokens_saida, resposta.tokens_saida)
            self.custo_usd = _somar_medido(self.custo_usd, resposta.custo_usd)

    def somar_uso(self, outro: "Uso") -> None:
        """Soma outro uso neste (ex.: os blocos de um documento numa execução só).

        Recebe: o outro Uso. Devolve: nada; este uso passa a ter as chamadas, os tokens e o custo dos dois.
        """
        # A trava: duas linhas de execução somando ao mesmo tempo não perdem conta
        with self._trava:
            # As chamadas somam sempre
            self.chamadas += outro.chamadas
            # Vale a primeira queda para o MOCK (a que explica o problema)
            if self.motivo_da_queda is None:
                self.motivo_da_queda = outro.motivo_da_queda
            # Soma só o que foi medido
            self.tokens_entrada = _somar_medido(self.tokens_entrada, outro.tokens_entrada)
            self.tokens_saida = _somar_medido(self.tokens_saida, outro.tokens_saida)
            self.custo_usd = _somar_medido(self.custo_usd, outro.custo_usd)

    def menos(self, outro: "Uso") -> "Uso":
        """Este uso sem a parte de outro (ex.: o total da leitura sem a parte do Conferidor).

        Recebe: o outro Uso (a parte a tirar). Devolve: um Uso novo com a diferença; este não muda.
        Onde o outro não foi medido, fica o valor deste; o resultado nunca fica negativo.
        Ex.: Uso(chamadas=5, custo_usd=0.05).menos(Uso(chamadas=2, custo_usd=0.002)) → Uso(chamadas=3, custo_usd=0.048).
        """
        # As chamadas, sem ficar negativas; o motivo da queda continua o deste uso
        resultado = Uso(chamadas=max(self.chamadas - outro.chamadas, 0), motivo_da_queda=self.motivo_da_queda)
        # Os tokens e o custo, tirando só o que o outro mediu
        resultado.tokens_entrada = _subtrair_medido(self.tokens_entrada, outro.tokens_entrada)
        resultado.tokens_saida = _subtrair_medido(self.tokens_saida, outro.tokens_saida)
        resultado.custo_usd = _subtrair_medido(self.custo_usd, outro.custo_usd)
        return resultado

    def em_dicionario(self) -> dict:
        """O uso como dicionário simples, para viajar dentro das medições (ex.: a do Leitor)."""
        return {"chamadas": self.chamadas, "tokens_entrada": self.tokens_entrada, "tokens_saida": self.tokens_saida,
                "custo_usd": self.custo_usd, "motivo_da_queda": self.motivo_da_queda}

    @classmethod
    def do_dicionario(cls, dados: dict | None) -> "Uso":
        """O caminho de volta de em_dicionario (sem dados, um uso vazio)."""
        if not dados:
            return cls()
        return cls(chamadas=dados.get("chamadas", 0), tokens_entrada=dados.get("tokens_entrada"),
                   tokens_saida=dados.get("tokens_saida"), custo_usd=dados.get("custo_usd"),
                   motivo_da_queda=dados.get("motivo_da_queda"))


def _somar_medido(atual, novo):
    """Soma dois valores em que None quer dizer "não medido". Ex.: (None, 5) → 5; (3, None) → 3; (None, None) → None."""
    if novo is None:
        return atual
    if atual is None:
        return novo
    return atual + novo


def _subtrair_medido(atual, parte):
    """Tira a parte do valor, sem ficar negativo. Ex.: (10, 4) → 6; (10, None) → 10; (None, 4) → None."""
    if atual is None or parte is None:
        return atual
    return max(atual - parte, 0)


# A medição aberta no contexto atual (None = nenhuma: a chamada não soma em execução nenhuma)
_MEDICAO_ABERTA: contextvars.ContextVar[Uso | None] = contextvars.ContextVar("medicao_do_uso_da_ia", default=None)


@contextmanager
def medir():
    """Abre uma medição: toda chamada à IA feita dentro do bloco soma no Uso devolvido.

    Uso:
        with uso_da_ia.medir() as uso:
            resposta = agente.trabalhar(...)
        execucoes.registrar(..., uso=uso)
    Ao sair do bloco (mesmo com erro), volta a valer a medição de fora, se havia.
    """
    uso = Uso()
    marca = _MEDICAO_ABERTA.set(uso)
    try:
        yield uso
    finally:
        # Devolve o contexto como estava antes (a medição de fora volta a valer)
        _MEDICAO_ABERTA.reset(marca)


def anotar(resposta) -> None:
    """Soma a resposta na medição aberta (chamado pelo cliente de IA a cada resposta). Sem medição aberta, nada."""
    uso = _MEDICAO_ABERTA.get()
    if uso is not None:
        uso.somar_resposta(resposta)
