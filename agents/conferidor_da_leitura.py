"""Agente Conferidor da Leitura: uma segunda IA confere o que o Leitor de Documentos entendeu (ADR-105).

Por que existe: as regras conferem o que dá para conferir sem entender o texto (o valor está no documento, ninguém
ficou de fora, o formato do CPF). O que elas NÃO pegam são erros de entendimento: o CPF do colega posto na pessoa
errada, a data de admissão trocada com a de nascimento, o bônus lido como salário. Este agente procura só isso.

Como ele fica independente do Leitor: usa o modelo PEQUENO, de outro fornecedor (o Leitor usa o grande), e recebe só o
trecho do documento e o que foi lido; não vê o raciocínio do Leitor. Ele não corrige nada: cada suspeita vira uma
pergunta para a empresa, presa à pessoa e ao campo.

Só a dúvida forte vira pergunta (v2, ADR-131): a IA precisa trazer o valor que o documento dá para
aquela pessoa e aquele campo, e ele precisa ser DIFERENTE do valor lido. Citar outro valor perto (um benefício, o CPF
de um dependente) não é erro. A pergunta é montada aqui, pelo código, com os dois valores ("Confira este valor: no
documento está X, mas ficou Y. Qual é o certo?"): o texto livre da IA nunca vai para a tela.

Fica DESLIGADO por padrão (CONFERIDOR_DA_LEITURA=nao no .env): ele dobra as chamadas de IA por documento e ainda não
sabemos se acha erros de verdade ou só gera alarme falso. O experimento EXP-015 (scripts/avaliar_conferidor.py) planta
erros nos documentos de teste e mede; a decisão de ligar sai do número.

Cada conferência também devolve a sua MEDIÇÃO (quando começou e terminou, se deu certo, qual modelo respondeu, se o
guardrail de saída descartou alguma suspeita). O Leitor junta as medições de todos os blocos numa execução só do
Conferidor, que vai para o Acompanhamento dos agentes (services/execucoes.py). Nada pessoal entra na medição.
"""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from models.contratos import CampoLayout
from services import execucoes
from services.uso_da_ia import Uso
from services.llm_client import LLMClient

# Pasta raiz do projeto (para achar o prompt)
RAIZ = Path(__file__).resolve().parent.parent
# Versão do prompt e nome da tarefa no cliente de IA
VERSAO_PROMPT = "conferidor_da_leitura_v2"
TAREFA = "conferir_leitura"
# Como o Conferidor aparece nas execuções (a coluna "agente") e qual etapa ele faz
NOME_DO_AGENTE = "Conferidor da leitura"
ETAPA = "conferir_leitura"
# O começo de toda pergunta que nasce de uma suspeita do Conferidor. Serve também para achar, entre as perguntas da
# leitura guardadas no envio, as que vieram dele (ex.: quantas a empresa corrigiu e quantas confirmou)
INICIO_DA_PERGUNTA = "Confira este valor: "
# O começo usado até a v1 (antes do ADR-131): continua reconhecido, para as perguntas dos envios antigos contarem
INICIO_DA_PERGUNTA_DA_V1 = "Uma segunda IA desconfia deste valor: "
# O maior valor que entra na pergunta: um campo do cadastro nunca é um parágrafo (mais que isso, a suspeita cai)
TAMANHO_MAXIMO_DO_VALOR = 60
# Marcas de link: um campo do cadastro nunca é um endereço de site (a suspeita que trouxer um cai; guardrail de saída)
MARCAS_DE_LINK = ("http", "www.", "://")
# O campo do salário: na pergunta, o valor lido dele aparece em reais ("R$ 650,00", e não "650.00")
CAMPO_DO_SALARIO = "valor_renda"


@dataclass
class Suspeita:
    """Um valor que o conferidor acha que a leitura entendeu errado."""

    pessoa: int                   # a posição da pessoa na lista conferida (1 = primeira)
    campo: str                    # o campo do layout
    motivo: str                   # por quê, em uma frase (só para a auditoria e os experimentos; não vai para a tela)
    valor_lido: str = ""          # o valor que a leitura pôs no campo
    valor_no_documento: str = ""  # o valor que o documento dá para a pessoa e o campo, segundo o conferidor


@lru_cache(maxsize=1)
def carregar_prompt() -> tuple[str, str]:
    """Devolve (sistema, pedido) do arquivo versionado em prompts/."""
    texto = (RAIZ / "prompts" / f"{VERSAO_PROMPT}.md").read_text(encoding="utf-8")
    _, sistema, pedido = re.split(r"^## (?:SISTEMA|PEDIDO)\s*$", texto, flags=re.M)
    return sistema.strip(), pedido.strip()


def descrever_layout(campos: list[CampoLayout]) -> str:
    """Os campos do layout, um por linha, com a descrição."""
    linhas = []
    for campo in campos:
        linhas.append(f"- {campo.campo}: {campo.descricao}")
    return "\n".join(linhas)


def descrever_pessoas(pessoas: list[dict[str, str]]) -> str:
    """O que foi lido de cada pessoa, uma por linha, numerada. Ex.: 'Pessoa 1: {"cpf": "529...", ...}'."""
    linhas = []
    for numero, valores in enumerate(pessoas, start=1):
        linhas.append(f"Pessoa {numero}: " + json.dumps(valores, ensure_ascii=False))
    return "\n".join(linhas)


def _json_da_resposta(texto: str) -> str:
    """Só o JSON da resposta: do primeiro "{" ao último "}"."""
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("a resposta não contém um objeto JSON")
    return texto[inicio:fim + 1]


def _so_numeros(valor: str) -> str:
    """Só os dígitos do valor. Ex.: "815.994.185-41" → "81599418541"."""
    digitos = []
    for caractere in valor:
        if caractere.isdigit():
            digitos.append(caractere)
    return "".join(digitos)


def _so_letras_e_numeros(valor: str) -> str:
    """O valor sem pontuação, espaços e maiúsculas, para comparar. Ex.: "Analista Financeira" → "analistafinanceira"."""
    letras_e_numeros = []
    for caractere in valor.lower():
        if caractere.isalnum():
            letras_e_numeros.append(caractere)
    return "".join(letras_e_numeros)


def _data_do_valor(valor: str) -> date | None:
    """A data escrita no valor, ou None se ele não for uma data válida.

    Aceita dia/mês/ano ("14/03/1991", "14-03-1991", "14.03.1991") e ano-mês-dia ("1991-03-14").
    Ex.: "09-09-2026" → date(2026, 9, 9); "31/02/2026" → None (o dia não existe); "5.300,00" → None.
    """
    # Primeiro o jeito brasileiro: dia, mês e ano, separados por barra, traço ou ponto
    partes = re.fullmatch(r"\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s*", valor)
    if partes:
        dia, mes, ano = partes.group(1), partes.group(2), partes.group(3)
    else:
        # Depois o jeito ISO: ano, mês e dia, separados por traço
        partes = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", valor)
        if not partes:
            return None
        ano, mes, dia = partes.group(1), partes.group(2), partes.group(3)
    try:
        # A data de verdade: um dia que não existe (31 de fevereiro) não é data
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


def _parece_dinheiro(valor: str) -> bool:
    """True se o valor tem cara de dinheiro: "R$", centavos no fim ou milhar separado.

    Ex.: "R$ 650" → True; "650.00" → True; "5.300" → True; "12345678900" → False (só dígitos: pode ser um CPF).
    """
    # O símbolo do real, em qualquer caixa
    if "r$" in valor.lower():
        return True
    # Os centavos no fim: um separador seguido de 1 ou 2 dígitos ("650.00", "4.350,5")
    if re.search(r"[.,]\d{1,2}\s*$", valor):
        return True
    # O milhar separado: 1 a 3 dígitos e grupos de 3 ("5.300", "1,250,000")
    return re.fullmatch(r"\s*\d{1,3}([.,]\d{3})+\s*", valor) is not None


def _numero_do_dinheiro(valor: str) -> Decimal | None:
    """O número de um valor em dinheiro, no padrão brasileiro ou americano; None se não for um número.

    O separador que aparece por último e tem 1 ou 2 dígitos depois é o dos centavos; o outro é o do milhar.
    Ex.: "R$ 5.300,00" → 5300.00; "5,300.00" → 5300.00; "650.00" → 650.00; "5.300" → 5300; "4350" → 4350;
    "815.994.185-41" → None (tem traço: é um CPF, não dinheiro).
    """
    # Tira o símbolo do real e os espaços
    texto = valor.lower().replace("r$", "").replace(" ", "")
    # Sobra só dígitos, ponto e vírgula; qualquer outra coisa (traço, barra, letra) não é dinheiro
    if not re.fullmatch(r"[\d.,]+", texto) or not texto[0].isdigit():
        return None
    # A posição do último separador (ponto ou vírgula), se houver
    posicao_do_ultimo = max(texto.rfind("."), texto.rfind(","))
    digitos_depois_do_ultimo = len(texto) - posicao_do_ultimo - 1
    if posicao_do_ultimo >= 0 and digitos_depois_do_ultimo in (1, 2):
        # O último separador é o dos centavos; o do milhar, se houver, é o outro sinal
        separador_dos_centavos = texto[posicao_do_ultimo]
        separador_do_milhar = "," if separador_dos_centavos == "." else "."
        parte_inteira = texto[:posicao_do_ultimo]
        # A parte inteira precisa ser só dígitos ou grupos de 3 com o separador do milhar ("5.300" em "5.300,00")
        so_digitos = re.fullmatch(r"\d+", parte_inteira) is not None
        milhar_em_grupos = re.fullmatch(r"\d{1,3}(" + re.escape(separador_do_milhar) + r"\d{3})+", parte_inteira)
        if not so_digitos and milhar_em_grupos is None:
            # Separadores fora do padrão (ex.: "53.00.0"): não dá para saber o número
            return None
        centavos = texto[posicao_do_ultimo + 1:]
        texto_do_numero = parte_inteira.replace(separador_do_milhar, "") + "." + centavos
    elif re.fullmatch(r"\d+", texto) or re.fullmatch(r"\d{1,3}([.,]\d{3})+", texto):
        # Sem centavos: número inteiro, com ou sem o milhar separado em grupos de 3
        texto_do_numero = texto.replace(".", "").replace(",", "")
    else:
        # Separadores fora do padrão (ex.: "53.00.0"): não dá para saber o número
        return None
    return Decimal(texto_do_numero)


def _mesmo_valor(valor_lido: str, valor_no_documento: str) -> bool:
    """True se os dois textos são o mesmo valor escrito de jeitos diferentes (revisão do ADR-131).

    A comparação depende do tipo do valor, sempre por uma regra geral:
    - duas datas: a mesma data ("09/09/2026" = "09-09-2026" = "2026-09-09");
    - dinheiro (um dos dois com "R$", centavos ou milhar): o mesmo número ("R$ 5.300,00" = "5300.00" = "5.300");
    - outro valor com dígitos (CPF, PIS, CEP): os mesmos dígitos, todos ("815.994.185-41" = "81599418541");
    - sem dígitos: o texto sem pontuação nem maiúsculas ("Analista Financeira" = "analista financeira").
    Ex.: ("650.00", "R$ 6.500,00") → False (um salário 10× maior é outro valor, não o mesmo com um zero a mais);
    ("12345678900", "123456789") → False.
    """
    # 1) Duas datas: compara a data, e não o jeito de escrever
    data_lida = _data_do_valor(valor_lido)
    data_do_documento = _data_do_valor(valor_no_documento)
    if data_lida is not None and data_do_documento is not None:
        return data_lida == data_do_documento
    # 2) Dinheiro: se um dos dois tem cara de dinheiro e os dois viram número, compara os números
    if _parece_dinheiro(valor_lido) or _parece_dinheiro(valor_no_documento):
        numero_lido = _numero_do_dinheiro(valor_lido)
        numero_do_documento = _numero_do_dinheiro(valor_no_documento)
        if numero_lido is not None and numero_do_documento is not None:
            return numero_lido == numero_do_documento
    # 3) Outro valor com dígitos (CPF, PIS, CEP): todos os dígitos contam, inclusive os zeros
    digitos_lidos = _so_numeros(valor_lido)
    digitos_do_documento = _so_numeros(valor_no_documento)
    if digitos_lidos or digitos_do_documento:
        return digitos_lidos == digitos_do_documento
    # 4) Sem dígitos: o texto sem pontuação nem maiúsculas
    return _so_letras_e_numeros(valor_lido) == _so_letras_e_numeros(valor_no_documento)


def _valor_serve_para_a_pergunta(valor: str) -> bool:
    """True se o valor pode ir para a pergunta: tem conteúdo, é curto, é uma linha só, sem "?" e sem link."""
    if not valor or len(valor) > TAMANHO_MAXIMO_DO_VALOR or "\n" in valor or "?" in valor:
        return False
    valor_minusculo = valor.lower()
    for marca in MARCAS_DE_LINK:
        if marca in valor_minusculo:
            return False
    return True


def conferir(documento: str, pessoas: list[dict[str, str]], campos: list[CampoLayout],
             cliente: LLMClient) -> tuple[list[Suspeita], object]:
    """Pede ao modelo pequeno as suspeitas de erro de entendimento na leitura.

    Recebe: documento — o trecho lido; pessoas — o que foi lido de cada uma ({campo: valor}); campos do layout.
    Devolve: (as suspeitas conferidas, a resposta da IA para somar o uso). Suspeita de pessoa que não existe ou de
    campo que a pessoa não tem é descartada (guardrail de saída). Resposta fora do formato: nenhuma suspeita.
    É a mesma conferência de conferir_e_medir, sem a medição (os experimentos e os testes usam esta).
    """
    suspeitas, resposta, _ = conferir_e_medir(documento, pessoas, campos, cliente)
    return suspeitas, resposta


def conferir_e_medir(documento: str, pessoas: list[dict[str, str]], campos: list[CampoLayout],
                     cliente: LLMClient) -> tuple[list[Suspeita], object, dict | None]:
    """A conferência (igual a conferir) e a medição dela, para o Acompanhamento dos agentes.

    Devolve: (as suspeitas, a resposta da IA, a medição). Sem pessoas, não há chamada: (lista vazia, None, None).
    A medição é {"inicio", "fim" (horários), "status" (OK ou ERRO), "tipo_erro", "modelo", "guardrail_disparado",
    "suspeitas" (quantas ficaram)}. Vira ERRO quando a resposta veio fora do formato ("RespostaForaDoContrato") ou
    quando, no modo real, o provedor não respondeu e a resposta é simulada ("IAIndisponivel"). Nos dois casos a
    leitura segue sem suspeitas, como antes: só a medição conta o que aconteceu.
    """
    if not pessoas:
        return [], None, None
    sistema, pedido = carregar_prompt()
    sistema = sistema.replace("{layout}", descrever_layout(campos))
    pedido = pedido.replace("{documento}", documento).replace("{pessoas}", descrever_pessoas(pessoas))
    # O relógio da medição: do pedido à resposta da IA
    inicio = datetime.now(timezone.utc)
    resposta = cliente.gerar(TAREFA, pedido, sistema, modelo="pequeno", temperatura=0.0)
    fim = datetime.now(timezone.utc)
    # O uso desta chamada (tokens e custo) entra na medição: o Conferidor paga só a sua parte (ADR-131)
    medicao = {"inicio": inicio, "fim": fim, "status": execucoes.OK, "tipo_erro": None, "modelo": resposta.modelo,
               "guardrail_disparado": False, "suspeitas": 0, "uso": Uso.da_resposta(resposta).em_dicionario()}
    # No modo real, resposta simulada quer dizer que o provedor falhou (a conferência não aconteceu de verdade)
    if cliente.modo == "llm" and resposta.modo == "mock":
        medicao["status"] = execucoes.ERRO
        medicao["tipo_erro"] = "IAIndisponivel"
    try:
        suspeitas_da_ia = json.loads(_json_da_resposta(resposta.texto))["suspeitas"]
    except (ValueError, KeyError, TypeError):
        # Fora do formato: a leitura segue sem suspeitas (as regras continuam conferindo); a medição registra o erro
        medicao["status"] = execucoes.ERRO
        if medicao["tipo_erro"] is None:
            medicao["tipo_erro"] = "RespostaForaDoContrato"
        return [], resposta, medicao
    suspeitas = []
    for item in suspeitas_da_ia:
        suspeita = _suspeita_conferida(item, pessoas)
        if suspeita is None:
            # Fora do formato, sobre quem não existe ou com valor impróprio: o guardrail de saída descarta
            medicao["guardrail_disparado"] = True
            continue
        if _mesmo_valor(suspeita.valor_lido, suspeita.valor_no_documento):
            # O documento dá o mesmo valor que foi lido: não há erro (é a dúvida fraca que a v2 não pergunta; ADR-131)
            continue
        suspeitas.append(suspeita)
    medicao["suspeitas"] = len(suspeitas)
    return suspeitas, resposta, medicao


def _suspeita_conferida(item, pessoas: list[dict[str, str]]) -> Suspeita | None:
    """A suspeita da IA, se estiver no formato e fizer sentido; senão, None (o guardrail de saída descarta).

    Vale só a suspeita sobre uma pessoa da lista e um campo que ela tem, com o valor do documento que sirva para a
    pergunta (curto, uma linha, sem link). Ex.: {"pessoa": 1, "campo": "cpf", "valor_no_documento": "111.444.777-35",
    "motivo": "..."} → Suspeita(pessoa=1, campo="cpf", ...).
    """
    if not isinstance(item, dict):
        return None
    pessoa = item.get("pessoa")
    campo = item.get("campo")
    # A pessoa precisa ser um número da lista (1 = primeira)
    if not isinstance(pessoa, int) or not (1 <= pessoa <= len(pessoas)):
        return None
    # O campo precisa ser um que a pessoa tem na leitura
    if campo not in pessoas[pessoa - 1]:
        return None
    valor_no_documento = str(item.get("valor_no_documento") or "").strip()
    valor_lido = str(pessoas[pessoa - 1][campo] or "").strip()
    # Sem o valor certo do documento, não é dúvida forte; com valor impróprio (longo, várias linhas, link), cai
    if not _valor_serve_para_a_pergunta(valor_no_documento) or not _valor_serve_para_a_pergunta(valor_lido):
        return None
    motivo = str(item.get("motivo") or "").strip()
    return Suspeita(pessoa=pessoa, campo=campo, motivo=motivo[:200], valor_lido=valor_lido,
                    valor_no_documento=valor_no_documento)


def juntar_as_medicoes(medicoes: list[dict]) -> dict | None:
    """Junta as medições de cada bloco numa execução só do Conferidor, para o documento inteiro.

    Recebe: as medições de conferir_e_medir (uma por bloco conferido). Devolve None se não houve nenhuma; senão, a
    execução no formato que o Leitor entrega (ver leitor_de_documentos.execucao_medida): do começo da primeira
    conferência ao fim da última; ERRO se algum bloco deu erro (com o tipo do primeiro erro); guardrail disparado se
    ele agiu em algum bloco. Ex.: 3 blocos, um fora do formato → status "ERRO", tipo_erro "RespostaForaDoContrato".
    """
    if not medicoes:
        return None
    inicio = medicoes[0]["inicio"]
    fim = medicoes[0]["fim"]
    status = execucoes.OK
    tipo_erro = None
    guardrail_disparado = False
    modelos = []
    # O uso de todas as conferências do documento, somado (tokens e custo; ADR-131)
    uso = Uso()
    for medicao in medicoes:
        uso.somar_uso(Uso.do_dicionario(medicao.get("uso")))
        # O começo mais cedo e o fim mais tarde
        inicio = min(inicio, medicao["inicio"])
        fim = max(fim, medicao["fim"])
        # Um bloco com erro já marca a conferência do documento como erro (vale o tipo do primeiro)
        if medicao["status"] == execucoes.ERRO and tipo_erro is None:
            status = execucoes.ERRO
            tipo_erro = medicao["tipo_erro"]
        if medicao["guardrail_disparado"]:
            guardrail_disparado = True
        # Cada modelo aparece uma vez só
        if medicao["modelo"] not in modelos:
            modelos.append(medicao["modelo"])
    return {"agente": NOME_DO_AGENTE, "etapa": ETAPA, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
            "status": status, "tipo_erro": tipo_erro, "modelo": ", ".join(modelos), "versao_prompt": VERSAO_PROMPT,
            "guardrail_disparado": guardrail_disparado, "uso": uso.em_dicionario()}


def pergunta_da_suspeita(suspeita: Suspeita) -> str:
    """A pergunta que a empresa vê na conferência: simples, com os dois valores, e montada aqui (nunca pela IA).

    O cartão já diz a pessoa e a informação; a pergunta só mostra o que o documento diz e o que ficou.
    Ex.: "Confira este valor: no documento está R$ 5.300,00, mas ficou R$ 720,00. Qual é o certo?"
    """
    return (INICIO_DA_PERGUNTA + "no documento está " + _valor_para_mostrar(suspeita.campo, suspeita.valor_no_documento)
            + ", mas ficou " + _valor_para_mostrar(suspeita.campo, suspeita.valor_lido) + ". Qual é o certo?")


def _valor_para_mostrar(campo: str, valor: str) -> str:
    """O valor do jeito que a empresa reconhece: o salário em reais; os outros campos, como vieram.

    Ex.: ("valor_renda", "650.00") → "R$ 650,00"; ("valor_renda", "2.600,00") → "R$ 2.600,00";
    ("valor_renda", "R$ 650,00") → igual; ("cpf", "111.444.777-35") → igual.
    """
    if campo != CAMPO_DO_SALARIO or valor.startswith("R$"):
        return valor
    try:
        numero = float(valor)
    except ValueError:
        # Escrito no padrão brasileiro (ex.: "2.600,00"): só falta o "R$"
        return "R$ " + valor
    # 1234.5 → "1,234.50" (padrão americano) → "1.234,50" (padrão brasileiro)
    no_padrao_americano = f"{numero:,.2f}"
    no_padrao_brasileiro = no_padrao_americano.replace(",", "_").replace(".", ",").replace("_", ".")
    return "R$ " + no_padrao_brasileiro


def simular_conferencia(prompt: str) -> str:
    """MOCK: o conferidor simulado não desconfia de nada (os testes passam um cliente próprio quando precisam)."""
    return json.dumps({"suspeitas": []})


def cliente_padrao() -> LLMClient:
    """Cliente do modo configurado; no MOCK, a conferência é simulada."""
    return LLMClient(respostas_mock={TAREFA: simular_conferencia})
