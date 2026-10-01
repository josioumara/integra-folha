"""Agente Leitor de Documentos, versão 2: lê um texto corrido e preenche os campos do layout, pessoa por pessoa (ADR-73).

Quando entra em ação: a empresa mandou um Word sem tabela e sem fichas ("Nome: ... / CPF: ..."), só texto: fichas
misturadas, e-mails, anotações. Regra não resolve isso; a IA resolve. O trabalho é feito numa "linha de montagem":

A IA lê o texto como a empresa mandou, com os dados reais (ADR-101): ela roda pelo AWS Bedrock, onde o fornecedor
do modelo não vê o pedido e nada fica guardado (ADR-96). No EXP-010, ler os dados reais acertou 98,9% dos campos,
contra 91,3% com os dados trocados por etiquetas.

1. BLOCOS (IA pequena, resposta curta): o documento é dividido em blocos, um por pessoa. Se a IA pequena falhar, uma
   regra divide (títulos curtos abrem um bloco novo). Assim cada chamada da IA grande é pequena, um bloco ruim não
   derruba o arquivo e as chamadas rodam ao mesmo tempo.
2. LEITURA (IA grande, com esforço controlado e formato garantido): para cada bloco, a IA preenche os campos do
   layout do banco, com o trecho do documento que prova cada valor, e faz perguntas quando não tem certeza.
3. CONFERÊNCIA (sem IA, guardrail de saída, ADR-38): campo fora do layout é descartado; valor que não está no bloco é
   avisado; campo repetido vira dúvida.
4. CONFERIDOR (opcional, desligado por padrão; ADR-105): uma segunda IA procura erros de entendimento (o CPF de outra
   pessoa, datas trocadas); cada suspeita vira pergunta para a empresa (agents/conferidor_da_leitura.py).

A versão 1 (ADR-72) pedia a tabela inteira numa chamada só, com colunas de nome livre: num documento com 13 pessoas, a
IA "pensou" até o limite de tokens e a resposta veio vazia.

MEDIÇÃO (Acompanhamento dos agentes): cada leitura mede a execução do Leitor e, se ele rodou, a do Conferidor (quando
começou e terminou, se deu certo, modelo, versão do prompt). O Leitor NÃO grava no banco: a leitura acontece antes de
o envio existir (ainda não há número do envio nem conexão). Ele devolve as medições junto com o uso da IA
(tabela.uso["execucoes_dos_agentes"]) ou, se a IA cair, dentro do erro (IAIndisponivel.execucoes_dos_agentes); quem
cria o envio (services/processamentos.py) grava em execucoes_agentes. Nada pessoal entra na medição.
"""
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from agents import conferidor_da_leitura
from agents.interpretador import extrair_json
from models.contratos import CampoLayout, RespostaLeitorDeDocumentos, RespostaSegmentacao
from services import config, detector_de_dados, execucoes, guardrail_injecao, progresso, teto_de_gasto
# O erro "a IA não respondeu" (sem crédito, fora do ar, limite da operação): a leitura para, e a empresa é avisada para
# tentar de novo. Desde o ADR-145, ele mora no cliente de IA, que o levanta para todos os agentes; o nome continua valendo
# aqui (leitor_de_documentos.IAIndisponivel), para quem já o usava. As execuções medidas até a falha seguem nele
# (IAIndisponivel.execucoes_dos_agentes), preenchidas por ler(): quem cria o envio as grava
from services.llm_client import IAIndisponivel, LLMClient
from services.uso_da_ia import Uso

# Pasta raiz do projeto (para achar os prompts)
RAIZ = Path(__file__).resolve().parent.parent
# Versões dos prompts e nomes das tarefas no cliente de LLM
VERSAO_PROMPT = "leitor_de_documentos_v5"
VERSAO_PROMPT_SEGMENTACAO = "leitor_segmentacao_v2"
TAREFA = "ler_documento"
TAREFA_SEGMENTACAO = "dividir_documento"
# Quantos blocos são lidos ao mesmo tempo (chamadas em paralelo à IA)
LEITURAS_AO_MESMO_TEMPO = 4
# Uma linha "título" (que abre um bloco na divisão por regra) tem no máximo estas palavras
PALAVRAS_DE_UM_TITULO = 8
# Quantos rótulos diferentes de cada campo a tela mostra (os mais usados no documento)
ROTULOS_POR_CAMPO = 3
# Tamanho máximo de um rótulo na tela (um trecho maior é cortado)
TAMANHO_MAXIMO_DO_ROTULO = 40
# Como o Leitor aparece nas execuções (a coluna "agente") e qual etapa ele faz
NOME_DO_AGENTE = "Leitor de documentos"
ETAPA = "ler_texto_corrido"
# A chave, no uso da IA, com as execuções medidas nesta leitura (quem cria o envio as tira dali e grava)
CHAVE_DAS_EXECUCOES = "execucoes_dos_agentes"


def conferir_que_a_ia_respondeu(cliente: LLMClient, resposta) -> None:
    """Resposta simulada no modo real: levanta IAIndisponivel com o motivo (a leitura nunca usa a simulação).

    Só acontece com o MOCK de reserva ligado, na máquina local (ADR-145): sem ele, o próprio cliente de IA já levanta o
    erro. Mesmo com a reserva, a leitura de um documento não pode sair de uma regra de simulação como se fosse da IA
    (EXP-010: o crédito da conta acabou no meio da prova e o resultado saiu errado, sem aviso).
    """
    if cliente.modo == "llm" and resposta.modo == "mock":
        raise IAIndisponivel(resposta.motivo_fallback or "o provedor de IA não respondeu")


@dataclass
class TabelaDoDocumento:
    """A tabela que saiu do texto, já com os valores de verdade, e o que a empresa precisa saber."""

    colunas: list[str]                                      # os campos do layout encontrados, na ordem do layout
    funcionarios: list[list[str]]                           # uma lista por funcionário, com os valores reais
    duvidas: list[str] = field(default_factory=list)        # todas as perguntas, em texto ("Nome · campo: ...")
    # As perguntas sobre uma pessoa da tabela: {"registro": N (1 = primeira pessoa), "campo": ..., "pergunta": ...}.
    # Viram pendência na conferência, presas à pessoa e ao campo (a empresa corrige ou confirma)
    perguntas: list[dict] = field(default_factory=list)
    # O que não dá para prender a ninguém (ex.: um trecho que a IA não conseguiu ler): aparece nos detalhes da leitura
    duvidas_gerais: list[str] = field(default_factory=list)
    # Como a empresa chamou cada campo no documento: {campo: {"rotulos": ["Registro do cliente", ...], "pessoas": 12}}.
    # É a "coluna" do texto corrido: mostra o jeito da empresa virando o padrão do banco
    origem_das_colunas: dict = field(default_factory=dict)
    # O rótulo de cada valor, pessoa por pessoa (na mesma ordem de "funcionarios"): {campo: "Registro do cliente"}.
    # Com ele, a tela mostra cada jeito de a empresa chamar o dado numa linha própria (services/leitura_de_word.py)
    rotulos_das_pessoas: list[dict] = field(default_factory=list)
    uso: dict = field(default_factory=dict)                 # chamadas, modo, modelos, tokens e custo (sem dado pessoal)


# ============================== Prompts ==============================

@lru_cache(maxsize=4)
def carregar_prompt(versao: str) -> tuple[str, str]:
    """Devolve (sistema, pedido) do arquivo versionado em prompts/."""
    texto = (RAIZ / "prompts" / f"{versao}.md").read_text(encoding="utf-8")
    # Corta nas linhas que SÃO o título da seção (a introdução do arquivo cita "## SISTEMA" no meio do texto)
    _, sistema, pedido = re.split(r"^## (?:SISTEMA|PEDIDO)\s*$", texto, flags=re.M)
    return sistema.strip(), pedido.strip()


def descrever_layout(campos: list[CampoLayout]) -> str:
    """Os campos do layout, um por linha, com a descrição e o "não confundir com" (o parâmetro do banco)."""
    linhas = []
    for campo in campos:
        linha = f"- {campo.campo} ({campo.tipo.value}): {campo.descricao}"
        if campo.nao_confundir_com:
            linha += f"; não confundir com: {campo.nao_confundir_com}"
        linhas.append(linha)
    return "\n".join(linhas)


def esquema_da_resposta(campos: list[CampoLayout]) -> dict:
    """O formato garantido da resposta (esquema JSON): "campo" só pode ser um dos campos do layout."""
    nomes_dos_campos = []
    for campo in campos:
        nomes_dos_campos.append(campo.campo)
    campo_lido = {"type": "object", "additionalProperties": False, "required": ["campo", "valor", "trecho", "rotulo"],
                  "properties": {"campo": {"type": "string", "enum": nomes_dos_campos},
                                 "valor": {"type": "string"}, "trecho": {"type": "string"},
                                 "rotulo": {"type": "string"}}}
    duvida = {"type": "object", "additionalProperties": False, "required": ["campo", "pergunta"],
              "properties": {"campo": {"type": "string"}, "pergunta": {"type": "string"}}}
    funcionario = {"type": "object", "additionalProperties": False, "required": ["campos", "duvidas"],
                   "properties": {"campos": {"type": "array", "items": campo_lido},
                                  "duvidas": {"type": "array", "items": duvida}}}
    return {"type": "object", "additionalProperties": False, "required": ["funcionarios"],
            "properties": {"funcionarios": {"type": "array", "items": funcionario}}}


def linhas_numeradas(linhas: list[str]) -> str:
    """As linhas com o número na frente ("L1: ...", "L2: ..."), para a divisão em blocos apontar onde começa cada um."""
    numeradas = []
    for numero, linha in enumerate(linhas, start=1):
        numeradas.append(f"L{numero}: {linha}")
    return "\n".join(numeradas)


# ============================== 2. Blocos ==============================

def _parece_titulo(linha: str) -> bool:
    """True se a linha tem cara de título ou de nome solto: curta e sem ponto final nem dois-pontos no meio.

    Ex.: "FICHA 001", "Ana Lima", "DADOS DO RECRUTAMENTO" → True; "Admissão: 01/03/2026." → False.
    """
    texto = linha.strip()
    # Frase terminada em pontuação ("Olá, pessoal do banco!") não é título
    if not texto or texto.endswith((".", ";", ",", "!", "?")) or ":" in texto:
        return False
    return len(texto.split()) <= PALAVRAS_DE_UM_TITULO


def dividir_por_regra(linhas: list[str]) -> list[tuple[int, int]]:
    """Divide o documento em blocos sem IA. Devolve [(inicio, fim)], contando as linhas de 1.

    Regra: uma sequência de linhas com cara de título abre um bloco novo, que vai até o próximo título. As linhas
    antes do primeiro título formam um bloco próprio (a IA devolve "ninguém" se ali não há funcionário).
    Sem nenhum título (ex.: uma frase por pessoa), cada linha é um bloco.
    Ex.: ["Relação", "FICHA 001", "Ana Lima", "CPF 529.982.247-25.", "FICHA 002", "CPF 111.444.777-35."]
    → [(1, 4), (5, 6)]
    (títulos seguidos, como "Relação" + "FICHA 001" + nome, abrem um bloco só).
    """
    inicios = []
    for posicao, linha in enumerate(linhas):
        # Um título logo depois de outro título continua o mesmo começo de bloco (ex.: "FICHA 001" + nome)
        anterior_e_titulo = posicao > 0 and _parece_titulo(linhas[posicao - 1])
        if _parece_titulo(linha) and not anterior_e_titulo:
            inicios.append(posicao + 1)
    # Sem títulos: uma linha por bloco
    if not inicios:
        blocos = []
        for numero in range(1, len(linhas) + 1):
            blocos.append((numero, numero))
        return blocos
    blocos = []
    # Linhas antes do primeiro título (ex.: uma introdução sem título)
    if inicios[0] > 1:
        blocos.append((1, inicios[0] - 1))
    for posicao, inicio in enumerate(inicios):
        if posicao + 1 < len(inicios):
            fim = inicios[posicao + 1] - 1
        else:
            fim = len(linhas)
        blocos.append((inicio, fim))
    return blocos


def _blocos_validos(resposta: RespostaSegmentacao, quantidade_de_linhas: int) -> list[tuple[int, int]]:
    """Os blocos da IA, conferidos: dentro do documento, na ordem e sem sobreposição. Levanta ValueError se não."""
    blocos = []
    fim_anterior = 0
    for bloco in resposta.blocos:
        if not (1 <= bloco.inicio <= bloco.fim <= quantidade_de_linhas):
            raise ValueError(f"bloco fora do documento: {bloco.inicio}-{bloco.fim}")
        if bloco.inicio <= fim_anterior:
            raise ValueError("blocos sobrepostos ou fora de ordem")
        blocos.append((bloco.inicio, bloco.fim))
        fim_anterior = bloco.fim
    if not blocos:
        raise ValueError("nenhum bloco")
    return blocos


def emendar_blocos(blocos: list[tuple[int, int]], quantidade_de_linhas: int) -> list[tuple[int, int]]:
    """Cada bloco vai do começo dele até a linha antes do próximo (o último, até o fim do documento).

    Por que: a IA pequena às vezes deixa de fora a linha do endereço ou do contato, que não tem o nome da pessoa
    (EXP-010, rodada 1: 23 erros de telefone, e-mail e CEP). Da resposta dela, vale só onde cada pessoa
    COMEÇA. Linhas antes da primeira pessoa (título, saudação) continuam de fora.
    Ex.: [(3, 4), (7, 8)] num documento de 10 linhas → [(3, 6), (7, 10)].
    """
    emendados = []
    for posicao, (inicio, _) in enumerate(blocos):
        if posicao + 1 < len(blocos):
            fim = blocos[posicao + 1][0] - 1
        else:
            fim = quantidade_de_linhas
        emendados.append((inicio, fim))
    return emendados


def dividir_em_blocos(linhas: list[str], cliente: LLMClient, uso: dict) -> list[tuple[int, int]]:
    """Pede à IA pequena onde começa cada pessoa e emenda os blocos. Se a resposta não servir, a regra divide."""
    sistema, pedido = carregar_prompt(VERSAO_PROMPT_SEGMENTACAO)
    pedido = pedido.replace("{documento}", linhas_numeradas(linhas))
    resposta = cliente.gerar(TAREFA_SEGMENTACAO, pedido, sistema, modelo="pequeno", temperatura=0.0)
    conferir_que_a_ia_respondeu(cliente, resposta)
    _somar_uso(uso, resposta)
    try:
        blocos = _blocos_validos(RespostaSegmentacao.model_validate_json(extrair_json(resposta.texto)), len(linhas))
        return emendar_blocos(blocos, len(linhas))
    except ValueError:
        # A IA pequena não serviu: a regra divide (e isso fica registrado)
        uso["divisao_por_regra"] = True
        return dividir_por_regra(linhas)


# ============================== 3. Leitura de cada bloco ==============================

def _somar_uso(uso: dict, resposta) -> None:
    """Soma a chamada no resumo de uso: quantidade, modo, modelos, tokens e custo (nada pessoal)."""
    uso["chamadas"] = uso.get("chamadas", 0) + 1
    uso["modo"] = resposta.modo
    modelos = uso.setdefault("modelos", [])
    if resposta.modelo not in modelos:
        modelos.append(resposta.modelo)
    for chave, valor in (("tokens_entrada", resposta.tokens_entrada), ("tokens_saida", resposta.tokens_saida),
                         ("custo_usd", resposta.custo_usd)):
        if valor is not None:
            uso[chave] = uso.get(chave, 0) + valor
    if resposta.cortada:
        uso["respostas_cortadas"] = uso.get("respostas_cortadas", 0) + 1


def ler_bloco(bloco: str, campos: list[CampoLayout], cliente: LLMClient,
              esforco: str) -> tuple[RespostaLeitorDeDocumentos | None, list]:
    """Pede à IA grande os campos de um bloco. Até duas tentativas.

    Devolve (resposta no contrato, ou None se as duas falharem; as respostas da IA, para somar o uso depois).
    O uso não é somado aqui porque vários blocos são lidos ao mesmo tempo: a soma é feita no fim, num lugar só.
    """
    chamadas = []
    sistema, pedido = carregar_prompt(VERSAO_PROMPT)
    sistema = sistema.replace("{layout}", descrever_layout(campos))
    pedido = pedido.replace("{bloco}", bloco)
    esquema = esquema_da_resposta(campos)
    pedido_da_tentativa = pedido
    for tentativa in (1, 2):
        resposta = cliente.gerar(TAREFA, pedido_da_tentativa, sistema, modelo="grande", temperatura=0.0,
                                 esforco=esforco, esquema_json=esquema)
        chamadas.append(resposta)
        conferir_que_a_ia_respondeu(cliente, resposta)
        try:
            return RespostaLeitorDeDocumentos.model_validate_json(extrair_json(resposta.texto)), chamadas
        except ValueError as erro:
            motivo = "a resposta foi cortada no limite de tamanho" if resposta.cortada else str(erro).split("\n")[0]
            pedido_da_tentativa = (pedido + f"\n\nSua resposta anterior foi rejeitada: {motivo}. "
                                   "Responda apenas com o JSON pedido, de forma curta.")
    return None, chamadas


# ============================== 4. Conferência ==============================

def pedaco_do_bloco(valor: str, bloco: str) -> str | None:
    """O pedaço do bloco que é o valor que a IA apontou, copiado do próprio documento. None se não houver.

    Regra "a IA aponta, o código copia" (ADR-73, passo 4):
    o valor que entra no cadastro é SEMPRE um pedaço contínuo do texto que a empresa mandou, recortado daqui, e nunca
    o texto que a IA escreveu. Por que isso importa: o documento da empresa continua sendo a referência dela. Se a IA
    trocasse "carteira de identidade" por "RG", ou juntasse palavras de lugares diferentes, a pessoa procuraria no
    arquivo algo que não existe lá e não conseguiria achar a informação original para corrigir. Recortando do
    documento, o que aparece na tela é sempre algo que ela encontra no arquivo dela.
    Aceita diferença só de maiúsculas e de espaços; a ordem e a continuidade das palavras precisam ser as do texto.
    Ex. (bloco "... como Analista de Sistemas, ..."): "analista de sistemas" → "Analista de Sistemas";
    "Sistemas Analista" → None; "RG" (o texto diz "carteira de identidade") → None.
    """
    pedacos_do_valor = valor.split()
    if not pedacos_do_valor:
        return None
    # O molde: os pedaços do valor, na mesma ordem, separados por qualquer espaço (e só por espaço)
    pedacos_escapados = []
    for pedaco in pedacos_do_valor:
        pedacos_escapados.append(re.escape(pedaco))
    # (?<!\w) e (?!\w): o valor começa e termina em palavra inteira ("RG" não vale dentro de "órgão")
    molde = r"(?<!\w)" + r"\s+".join(pedacos_escapados) + r"(?!\w)"
    encontrado = re.search(molde, bloco, re.IGNORECASE)
    if encontrado is None:
        return None
    return bloco[encontrado.start():encontrado.end()]


def conferir_rotulo(rotulo: str, bloco: str) -> str:
    """O rótulo que a IA devolveu (como a empresa chamou o dado), conferido contra o documento (ADR-105).

    A IA aponta, o código copia: o rótulo só vale se for um pedaço do próprio documento, sem dado nenhum (número ou
    e-mail) e sem ser só palavras de ligação. Senão, fica "": o dado foi achado pelo lugar no texto.
    Ex. (bloco "Registro do cliente 529.982.247-25"): "registro do cliente" → "Registro do cliente";
    "CPF" (a palavra não está no bloco) → ""; "Registro 529.982.247-25" → "" (tem um dado); "A" → "".
    """
    rotulo = rotulo.strip(" .,;:=|-–—()[]\"'")
    if not rotulo:
        return ""
    # Só vale o que está escrito no documento (com a grafia do documento)
    copiado = pedaco_do_bloco(rotulo, bloco)
    if copiado is None:
        return ""
    # Número ou e-mail no rótulo é dado, não rótulo
    if re.search(r"\d", copiado) or "@" in copiado:
        return ""
    # Só palavras de ligação ("A", "O", "Também temos o"): não é rótulo
    if detector_de_dados.so_palavras_de_ligacao(copiado):
        return ""
    return copiado[:TAMANHO_MAXIMO_DO_ROTULO].strip()


def origem_das_colunas(rotulos_por_campo: dict[str, Counter], pessoas_por_campo: Counter) -> dict:
    """Junta, por campo, os rótulos mais usados e em quantas pessoas o campo apareceu."""
    origem = {}
    for campo, quantidade in pessoas_por_campo.items():
        rotulos = []
        for rotulo, _ in rotulos_por_campo.get(campo, Counter()).most_common(ROTULOS_POR_CAMPO):
            rotulos.append(rotulo)
        origem[campo] = {"rotulos": rotulos, "pessoas": quantidade}
    return origem


def _nome_para_a_pergunta(campos_lidos: dict[str, str], numero: int) -> str:
    """Como a pessoa aparece na pergunta: o nome lido ou "Pessoa N"."""
    return campos_lidos.get("nome_completo") or f"Pessoa {numero}"


def _quem_e_para_a_empresa(bloco: str) -> str:
    """Como a pessoa SEM nome lido aparece para a empresa nos detalhes da leitura: pelo começo do trecho dela.

    "Pessoa 5" não diz nada para quem lê a tela. Ex.: "Contratamos a nova analista..." →
    'a pessoa do trecho que começa em "Contratamos a nova analista..."'.
    """
    # A primeira linha do trecho, curta
    primeira_linha = bloco.split("\n")[0].strip()
    return f"a pessoa do trecho que começa em \"{primeira_linha[:60]}\""


def onde_esta_no_documento(pedaco: str, bloco: str, primeira_linha: int) -> str:
    """Onde a empresa acha o pedaço no arquivo dela: o número do parágrafo e o começo dele.

    Recebe: o pedaço (como está no bloco); o bloco; primeira_linha — o número do parágrafo em que o bloco começa
    (contando só os parágrafos com texto, como a leitura conta). Devolve, ex.: 'parágrafo 7, que começa com "A Ana
    Lima foi contratada"'. Sem achar o pedaço, aponta o começo do trecho da pessoa.
    """
    for deslocamento, linha in enumerate(bloco.split("\n")):
        if pedaco and pedaco in linha:
            # O começo do parágrafo, para a empresa achar no arquivo
            comeco = linha.strip()[:50]
            return f"parágrafo {primeira_linha + deslocamento}, que começa com \"{comeco}\""
    # Sem achar o pedaço: o começo do trecho da pessoa
    comeco = bloco.split("\n")[0].strip()[:50]
    return f"trecho que começa no parágrafo {primeira_linha} (\"{comeco}\")"


def pergunta_do_trecho_para_conferir(trecho_de_verdade: str, onde: str) -> str:
    """A pergunta quando a IA não separou só o valor: o campo fica com o texto do documento, como está, para conferir.

    Nunca apagar: a empresa vê o que está no arquivo dela, no lugar em que está, e deixa só o valor ou confirma.
    """
    return (f"O Agente Leitor não conseguiu separar só o valor deste campo. Para você não perder a referência do seu "
            f"arquivo, ele deixou o texto como está no documento: \"{trecho_de_verdade[:80]}\" ({onde}). Deixe só o "
            "valor certo ou confirme se está certo assim.")


def pergunta_do_valor_que_nao_esta_no_documento(onde: str) -> str:
    """A pergunta quando nem o valor nem o trecho que a IA citou estão no documento: não há texto original a mostrar.

    O campo fica sem valor porque nada do arquivo sustenta o que a IA escreveu (inventar seria pior), e a pergunta
    diz onde procurar.
    """
    return (f"O Agente Leitor indicou este campo no {onde}, mas o que ele escreveu não está assim no documento. "
            "Confira esse trecho do seu arquivo e informe o valor certo.")


def conferir_pessoa(funcionario, bloco: str, campos: list[CampoLayout],
                    primeira_linha: int = 1) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Confere os campos de uma pessoa. Devolve ({campo: valor de verdade}, [(campo, pergunta)]).

    O dicionário vem vazio se não sobrou nenhum campo. Tudo o que a conferência acha (valor que não está no documento,
    dois valores para o mesmo campo, dúvida da IA) vira pergunta: ela volta para quem chamou, que a prende à pessoa
    (ou, se a pessoa não entrou, às dúvidas gerais).
    primeira_linha: o parágrafo do documento em que o bloco começa (para a pergunta dizer onde achar).
    Todo valor aceito é recortado do bloco (pedaco_do_bloco): a IA aponta, o código copia.
    """
    nomes_do_layout = set()
    for campo in campos:
        nomes_do_layout.add(campo.campo)
    campos_lidos = {}
    campos_repetidos = set()
    # Os campos em que a IA escreveu algo que não está no documento: {campo: o trecho que ela citou}
    campos_fora_do_documento = {}
    # Os campos que ficaram com o trecho do documento, como está, para a empresa conferir: {campo: o trecho}
    campos_com_trecho_para_conferir = {}
    # O rótulo que a empresa usou para cada campo desta pessoa
    rotulos = {}
    for campo_lido in funcionario.campos:
        valor = campo_lido.valor.strip()
        # Campo que não existe no layout ou valor vazio: descartado
        if campo_lido.campo not in nomes_do_layout or not valor:
            continue
        # A IA aponta, o código copia: o valor é recortado do documento (ver pedaco_do_bloco)
        copiado = pedaco_do_bloco(valor, bloco)
        if copiado is None:
            # O valor não é um pedaço do documento (a IA trocou a palavra, reformatou ou juntou partes). Nunca apagar:
            # se o trecho que ela citou está no documento, o campo fica com ele, como está, para a empresa conferir
            trecho_copiado = pedaco_do_bloco(campo_lido.trecho.strip(), bloco)
            if trecho_copiado is None:
                campos_fora_do_documento[campo_lido.campo] = campo_lido.trecho.strip()
                continue
            campos_com_trecho_para_conferir[campo_lido.campo] = trecho_copiado
            copiado = trecho_copiado
        valor = copiado
        # O mesmo campo duas vezes com valores diferentes: vira dúvida
        if campo_lido.campo in campos_lidos and campos_lidos[campo_lido.campo] != valor:
            campos_repetidos.add(campo_lido.campo)
            continue
        campos_lidos[campo_lido.campo] = valor
        # Como a empresa chamou o dado: o rótulo que a IA devolveu, conferido contra o documento
        rotulos[campo_lido.campo] = conferir_rotulo(campo_lido.rotulo, bloco)
    # O campo repetido sai: a empresa diz qual valor é o certo
    for campo in campos_repetidos:
        campos_lidos.pop(campo, None)
    valores = campos_lidos
    perguntas = []
    # O campo ficou com o trecho do documento, como está: a empresa confere, sabendo onde achar no arquivo
    for campo, trecho in campos_com_trecho_para_conferir.items():
        if campo in valores:
            onde = onde_esta_no_documento(trecho, bloco, primeira_linha)
            perguntas.append((campo, pergunta_do_trecho_para_conferir(valores[campo], onde)))
    # Nem o valor nem o trecho estão no documento: a pergunta diz onde procurar
    for campo, trecho_citado in campos_fora_do_documento.items():
        onde = onde_esta_no_documento(trecho_citado, bloco, primeira_linha)
        perguntas.append((campo, pergunta_do_valor_que_nao_esta_no_documento(onde)))
    for campo in sorted(campos_repetidos):
        perguntas.append((campo, "O documento traz dois valores diferentes para este campo. Qual é o certo?"))
    for duvida in funcionario.duvidas:
        # Pergunta sobre um campo que não existe no layout vira pergunta sobre a pessoa
        campo_da_duvida = duvida.campo if duvida.campo in nomes_do_layout else ""
        perguntas.append((campo_da_duvida, duvida.pergunta.strip()))
    # O rótulo de cada campo que ficou (vai junto, com a chave "_rotulos", e sai antes de montar a tabela)
    rotulos_que_ficaram = {}
    for campo in valores:
        rotulos_que_ficaram[campo] = rotulos.get(campo, "")
    if valores:
        valores["_rotulos"] = rotulos_que_ficaram
    return valores, perguntas


def conferir_o_bloco(bloco: str, pessoas: list[dict], pessoas_do_bloco: list[int], campos: list[CampoLayout],
                     cliente: LLMClient, tabela: TabelaDoDocumento, medicoes_do_conferidor: list[dict]) -> None:
    """Pede ao Conferidor da Leitura as suspeitas do bloco e prende cada uma à pessoa e ao campo (ADR-105).

    Recebe: o bloco; todas as pessoas lidas; as posições (1 = primeira) das pessoas deste bloco; os campos; o cliente
    de IA; a tabela (ganha as perguntas e o uso); medicoes_do_conferidor (ganha a medição desta conferência). O
    conferidor vê só o bloco e os valores lidos (sem os rótulos).
    """
    valores_do_bloco = []
    for posicao in pessoas_do_bloco:
        valores = {}
        for campo, valor in pessoas[posicao - 1].items():
            # "_rotulos" é controle interno, não um campo lido
            if campo != "_rotulos":
                valores[campo] = valor
        valores_do_bloco.append(valores)
    suspeitas, resposta, medicao = conferidor_da_leitura.conferir_e_medir(bloco, valores_do_bloco, campos, cliente)
    if resposta is not None:
        _somar_uso(tabela.uso, resposta)
    # A medição desta conferência (o Leitor junta as de todos os blocos numa execução só do Conferidor)
    if medicao is not None:
        medicoes_do_conferidor.append(medicao)
    tabela.uso["suspeitas_do_conferidor"] = tabela.uso.get("suspeitas_do_conferidor", 0) + len(suspeitas)
    for suspeita in suspeitas:
        registro = pessoas_do_bloco[suspeita.pessoa - 1]
        pergunta = conferidor_da_leitura.pergunta_da_suspeita(suspeita)
        tabela.perguntas.append({"registro": registro, "campo": suspeita.campo, "pergunta": pergunta})
        tabela.duvidas.append(f"Pessoa {registro} · {suspeita.campo}: {pergunta}")


def guardar_perguntas(tabela: TabelaDoDocumento, perguntas: list[tuple[str, str]], nome: str,
                      registro: int | None, quem_e: str = "") -> None:
    """Guarda as perguntas de uma pessoa: presas a ela (registro = posição na tabela) ou, sem pessoa, nas gerais.

    nome: como a pessoa entra no registro das dúvidas (o nome ou "Pessoa N", usado pela régua do EXP-010);
    quem_e: como ela aparece para a empresa nos detalhes da leitura (sem informar, vale o nome).
    """
    for campo, pergunta in perguntas:
        # A pergunta é texto livre da IA e vai para a tela da empresa: link sai (um link de golpe na dúvida levaria a
        # empresa para um site falso)
        pergunta = guardrail_injecao.tirar_links(pergunta)
        rotulo = f" · {campo}" if campo else ""
        texto = f"{nome}{rotulo}: {pergunta}"
        tabela.duvidas.append(texto)
        if registro is None:
            # A empresa lê "a pessoa do trecho que começa em ...", nunca "Pessoa 5"
            tabela.duvidas_gerais.append(f"{quem_e or nome}{rotulo}: {pergunta}")
        else:
            tabela.perguntas.append({"registro": registro, "campo": campo, "pergunta": pergunta})


# Os tipos de dado que, soltos num parágrafo, indicam um funcionário (um título ou uma saudação não têm nenhum)
TIPOS_QUE_INDICAM_PESSOA = ("CPF", "DATA", "VALOR", "CEP", "TELEFONE", "CELULAR", "EMAIL", "DOCUMENTO")


def _paragrafo_tem_dado(linha: str) -> bool:
    """True se o parágrafo tem um dado de pessoa (CPF, data, valor, CEP, telefone, e-mail ou documento).

    Usa o detector de services/detector_de_dados.py só para PROCURAR: ele marca os dados numa cópia do parágrafo, e a
    cópia serve apenas para esta pergunta (nada daqui vai para a IA).
    """
    linha_marcada = detector_de_dados.marcar(linha).texto
    for etiqueta in detector_de_dados.etiquetas_do_texto(linha_marcada):
        if etiqueta[1:].split("_")[0] in TIPOS_QUE_INDICAM_PESSOA:
            return True
    return False


def avisar_paragrafos_com_dado_fora_dos_blocos(linhas: list[str], blocos: list[tuple[int, int]],
                                              tabela: TabelaDoDocumento) -> None:
    """Avisa cada parágrafo com dado de pessoa que não entrou em nenhum bloco (ninguém se perde calado).

    Ex.: 'O parágrafo 12 tem dados ("CPF 529.982.247-25, admitido em ..."), mas não entrou em nenhuma pessoa.'
    """
    dentro_de_algum_bloco = set()
    for inicio, fim in blocos:
        for numero in range(inicio, fim + 1):
            dentro_de_algum_bloco.add(numero)
    for numero, linha in enumerate(linhas, start=1):
        if numero in dentro_de_algum_bloco or not _paragrafo_tem_dado(linha):
            continue
        # O começo do parágrafo, para a empresa achar no arquivo
        comeco = linha.strip()[:60]
        texto = (f"O parágrafo {numero} tem dados (\"{comeco}\"), mas não entrou em nenhuma pessoa. Confira se "
                 "alguém ficou de fora.")
        tabela.duvidas.append(texto)
        tabela.duvidas_gerais.append(texto)


# ============================== O agente ==============================

def _agora() -> datetime:
    """O horário de agora, em UTC (o relógio das medições)."""
    return datetime.now(timezone.utc)


def _uso_do_leitor(resumo_do_uso: dict, medicoes_do_conferidor: list[dict]) -> Uso:
    """O uso só do Leitor: o total da leitura (divisão em blocos, leitura e conferência) menos o do Conferidor.

    Ex.: total de 3 chamadas e US$ 0,030, Conferidor com 1 chamada e US$ 0,002 → Leitor com 2 chamadas e US$ 0,028.
    """
    total = Uso(chamadas=resumo_do_uso.get("chamadas", 0), tokens_entrada=resumo_do_uso.get("tokens_entrada"),
                tokens_saida=resumo_do_uso.get("tokens_saida"), custo_usd=resumo_do_uso.get("custo_usd"))
    do_conferidor = Uso()
    for medicao in medicoes_do_conferidor:
        do_conferidor.somar_uso(Uso.do_dicionario(medicao.get("uso")))
    return total.menos(do_conferidor)


def execucao_do_leitor(inicio: datetime, fim: datetime, status: str, modelos: list[str], cliente: LLMClient,
                       tipo_erro: str | None = None) -> dict:
    """A execução do Leitor numa leitura, pronta para services/execucoes.registrar (horários em texto ISO).

    Recebe: o começo e o fim da leitura; o status (OK ou ERRO); os modelos que responderam ao Leitor (a divisão usa o
    pequeno e a leitura o grande: os dois entram, separados por vírgula); o cliente de IA; o tipo do erro, se houve.
    Sem nenhum modelo anotado (a IA caiu na primeira chamada), no modo simulado vale "mock" (a origem fica MOCK); no
    real fica vazio (a origem fica REAL, porque a chamada foi à IA de verdade).
    Ex.: {"agente": "Leitor de documentos", "etapa": "ler_texto_corrido", "status": "OK", "modelo": "mock", ...}.
    O guardrail de entrada (parágrafos com cara de ordem para a IA) age antes do Leitor, em services/leitura_de_word.py,
    que marca "guardrail_disparado" quando tirou algum parágrafo.
    """
    modelo = ", ".join(modelos)
    if not modelo and cliente.modo == "mock":
        modelo = "mock"
    return {"agente": NOME_DO_AGENTE, "etapa": ETAPA, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
            "status": status, "tipo_erro": tipo_erro, "modelo": modelo or None,
            "versao_prompt": f"{VERSAO_PROMPT}, {VERSAO_PROMPT_SEGMENTACAO}", "guardrail_disparado": False}


def ler(texto_do_documento: str, campos: list[CampoLayout], cliente: LLMClient,
        esforco: str | None = None, conferir_com_outra_ia: bool | None = None) -> TabelaDoDocumento:
    """Lê o texto corrido e devolve a TabelaDoDocumento (colunas = campos do layout encontrados).

    A IA recebe o texto como a empresa mandou (ADR-101).
    esforco: o quanto a IA grande "pensa" em cada bloco ("low", "medium", "high"); padrão do .env.
    conferir_com_outra_ia: liga o Conferidor da Leitura (ADR-105); padrão do .env (desligado).
    Medição: tabela.uso["execucoes_dos_agentes"] leva a execução do Leitor (OK) e, se ele rodou, a do Conferidor. Se
    a IA cair, o erro IAIndisponivel leva a execução do Leitor com ERRO (e a do Conferidor, se ele já tinha rodado).
    """
    if esforco is None:
        esforco = config.LEITOR_ESFORCO
    if conferir_com_outra_ia is None:
        conferir_com_outra_ia = config.CONFERIDOR_DA_LEITURA
    tabela = TabelaDoDocumento(colunas=[], funcionarios=[])
    tabela.uso = {"esforco": esforco}
    # Os modelos que responderam ao Leitor (anotados antes do Conferidor, que soma o uso dele no mesmo lugar)
    modelos_do_leitor = []
    # A medição de cada conferência de bloco (vazia se o Conferidor não rodou)
    medicoes_do_conferidor = []
    inicio = _agora()
    try:
        _montar_a_tabela(texto_do_documento, campos, cliente, esforco, conferir_com_outra_ia, tabela,
                         modelos_do_leitor, medicoes_do_conferidor)
    except (IAIndisponivel, teto_de_gasto.TetoDeGastoAtingido) as erro:
        # A IA caiu (ou foi pausada pelo teto de gasto; ADR-131) no meio da leitura: se ainda não chegou ao
        # Conferidor, valem os modelos anotados até ali
        if not modelos_do_leitor:
            modelos_do_leitor = list(tabela.uso.get("modelos", []))
        # O tipo do erro na Telemetria: a pausa pelo teto tem o seu, para o banco saber que foi o teto
        if isinstance(erro, teto_de_gasto.TetoDeGastoAtingido):
            tipo_do_erro = execucoes.TIPO_DA_PAUSA_PELO_TETO
        else:
            tipo_do_erro = execucoes.TIPO_DA_QUEDA
        execucao = execucao_do_leitor(inicio, _agora(), execucoes.ERRO, modelos_do_leitor, cliente,
                                      tipo_erro=tipo_do_erro)
        erro.execucoes_dos_agentes = _com_a_do_conferidor(execucao, medicoes_do_conferidor, tabela.uso)
        raise
    execucao = execucao_do_leitor(inicio, _agora(), execucoes.OK, modelos_do_leitor, cliente)
    tabela.uso[CHAVE_DAS_EXECUCOES] = _com_a_do_conferidor(execucao, medicoes_do_conferidor, tabela.uso)
    return tabela


def _com_a_do_conferidor(execucao_do_leitor_medida: dict, medicoes_do_conferidor: list[dict],
                         resumo_do_uso: dict) -> list[dict]:
    """A lista das execuções da leitura: a do Leitor e, se o Conferidor rodou, a dele (os blocos juntos numa só).

    resumo_do_uso: o uso da leitura inteira (tabela.uso), em que o Leitor e o Conferidor somam juntos. A execução do
    Leitor ganha o uso dele: o total menos a parte do Conferidor, que vai na execução do Conferidor (ADR-131).
    """
    execucao_do_leitor_medida["uso"] = _uso_do_leitor(resumo_do_uso, medicoes_do_conferidor).em_dicionario()
    execucoes_da_leitura = [execucao_do_leitor_medida]
    execucao_do_conferidor = conferidor_da_leitura.juntar_as_medicoes(medicoes_do_conferidor)
    if execucao_do_conferidor is not None:
        execucoes_da_leitura.append(execucao_do_conferidor)
    return execucoes_da_leitura


def _montar_a_tabela(texto_do_documento: str, campos: list[CampoLayout], cliente: LLMClient, esforco: str,
                     conferir_com_outra_ia: bool, tabela: TabelaDoDocumento, modelos_do_leitor: list[str],
                     medicoes_do_conferidor: list[dict]) -> None:
    """O trabalho da leitura (blocos, leitura, conferência e colunas), preenchendo a tabela recebida.

    Recebe, além do que ler() recebe: a tabela (já com o esforço no uso), que ganha tudo o que foi lido;
    modelos_do_leitor, que ganha os modelos que responderam ao Leitor; medicoes_do_conferidor, que ganha a medição de
    cada bloco conferido. Levanta IAIndisponivel se a IA cair.
    """
    # Um parágrafo por linha
    linhas = texto_do_documento.split("\n")
    # 1. Blocos, um por pessoa
    progresso.anotar("É um texto corrido: o Agente Leitor está separando o texto por pessoa.")
    blocos = dividir_em_blocos(linhas, cliente, tabela.uso)
    textos_dos_blocos = []
    for inicio, fim in blocos:
        textos_dos_blocos.append("\n".join(linhas[inicio - 1:fim]))
    tabela.uso["blocos"] = len(blocos)
    # Nenhum parágrafo com dado se perde calado: o que não entrou em pessoa nenhuma vira aviso
    avisar_paragrafos_com_dado_fora_dos_blocos(linhas, blocos, tabela)
    # 2. Leitura dos blocos, vários ao mesmo tempo
    progresso.anotar(f"O Agente Leitor está lendo {len(textos_dos_blocos)} trecho(s) do texto.")
    with ThreadPoolExecutor(max_workers=LEITURAS_AO_MESMO_TEMPO) as executor:
        tarefas = []
        for bloco in textos_dos_blocos:
            tarefas.append(executor.submit(ler_bloco, bloco, campos, cliente, esforco))
        respostas = []
        for tarefa in tarefas:
            resposta, chamadas = tarefa.result()
            respostas.append(resposta)
            # A tela mostra quantas já foram lidas (a espera é na ordem do texto)
            progresso.anotar(f"O Agente Leitor leu {len(respostas)} de {len(textos_dos_blocos)} trecho(s).")
            # O uso de cada leitura é somado aqui, uma de cada vez
            for chamada in chamadas:
                _somar_uso(tabela.uso, chamada)
    # Os modelos do Leitor, anotados antes de o Conferidor somar o uso dele
    modelos_do_leitor.extend(tabela.uso.get("modelos", []))
    # 3. Conferência, pessoa por pessoa
    progresso.anotar("Conferindo cada valor com o documento.")
    pessoas = []
    for numero_do_bloco, resposta in enumerate(respostas, start=1):
        bloco = textos_dos_blocos[numero_do_bloco - 1]
        if resposta is None:
            # O começo do trecho que não foi lido, para a empresa achar no arquivo
            primeira_linha = bloco.split("\n")[0]
            texto = f"Não consegui ler o trecho que começa em \"{primeira_linha[:80]}\". Confira se alguém ficou de fora."
            tabela.duvidas.append(texto)
            tabela.duvidas_gerais.append(texto)
            continue
        # As pessoas deste bloco, pela posição na tabela (para o conferidor prender cada suspeita à pessoa certa)
        pessoas_do_bloco = []
        for funcionario in resposta.funcionarios:
            valores, perguntas = conferir_pessoa(funcionario, bloco, campos, blocos[numero_do_bloco - 1][0])
            nome = _nome_para_a_pergunta(valores, len(pessoas) + 1)
            if valores:
                pessoas.append(valores)
                pessoas_do_bloco.append(len(pessoas))
                guardar_perguntas(tabela, perguntas, nome, len(pessoas))
            else:
                # Sem nenhum valor, a pessoa não entra: a empresa vê o começo do trecho dela
                guardar_perguntas(tabela, perguntas, nome, None, _quem_e_para_a_empresa(bloco))
        # 4. O conferidor (se ligado): uma segunda IA procura erros de entendimento neste bloco
        if conferir_com_outra_ia and pessoas_do_bloco:
            conferir_o_bloco(bloco, pessoas, pessoas_do_bloco, campos, cliente, tabela, medicoes_do_conferidor)
    # Como a empresa chamou cada campo e em quantas pessoas ele apareceu (a "coluna" do texto corrido)
    rotulos_por_campo = {}
    pessoas_por_campo = Counter()
    for pessoa in pessoas:
        rotulos_da_pessoa = pessoa.pop("_rotulos")
        # Guarda o rótulo de cada valor desta pessoa (a tela mostra cada jeito de chamar o dado numa linha)
        tabela.rotulos_das_pessoas.append(rotulos_da_pessoa)
        for campo, rotulo in rotulos_da_pessoa.items():
            pessoas_por_campo[campo] += 1
            if rotulo:
                rotulos_por_campo.setdefault(campo, Counter())[rotulo] += 1
    tabela.origem_das_colunas = origem_das_colunas(rotulos_por_campo, pessoas_por_campo)
    # As colunas: os campos encontrados em alguém, na ordem do layout
    for campo in campos:
        for pessoa in pessoas:
            if campo.campo in pessoa:
                tabela.colunas.append(campo.campo)
                break
    for pessoa in pessoas:
        linha = []
        for coluna in tabela.colunas:
            linha.append(pessoa.get(coluna, ""))
        tabela.funcionarios.append(linha)


# ============================== Simulação (modo MOCK) ==============================

def _documento_do_pedido(prompt: str) -> str:
    """O texto entre <documento_da_empresa> e </documento_da_empresa> do pedido."""
    inicio = prompt.find("<documento_da_empresa>") + len("<documento_da_empresa>")
    fim = prompt.find("</documento_da_empresa>")
    return prompt[inicio:fim].strip()


def simular_divisao(prompt: str) -> str:
    """MOCK da divisão em blocos: a mesma regra de dividir_por_regra, no formato da resposta da IA."""
    linhas = []
    for linha in _documento_do_pedido(prompt).split("\n"):
        # Tira o "L12: " da frente
        linhas.append(re.sub(r"^L\d+: ", "", linha))
    blocos = []
    for inicio, fim in dividir_por_regra(linhas):
        blocos.append({"inicio": inicio, "fim": fim})
    return json.dumps({"blocos": blocos})


def _primeira(padrao: str, texto: str) -> str:
    """O primeiro trecho que casa com o padrão (o grupo 1), ou "" se não houver."""
    encontrado = re.search(padrao, texto, flags=re.IGNORECASE)
    if encontrado is None:
        return ""
    return encontrado.group(1).strip()


def _trecho_em_volta(bloco: str, valor: str) -> str:
    """O trecho de prova do simulador: até 25 caracteres antes do valor e o valor (ex.: ", CPF 529.982.247-25")."""
    posicao = bloco.find(valor)
    if posicao < 0:
        return valor
    return bloco[max(0, posicao - 25):posicao + len(valor)]


def _rotulo_simulado(trecho_marcado: str, valor_marcado: str) -> str:
    """MOCK: o rótulo que a IA devolveria, por regra, a partir do trecho já marcado pelo detector.

    Fica o último pedaço antes do valor, depois do último separador ou da última marca de dado; só palavras de ligação
    não é rótulo. Ex.: ("Registro do cliente [CPF_1]", "[CPF_1]") → "Registro do cliente";
    ("A [TEXTO_1] [TEXTO_2], CPF [CPF_1]", "[CPF_1]") → "CPF"; ("entrou em [DATA_1]", "[DATA_1]") → "entrou em".
    """
    # O que vem antes do valor (sem achar o valor no trecho, vale o trecho inteiro)
    posicao = trecho_marcado.find(valor_marcado)
    antes = trecho_marcado[:posicao] if posicao >= 0 else trecho_marcado
    # Só o último pedaço, depois do último separador ou da última marca
    pedacos = re.split(r"[,;|/()]|" + detector_de_dados.PADRAO_DA_ETIQUETA.pattern, antes)
    rotulo = pedacos[-1].strip(" .,;:=|-–—()[]\"'") if pedacos else ""
    if detector_de_dados.so_palavras_de_ligacao(rotulo):
        return ""
    return rotulo


def simular_leitura(prompt: str) -> str:
    """MOCK do Leitor: uma regra simples que imita a IA, para testes e demo sem custo.

    Para achar os dados, o simulador marca uma CÓPIA do bloco com o detector de services/detector_de_dados.py (o nome
    vira [TEXTO_1] [TEXTO_2], o CPF vira [CPF_1]...) e usa regras sobre essas marcas: o nome são as primeiras marcas de
    palavra seguidas; o CPF, a primeira marca de CPF; a admissão, a data depois de "entrou", "admiss", "começou" ou "contrat";
    o salário, o primeiro valor em R$; o cargo, as palavras depois de "como". Depois troca as marcas de volta pelos
    valores reais: a resposta traz os dados como estão no documento, igual à IA de verdade. Sem CPF, vira pergunta.
    """
    bloco_real = _documento_do_pedido(prompt)
    # A cópia marcada serve só para achar os dados (nada dela sai do simulador)
    copia_marcada = detector_de_dados.marcar(bloco_real)
    bloco = copia_marcada.texto
    if "[CPF_" not in bloco and "[DATA_" not in bloco and "[VALOR_" not in bloco and "R$" not in bloco:
        return json.dumps({"funcionarios": []})
    achados = {
        "nome_completo": _primeira(r"(\[TEXTO_\d+\](?: \[TEXTO_\d+\])*)", bloco),
        "cpf": _primeira(r"(\[CPF_\d+\])", bloco),
        "data_admissao": _primeira(r"(?:entrou|admiss\w*|come\w+|contrat\w*)\D{0,20}(\[DATA_\d+\])", bloco),
        "data_nascimento": _primeira(r"nasc\w*\D{0,20}(\[DATA_\d+\])", bloco),
        "valor_renda": _primeira(r"(\[VALOR_\d+\]|R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", bloco),
        "cargo": _primeira(r"\bcomo ([a-zà-ú ]+?)(?=\s*[,.;(]|$)", bloco),
    }
    campos = []
    for campo, valor in achados.items():
        if valor:
            # O trecho em volta do valor, achado na cópia marcada
            trecho = _trecho_em_volta(bloco, valor)
            # As marcas voltam a ser os valores reais do documento; o rótulo já não tem marca nenhuma
            valor_real = detector_de_dados.desmarcar(valor, copia_marcada.valor_da_etiqueta)
            trecho_real = detector_de_dados.desmarcar(trecho, copia_marcada.valor_da_etiqueta)
            campos.append({"campo": campo, "valor": valor_real, "trecho": trecho_real,
                           "rotulo": _rotulo_simulado(trecho, valor)})
    duvidas = []
    if not achados["cpf"]:
        duvidas.append({"campo": "cpf", "pergunta": "Não encontrei o CPF desta pessoa. Pode mandar? (simulação MOCK)"})
    return json.dumps({"funcionarios": [{"campos": campos, "duvidas": duvidas}]}, ensure_ascii=False)


def cliente_padrao() -> LLMClient:
    """Cliente do modo configurado; no MOCK, a divisão e a leitura são simuladas por regra.

    A conferência também tem a sua simulação (não desconfia de nada): sem ela, o Conferidor receberia o texto genérico
    do MOCK, que não é JSON, e a medição contaria um erro que não existe (o resultado da leitura é o mesmo: sem suspeitas).
    """
    return LLMClient(respostas_mock={TAREFA: simular_leitura, TAREFA_SEGMENTACAO: simular_divisao,
                                     conferidor_da_leitura.TAREFA: conferidor_da_leitura.simular_conferencia})
