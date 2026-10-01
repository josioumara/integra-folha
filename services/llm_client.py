"""Único ponto de contato com o provedor de IA (o "LLM") (ADR-36).

Todo agente do sistema fala com a IA por aqui. Isso traz três vantagens:
- trocar de provedor mexe só neste arquivo;
- o modo MOCK devolve respostas simuladas, então os testes e a demo funcionam sem chave e sem custo;
- o controle de custo fica num lugar só: o limite de chamadas e o teto de gasto do cliente, e os tetos do DIA e do
  MÊS, que valem para a aplicação inteira (services/teto_de_gasto.py; ADR-131).

A IA real que não pode responder PAUSA o trabalho, e nada é simulado no lugar (ADR-145):
- o teto do dia ou do mês foi atingido: gerar levanta TetoDeGastoAtingido (ADR-131);
- o provedor falhou (fora do ar, sem permissão, tempo esgotado), ou esta operação passou do limite de chamadas ou do
  teto de gasto do cliente: gerar levanta IAIndisponivel.
Quem chamou pausa e avisa a pessoa: o envio fica em "tentar de novo", e a tela recebe o aviso "indisponível agora".
A resposta nunca é trocada, em silêncio, por uma SIMULADA: a empresa receberia um mapeamento inventado sem saber.

A queda para a simulação continua só como MOCK DE RESERVA, ligado pela chave MOCK_DE_RESERVA=sim do .env, para a
máquina local (a demo sem rede e as medições, que recusam a resposta simulada). O servidor nunca recebe a chave.

Analogia: é o caixa eletrônico sem sistema. Ele mostra "indisponível, tente mais tarde" e guarda o cartão; nunca
entrega notas de brinquedo para a fila andar.

Cada resposta também é anotada na medição aberta da execução (services/uso_da_ia.py): é assim que os tokens e o custo
chegam à linha da execução na Telemetria.

A checagem de ataques do Bedrock Guardrails (ADR-147) também sai por aqui (checar_ataques): segue o modo, o teto do dia
e do mês e a medição, como as chamadas à IA. A diferença é a falha: o tempo estourado e o erro do detector não pausam
nada, e a mensagem segue só com a lista de frases.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from services import config, provedores_de_ia, teto_de_gasto, uso_da_ia

# O registro do servidor (log): o motivo técnico da falha fica aqui, e nunca vai para a tela
registro = logging.getLogger(__name__)

# O recado para o especialista do banco (as rotas /api/banco/...) quando a IA real não responde (ADR-145). A empresa
# recebe o recado da pausa pelo teto (teto_de_gasto.RECADO_PARA_A_EMPRESA), porque para ela o efeito é o mesmo: o
# trabalho fica guardado e volta pelo "Tentar de novo"
RECADO_DA_FALHA_PARA_O_BANCO = ("O agente não respondeu agora (falha no provedor do modelo), e nada foi simulado no "
                                "lugar. Tente de novo em alguns minutos; o erro fica registrado na Telemetria.")


class IAIndisponivel(Exception):
    """A IA real não respondeu, e o trabalho pausa (ADR-145): nada é simulado no lugar.

    Acontece quando o provedor falha, ou quando a operação passa do limite de chamadas ou do teto de gasto do cliente.
    A mensagem é o recado para a empresa, o mesmo da pausa pelo teto. O motivo técnico fica em "motivo" (para os testes
    e para quem tratar o erro) e nunca vai para a tela. O registro do servidor guarda o que aconteceu: o limite, o teto
    ou só o TIPO do erro do provedor (a mensagem dele pode trazer endereços internos).
    Ex.: IAIndisponivel("limite de chamadas da operação atingido").motivo → "limite de chamadas da operação atingido";
    str(...) → o recado "A análise automática está indisponível agora...".
    """

    # As execuções medidas até a falha, quando um agente as anota (o Leitor de Documentos anota as dele, para quem cria
    # o envio gravar). Uma tupla vazia como padrão (e não uma lista), para nenhum erro dividir a mesma lista com outro
    execucoes_dos_agentes = ()

    def __init__(self, motivo: str):
        """Recebe o motivo técnico da falha (ex.: "limite de chamadas da operação atingido")."""
        # A mensagem da exceção é o recado simples, que pode ir direto para a tela
        super().__init__(teto_de_gasto.RECADO_PARA_A_EMPRESA)
        # O motivo técnico fica guardado para os testes e para quem tratar o erro (nunca para a tela)
        self.motivo = motivo


@dataclass
class RespostaLLM:
    """A resposta da IA, sempre no mesmo formato, venha do MOCK ou do provedor real."""

    texto: str                            # o texto que a IA respondeu
    modo: str                             # "mock" ou "llm"
    modelo: str                           # qual modelo respondeu ("mock" no modo simulado)
    tokens_entrada: int | None = None     # tamanho do pedido; None = "não medido" (o painel nunca inventa número)
    tokens_saida: int | None = None       # tamanho da resposta; None = "não medido"
    custo_usd: float | None = None        # quanto a chamada custou, quando o provedor informa; None = "não medido"
    motivo_fallback: str | None = None    # por que caiu para o MOCK de reserva (só na máquina local; ADR-145)
    cortada: bool = False                 # True: a resposta parou no limite de tokens (está incompleta)


# Os resultados de uma checagem do detector de ataques do Bedrock Guardrails (ADR-147)
CHECAGEM_NAO_FEITA = "nao_checada"   # no MOCK: nada sai da máquina, e vale só a lista de frases
CHECAGEM_NORMAL = "normal"           # as 3 notas ficaram abaixo do limiar
CHECAGEM_SUSPEITA = "suspeito"       # alguma nota chegou ao limiar: a mensagem é recusada
CHECAGEM_ESTOUROU = "estourou"       # passou do tempo máximo: a mensagem segue só com a lista
CHECAGEM_COM_ERRO = "erro"           # o detector falhou (403, 429, 5xx, a configuração): segue só com a lista
# O tipo do erro que a Telemetria mostra quando a checagem passa do tempo máximo
TIPO_DO_TEMPO_ESTOURADO = "TempoEstourado"


@dataclass
class ChecagemDeAtaque:
    """O resultado de uma checagem do detector de ataques (ADR-147), sem o texto checado.

    Ex.: ChecagemDeAtaque("suspeito", inicio, fim, maior_nota=0.8, categoria="PROMPT_INJECTION", unidades=1,
    custo_usd=0.00008).
    """

    resultado: str                    # CHECAGEM_NAO_FEITA, _NORMAL, _SUSPEITA, _ESTOUROU ou _COM_ERRO
    inicio: datetime                  # quando a checagem começou (horário universal)
    fim: datetime                     # quando terminou (no "estourou", quando a espera desistiu)
    maior_nota: float | None = None   # a maior nota entre as 3 categorias; None sem resposta
    categoria: str | None = None      # a categoria da maior nota
    unidades: int | None = None       # as unidades de texto cobradas; None sem resposta ("não medido")
    custo_usd: float | None = None    # o custo; None sem resposta ("não medido", nunca um zero inventado)
    tipo_erro: str | None = None      # no "estourou" e no "erro": o tipo (ex.: "HTTP403"), nunca a mensagem


class LLMClient:
    """Cliente da IA, com modo MOCK e limite de chamadas por operação.

    Cada operação (um envio, uma conversa, uma leitura) cria o seu cliente: o contador de chamadas é dela.
    """

    def __init__(self, modo: str | None = None, limite_chamadas: int | None = None,
                 respostas_mock: dict | None = None, teto_de_gasto_usd: float | None = None,
                 mock_de_reserva: bool | None = None):
        """modo: "mock" ou "llm" (sem informar, usa o do .env).
        limite_chamadas: quantas chamadas reais a operação pode fazer; passou disso, a IA pausa.
        respostas_mock: por tarefa, um texto fixo ou uma função que recebe o pedido e simula a IA.
        teto_de_gasto_usd: quanto a operação pode gastar (em dólares); atingido, a IA pausa.
        mock_de_reserva: True faz a IA que não responde cair para a simulação, como antes (só na máquina local);
            sem informar, vale a chave MOCK_DE_RESERVA do .env (padrão: desligada, e a IA pausa).
        """
        # Modo em minúsculas; sem informar, vem do arquivo .env
        self.modo = (modo or config.MODO).lower()
        # Só dois modos existem
        if self.modo not in ("mock", "llm"):
            raise ValueError(f"MODE inválido: {self.modo!r}. Use 'mock' ou 'llm'.")
        # Limite de chamadas; sem informar, vem do .env
        self.limite_chamadas = limite_chamadas or config.LIMITE_CHAMADAS_LLM_POR_SESSAO
        # Quantas chamadas reais esta operação já fez
        self.chamadas_realizadas = 0
        # Teto de gasto da operação (sem informar, vem do .env) e quanto já foi gasto nas chamadas medidas
        self.teto_de_gasto_usd = teto_de_gasto_usd if teto_de_gasto_usd is not None else config.TETO_DE_GASTO_USD
        self.gasto_usd = 0.0
        # Respostas simuladas por tarefa (ex.: "interpretar_colunas" -> função que simula o Interpretador)
        self.respostas_mock = respostas_mock or {}
        # O MOCK de reserva: ligado só quando pedido aqui ou pela chave do .env (ADR-145)
        if mock_de_reserva is None:
            self.mock_de_reserva = config.MOCK_DE_RESERVA
        else:
            self.mock_de_reserva = mock_de_reserva

    def gerar(self, tarefa: str, prompt: str, sistema: str = "", modelo: str | None = None,
              temperatura: float = 0.0, esforco: str | None = None, esquema_json: dict | None = None) -> RespostaLLM:
        """Pede uma resposta à IA.

        tarefa: o nome da tarefa do agente; no MOCK, escolhe a resposta simulada.
        prompt: o pedido.
        sistema: o papel e as regras do agente.
        modelo: "grande" ou "pequeno" (ou o nome do modelo), para o experimento B0–B5.
        temperatura: baixa (0) por padrão, para a IA responder sempre do mesmo jeito (ADR-07).
        esforco: o quanto a IA "pensa" antes de responder ("low", "medium", "high"); sem informar, o padrão do modelo.
        esquema_json: o formato que a resposta precisa seguir (saída estruturada); sem informar, texto livre.
        Levanta TetoDeGastoAtingido (o teto do dia ou do mês) ou IAIndisponivel (a IA real não respondeu): nos dois
        casos, quem chamou pausa o trabalho (ADR-131 e ADR-145).
        Toda resposta (real ou simulada) é anotada na medição aberta da execução, se houver (services/uso_da_ia.py).
        """
        resposta = self._gerar(tarefa, prompt, sistema, modelo, temperatura, esforco, esquema_json)
        # O taxímetro da execução: soma a chamada, os tokens e o custo na medição aberta
        uso_da_ia.anotar(resposta)
        return resposta

    def _gerar(self, tarefa: str, prompt: str, sistema: str, modelo: str | None, temperatura: float,
               esforco: str | None, esquema_json: dict | None) -> RespostaLLM:
        """A resposta, com as proteções de custo (ver gerar)."""
        # Modo MOCK: responde com a simulação, sem chamar ninguém
        if self.modo == "mock":
            return self._resposta_mock(tarefa, prompt)

        # Proteção de custo: passado o limite de chamadas desta operação, a IA pausa (ou cai para a reserva)
        if self.chamadas_realizadas >= self.limite_chamadas:
            motivo = "limite de chamadas da operação atingido"
            return self._sem_a_ia_real(tarefa, prompt, motivo, motivo)
        # Proteção de gasto: atingido o teto em dólares desta operação, também pausa (ou cai para a reserva)
        if self.gasto_usd >= self.teto_de_gasto_usd:
            motivo = "teto de gasto da operação atingido"
            return self._sem_a_ia_real(tarefa, prompt, motivo, motivo)
        # Proteção da aplicação: a soma de TODAS as chamadas reais chegou ao teto do dia ou do mês (vale para todos os
        # pedidos). A IA PAUSA: nada de resposta simulada no lugar da real (ADR-131)
        periodo_atingido = teto_de_gasto.teto_atingido()
        if periodo_atingido is not None:
            raise teto_de_gasto.TetoDeGastoAtingido(periodo_atingido)

        # Conta a chamada real
        self.chamadas_realizadas += 1
        try:
            # Chama o provedor de verdade
            resposta = self._chamar_provedor(tarefa, prompt, sistema, modelo, temperatura, esforco, esquema_json)
        except provedores_de_ia.ConfiguracaoDoProvedor:
            # Erro de configuração (falta a chave ou o modelo no .env): avisa, não esconde atrás de nada
            raise
        except Exception as erro:
            # Qualquer falha do provedor: a IA pausa (ou cai para a reserva). O registro do servidor guarda só o TIPO
            # do erro, porque a mensagem do provedor pode trazer endereços internos; ela fica só no motivo, que nunca
            # vai para a tela
            motivo_no_registro = f"falha no provedor ({type(erro).__name__})"
            return self._sem_a_ia_real(tarefa, prompt, f"falha no provedor: {erro}", motivo_no_registro)
        # Soma o custo, quando o provedor informa (sem medição, nada é somado nem inventado)
        if resposta.custo_usd is not None:
            self.gasto_usd += resposta.custo_usd
        # Soma no gasto do dia (a conta dos tetos do dia e do mês; sem custo medido, o log avisa)
        teto_de_gasto.anotar_custo(resposta.custo_usd, resposta.modelo)
        return resposta

    def _sem_a_ia_real(self, tarefa: str, prompt: str, motivo: str, motivo_no_registro: str) -> RespostaLLM:
        """A IA real não pode responder: pausa (levanta IAIndisponivel) ou, com o MOCK de reserva, simula (ADR-145).

        Recebe: a tarefa e o pedido (para a simulação da reserva); o motivo técnico (ex.: "limite de chamadas da
        operação atingido"); e o que vai para o registro do servidor, sem dado nenhum (na falha do provedor, só o tipo
        do erro). Devolve: a resposta simulada, só com a reserva ligada; sem ela, levanta IAIndisponivel.
        """
        # Com a reserva ligada (só na máquina local), a demo continua com a simulação, e o motivo vai junto
        if self.mock_de_reserva:
            registro.warning("A IA real não respondeu (%s): vale o MOCK de reserva desta máquina.", motivo_no_registro)
            return self._resposta_mock(tarefa, prompt, motivo=motivo)
        # O registro do servidor: o que aconteceu (o limite, o teto ou o tipo do erro do provedor)
        registro.warning("A IA real não respondeu (%s): a operação pausa, sem resposta simulada.", motivo_no_registro)
        # Sem a reserva (o padrão, e sempre no servidor): a IA pausa, e quem chamou avisa a pessoa
        raise IAIndisponivel(motivo)

    def _resposta_mock(self, tarefa: str, prompt: str = "", motivo: str | None = None) -> RespostaLLM:
        """A resposta simulada da tarefa: um texto fixo ou o resultado da função simuladora."""
        # Procura a simulação da tarefa; sem simulação, usa um texto padrão que deixa claro que é MOCK
        simulacao = self.respostas_mock.get(tarefa, f"[MOCK] resposta simulada para a tarefa '{tarefa}'")
        # Se a simulação é uma função, ela recebe o pedido e monta a resposta (o fluxo roda igual ao real)
        if callable(simulacao):
            texto = simulacao(prompt)
        else:
            texto = simulacao
        return RespostaLLM(texto=texto, modo="mock", modelo="mock", motivo_fallback=motivo)

    def _chamar_provedor(self, tarefa: str, prompt: str, sistema: str, modelo: str | None,
                         temperatura: float, esforco: str | None = None,
                         esquema_json: dict | None = None) -> RespostaLLM:
        """Chamada ao provedor real (OpenAI ou Anthropic, direto ou pelo Bedrock), com tokens e custo medidos."""
        nome_do_modelo = modelo_escolhido(modelo)
        resposta = provedores_de_ia.chamar(nome_do_modelo, sistema, prompt, temperatura, esforco, esquema_json)
        custo = provedores_de_ia.custo_em_dolares(nome_do_modelo, resposta.tokens_entrada, resposta.tokens_saida)
        return RespostaLLM(texto=resposta.texto, modo="llm", modelo=nome_do_modelo,
                           tokens_entrada=resposta.tokens_entrada, tokens_saida=resposta.tokens_saida, custo_usd=custo,
                           cortada=resposta.cortada)

    def checar_ataques(self, texto: str, limiar: float, tempo_maximo_s: float) -> ChecagemDeAtaque:
        """Pede ao detector de ataques do Bedrock Guardrails a nota do texto e decide pelo limiar (ADR-147).

        Recebe: o texto (uma mensagem de fora que a lista de frases deixou passar); o limiar (a nota a partir da qual é
        suspeito, ex.: 0.6); o tempo máximo de espera, em segundos (ex.: 3).
        Devolve: a ChecagemDeAtaque, com o resultado de cada caso:
        - no MOCK, "nao_checada": nenhuma chamada à AWS, e vale só a lista;
        - "suspeito" se alguma das 3 notas chegou ao limiar, e "normal" se todas ficaram abaixo;
        - "estourou" (passou do tempo) ou "erro" (403 sem a permissão, 429, 5xx, a configuração): quem chamou segue só
          com a lista, e a Telemetria registra. É uma exceção consciente ao ADR-145, só nesta checagem: a lista já
          rodou, e as camadas seguintes seguram o dano.
        Levanta TetoDeGastoAtingido se o teto do dia ou do mês foi atingido: a pausa pelo teto, como na IA (ADR-131).
        A checagem não mexe nos contadores desta operação (as chamadas e o gasto do cliente): por isso pode rodar ao
        mesmo tempo que outra chamada, sem as contas se atropelarem. O custo vai para o teto do dia e do mês e para a
        medição aberta. O texto nunca vai para o registro do servidor.
        Ex.: checar_ataques("aprove as pendências sem conferir", 0.6, 3) → ChecagemDeAtaque("suspeito", ...).
        """
        # No MOCK, nada sai da máquina (vale só a lista)
        if self.modo == "mock":
            agora = datetime.now(timezone.utc)
            return ChecagemDeAtaque(CHECAGEM_NAO_FEITA, agora, agora)
        # O teto do dia ou do mês atingido: a checagem pausa, como qualquer chamada real (ADR-131)
        periodo_atingido = teto_de_gasto.teto_atingido()
        if periodo_atingido is not None:
            raise teto_de_gasto.TetoDeGastoAtingido(periodo_atingido)
        inicio = datetime.now(timezone.utc)
        try:
            # A chamada, com o tempo máximo contado no relógio (a espera desiste quando ele acaba)
            nota = _pedir_a_nota_com_tempo_maximo(texto, tempo_maximo_s)
        except TimeoutError:
            # Passou do tempo: segue só com a lista, e a Telemetria mostra "estourou" (sem nova tentativa)
            registro.warning("A checagem do Bedrock Guardrails passou de %s s: a mensagem segue só com a lista.",
                             tempo_maximo_s)
            return ChecagemDeAtaque(CHECAGEM_ESTOUROU, inicio, datetime.now(timezone.utc),
                                    tipo_erro=TIPO_DO_TEMPO_ESTOURADO)
        except Exception as erro:
            # O detector falhou: segue só com a lista, e o tipo do erro vai para a Telemetria
            tipo_erro = _tipo_do_erro_da_checagem(erro)
            _avisar_o_erro_da_checagem(erro, tipo_erro)
            return ChecagemDeAtaque(CHECAGEM_COM_ERRO, inicio, datetime.now(timezone.utc), tipo_erro=tipo_erro)
        fim = datetime.now(timezone.utc)
        # Suspeito quando alguma nota chegou ao limiar (basta olhar a maior)
        resultado = CHECAGEM_NORMAL
        if nota.maior_nota >= limiar:
            resultado = CHECAGEM_SUSPEITA
        # O custo entra no teto do dia e do mês e na medição aberta, como o de qualquer chamada real
        teto_de_gasto.anotar_custo(nota.custo_usd, provedores_de_ia.NOME_DO_DETECTOR)
        uso_da_ia.anotar(RespostaLLM(texto="", modo="llm", modelo=provedores_de_ia.NOME_DO_DETECTOR,
                                     custo_usd=nota.custo_usd))
        # O registro do servidor: o resultado, o tempo, a nota, as unidades e o custo (nunca o texto)
        milissegundos = round((fim - inicio).total_seconds() * 1000)
        registro.info("Checagem do Bedrock Guardrails: %s em %d ms (maior nota %.1f, %d unidade(s), US$ %.5f).",
                      resultado, milissegundos, nota.maior_nota, nota.unidades, nota.custo_usd)
        return ChecagemDeAtaque(resultado, inicio, fim, maior_nota=nota.maior_nota, categoria=nota.categoria,
                                unidades=nota.unidades, custo_usd=nota.custo_usd)


def modelo_escolhido(modelo: str | None) -> str:
    """O nome real do modelo: "grande" e "pequeno" (ou nada) viram os modelos escolhidos no .env.

    Ex.: "pequeno" → o valor de MODELO_PEQUENO; "gpt-6-sol" continua "gpt-6-sol" (a comparação pede o modelo pelo nome).
    """
    if modelo == "pequeno":
        escolhido = config.MODELO_PEQUENO
        variavel = "MODELO_PEQUENO"
    elif modelo in (None, "", "grande"):
        escolhido = config.MODELO_GRANDE
        variavel = "MODELO_GRANDE"
    else:
        return modelo
    # Ainda não escolhido: a escolha sai da comparação de modelos (ADR-11)
    if not escolhido:
        raise provedores_de_ia.ConfiguracaoDoProvedor(f"Falta escolher o modelo: coloque {variavel} no arquivo .env.")
    return escolhido


# ---------------- A checagem de ataques do Bedrock Guardrails (ADR-147) ----------------

def _pedir_a_nota_com_tempo_maximo(texto: str, tempo_maximo_s: float) -> provedores_de_ia.NotaDoDetector:
    """A chamada ao detector numa linha de execução à parte, para a espera poder desistir no tempo máximo.

    Por quê: o tempo da conexão vale para cada etapa dela (conectar, mandar, receber), e as etapas somadas poderiam
    passar do máximo. Aqui, a espera conta no relógio. Quando ela desiste, a chamada termina sozinha depois, e ninguém
    espera por ela.
    Levanta TimeoutError (a espera desistiu, ou a conexão estourou) ou o erro do detector (ver
    provedores_de_ia.checar_ataques).
    """
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        tarefa = executor.submit(provedores_de_ia.checar_ataques, texto, tempo_maximo_s)
        # Desde o Python 3.11, a espera que desiste levanta o mesmo TimeoutError da conexão que estoura
        return tarefa.result(timeout=tempo_maximo_s)
    finally:
        # Não espera a linha de execução terminar: no "estourou", ela acaba sozinha
        executor.shutdown(wait=False)


def _tipo_do_erro_da_checagem(erro: Exception) -> str:
    """O tipo do erro da checagem, para a Telemetria (nunca a mensagem, que pode trazer endereços internos).

    Ex.: RecusaDoDetector(403) → "HTTP403"; RecusaDoDetector(429) → "HTTP429"; um ConnectError → "ConnectError".
    """
    # A recusa do detector leva o código HTTP, que diz o que aconteceu (403 = a permissão falta)
    if isinstance(erro, provedores_de_ia.RecusaDoDetector):
        return f"HTTP{erro.codigo}"
    return type(erro).__name__


def _avisar_o_erro_da_checagem(erro: Exception, tipo_erro: str) -> None:
    """O aviso no registro do servidor quando o detector falha, sem o texto e sem a mensagem do provedor."""
    # O 403: o aviso diz qual permissão falta, para quem cuida da AWS
    if isinstance(erro, provedores_de_ia.RecusaDoDetector) and erro.codigo == 403:
        registro.warning("O Bedrock Guardrails recusou a checagem (HTTP403): falta a permissão "
                         "bedrock:InvokeGuardrailChecks na chave. A mensagem segue só com a lista.")
    # A configuração que falta (a rota ou a chave): a mensagem é nossa e diz o que acertar no .env
    elif isinstance(erro, provedores_de_ia.ConfiguracaoDoProvedor):
        registro.warning("A checagem do Bedrock Guardrails não foi feita (%s) A mensagem segue só com a lista.", erro)
    # Qualquer outra falha: só o tipo (a mensagem do provedor pode trazer endereços internos)
    else:
        registro.warning("A checagem do Bedrock Guardrails falhou (%s): a mensagem segue só com a lista.", tipo_erro)
