"""Conversa com os provedores de IA de verdade: OpenAI e Anthropic, direto ou pelo AWS Bedrock (ADR-11, 65 e 96).

Duas rotas (ROTA_DA_IA no .env):
- "bedrock": a chamada vai para a nossa conta na AWS, no perfil geográfico EUA. Os
  modelos são os mesmos, mas rodam em contas operadas pela AWS: o fornecedor (Anthropic, OpenAI) não vê o pedido;
- "direta": as APIs da Anthropic e da OpenAI, como era antes.
Nas duas rotas, os modelos que guardam os pedidos por até 30 dias ficam proibidos (MODELOS_QUE_GUARDAM_PEDIDOS).

No Bedrock há dois jeitos de chamar (ADR-106): o endereço que imita a API do fornecedor (o mesmo código da rota
direta, só trocando o endereço) e a API geral do Bedrock, o "Converse", que atende qualquer modelo do catálogo.
O Converse é usado para os modelos que o primeiro jeito não atende (MODELOS_SO_PELO_CONVERSE): o Claude Sonnet 4.6
e o Amazon Nova, o plano B caso o Sonnet 5 e o GPT-6 Luna continuem fora da conta.

O resto do sistema nunca chama um provedor direto: passa pelo cliente de IA (services/llm_client.py), que usa
este arquivo quando o modo é "llm". Aqui ficam só quatro coisas:
1. descobrir de qual provedor é um modelo, pelo nome (ex.: "claude-sonnet-5" é da Anthropic);
2. fazer a chamada do jeito que cada provedor pede e devolver sempre no mesmo formato: o texto e quantos
   tokens entraram e saíram (token é o "pedaço de palavra" pelo qual o provedor cobra);
3. calcular o custo em dólares com a tabela de preços do projeto (data/avaliacao/modelos_candidatos.json);
4. pedir ao detector de ataques do Bedrock Guardrails a nota de uma mensagem (ADR-147). Ele não é um modelo que
   responde texto: só dá uma nota de 0 a 1 para cada tipo de ataque, e quem decide pelo limiar é o nosso código.

Diferenças entre os provedores que este arquivo esconde do resto do sistema:
- OpenAI: o papel do agente vai em "instructions"; aceita "temperature" (0 = responder sempre igual), mas se um
  modelo recusar, a chamada é refeita sem ela e isso fica anotado;
- Anthropic: o papel vai em "system"; a versão atual da API não tem "temperature". Aceita dois controles (ADR-72):
  o ESFORÇO ("effort": low, medium, high), que diz o quanto o modelo "pensa" antes de responder, e o FORMATO GARANTIDO
  ("saída estruturada"): um esquema JSON que a resposta obrigatoriamente segue. Na OpenAI, os dois são ignorados
  por enquanto (o pedido continua pedindo JSON no texto).
Nos dois, o raciocínio que o modelo faz antes de responder é cobrado como saída. Se raciocínio + resposta passam do
limite de tokens, a resposta vem CORTADA (e pode vir até vazia): isso é informado, para ninguém confundir com erro de
formato.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from services import config

# A tabela de preços do projeto (a mesma da triagem dos modelos)
CAMINHO_DOS_PRECOS = Path(__file__).resolve().parent.parent / "data" / "avaliacao" / "modelos_candidatos.json"
# Os preços dos modelos que só existem pelo Bedrock (ex.: o Amazon Nova), fora da triagem das APIs diretas
CAMINHO_DOS_PRECOS_SO_NO_BEDROCK = CAMINHO_DOS_PRECOS.parent / "precos_so_no_bedrock.json"
# Limite de tokens de saída por chamada (raciocínio + resposta); protege o custo de uma chamada só
LIMITE_DE_TOKENS_DE_SAIDA = 16000
# O perfil geográfico do Bedrock: "us" = o pedido só é processado em regiões dos EUA e do Canadá (ADR-96).
# Fica no código, e não no .env, de propósito: mudar a geografia do dado pede decisão nova (ADR)
PERFIL_GEOGRAFICO_DO_BEDROCK = "us"
# Quanto o perfil EUA custa a mais que o preço da tabela (o perfil "global" não tem acréscimo; documentação da AWS,
# 2026-09-27). Aplicado nas duas marcas por segurança: na dúvida, o teto de gasto conta a mais, nunca a menos
ACRESCIMO_DO_PERFIL_EUA = 0.10
# Modelos que guardam os pedidos por até 30 dias para detectar abuso (documentação do Bedrock, 2026-09-27). Ficam
# fora (ADR-96), em qualquer rota: um pedido para eles é recusado antes de sair daqui
MODELOS_QUE_GUARDAM_PEDIDOS = {"claude-fable-5", "claude-fable-5-1", "gpt-6-astra", "gpt-5.4", "gpt-5.5",
                               "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-cyber"}
# O nome de cada modelo no Bedrock, quando é diferente do nome usado no projeto (catálogo da conta, 2026-09-27)
NOME_NO_BEDROCK = {"claude-haiku-4-5": "claude-haiku-4-5-20251001-v1:0", "nova-pro": "nova-pro-v1:0",
                   "nova-2-lite": "nova-2-lite-v1:0"}
# Os modelos de pesos abertos, pelo nome COMPLETO no Bedrock (catálogo da conta, 2026-09-27). Não seguem a regra
# "perfil + fornecedor + nome": a maioria só roda na própria região (sem o perfil "us."), e o nome muda de formato
ID_COMPLETO_NO_BEDROCK = {"mistral-large-3": "mistral.mistral-large-3-675b-instruct", "deepseek-v3.2": "deepseek.v3.2",
                          "qwen3-vl-235b": "qwen.qwen3-vl-235b-a22b", "kimi-k3": "us.moonshotai.kimi-k3"}
# Modelos que só existem pelo Bedrock (o Nova é da Amazon; os abertos, aqui, só rodam lá): na rota direta, aviso
MODELOS_SO_NO_BEDROCK = {"nova-pro", "nova-2-lite", "mistral-large-3", "deepseek-v3.2", "qwen3-vl-235b", "kimi-k3"}
# Modelos que vão pela API geral do Bedrock (Converse), e não pelo endereço que imita a API do fornecedor (ADR-106 e
# ADR-107). Medido em 2026-09-27: o Sonnet 4.6 dá "não existe" no endereço da Anthropic; o Nova e os abertos só têm o
# Converse; o Haiku 4.5 vai por ele porque só lá tem o formato garantido (no endereço da Anthropic, o Bedrock recusa)
MODELOS_SO_PELO_CONVERSE = {"claude-sonnet-4-6", "claude-haiku-4-5"} | MODELOS_SO_NO_BEDROCK
# Modelos que recusam o formato garantido por esquema ("This model doesn't support the outputConfig field"): neles, o
# formato é garantido de outro jeito, pedindo a resposta como o preenchimento de uma "ferramenta" obrigatória (ADR-107)
MODELOS_COM_FERRAMENTA_FORCADA = {"nova-pro", "nova-2-lite"}
# O nome da "ferramenta" que o modelo é obrigado a preencher (só existe para carregar o esquema da resposta)
NOME_DA_FERRAMENTA_DE_RESPOSTA = "responder"
# Modelos com limite de saída menor que o padrão do projeto (o Bedrock recusa o pedido acima dele)
LIMITE_DE_SAIDA_DO_MODELO = {"nova-pro": 10000}
# Quantas vezes a chamada pelo Converse é tentada quando o Bedrock pede para esperar (muitas chamadas ao mesmo tempo)
TENTATIVAS_NO_CONVERSE = 4
# Quantos segundos esperar antes de cada nova tentativa (a espera cresce: 5, 15 e 30 segundos)
ESPERAS_ENTRE_TENTATIVAS = [5, 15, 30]
# Os códigos de resposta que querem dizer "espere e tente de novo" (429 = muitas chamadas; 503 = serviço ocupado)
CODIGOS_PARA_TENTAR_DE_NOVO = {429, 503}


class ConfiguracaoDoProvedor(Exception):
    """Falta algo que quem administra o ambiente precisa configurar (chave ou modelo): não é falha do provedor."""


@dataclass
class RespostaDoProvedor:
    """O que volta de qualquer provedor, sempre no mesmo formato."""

    texto: str                             # a resposta do modelo
    tokens_entrada: int                    # tokens do pedido (o que o provedor cobrou como entrada)
    tokens_saida: int                      # tokens da resposta, incluindo o raciocínio
    tokens_raciocinio: int | None = None   # quantos da saída foram raciocínio (quando o provedor informa)
    aceitou_temperatura: bool = True       # False quando o modelo recusou "temperature" e a chamada foi refeita
    cortada: bool = False                  # True quando a resposta parou no limite de tokens (incompleta)


def provedor_do_modelo(modelo: str) -> str:
    """De qual provedor é o modelo, pelo nome.

    Ex.: "claude-sonnet-5" → "anthropic"; "nova-pro" → "amazon"; "mistral-large-3" → "aberto"; "gpt-6-sol" → "openai".
    """
    if modelo.startswith("claude-"):
        return "anthropic"
    # O Nova é da própria Amazon: só existe pelo Bedrock
    if modelo.startswith("nova-"):
        return "amazon"
    # Os modelos de pesos abertos (Mistral, DeepSeek, Qwen, Kimi), aqui chamados pelo Bedrock
    if modelo in ID_COMPLETO_NO_BEDROCK:
        return "aberto"
    return "openai"


def usa_o_bedrock() -> bool:
    """True quando o .env manda as chamadas pelo AWS Bedrock (ROTA_DA_IA=bedrock)."""
    return config.ROTA_DA_IA == "bedrock"


def nome_do_modelo_na_rota(modelo: str) -> str:
    """O nome que o provedor da rota entende.

    Ex. (rota bedrock): "claude-sonnet-5" → "us.anthropic.claude-sonnet-5"; "gpt-6-luna" → "us.openai.gpt-6-luna";
    "claude-haiku-4-5" → "us.anthropic.claude-haiku-4-5-20251001-v1:0" (nome diferente no Bedrock).
    Na rota direta, o nome fica como está.
    """
    if not usa_o_bedrock():
        return modelo
    # Os modelos abertos já têm o nome completo (ex.: "mistral-large-3" → "mistral.mistral-large-3-675b-instruct")
    if modelo in ID_COMPLETO_NO_BEDROCK:
        return ID_COMPLETO_NO_BEDROCK[modelo]
    # Alguns modelos têm outro nome no Bedrock (com data e versão); os outros usam o mesmo nome do projeto
    nome_no_bedrock = NOME_NO_BEDROCK.get(modelo, modelo)
    # Perfil geográfico + marca do fornecedor + nome do modelo (o formato de "inference profile" do Bedrock)
    return PERFIL_GEOGRAFICO_DO_BEDROCK + "." + provedor_do_modelo(modelo) + "." + nome_no_bedrock


def recusar_modelo_que_guarda_pedidos(modelo: str) -> None:
    """Levanta ConfiguracaoDoProvedor se o modelo guarda os pedidos por até 30 dias (proibido pelo ADR-96)."""
    if modelo in MODELOS_QUE_GUARDAM_PEDIDOS:
        raise ConfiguracaoDoProvedor(f"O modelo {modelo!r} guarda os pedidos por até 30 dias e está fora do projeto "
                                     "(ADR-96). Escolha outro modelo no .env.")


def chamar(modelo: str, sistema: str, pedido: str, temperatura: float, esforco: str | None = None,
           esquema_json: dict | None = None) -> RespostaDoProvedor:
    """Faz a chamada ao provedor do modelo, pela rota do .env, e devolve o texto e os tokens.

    esforco: "low", "medium" ou "high" (só Anthropic); sem informar, vale o padrão do modelo.
    esquema_json: o formato que a resposta precisa seguir. Vale na Anthropic da rota direta e, no Bedrock, nos modelos
    que vão pela API Converse (ADR-107); no endereço da Anthropic no Bedrock, o esquema não vai (o Bedrock recusa), e na
    OpenAI é ignorado. Sem informar, texto livre.
    """
    # A trava vem antes de tudo: modelo proibido não chega a montar o pedido
    recusar_modelo_que_guarda_pedidos(modelo)
    # O Nova e os abertos só existem pelo Bedrock: na rota direta, avisa em vez de tentar uma chamada sem destino
    if modelo in MODELOS_SO_NO_BEDROCK and not usa_o_bedrock():
        raise ConfiguracaoDoProvedor(f"O modelo {modelo!r} só existe pelo AWS Bedrock: use ROTA_DA_IA=bedrock no .env.")
    nome_na_rota = nome_do_modelo_na_rota(modelo)
    # Os modelos que o Bedrock atende pela API geral vão por ela (sem esforço; o formato garantido vai de um dos dois
    # jeitos: esquema ou ferramenta forçada, conforme o modelo aceita)
    if usa_o_bedrock() and modelo in MODELOS_SO_PELO_CONVERSE:
        limite = LIMITE_DE_SAIDA_DO_MODELO.get(modelo, LIMITE_DE_TOKENS_DE_SAIDA)
        formato_por_ferramenta = modelo in MODELOS_COM_FERRAMENTA_FORCADA
        return chamar_pelo_converse(nome_na_rota, sistema, pedido, temperatura, limite, esquema_json,
                                    formato_por_ferramenta)
    if provedor_do_modelo(modelo) == "anthropic":
        # No Bedrock, o esquema não vai; a resposta é conferida do mesmo jeito pelo agente (e refeita se vier errada)
        if usa_o_bedrock():
            esquema_json = None
        return chamar_anthropic(nome_na_rota, sistema, pedido, esforco, esquema_json)
    return chamar_openai(nome_na_rota, sistema, pedido, temperatura)


def endereco_do_bedrock(caminho: str) -> str:
    """O endereço do Bedrock na região do .env.

    Ex.: "/anthropic" → "https://bedrock-runtime.us-east-1.amazonaws.com/anthropic".
    """
    return "https://bedrock-runtime." + config.REGIAO_BEDROCK + ".amazonaws.com" + caminho


def _exigir_chave_do_bedrock() -> str:
    """A chave do Bedrock do .env. Sem chave, avisa (não é falha do provedor)."""
    if not config.CHAVE_BEDROCK:
        raise ConfiguracaoDoProvedor("Falta a chave do Bedrock: coloque AWS_BEARER_TOKEN_BEDROCK no arquivo .env.")
    return config.CHAVE_BEDROCK


# ---------------- OpenAI ----------------

def _cliente_openai():
    """O cliente oficial da OpenAI, com a chave do .env. Sem chave, avisa (não é falha do provedor).

    Na rota bedrock, o mesmo cliente fala com o Bedrock (que entende a API da OpenAI) usando a chave do Bedrock.
    """
    # Importado aqui: só quem usa a OpenAI de verdade precisa da biblioteca carregada
    import openai
    if usa_o_bedrock():
        return openai.OpenAI(api_key=_exigir_chave_do_bedrock(), base_url=endereco_do_bedrock("/openai/v1"))
    if not config.CHAVE_OPENAI:
        raise ConfiguracaoDoProvedor("Falta a chave da OpenAI: coloque OPENAI_API_KEY no arquivo .env.")
    return openai.OpenAI(api_key=config.CHAVE_OPENAI)


def chamar_openai(modelo: str, sistema: str, pedido: str, temperatura: float) -> RespostaDoProvedor:
    """Chamada à OpenAI (Responses API). Se o modelo recusar "temperature", refaz sem ela e anota."""
    import openai
    cliente = _cliente_openai()
    aceitou_temperatura = True
    try:
        resposta = cliente.responses.create(model=modelo, instructions=sistema, input=pedido, temperature=temperatura,
                                            max_output_tokens=LIMITE_DE_TOKENS_DE_SAIDA)
    except openai.BadRequestError as erro:
        # Só a recusa da temperatura justifica tentar de novo; qualquer outro erro sobe como está
        if "temperature" not in str(erro):
            raise
        aceitou_temperatura = False
        resposta = cliente.responses.create(model=modelo, instructions=sistema, input=pedido,
                                            max_output_tokens=LIMITE_DE_TOKENS_DE_SAIDA)
    uso = resposta.usage
    # Quantos tokens da saída foram raciocínio (quando a OpenAI informa)
    tokens_raciocinio = None
    if uso.output_tokens_details is not None:
        tokens_raciocinio = uso.output_tokens_details.reasoning_tokens
    # "incomplete" quer dizer que a resposta parou antes do fim (em geral, no limite de tokens)
    cortada = getattr(resposta, "status", None) == "incomplete"
    return RespostaDoProvedor(texto=resposta.output_text, tokens_entrada=uso.input_tokens,
                              tokens_saida=uso.output_tokens, tokens_raciocinio=tokens_raciocinio,
                              aceitou_temperatura=aceitou_temperatura, cortada=cortada)


# ---------------- Anthropic ----------------

def _cliente_anthropic():
    """O cliente oficial da Anthropic, com a chave do .env. Sem chave, avisa (não é falha do provedor).

    Na rota bedrock, o mesmo cliente fala com o Bedrock (que entende a API da Anthropic) usando a chave do Bedrock.
    """
    # Importado aqui: só quem usa a Anthropic de verdade precisa da biblioteca carregada
    import anthropic
    if usa_o_bedrock():
        return anthropic.Anthropic(api_key=_exigir_chave_do_bedrock(), base_url=endereco_do_bedrock("/anthropic"))
    if not config.CHAVE_ANTHROPIC:
        raise ConfiguracaoDoProvedor("Falta a chave da Anthropic: coloque ANTHROPIC_API_KEY no arquivo .env.")
    return anthropic.Anthropic(api_key=config.CHAVE_ANTHROPIC)


def texto_da_resposta_anthropic(blocos) -> str:
    """Junta só os blocos de texto da resposta (os blocos de raciocínio ficam de fora)."""
    partes = []
    for bloco in blocos:
        if bloco.type == "text":
            partes.append(bloco.text)
    return "".join(partes)


def _configuracao_da_saida(esforco: str | None, esquema_json: dict | None) -> dict:
    """O "output_config" da Anthropic: esforço e formato garantido, só o que foi pedido. Vazio se nada foi pedido.

    Ex.: ("low", None) → {"effort": "low"}; (None, {...}) → {"format": {"type": "json_schema", "schema": {...}}}.
    """
    configuracao = {}
    if esforco:
        configuracao["effort"] = esforco
    if esquema_json:
        configuracao["format"] = {"type": "json_schema", "schema": esquema_json}
    return configuracao


def chamar_anthropic(modelo: str, sistema: str, pedido: str, esforco: str | None = None,
                     esquema_json: dict | None = None) -> RespostaDoProvedor:
    """Chamada à Anthropic (Messages API). A API atual não tem "temperature": a consistência vem do contrato."""
    cliente = _cliente_anthropic()
    parametros = {"model": modelo, "system": sistema, "max_tokens": LIMITE_DE_TOKENS_DE_SAIDA,
                  "messages": [{"role": "user", "content": pedido}]}
    # Esforço e formato garantido entram só quando pedidos (os outros agentes seguem como antes)
    configuracao_da_saida = _configuracao_da_saida(esforco, esquema_json)
    if configuracao_da_saida:
        parametros["output_config"] = configuracao_da_saida
    resposta = cliente.messages.create(**parametros)
    # "max_tokens" = parou no limite: a resposta está incompleta
    cortada = getattr(resposta, "stop_reason", None) == "max_tokens"
    return RespostaDoProvedor(texto=texto_da_resposta_anthropic(resposta.content),
                              tokens_entrada=resposta.usage.input_tokens, tokens_saida=resposta.usage.output_tokens,
                              aceitou_temperatura=False, cortada=cortada)


# ---------------- Bedrock: a API geral (Converse) ----------------

def pedido_do_converse(sistema: str, pedido: str, temperatura: float | None, limite: int,
                       esquema_json: dict | None = None, formato_por_ferramenta: bool = False) -> dict:
    """O corpo do pedido no formato da API geral do Bedrock. Sem temperatura (None), o campo não vai.

    Ex.: ("Responda em uma palavra.", "Capital do Brasil?", 0.0, 100) →
    {"system": [{"text": "Responda..."}], "messages": [{"role": "user", "content": [{"text": "Capital..."}]}],
     "inferenceConfig": {"maxTokens": 100, "temperature": 0.0}}
    Com esquema_json, o formato garantido entra de um dos dois jeitos (ADR-107):
    - esquema ("outputConfig"): o modelo é obrigado a responder um texto que segue o esquema;
    - ferramenta forçada ("toolConfig"), para quem recusa o esquema (o Nova): o modelo é obrigado a "preencher" uma
      ferramenta cujo formato é o esquema, e o preenchimento é a resposta.
    """
    configuracao = {"maxTokens": limite}
    if temperatura is not None:
        configuracao["temperature"] = temperatura
    corpo = {"system": [{"text": sistema}], "messages": [{"role": "user", "content": [{"text": pedido}]}],
             "inferenceConfig": configuracao}
    # Sem esquema, o pedido é só o texto (como antes)
    if esquema_json is None:
        return corpo
    if formato_por_ferramenta:
        ferramenta = {"toolSpec": {"name": NOME_DA_FERRAMENTA_DE_RESPOSTA, "description": "Devolve a resposta pedida.",
                                   "inputSchema": {"json": esquema_json}}}
        # "toolChoice" com o nome da ferramenta: o modelo não pode responder de outro jeito
        corpo["toolConfig"] = {"tools": [ferramenta], "toolChoice": {"tool": {"name": NOME_DA_FERRAMENTA_DE_RESPOSTA}}}
        return corpo
    # O Bedrock pede o esquema como texto (JSON dentro de uma string)
    corpo["outputConfig"] = {"textFormat": {"type": "json_schema", "structure": {
        "jsonSchema": {"schema": json.dumps(esquema_json, ensure_ascii=False), "name": "resposta"}}}}
    return corpo


def texto_da_resposta_converse(blocos: list[dict]) -> str:
    """O texto da resposta. Com ferramenta forçada, o preenchimento dela, como JSON; senão, os blocos de texto.

    Os blocos de raciocínio ("reasoningContent") ficam de fora nos dois casos.
    Ex.: [{"toolUse": {"input": {"itens": []}}}] → '{"itens": []}'; [{"text": "Brasília"}] → "Brasília".
    """
    # A ferramenta forçada: a resposta é o que o modelo preencheu nela
    for bloco in blocos:
        if "toolUse" in bloco:
            return json.dumps(bloco["toolUse"]["input"], ensure_ascii=False)
    partes = []
    for bloco in blocos:
        if "text" in bloco:
            partes.append(bloco["text"])
    return "".join(partes)


def enviar_ao_converse(nome_na_rota: str, corpo: dict):
    """Manda o pedido ao Bedrock e devolve a resposta HTTP. Se o Bedrock pedir para esperar, espera e tenta de novo.

    Com vários modelos medidos ao mesmo tempo, a conta pode passar do limite de chamadas por minuto: o Bedrock
    responde 429 ("muitas chamadas") e a chamada é refeita depois de 5, 15 e 30 segundos.
    """
    # Importados aqui: só quem usa o Bedrock de verdade precisa deles
    import time
    import httpx
    cabecalhos = {"Authorization": "Bearer " + _exigir_chave_do_bedrock(), "Content-Type": "application/json"}
    endereco = endereco_do_bedrock("/model/" + nome_na_rota + "/converse")
    for numero_da_tentativa in range(TENTATIVAS_NO_CONVERSE):
        resposta = httpx.post(endereco, headers=cabecalhos, json=corpo, timeout=300)
        # Deu certo, ou deu um erro que esperar não resolve: devolve para quem chamou decidir
        if resposta.status_code not in CODIGOS_PARA_TENTAR_DE_NOVO:
            return resposta
        # Última tentativa: não há mais o que esperar
        if numero_da_tentativa == TENTATIVAS_NO_CONVERSE - 1:
            return resposta
        time.sleep(ESPERAS_ENTRE_TENTATIVAS[numero_da_tentativa])
    return resposta


def chamar_pelo_converse(nome_na_rota: str, sistema: str, pedido: str, temperatura: float, limite: int,
                         esquema_json: dict | None = None,
                         formato_por_ferramenta: bool = False) -> RespostaDoProvedor:
    """Chamada pela API geral do Bedrock (Converse), que atende qualquer modelo do catálogo.

    esquema_json: o formato garantido (sem ele, texto livre); formato_por_ferramenta: garantir pelo jeito da
    ferramenta forçada (para quem recusa o esquema). Se o modelo recusar "temperature", refaz sem ela e anota (como
    na OpenAI). Qualquer outro erro sobe com a mensagem do Bedrock, e o cliente de IA decide o que fazer.
    """
    aceitou_temperatura = True
    corpo = pedido_do_converse(sistema, pedido, temperatura, limite, esquema_json, formato_por_ferramenta)
    resposta = enviar_ao_converse(nome_na_rota, corpo)
    # Só a recusa da temperatura justifica tentar de novo sem ela
    if resposta.status_code == 400 and "temperature" in resposta.text:
        aceitou_temperatura = False
        corpo = pedido_do_converse(sistema, pedido, None, limite, esquema_json, formato_por_ferramenta)
        resposta = enviar_ao_converse(nome_na_rota, corpo)
    # Erro do Bedrock (modelo fora da conta, pedido inválido) sobe como está, com a mensagem dele
    resposta.raise_for_status()
    dados = resposta.json()
    # "max_tokens" = parou no limite: a resposta está incompleta (com a ferramenta, o fim normal é "tool_use")
    cortada = dados.get("stopReason") == "max_tokens"
    return RespostaDoProvedor(texto=texto_da_resposta_converse(dados["output"]["message"]["content"]),
                              tokens_entrada=dados["usage"]["inputTokens"], tokens_saida=dados["usage"]["outputTokens"],
                              aceitou_temperatura=aceitou_temperatura, cortada=cortada)


# ---------------- Bedrock Guardrails: o detector de ataques ao prompt (ADR-147) ----------------

# O nome do detector na Telemetria e no teto de gasto (a coluna "modelo" da execução)
NOME_DO_DETECTOR = "bedrock-guardrails"
# O caminho da API que só DETECTA (InvokeGuardrailChecks, lançada em 16/06/2026). Não precisa de um guardrail criado na
# conta e não chama modelo nenhum, por isso não usa o perfil "us.": vai ao endereço da região do .env, o mesmo da IA
# (documentação da AWS consultada em 30/09/2026)
CAMINHO_DO_DETECTOR = "/guardrail-checks/invoke"
# As 3 categorias de ataque ao prompt: tirar a IA das regras (JAILBREAK), esconder uma ordem no texto
# (PROMPT_INJECTION) e arrancar as instruções internas dela (PROMPT_LEAKAGE)
CATEGORIAS_DE_ATAQUE = ("JAILBREAK", "PROMPT_INJECTION", "PROMPT_LEAKAGE")
# O preço: US$ 0,08 por 1.000 unidades de texto (página de preços do Bedrock, consultada em 30/09/2026)
PRECO_DE_MIL_UNIDADES_DE_TEXTO_USD = 0.08
# Uma unidade de texto tem até 1.000 caracteres, e cada texto arredonda para cima (a mesma página de preços)
CARACTERES_POR_UNIDADE_DE_TEXTO = 1000


class RecusaDoDetector(Exception):
    """O detector respondeu com erro: 403 (a chave não tem a permissão), 429 (muitas chamadas) ou 5xx (fora do ar).

    Guarda só o código da resposta: a mensagem do Bedrock pode trazer endereços internos.
    Ex.: RecusaDoDetector(403).codigo → 403.
    """

    def __init__(self, codigo: int):
        """Recebe o código HTTP da resposta (ex.: 403)."""
        super().__init__(f"o detector respondeu {codigo}")
        # O código fica guardado para a Telemetria (ex.: "HTTP403")
        self.codigo = codigo


@dataclass
class NotaDoDetector:
    """O que o detector devolveu para um texto, já lido: a maior nota, a categoria dela e o que a checagem custou."""

    maior_nota: float           # a maior nota entre as 3 categorias (de 0 a 1, em degraus de 0,2)
    categoria: str | None       # a categoria da maior nota (None quando todas vieram 0)
    unidades: int               # as unidades de texto cobradas
    custo_usd: float            # unidades × o preço de cada uma


def pedido_ao_detector(texto: str) -> dict:
    """O corpo do pedido: o texto como uma mensagem de "user" (a entrada de quem está fora) e as 3 categorias.

    Ex.: "oi" → {"messages": [{"role": "user", "content": [{"text": "oi"}]}],
                 "checks": {"promptAttack": {"categories": [{"category": "JAILBREAK"}, ...]}}}
    """
    # Cada categoria vai como um item da lista
    categorias = []
    for categoria in CATEGORIAS_DE_ATAQUE:
        categorias.append({"category": categoria})
    # A mensagem: o papel "user" e o texto num bloco (o único tipo de bloco que a API aceita hoje)
    mensagem = {"role": "user", "content": [{"text": texto}]}
    return {"messages": [mensagem], "checks": {"promptAttack": {"categories": categorias}}}


def unidades_de_texto(texto: str) -> int:
    """Quantas unidades de texto a checagem cobra: uma a cada 1.000 caracteres, arredondando para cima.

    Ex.: "oi" → 1; um texto de 1.000 caracteres → 1; um de 1.001 → 2.
    """
    # A divisão arredondada para cima; um texto curto ainda conta uma unidade
    return max(1, math.ceil(len(texto) / CARACTERES_POR_UNIDADE_DE_TEXTO))


def custo_da_checagem(unidades: int) -> float:
    """O custo da checagem em dólares. Ex.: 1 unidade → US$ 0,00008; 3 unidades → US$ 0,00024."""
    return unidades * PRECO_DE_MIL_UNIDADES_DE_TEXTO_USD / 1000


def ler_a_resposta_do_detector(dados: dict, texto: str) -> NotaDoDetector:
    """A maior nota, a categoria dela e as unidades cobradas, lidas da resposta do detector.

    Recebe: o JSON da resposta e o texto checado (para contar as unidades, se a resposta não trouxer).
    Levanta KeyError se a resposta vier sem as notas: o detector devolve uma nota por categoria pedida, e uma resposta
    sem nota nenhuma não pode passar como "normal".
    Ex.: {"results": {"promptAttack": {"results": [{"category": "JAILBREAK", "severityScore": 0.8}]}},
          "usage": {"promptAttack": {"textUnits": 1}}} → NotaDoDetector(0.8, "JAILBREAK", 1, 0.00008)
    """
    # As notas de cada categoria (a falta delas levanta KeyError, de propósito)
    notas = dados["results"]["promptAttack"]["results"]
    if not notas:
        raise KeyError("a resposta do detector veio sem notas")
    maior_nota = 0.0
    categoria_da_maior_nota = None
    for nota in notas:
        valor = float(nota["severityScore"])
        # Fica com a maior nota e com a categoria dela
        if valor > maior_nota:
            maior_nota = valor
            categoria_da_maior_nota = nota["category"]
    # As unidades cobradas, como o Bedrock informa; sem a informação, a conta pelo tamanho do texto
    uso_da_checagem = dados.get("usage") or {}
    uso_do_detector = uso_da_checagem.get("promptAttack") or {}
    unidades = uso_do_detector.get("textUnits")
    if unidades is None:
        unidades = unidades_de_texto(texto)
    unidades = int(unidades)
    return NotaDoDetector(maior_nota, categoria_da_maior_nota, unidades, custo_da_checagem(unidades))


def checar_ataques(texto: str, tempo_maximo_s: float) -> NotaDoDetector:
    """Pede ao detector de ataques do Bedrock Guardrails a nota do texto (ADR-147). Uma chamada só, sem nova tentativa.

    Recebe: o texto e o tempo máximo de espera, em segundos.
    Devolve: a NotaDoDetector. Levanta ConfiguracaoDoProvedor (fora da rota do Bedrock, ou sem a chave), TimeoutError
    (passou do tempo) ou RecusaDoDetector (403, 429, 5xx). Quem decide o que fazer é o cliente de IA
    (services/llm_client.py): nesta checagem, a falha nunca pausa a mensagem (ADR-147).
    """
    # Importado aqui: só quem usa o Bedrock de verdade precisa dele
    import httpx
    # O detector só existe pelo Bedrock
    if not usa_o_bedrock():
        raise ConfiguracaoDoProvedor("O Bedrock Guardrails só existe pelo AWS Bedrock: use ROTA_DA_IA=bedrock no .env.")
    # A mesma chave e a mesma região das chamadas à IA
    cabecalhos = {"Authorization": "Bearer " + _exigir_chave_do_bedrock(), "Content-Type": "application/json"}
    try:
        resposta = httpx.post(endereco_do_bedrock(CAMINHO_DO_DETECTOR), headers=cabecalhos,
                              json=pedido_ao_detector(texto), timeout=tempo_maximo_s)
    except httpx.TimeoutException as erro:
        # O tempo acabou do lado da conexão: é o mesmo "estourou" de quando a espera desiste
        raise TimeoutError(f"o detector passou de {tempo_maximo_s} s") from erro
    # 403, 429, 5xx: sobe só com o código, sem esperar nem tentar de novo (o tempo máximo não deixa)
    if not resposta.is_success:
        raise RecusaDoDetector(resposta.status_code)
    return ler_a_resposta_do_detector(resposta.json(), texto)


# ---------------- Custo ----------------

def carregar_precos() -> dict:
    """Preço de cada modelo das tabelas do projeto: {"gpt-6-sol": (2.0, 10.0), ...} em dólares por 1M tokens.

    Junta a tabela da triagem (APIs diretas) com a dos modelos que só existem pelo Bedrock (ex.: o Nova).
    """
    precos = {}
    for caminho_da_tabela in (CAMINHO_DOS_PRECOS, CAMINHO_DOS_PRECOS_SO_NO_BEDROCK):
        dados = json.loads(caminho_da_tabela.read_text(encoding="utf-8"))
        for modelo in dados["modelos"]:
            precos[modelo["modelo"]] = (modelo["entrada"], modelo["saida"])
    return precos


def custo_em_dolares(modelo: str, tokens_entrada: int, tokens_saida: int) -> float | None:
    """O custo da chamada em dólares; None ("não medido") se o modelo não está na tabela de preços.

    Ex.: gpt-6-sol (US$ 2 / 10), 5.000 tokens de entrada e 1.500 de saída → 0,01 + 0,015 = US$ 0,025.
    Na rota bedrock (perfil EUA), o mesmo cálculo com 10% a mais: US$ 0,0275.
    """
    precos = carregar_precos()
    if modelo not in precos:
        return None
    preco_de_entrada, preco_de_saida = precos[modelo]
    custo = (tokens_entrada * preco_de_entrada + tokens_saida * preco_de_saida) / 1_000_000
    # O perfil EUA do Bedrock cobra um acréscimo sobre o preço da tabela
    if usa_o_bedrock():
        custo = custo * (1 + ACRESCIMO_DO_PERFIL_EUA)
    return custo
