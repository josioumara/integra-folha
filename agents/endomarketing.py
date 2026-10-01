"""Agente de Endomarketing: o especialista do BANCO gera os materiais que a empresa vai divulgar (ADR-19, ADR-115).

Quem gera é o banco, não a empresa (ADR-115): assim nenhuma empresa divulga um benefício do Santander sem
a validação do Santander. O especialista escolhe a empresa, o tipo de material (comunicado interno, FAQ, kit de
boas-vindas ou lembrete para abrir a conta, este sempre para toda a equipe), o canal (e-mail, mural ou WhatsApp, que
decide o tamanho), QUAIS BENEFÍCIOS do catálogo da empresa entram e, se quiser, algo a destacar. O agente:
1. confere o destaque com o guardrail de injeção (texto digitado é dado, nunca instrução);
2. junta os trechos do catálogo SÓ da empresa escolhida, SÓ dos documentos vigentes e SÓ dos benefícios escolhidos
   (mais os canais de atendimento, que fecham todo material);
3. pede ao LLM um rascunho em blocos, cada bloco citando a sua fonte, no FORMATO GARANTIDO (ADR-150): o esquema do
   JSON vai junto com o pedido, e o provedor obriga o modelo a segui-lo; a resposta fora do formato ganha uma segunda
   tentativa, com o motivo. No prompt v5 (o padrão; a chave ENDOMARKETING_COM_AS_KBS=nao volta para a v3), o pedido
   leva também o tom de voz e os termos proibidos das KBs gerais publicadas, a assinatura do kit em uso (o nome da
   empresa no kit próprio; nada no kit padrão) e a lista dos benefícios escolhidos;
4. confere a saída (guardrail): bloco sem fonte, com fonte que não veio dos trechos, com número ou link que não
   está no trecho citado ou com um termo proibido é removido; o título com um termo proibido vira o nome do tipo.
   Um benefício escolhido que ficou sem bloco ganha a frase do próprio catálogo, com a fonte, e o canal limita o
   número de blocos sem tirar conteúdo (o WhatsApp junta os blocos a mais no último).
   Destaque que os benefícios escolhidos não trazem é recusado, e a tela diz isso;
5. guarda o RASCUNHO. O especialista confere e PUBLICA (só então a empresa vê e baixa) ou descarta; um material
   publicado pode ser RETIRADO depois (ex.: o benefício mudou).

Também informa quantos funcionários da empresa ainda não têm conta (só o total), para sugerir o lembrete.
Sem benefícios escolhidos (chamada antiga, usada pela avaliação), as buscas de cada tipo vão ao catálogo pelo RAG.
No modo MOCK, o simulador no fim deste arquivo monta o rascunho copiando os trechos do catálogo.
"""
import base64
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from models.contratos import EstadoProcessamento, TipoCarga
from rag import busca as busca_rag
from rag.trechos import trechos_catalogo
from services import (banco, catalogo, config, contas_abertas, execucoes, guardrail_injecao, homologacao,
                      kbs_endomarketing, processamentos, teto_de_gasto, uso_da_ia)
# O cadastro das empresas: o nome da empresa é a assinatura do kit próprio
from services import empresas as cadastro_de_empresas
from services.llm_client import LLMClient
# A IA real que não respondeu (ADR-145): o material não é gerado, e nada é simulado no lugar
from services.llm_client import IAIndisponivel

# Pasta raiz do projeto (para achar o prompt)
RAIZ = Path(__file__).resolve().parent.parent
# As versões do prompt. A v5 é a padrão (ADR-150): a v4 (o tom de voz e os termos proibidos das KBs gerais publicadas e
# a assinatura do kit em uso) mais a lista dos benefícios escolhidos, que aparecem todos em qualquer canal. A chave
# ENDOMARKETING_COM_AS_KBS=nao volta para a v3, que fica como histórico
VERSAO_PROMPT = "endomarketing_v5"
VERSAO_PROMPT_ANTERIOR = "endomarketing_v3"
# Os tipos de KB que o prompt lê (desde a v4): o tom de voz e os termos proibidos (KBs gerais) e o kit da marca (da
# empresa)
TIPO_DO_TOM_DE_VOZ, TIPO_DOS_TERMOS_PROIBIDOS, TIPO_DO_KIT = "tom_de_voz", "termos_proibidos", "kit_da_marca"
TAREFA = "endomarketing_gerar"
# Os tipos de material e as buscas feitas no catálogo para cada um
TIPOS = {
    "comunicado": {"nome": "Comunicado interno",
                   "buscas": ["conta salário e tarifas", "benefícios da conta corrente", "crédito consignado",
                              "onde consultar e canais de dúvidas"]},
    "faq": {"nome": "FAQ para funcionários",
            "buscas": ["conta salário e portabilidade", "benefícios da conta corrente", "crédito consignado",
                       "canais de dúvidas e atendimento"]},
    "kit_boas_vindas": {"nome": "Kit de boas-vindas",
                        "buscas": ["conta salário", "como abrir conta e benefícios", "canais de dúvidas"]},
    # Para TODA a equipe: o banco não informa à empresa quem tem conta (sigilo bancário, ADR-30); ADR-93
    "lembrete_conta": {"nome": "Lembrete para abrir a conta",
                       "buscas": ["como abrir a conta salário", "conta salário e tarifas", "benefícios da conta corrente",
                                  "canais de dúvidas"]},
}
# O título de cada tipo, sem número nem promessa: usado pelo simulador e no lugar de um título da IA que inventou um
# número ou um link (o título passa pela mesma conferência dos blocos)
TITULO_PADRAO_DO_TIPO = {"comunicado": "Comunicado: os benefícios do banco para a nossa equipe",
                         "faq": "Perguntas frequentes: conta e benefícios",
                         "kit_boas_vindas": "Boas-vindas: sua conta salário e os seus benefícios",
                         "lembrete_conta": "Lembrete para toda a equipe: abra a sua conta e aproveite os benefícios"}
# Os canais: o nome e quantos blocos cabem (None = sem limite). O canal muda o tamanho, nunca o conteúdo (ADR-93): os
# blocos que passam do limite se juntam ao último que cabe, e nenhum benefício escolhido sai do material (ADR-150)
CANAIS = {
    "email": {"nome": "E-mail", "maximo_de_blocos": None},
    "mural": {"nome": "Mural ou intranet", "maximo_de_blocos": None},
    "whatsapp": {"nome": "WhatsApp", "maximo_de_blocos": 3},
}
# O canal quando a tela não diz qual
CANAL_PADRAO = "email"
# Quantos trechos cada busca traz
TRECHOS_POR_BUSCA = 2
# O destaque é comparado com UMA seção do catálogo, a mais parecida com ele: se ela entrou no material, o destaque está
# coberto. Com as duas mais parecidas, a segunda quase sempre caía numa seção que entra em todo material (o atendimento)
# ou num benefício escolhido parecido, e o aviso de destaque fora do catálogo não saía
SECOES_COMPARADAS_COM_O_DESTAQUE = 1
# A distância máxima para a seção mais parecida valer como o assunto do destaque (0 = idêntico; 2 = oposto). Fica no
# corte geral do catálogo até a medição da separação entre "o catálogo tem" e "não tem" nos destaques; só vale um valor
# menor que ele, porque a busca do catálogo já corta no geral
DISTANCIA_MAXIMA_DO_DESTAQUE = busca_rag.DISTANCIA_MAXIMA_CATALOGO
# Quantas vezes o material é pedido quando a resposta da IA não vem no formato combinado (a segunda leva o motivo)
TENTATIVAS_DO_FORMATO = 2
# As situações de um pedido de material
GERADO, SEM_EVIDENCIA, RECUSADO, FALHA = "GERADO", "SEM_EVIDENCIA", "RECUSADO", "FALHA"
# O catálogo ainda não foi indexado neste servidor (ex.: antes de rodar scripts/build_index.py)
INDISPONIVEL = "INDISPONIVEL"
# As situações de um material guardado (ADR-115): o rascunho do banco vira PUBLICADO (a empresa vê) ou DESCARTADO;
# o publicado pode ser RETIRADO (a empresa deixa de ver). APROVADO é do modelo anterior, em que a própria empresa
# aprovava: esses materiais ficam no histórico do banco, mas a empresa não os vê mais
RASCUNHO, PUBLICADO, DESCARTADO, RETIRADO, APROVADO = "RASCUNHO", "PUBLICADO", "DESCARTADO", "RETIRADO", "APROVADO"
# O nome de cada situação na tela do banco
NOME_DA_SITUACAO = {RASCUNHO: "Rascunho", PUBLICADO: "Publicado para a empresa", DESCARTADO: "Descartado",
                    RETIRADO: "Retirado da empresa", APROVADO: "Aprovado pela empresa (modelo anterior)"}


# ---------------- Contrato da resposta do LLM ----------------

class Bloco(BaseModel):
    """Um trecho do material e as fontes de onde ele saiu.

    Todo bloco precisa de pelo menos uma fonte, mas quem cobra isso é a conferência (conferir_material): o bloco sem
    fonte sai com a observação, e o resto do material continua. Se a regra ficasse aqui, um bloco sem fonte derrubaria
    a leitura da resposta inteira.
    """

    texto: str
    fontes: list[str] = []


class MaterialGerado(BaseModel):
    """O rascunho: título, blocos com fonte e o que foi pedido mas não está no catálogo."""

    titulo: str
    blocos: list[Bloco] = []
    nao_encontrado: list[str] = []


def esquema_da_resposta() -> dict:
    """O formato garantido da resposta (esquema JSON): o mesmo contrato de MaterialGerado (ADR-150).

    Com ele, o provedor obriga o modelo a devolver um JSON que segue o esquema. É o que acaba com a resposta perdida por
    um JSON quebrado: sem ele, a IA copiava do catálogo um nome entre aspas retas sem o escape, e o texto do JSON
    fechava no meio. O conteúdo continua conferido pelo código (as fontes, os números, os links e os termos proibidos).
    Todo objeto exige todos os campos e não aceita outros ("additionalProperties": false), como o Bedrock pede. A regra
    "pelo menos uma fonte por bloco" fica na conferência, porque o formato garantido não aceita limite no tamanho de
    uma lista.
    """
    # Um bloco: o texto e a lista das fontes citadas
    bloco = {"type": "object", "additionalProperties": False, "required": ["texto", "fontes"],
             "properties": {"texto": {"type": "string"},
                            "fontes": {"type": "array", "items": {"type": "string"}}}}
    # O material: o título, os blocos e o que o destaque pediu e os trechos não trazem
    return {"type": "object", "additionalProperties": False, "required": ["titulo", "blocos", "nao_encontrado"],
            "properties": {"titulo": {"type": "string"},
                           "blocos": {"type": "array", "items": bloco},
                           "nao_encontrado": {"type": "array", "items": {"type": "string"}}}}


def ler_resposta(texto: str) -> MaterialGerado:
    """Lê a resposta da IA no contrato do material. Fora do contrato: ValueError com o motivo numa linha.

    Recebe: o texto que a IA devolveu. Com o formato garantido, ele já é o JSON do esquema; sem ele (um provedor que
    não aceita o esquema), o JSON é procurado do primeiro "{" ao último "}".
    Devolve: o MaterialGerado.
    Exemplo: '{"titulo": "Oi", "blocos": [], "nao_encontrado": []}' → MaterialGerado(titulo="Oi", ...);
             '{"titulo": "Na área "Menu""}' → ValueError("Invalid JSON: ...").
    """
    # Do primeiro "{" ao último "}": tira cercas de código e texto em volta
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("a resposta não trouxe um objeto JSON")
    try:
        return MaterialGerado.model_validate_json(texto[inicio:fim + 1])
    except ValidationError as erro:
        # Só o primeiro problema, com o lugar dele (ex.: "Field required (em blocos.0.texto)")
        primeiro_problema = erro.errors()[0]
        partes_do_lugar = []
        for parte in primeiro_problema["loc"]:
            partes_do_lugar.append(str(parte))
        motivo = primeiro_problema["msg"]
        if partes_do_lugar:
            motivo = motivo + " (em " + ".".join(partes_do_lugar) + ")"
        raise ValueError(motivo) from erro


@dataclass
class ResultadoDoPedido:
    """O que volta para a tela: a situação, o rascunho guardado (se houver) e as observações."""

    situacao: str
    mensagem: str
    material_id: str | None = None
    material: dict | None = None
    observacoes: list[str] = field(default_factory=list)
    modelo: str | None = None               # o modelo que redigiu (None se o LLM nem foi chamado)


# ---------------- O resumo da equipe (só agregado) ----------------

def consultar_resumo_equipe(conexao, empresa_id: str) -> dict:
    """Quantos funcionários da empresa ainda não têm conta confirmada: o total, para o comunicado (ADR-102).

    São os Cadastrados que ainda aguardam o retorno do banco (o arquivo de contas ainda não trouxe a conta deles),
    pela conta única das contas (services/contas_abertas.py, retorno_da_empresa): o mesmo número em todas as telas.
    Devolve: {"quantidade": 12, "texto": "12"}.
    """
    sem_conta = contas_abertas.retorno_da_empresa(conexao, empresa_id)["aguardando_retorno"]
    return {"quantidade": sem_conta, "texto": str(sem_conta)}


# ---------------- A busca no catálogo ----------------

def _buscar_no_catalogo(empresa_id: str, consulta: str, busca, k: int) -> list[dict]:
    """Uma busca no catálogo da empresa. busca: a função de busca (a do RAG, ou uma falsa nos testes)."""
    if busca is None:
        # Buscado pelo módulo na hora da chamada: os testes podem trocar a função
        return busca_rag.buscar_beneficios(empresa_id, consulta, dia=date.today(), k=k)
    return busca(empresa_id, consulta, k=k)


def _trechos_do_material(empresa_id: str, tipo: str, destaque: str, busca) -> tuple[list[dict], list[str]]:
    """Os trechos do catálogo para o material (sem repetir fonte) e os destaques que o catálogo não traz."""
    trechos, fontes_vistas, nao_encontrados = [], set(), []
    consultas = []
    if destaque:
        # O destaque vem primeiro: se o catálogo não trouxer nada sobre ele, a empresa fica sabendo
        destaques = _buscar_no_catalogo(empresa_id, destaque, busca, TRECHOS_POR_BUSCA)
        if not destaques:
            nao_encontrados.append(destaque)
        consultas.append(destaques)
    for consulta in TIPOS[tipo]["buscas"]:
        consultas.append(_buscar_no_catalogo(empresa_id, consulta, busca, TRECHOS_POR_BUSCA))
    for resultado_da_busca in consultas:
        for trecho in resultado_da_busca:
            # Defesa extra: um trecho de outra empresa nunca entra (a busca já filtra)
            if trecho.get("empresa_id", empresa_id) != empresa_id:
                continue
            if trecho["fonte"] not in fontes_vistas:
                fontes_vistas.add(trecho["fonte"])
                trechos.append(trecho)
    return trechos, nao_encontrados


def beneficios_do_catalogo(conexao, empresa_id: str) -> list[str]:
    """Os nomes dos benefícios do catálogo vigente da empresa (as seções, sem as de atendimento), sem repetir.

    Recebe: conexao; empresa_id. Devolve: ex.: ["Conta salário", "Crédito consignado", "Seguro de vida"].
    São esses nomes que o especialista marca na tela para dizer o que entra em cada material.
    """
    nomes = []
    # Cada documento vigente da empresa, e cada seção dele
    for documento in catalogo.documentos_vigentes(conexao, empresa_id):
        for secao in catalogo.secoes_do_documento(documento["conteudo_md"]):
            # Os canais de atendimento não são benefício: entram sempre, no fim do material
            if secao["titulo"] in catalogo.SECOES_DE_ATENDIMENTO:
                continue
            # O mesmo benefício em dois documentos aparece uma vez só
            if secao["titulo"] not in nomes:
                nomes.append(secao["titulo"])
    return nomes


def _trechos_dos_beneficios_escolhidos(conexao, empresa_id: str, beneficios: list[str]) -> list[dict]:
    """Os trechos do catálogo vigente da empresa que falam dos benefícios escolhidos, mais os de atendimento.

    Recebe: conexao; empresa_id (a empresa escolhida pelo especialista); beneficios (os nomes marcados na tela).
    Devolve: [{fonte, texto, empresa_id}], um por seção, no formato que a busca do RAG devolve (a primeira linha do
    texto é a fonte). Uma seção longa, que o índice guarda em vários pedaços, volta num trecho só.
    Levanta ValueError se nada foi escolhido ou se um nome não é benefício do catálogo vigente da empresa.
    Por que sem a busca do RAG: aqui não há o que procurar, o especialista já disse quais seções entram. A regra do
    RAG continua: só o catálogo desta empresa e só o que está vigente.
    """
    # Pelo menos um benefício: o material existe para divulgar algo que o banco escolheu
    if not beneficios:
        raise ValueError("Escolha pelo menos um benefício para o material.")
    # Cada nome precisa ser um benefício do catálogo vigente desta empresa (a tela manda os nomes)
    disponiveis = beneficios_do_catalogo(conexao, empresa_id)
    for nome in beneficios:
        if nome not in disponiveis:
            raise ValueError(f"O benefício \"{nome}\" não está no catálogo vigente desta empresa.")
    # As seções que entram: as escolhidas e as de atendimento
    secoes_que_entram = set(beneficios) | set(catalogo.SECOES_DE_ATENDIMENTO)
    # Os mesmos pedaços que o índice do RAG guarda, cortados do catálogo vigente da empresa
    pedacos = trechos_catalogo(catalogo.documentos_vigentes(conexao, empresa_id))
    trecho_da_fonte = {}
    for pedaco in pedacos:
        # Só as seções que entram no material
        if pedaco.metadados["secao"] not in secoes_que_entram:
            continue
        fonte = pedaco.metadados["fonte"]
        # O primeiro pedaço de uma seção vira o trecho dela
        if fonte not in trecho_da_fonte:
            trecho_da_fonte[fonte] = {"fonte": fonte, "texto": pedaco.texto, "empresa_id": empresa_id}
        else:
            # Os pedaços seguintes da mesma seção são somados ao trecho, sem repetir a linha da fonte
            continuacao = pedaco.texto.split("\n", 1)[1]
            trecho_da_fonte[fonte]["texto"] += "\n" + continuacao
    return list(trecho_da_fonte.values())


def _destaques_fora_da_escolha(empresa_id: str, destaque: str, trechos: list[dict], busca) -> list[str]:
    """Confere se o destaque digitado está no que entrou no material. Devolve [destaque] se não está, senão [].

    Recebe: empresa_id; destaque (pode ser vazio); trechos (os dos benefícios escolhidos e os do atendimento, que
    entram em todo material); busca (a do RAG ou a falsa dos testes).
    Duas regras, nesta ordem:
    1. o destaque cita pelo nome uma seção que entrou (um benefício escolhido ou um canal de atendimento): está
       coberto. O nome escrito vale mais que a semelhança, porque a busca confunde nomes parecidos (ex.: "conta
       salário" fica mais perto de "salário antecipado" do que da própria seção "Conta salário");
    2. senão, decide a seção do catálogo mais parecida com o destaque: se ela entrou no material, está coberto; se é
       outra seção, ou se nem a mais parecida está perto o bastante, os benefícios escolhidos não trazem o assunto.
    Exemplo: benefícios escolhidos "Conta salário"; destaque "seguro de vida" → ["seguro de vida"] (a tela avisa e
    nada é escrito sobre isso); destaque "reforce que a conta salário não tem tarifa" → [].
    """
    # Sem destaque, nada a conferir
    if not destaque:
        return []
    # As fontes e os nomes das seções que entraram no material
    fontes_escolhidas = set()
    nomes_das_secoes = []
    for trecho in trechos:
        fontes_escolhidas.add(trecho["fonte"])
        nomes_das_secoes.append(_titulo_da_secao(trecho["fonte"]))
    # 1. O destaque cita pelo nome uma seção que entrou
    if _termos_como_palavras_inteiras(destaque, nomes_das_secoes):
        return []
    # 2. A seção mais parecida com o destaque precisa ser uma das que entraram, e estar perto o bastante
    for encontrado in _buscar_no_catalogo(empresa_id, destaque, busca, SECOES_COMPARADAS_COM_O_DESTAQUE):
        # A busca do RAG já corta no limite geral do catálogo; o do destaque pode ser mais apertado. Sem a distância
        # (a busca por palavras dos testes não mede), vale o que a busca trouxe
        distancia = encontrado.get("distancia", 0.0)
        if distancia <= DISTANCIA_MAXIMA_DO_DESTAQUE and encontrado["fonte"] in fontes_escolhidas:
            return []
    return [destaque]


def _conteudo(trecho: dict) -> str:
    """O texto do trecho numa linha só, sem a primeira linha (que repete a fonte).

    Por que numa linha: o pedido lista um trecho por linha, cada um com a fonte na frente; uma segunda linha solta
    perderia a fonte. A linha "Categoria: ..." serve só à vitrine e fica de fora; "### Como funciona" vira
    "Como funciona:".
    Exemplo: "Aurora › Seguro\nCategoria: Proteção\nCondição especial.\n### Como funciona\nCobertura por morte."
             → "Condição especial. Como funciona: Cobertura por morte."
    """
    linhas = []
    # Pula a primeira linha (a fonte) e junta as outras
    for linha in trecho["texto"].split("\n")[1:]:
        limpa = linha.strip()
        # Linha vazia e a da categoria ficam de fora
        if not limpa or limpa.startswith(catalogo.MARCA_DA_CATEGORIA):
            continue
        # O título de uma parte vira o começo da frase
        if limpa.startswith("### "):
            limpa = limpa[4:].strip() + ":"
        linhas.append(limpa)
    return " ".join(linhas)


# ---------------- O guardrail de saída ----------------

def _numeros(texto: str) -> list[str]:
    """Os números de um texto, só com dígitos (ex.: "0800 000 0001" vira "0800", "000", "0001")."""
    return re.findall(r"\d+", texto)


def fonte_sem_colchetes(fonte: str) -> str:
    """A fonte sem espaços e sem os colchetes em volta. Ex.: "[Pacote v1 › Conta salário]" → "Pacote v1 › Conta salário"."""
    fonte = fonte.strip()
    if fonte.startswith("[") and fonte.endswith("]"):
        fonte = fonte[1:-1].strip()
    return fonte


def conferir_material(material: MaterialGerado, trechos: list[dict]) -> tuple[list[dict], list[str]]:
    """Os blocos que passam na conferência e as observações sobre os que foram removidos.

    Um bloco passa se cita pelo menos uma fonte, se TODAS as fontes dele vieram da busca e se todo número e todo link
    do texto estão nos trechos citados (um prazo "24 meses" que o catálogo diz ser "12 meses" é barrado).
    """
    conteudo_da_fonte = {}
    for trecho in trechos:
        conteudo_da_fonte[trecho["fonte"]] = trecho["texto"]
    aprovados, observacoes = [], []
    for bloco in material.blocos:
        # O bloco sem fonte sai: toda afirmação precisa dizer de qual trecho do catálogo veio
        if not bloco.fontes:
            observacoes.append("Bloco removido: não cita nenhuma fonte do catálogo.")
            continue
        fontes_desconhecidas = []
        texto_das_fontes = ""
        # A IA real às vezes copia a fonte com os colchetes do pedido: "[Pacote... › Conta salário]" (achado do
        # primeiro teste com IA real); a conferência compara a fonte sem eles
        fontes_do_bloco = []
        for fonte_citada in bloco.fontes:
            fontes_do_bloco.append(fonte_sem_colchetes(fonte_citada))
        bloco = Bloco(texto=bloco.texto, fontes=fontes_do_bloco)
        for fonte in bloco.fontes:
            if fonte not in conteudo_da_fonte:
                fontes_desconhecidas.append(fonte)
            else:
                texto_das_fontes += " " + conteudo_da_fonte[fonte]
        if fontes_desconhecidas:
            observacoes.append(f"Bloco removido: cita uma fonte que não veio do catálogo ({fontes_desconhecidas[0]}).")
            continue
        numeros_das_fontes = set(_numeros(texto_das_fontes))
        numeros_sem_fonte = []
        for numero in _numeros(bloco.texto):
            if numero not in numeros_das_fontes:
                numeros_sem_fonte.append(numero)
        if numeros_sem_fonte:
            observacoes.append(f"Bloco removido: o número {numeros_sem_fonte[0]} não está no trecho citado.")
            continue
        # Link que não está no trecho citado derruba o bloco, como o número inventado: um link de golpe
        # chegaria aos funcionários da empresa com a cara de um comunicado do banco
        links_sem_fonte = _links_que_nao_estao_nas_fontes(bloco.texto, texto_das_fontes)
        if links_sem_fonte:
            observacoes.append(f"Bloco removido: o link {links_sem_fonte[0]} não está no trecho citado.")
            continue
        aprovados.append({"texto": bloco.texto, "fontes": bloco.fontes})
    return aprovados, observacoes


def _links_que_nao_estao_nas_fontes(texto: str, texto_das_fontes: str) -> list[str]:
    """Os links do texto que não aparecem no texto das fontes citadas. Lista vazia: nenhum link inventado.

    Os dois lados são comparados sem a pontuação da frase colada no fim do link (guardrail_injecao.links_no_texto).
    Exemplo: "Abra pelo site https://golpe.exemplo.com" com fontes sem esse endereço → ["https://golpe.exemplo.com"];
             "Veja em https://beneficios.exemplo/rh, e tire as dúvidas" com a fonte "https://beneficios.exemplo/rh" → [].
    """
    # Os links que aparecem nas fontes (os únicos que podem ir para o material)
    links_das_fontes = guardrail_injecao.links_no_texto(texto_das_fontes)
    # Cada link do texto que não está entre eles
    inventados = []
    for link in guardrail_injecao.links_no_texto(texto):
        if link not in links_das_fontes:
            inventados.append(link)
    return inventados


def conferir_titulo(titulo: str, tipo: str, trechos: list[dict]) -> tuple[str, list[str]]:
    """O título conferido como os blocos: número e link só se estiverem no catálogo.

    Recebe: o título que a IA escreveu, o tipo do material e os trechos do catálogo que a busca trouxe.
    Devolve: (o título que vai para o material, as observações). Se o título inventa um número ou um link, ele é
    trocado pelo título padrão do tipo, e a observação diz o porquê.
    Exemplo: "Isenção total de tarifas por 36 meses" com um catálogo sem "36" → o título padrão do comunicado.
    """
    # O texto de todos os trechos do catálogo que a busca trouxe
    texto_do_catalogo = ""
    for trecho in trechos:
        texto_do_catalogo = texto_do_catalogo + " " + trecho["texto"]
    # Os números do catálogo, para comparar com os do título
    numeros_do_catalogo = set(_numeros(texto_do_catalogo))
    # Um número do título que o catálogo não tem
    for numero in _numeros(titulo):
        if numero not in numeros_do_catalogo:
            return TITULO_PADRAO_DO_TIPO[tipo], [f"Título trocado pelo padrão: o número {numero} não está no catálogo."]
    # Um link do título que o catálogo não tem
    links_inventados = _links_que_nao_estao_nas_fontes(titulo, texto_do_catalogo)
    if links_inventados:
        return TITULO_PADRAO_DO_TIPO[tipo], [f"Título trocado pelo padrão: o link {links_inventados[0]} não está no "
                                             "catálogo."]
    # Passou: o título da IA fica
    return titulo, []


def _sem_acento_e_minusculo(texto: str) -> str:
    """O texto sem acento, em minúsculas e com um espaço só entre as palavras, para comparar sem ligar para a grafia.

    É a mesma comparação que a trava das KBs faz (services/kbs_endomarketing.py).
    Exemplo: "Aprovação  IMEDIATA" → "aprovacao imediata".
    """
    # Separa cada letra do acento dela e joga o acento fora
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    # Minúsculas, e os espaços, as quebras de linha e as tabulações viram um espaço só
    return " ".join(sem_acento.lower().split())


def termos_proibidos_no_texto(texto: str, termos: list[str]) -> list[str]:
    """Os termos proibidos que aparecem no texto, na ordem da lista (vazio se nenhum aparece).

    Recebe: texto (o título ou um bloco do material); termos (a lista da KB de termos proibidos).
    A regra é a mesma da trava das KBs: o termo como palavra inteira, sem ligar para acento nem para maiúsculas.
    Exemplo: ("Crédito com APROVACAO IMEDIATA", ["garantido", "aprovação imediata"]) → ["aprovação imediata"].
    E "garantidos" não é o termo "garantido": a palavra inteira é outra.
    """
    return _termos_como_palavras_inteiras(texto, termos)


def _termos_como_palavras_inteiras(texto: str, termos: list[str]) -> list[str]:
    """Os termos que aparecem no texto como palavras inteiras, na ordem da lista, sem ligar para acento nem maiúsculas.

    Recebe: o texto e a lista dos termos. Devolve: os termos encontrados (vazio se nenhum aparece).
    Serve aos termos proibidos e aos nomes das seções citados num destaque.
    Exemplo: ("reforce que a CONTA SALARIO não tem tarifa", ["Conta salário", "Crédito"]) → ["Conta salário"].
    """
    # O texto e cada termo são comparados sem acento e em minúsculas
    texto_comparado = _sem_acento_e_minusculo(texto)
    encontrados = []
    for termo in termos:
        # O termo inteiro: sem letra nem número colado antes ou depois dele
        padrao_do_termo = r"(?<![a-z0-9])" + re.escape(_sem_acento_e_minusculo(termo)) + r"(?![a-z0-9])"
        if re.search(padrao_do_termo, texto_comparado):
            encontrados.append(termo)
    return encontrados


def conferir_termos_proibidos(titulo: str, blocos: list[dict], termos: list[str],
                              titulo_neutro: str) -> tuple[str, list[dict], list[str]]:
    """Barra o termo proibido no texto gerado: o bloco que usa um sai, e o título que usa um é trocado.

    Recebe: titulo e blocos (os que já passaram na conferência das fontes); termos (a lista da KB de termos
    proibidos); titulo_neutro (o nome do tipo de material, que entra no lugar de um título barrado).
    Devolve: (o título, os blocos que ficam, as observações). Cada observação diz o termo que barrou.
    Exemplo: o bloco "Crédito garantido para todos." com "garantido" na lista sai, com a observação
    'Bloco removido: usa o termo proibido "garantido".'
    """
    observacoes = []
    # O título com um termo proibido vira o nome do tipo: o material continua, com um título neutro
    termos_do_titulo = termos_proibidos_no_texto(titulo, termos)
    if termos_do_titulo:
        observacoes.append(f"Título trocado pelo nome do material: usava o termo proibido \"{termos_do_titulo[0]}\".")
        titulo = titulo_neutro
    blocos_que_ficam = []
    for bloco in blocos:
        termos_do_bloco = termos_proibidos_no_texto(bloco["texto"], termos)
        # O bloco sai inteiro: trocar só a palavra poderia mudar o sentido do que a fonte diz
        if termos_do_bloco:
            observacoes.append(f"Bloco removido: usa o termo proibido \"{termos_do_bloco[0]}\".")
            continue
        blocos_que_ficam.append(bloco)
    return titulo, blocos_que_ficam, observacoes


# ---------------- Os benefícios escolhidos e o tamanho do canal (ADR-150) ----------------

def _primeira_frase(texto: str) -> str:
    """A primeira frase do texto: até o primeiro ponto seguido de espaço (o texto inteiro, se não houver).

    Exemplo: "Conta sem tarifa. Portabilidade sem custo." → "Conta sem tarifa."
    """
    # O ponto que fecha a frase vem seguido de espaço: o de "1.500" ou o de um endereço de site não fecha
    fim_da_frase = texto.find(". ")
    if fim_da_frase < 0:
        return texto
    return texto[:fim_da_frase + 1]


def _trechos_da_secao(trechos: list[dict], secao: str) -> list[dict]:
    """Os trechos de uma seção (a mesma seção pode vir de mais de um documento do catálogo)."""
    da_secao = []
    for trecho in trechos:
        if _titulo_da_secao(trecho["fonte"]) == secao:
            da_secao.append(trecho)
    return da_secao


def _algum_ja_citado(trechos: list[dict], blocos: list[dict]) -> bool:
    """True se algum bloco cita a fonte de algum dos trechos."""
    # As fontes que os blocos citam
    fontes_citadas = set()
    for bloco in blocos:
        fontes_citadas.update(bloco["fontes"])
    for trecho in trechos:
        if trecho["fonte"] in fontes_citadas:
            return True
    return False


def _so_cita_o_atendimento(bloco: dict) -> bool:
    """True se todas as fontes do bloco são seções de atendimento (ex.: "Pacote › Canais de dúvidas")."""
    for fonte in bloco["fontes"]:
        if _titulo_da_secao(fonte) not in catalogo.SECOES_DE_ATENDIMENTO:
            return False
    return True


def _posicao_do_fechamento(blocos: list[dict]) -> int:
    """A posição onde começam os blocos do fim que só citam o atendimento (os canais que fecham o material).

    Devolve len(blocos) quando o último bloco fala de um benefício.
    Exemplo: [benefício, benefício, atendimento] → 2.
    """
    posicao = len(blocos)
    # Anda do fim para o começo enquanto o bloco só cita seções de atendimento
    while posicao > 0 and _so_cita_o_atendimento(blocos[posicao - 1]):
        posicao -= 1
    return posicao


def completar_os_beneficios(blocos: list[dict], beneficios: list[str], trechos: list[dict],
                            termos: list[str]) -> tuple[list[dict], list[str]]:
    """Todo benefício escolhido fica no material: o que ficou sem bloco ganha a frase do próprio catálogo, com a fonte.

    Recebe: blocos (os que passaram nas conferências); beneficios (os nomes marcados pelo especialista); trechos (os do
    catálogo que entraram no pedido); termos (a lista dos termos proibidos, que vale também para a frase nova).
    Devolve: (os blocos, com os novos logo antes do atendimento que fecha o material; as observações).
    Por quê: quem escolhe o que entra é o especialista. A IA pode deixar um benefício de fora (ex.: para caber no
    WhatsApp), ou a conferência pode tirar o bloco dele. A frase do catálogo é fiel por construção: o número e o link
    vêm da própria fonte.
    Exemplo: "Crédito consignado" escolhido e sem bloco → entra "Crédito consignado: Taxa negociada para a equipe."
    """
    novos, observacoes = [], []
    for beneficio in beneficios:
        trechos_do_beneficio = _trechos_da_secao(trechos, beneficio)
        # Já citado por um bloco (ou sem trecho no pedido): nada a completar
        if not trechos_do_beneficio or _algum_ja_citado(trechos_do_beneficio, blocos):
            continue
        # O nome do benefício e a primeira frase do trecho dele, sem o negrito do Markdown
        trecho = trechos_do_beneficio[0]
        texto = beneficio + ": " + _primeira_frase(_conteudo(trecho).replace("**", ""))
        # A frase nova também não pode usar um termo proibido
        termos_da_frase = termos_proibidos_no_texto(texto, termos)
        if termos_da_frase:
            observacoes.append(f"O benefício \"{beneficio}\" ficou fora do texto: a frase dele no catálogo usa o termo "
                               f"proibido \"{termos_da_frase[0]}\". Gere o material de novo.")
            continue
        novos.append({"texto": texto, "fontes": [trecho["fonte"]]})
        observacoes.append(f"O benefício \"{beneficio}\" não veio no texto do Agente de Endomarketing: entrou a frase "
                           "do catálogo, com a fonte.")
    # Os blocos novos entram antes dos blocos do atendimento, que fecham o material
    posicao = _posicao_do_fechamento(blocos)
    return blocos[:posicao] + novos + blocos[posicao:], observacoes


def ajustar_ao_canal(blocos: list[dict], canal: str) -> tuple[list[dict], list[str]]:
    """O material no tamanho do canal, sem tirar conteúdo: os blocos que passam do limite se juntam ao último que cabe.

    Recebe: os blocos já conferidos; o canal (a chave de CANAIS). Devolve: (os blocos, as observações).
    Por quê: o canal muda o tamanho, nunca o conteúdo (ADR-93). Cortar os blocos do fim tirava do material benefícios
    que o especialista escolheu; juntá-los mantém tudo, com as fontes de cada parte.
    Exemplo (WhatsApp, até 3 blocos): 5 blocos → o 1º, o 2º e um 3º com o texto e as fontes do 3º, do 4º e do 5º.
    """
    maximo = CANAIS[canal]["maximo_de_blocos"]
    # Sem limite, ou dentro dele: nada muda
    if maximo is None or len(blocos) <= maximo:
        return blocos, []
    # O último bloco que cabe recebe o texto e as fontes de todos os que passam do limite
    juntado = _juntar_blocos(blocos[maximo - 1:])
    observacao = (f"No {CANAIS[canal]['nome']}, cabem {maximo} trechos: os que passavam disso foram juntados ao "
                  "último, sem tirar nada do texto.")
    return blocos[:maximo - 1] + [juntado], [observacao]


def _juntar_blocos(blocos: list[dict]) -> dict:
    """Um bloco só com o texto de todos, em ordem, e as fontes de todos, sem repetir.

    Exemplo: [{"texto": "A.", "fontes": ["F1"]}, {"texto": "B.", "fontes": ["F1", "F2"]}]
             → {"texto": "A. B.", "fontes": ["F1", "F2"]}.
    """
    textos, fontes = [], []
    for bloco in blocos:
        textos.append(bloco["texto"])
        for fonte in bloco["fontes"]:
            if fonte not in fontes:
                fontes.append(fonte)
    return {"texto": " ".join(textos), "fontes": fontes}


# ---------------- Persistência ----------------

# As colunas que chegaram com o ADR-115 (quem publicou e quem retirou, e quando); bancos antigos ganham na hora
COLUNAS_DA_PUBLICACAO = ("publicado_por", "publicado_em", "retirado_por", "retirado_em")


def _preparar(conexao) -> None:
    """Cria as tabelas dos materiais e das artes, se ainda não existirem, e acrescenta as colunas novas."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS materiais_endomarketing (
               material_id      TEXT PRIMARY KEY,
               empresa_id       TEXT NOT NULL,
               tipo             TEXT NOT NULL,
               conteudo         TEXT NOT NULL,     -- título, blocos com fontes, canal e benefícios (JSON)
               status           TEXT NOT NULL,     -- RASCUNHO, PUBLICADO, DESCARTADO ou RETIRADO (APROVADO: antigo)
               processamento_id TEXT,              -- a inclusão que motivou o kit de boas-vindas (se houver)
               modelo           TEXT NOT NULL,
               versao_prompt    TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               criado_por       TEXT NOT NULL,     -- o especialista do banco que gerou
               decidido_por     TEXT,              -- quem descartou (ou, no modelo antigo, quem aprovou)
               decidido_em      TEXT
           )"""
    )
    # Bancos criados antes do ADR-115 não tinham as colunas da publicação: acrescenta, sem perder os materiais
    colunas_existentes = banco.colunas_da_tabela(conexao, "materiais_endomarketing")
    for coluna in COLUNAS_DA_PUBLICACAO:
        if coluna not in colunas_existentes:
            conexao.execute(f"ALTER TABLE materiais_endomarketing ADD COLUMN {coluna} TEXT")
    # A arte de cada material publicado: a imagem PNG desenhada na tela do banco, guardada como texto (base64)
    # para funcionar igual no SQLite e no PostgreSQL. A empresa baixa exatamente a imagem que o banco validou
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS artes_dos_materiais (
               material_id   TEXT PRIMARY KEY,
               empresa_id    TEXT NOT NULL,
               imagem_base64 TEXT NOT NULL,
               gravada_em    TEXT NOT NULL
           )"""
    )


def _agora() -> str:
    """Data e hora atuais (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# As colunas que listar() lê, na ordem do SELECT
COLUNAS_DO_MATERIAL = ("material_id", "tipo", "conteudo", "status", "processamento_id", "modelo", "criado_em",
                       "criado_por", "decidido_por", "decidido_em", "publicado_por", "publicado_em", "retirado_por",
                       "retirado_em")


def listar(conexao, empresa_id: str, status: str | None = None) -> list[dict]:
    """Os materiais da empresa, do mais recente para o mais antigo (com status, só os daquele status).

    Recebe: conexao; empresa_id; status (ex.: PUBLICADO) ou None para todos.
    Devolve: [{material_id, tipo, conteudo, status, processamento_id, modelo, criado_em, criado_por, decidido_por,
    decidido_em, publicado_por, publicado_em, retirado_por, retirado_em, tem_arte}].
    """
    _preparar(conexao)
    # As artes guardadas desta empresa, para dizer quais materiais têm imagem
    materiais_com_arte = set()
    for (material_id,) in conexao.execute("SELECT material_id FROM artes_dos_materiais WHERE empresa_id = ?",
                                          (empresa_id,)):
        materiais_com_arte.add(material_id)
    consulta = conexao.execute(
        "SELECT " + ", ".join(COLUNAS_DO_MATERIAL) + " FROM materiais_endomarketing "
        "WHERE empresa_id = ? AND (? IS NULL OR status = ?) ORDER BY criado_em DESC, rowid DESC",
        (empresa_id, status, status))
    materiais = []
    for linha in consulta:
        # A linha como dicionário (nome da coluna → valor), com o conteúdo (JSON) já aberto
        material = dict(zip(COLUNAS_DO_MATERIAL, linha))
        material["conteudo"] = json.loads(material["conteudo"])
        material["tem_arte"] = material["material_id"] in materiais_com_arte
        materiais.append(material)
    return materiais


def obter(conexao, empresa_id: str, material_id: str) -> dict:
    """Um material da empresa (mesmo formato de listar). Material de outra empresa ou inexistente: KeyError."""
    for material in listar(conexao, empresa_id):
        if material["material_id"] == material_id:
            return material
    raise KeyError(material_id)


def _situacao_atual(conexao, empresa_id: str, material_id: str) -> str:
    """A situação do material desta empresa. Material de outra empresa (ou que não existe): KeyError (vira 404)."""
    _preparar(conexao)
    linha = conexao.execute("SELECT status FROM materiais_endomarketing WHERE material_id = ? AND empresa_id = ?",
                            (material_id, empresa_id)).fetchone()
    if linha is None:
        raise KeyError(material_id)
    return linha[0]


def publicar(conexao, empresa_id: str, material_id: str, usuario: str, arte_png: bytes | None = None) -> None:
    """O especialista publica um rascunho: a partir daqui a empresa vê o material e baixa o texto e a arte.

    Recebe: conexao; empresa_id; material_id; usuario (o login do especialista); arte_png (a imagem já conferida
    pela porta de entrada, ou None se o material não tem arte). Devolve: nada. Só rascunho pode ser publicado.
    """
    if _situacao_atual(conexao, empresa_id, material_id) != RASCUNHO:
        raise ValueError("Só um rascunho pode ser publicado.")
    agora = _agora()
    # A arte, se veio, é guardada junto (uma por material), em texto base64
    if arte_png is not None:
        conexao.execute("INSERT INTO artes_dos_materiais (material_id, empresa_id, imagem_base64, gravada_em) "
                        "VALUES (?, ?, ?, ?)",
                        (material_id, empresa_id, base64.b64encode(arte_png).decode("ascii"), agora))
    # A situação muda para PUBLICADO, com quem publicou e quando
    conexao.execute("UPDATE materiais_endomarketing SET status = ?, publicado_por = ?, publicado_em = ? "
                    "WHERE material_id = ?", (PUBLICADO, usuario, agora, material_id))
    conexao.commit()


def descartar(conexao, empresa_id: str, material_id: str, usuario: str) -> None:
    """O especialista descarta um rascunho (a empresa nunca chega a vê-lo). Só rascunho pode ser descartado."""
    if _situacao_atual(conexao, empresa_id, material_id) != RASCUNHO:
        raise ValueError("Só um rascunho pode ser descartado.")
    conexao.execute("UPDATE materiais_endomarketing SET status = ?, decidido_por = ?, decidido_em = ? "
                    "WHERE material_id = ?", (DESCARTADO, usuario, _agora(), material_id))
    conexao.commit()


def retirar(conexao, empresa_id: str, material_id: str, usuario: str) -> None:
    """O especialista retira um material publicado (ex.: o benefício mudou): a empresa deixa de vê-lo e de baixá-lo."""
    if _situacao_atual(conexao, empresa_id, material_id) != PUBLICADO:
        raise ValueError("Só um material publicado pode ser retirado.")
    conexao.execute("UPDATE materiais_endomarketing SET status = ?, retirado_por = ?, retirado_em = ? "
                    "WHERE material_id = ?", (RETIRADO, usuario, _agora(), material_id))
    conexao.commit()


def arte(conexao, empresa_id: str, material_id: str) -> bytes:
    """A imagem PNG da arte do material desta empresa. Sem arte (ou de outra empresa): KeyError (vira 404)."""
    _preparar(conexao)
    linha = conexao.execute("SELECT imagem_base64 FROM artes_dos_materiais WHERE material_id = ? AND empresa_id = ?",
                            (material_id, empresa_id)).fetchone()
    if linha is None:
        raise KeyError(material_id)
    return base64.b64decode(linha[0])


def em_texto(material: dict) -> str:
    """O material em Markdown, com a fonte de cada bloco (usado pela avaliação)."""
    linhas = [f"# {material['titulo']}", ""]
    for bloco in material["blocos"]:
        linhas.append(bloco["texto"])
        linhas.append(f"_Fonte: {'; '.join(bloco['fontes'])}_")
        linhas.append("")
    return "\n".join(linhas)


# ---------------- O que o prompt leva desde a v4: as KBs gerais e a assinatura do kit em uso ----------------

def versao_do_prompt() -> str:
    """A versão do prompt em uso: a padrão (VERSAO_PROMPT) com a chave ENDOMARKETING_COM_AS_KBS ligada; desligada, a v3.

    A chave é lida a cada pedido: desligá-la é o jeito de voltar para a v3 sem mexer no código.
    """
    # Chave ligada (o padrão): a versão padrão; desligada: a v3, o histórico
    if config.ENDOMARKETING_COM_AS_KBS:
        return VERSAO_PROMPT
    return VERSAO_PROMPT_ANTERIOR


def _texto_da_kb_geral(conexao, tipo: str) -> str:
    """O texto da KB GERAL publicada e vigente do tipo pedido, sem a ficha. Sem ela: texto vazio.

    Recebe: conexao; tipo (ex.: "tom_de_voz"). Devolve: o corpo da KB, com as seções.
    Por que a publicada: quem publica uma versão nova da KB muda o que o agente lê, sem mexer no código.
    """
    # As KBs gerais daquele tipo, só as publicadas e vigentes hoje
    kbs = kbs_endomarketing.kbs_publicadas(conexao, dono=kbs_endomarketing.DONO_GERAL, tipo=tipo)
    # Sem versão publicada e vigente (ex.: a KB foi retirada), o prompt segue só com as regras dele
    if not kbs:
        return ""
    # A primeira (na prática, há uma KB geral de cada tipo): o texto das seções, sem a ficha
    return kbs[0]["corpo"]


def assinatura_do_kit_em_uso(conexao, empresa_id: str) -> str:
    """A assinatura do kit em uso da empresa: o nome dela no kit próprio; nada (texto vazio) no kit padrão.

    Recebe: conexao; empresa_id. Devolve: o nome da empresa, como está no cadastro, ou "".
    O kit em uso sai da KB "Kit da marca" publicada e vigente da empresa, a fonte única do kit (desde o prompt v4);
    sem ela, vale o kit padrão. A assinatura é a mesma que a arte usa (services/endomarketing_do_banco.py,
    kit_da_empresa): o texto e a imagem assinam igual.
    """
    # As KBs de kit publicadas e vigentes SÓ desta empresa (a assinatura de uma nunca vai para outra)
    kits = kbs_endomarketing.kbs_publicadas(conexao, dono=empresa_id, tipo=TIPO_DO_KIT)
    # Sem KB de kit publicada, o kit em uso é o padrão, que não leva a assinatura da empresa
    if not kits:
        return ""
    # A primeira KB de kit da empresa é a que vale (na prática, há uma só), como na vitrine e na arte.
    # O kit padrão também não leva a assinatura: o selo do banco parceiro já vai na arte
    if kits[0]["ficha"].get("kit_escolhido") != kbs_endomarketing.KIT_PROPRIO:
        return ""
    # Kit próprio: assina com o nome da empresa, como está no cadastro
    return cadastro_de_empresas.obter(conexao, empresa_id)["nome"]


def contexto_das_kbs(conexao, empresa_id: str) -> dict:
    """O que o prompt leva além dos trechos (desde a v4): o tom de voz, os termos proibidos e a assinatura do kit em uso.

    Recebe: conexao; empresa_id (a empresa do material).
    Devolve: {"tom_de_voz": texto, "termos_proibidos": texto, "assinatura": texto}. As duas KBs são GERAIS (as
    mesmas para todas as empresas); a assinatura é só desta empresa, e nunca vai para o material de outra.
    """
    return {"tom_de_voz": _texto_da_kb_geral(conexao, TIPO_DO_TOM_DE_VOZ),
            "termos_proibidos": _texto_da_kb_geral(conexao, TIPO_DOS_TERMOS_PROIBIDOS),
            "assinatura": assinatura_do_kit_em_uso(conexao, empresa_id)}


# ---------------- O pedido de material ----------------

def _sistema(versao_prompt: str) -> str:
    """A seção SISTEMA do prompt da versão pedida (ex.: "endomarketing_v5")."""
    texto = (RAIZ / "prompts" / f"{versao_prompt}.md").read_text(encoding="utf-8")
    return re.split(r"^## SISTEMA\s*$", texto, flags=re.M)[1].strip()


def _montar_pedido(tipo: str, canal: str, destaque: str, trechos: list[dict], contexto: dict | None = None,
                   beneficios_escolhidos: list[str] | None = None) -> str:
    """O pedido ao LLM: o tipo, o canal, os trechos (cada um com a fonte) e o destaque da empresa como DADO.

    Com o contexto (desde a v4), o pedido leva também o tom de voz, os termos proibidos e a assinatura, cada um entre
    as suas marcações e antes dos trechos. Com a lista dos benefícios escolhidos (a v5), leva também esses nomes, um
    por linha: é a lista do que precisa aparecer no material, em qualquer canal. Sem os dois (a v3, o histórico), o
    pedido é o de antes.
    """
    # Um trecho por linha, cada um com a fonte na frente
    linhas_dos_trechos = []
    for trecho in trechos:
        linhas_dos_trechos.append(f"[{trecho['fonte']}] {_conteudo(trecho)}")
    # O tipo e o canal abrem o pedido
    cabecalho = f"Tipo de material: {tipo}\nCanal: {canal}\n\n"
    # O contexto das KBs e a assinatura: dados de referência, cada um entre as suas marcações
    if contexto is not None:
        cabecalho += (f"<tom_de_voz>\n{contexto['tom_de_voz']}\n</tom_de_voz>\n\n"
                      f"<termos_proibidos>\n{contexto['termos_proibidos']}\n</termos_proibidos>\n\n"
                      f"<assinatura>\n{contexto['assinatura']}\n</assinatura>\n\n")
    # Os benefícios escolhidos, um por linha (vazio quando o especialista não marcou nenhum)
    if beneficios_escolhidos is not None:
        cabecalho += ("<beneficios_escolhidos>\n" + "\n".join(beneficios_escolhidos) +
                      "\n</beneficios_escolhidos>\n\n")
    # Os trechos e o destaque fecham o pedido, como sempre
    return (cabecalho + "<trechos>\n" + "\n".join(linhas_dos_trechos) + "\n</trechos>\n\n" +
            f"<destaque>\n{destaque}\n</destaque>")


def gerar_material(conexao, empresa_id: str, tipo: str, usuario: str, destaque: str = "",
                   processamento_id: str | None = None, cliente: LLMClient | None = None,
                   busca=None, canal: str = CANAL_PADRAO, beneficios: list[str] | None = None) -> ResultadoDoPedido:
    """Gera e guarda um RASCUNHO para a empresa e grava a execução para a Telemetria.

    Recebe: empresa_id (a empresa escolhida pelo especialista); tipo; usuario (o login de quem gerou); destaque (o
    "algo a mais", pode ser vazio); processamento_id (só no kit de boas-vindas de uma inclusão); canal ("email",
    "mural" ou "whatsapp": o WhatsApp fica com no máximo 3 blocos, sem deixar benefício de fora); beneficios (os nomes
    dos benefícios do catálogo que entram; None = as buscas de cada tipo pelo RAG, o jeito antigo, usado pela
    avaliação).
    A empresa só vê o material depois que o especialista publicar (publicar()).
    """
    inicio = datetime.now(timezone.utc)
    # A versão do prompt deste pedido (a padrão, ou a v3 com a chave desligada): vai para o rascunho e para a Telemetria
    versao_prompt = versao_do_prompt()
    # O taxímetro do pedido: as chamadas à IA para gerar o material somam aqui (tokens e custo; ADR-131)
    with uso_da_ia.medir() as uso:
        try:
            resultado = _gerar(conexao, empresa_id, tipo, usuario, destaque, processamento_id, cliente, busca, canal,
                               beneficios, versao_prompt)
        except teto_de_gasto.TetoDeGastoAtingido:
            # A IA foi pausada pelo teto de gasto (ADR-131): o ERRO vai para a Telemetria, e a API avisa o especialista
            identificador = processamento_id or f"endomarketing-{uuid.uuid4().hex[:10]}"
            execucoes.registrar_pausa_pelo_teto(conexao, identificador, empresa_id, "gerar_material:pausado",
                                                "Endomarketing", inicio, uso)
            raise
        except IAIndisponivel:
            # A IA real não respondeu (ADR-145): nenhum rascunho simulado; o ERRO vai para a Telemetria, e a API avisa o
            # especialista, que tenta de novo depois
            identificador = processamento_id or f"endomarketing-{uuid.uuid4().hex[:10]}"
            execucoes.registrar_queda_da_ia(conexao, identificador, empresa_id, "gerar_material:pausado",
                                            "Endomarketing", inicio, uso)
            raise
    _registrar_execucao(conexao, empresa_id, processamento_id, resultado, inicio, uso, versao_prompt)
    return resultado


def _registrar_execucao(conexao, empresa_id: str, processamento_id: str | None, resultado: ResultadoDoPedido,
                        inicio: datetime, uso: uso_da_ia.Uso, versao_prompt: str) -> None:
    """Uma execução por pedido de material (sem o texto do material nem do destaque), com a versão do prompt usada."""
    if resultado.situacao == RECUSADO:
        status, tipo_erro = execucoes.BLOQUEADO, None
    elif resultado.situacao == FALHA:
        status, tipo_erro = execucoes.ERRO, "RespostaForaDoContrato"
    elif resultado.situacao == INDISPONIVEL:
        # Não é erro da IA: o servidor ainda não tem o índice do catálogo
        status, tipo_erro = execucoes.ERRO, "IndiceAusente"
    else:
        status, tipo_erro = execucoes.OK, None
    # Bloco removido e título trocado pela conferência também contam como guardrail disparado
    guardrail = resultado.situacao == RECUSADO
    for observacao in resultado.observacoes:
        if observacao.startswith("Bloco removido") or observacao.startswith("Título trocado"):
            guardrail = True
    identificador = processamento_id or f"endomarketing-{resultado.material_id or uuid.uuid4().hex[:10]}"
    execucoes.registrar(conexao, identificador, empresa_id, f"gerar_material:{resultado.situacao}", "Endomarketing",
                        inicio, datetime.now(timezone.utc), status, modelo=resultado.modelo,
                        versao_prompt=versao_prompt, tipo_erro=tipo_erro, guardrail_disparado=guardrail, uso=uso)


def _gerar(conexao, empresa_id: str, tipo: str, usuario: str, destaque: str, processamento_id: str | None,
           cliente: LLMClient | None, busca, canal: str = CANAL_PADRAO,
           beneficios: list[str] | None = None, versao_prompt: str = VERSAO_PROMPT) -> ResultadoDoPedido:
    """O pedido de material em si (sem gravar a execução: quem grava é gerar_material).

    versao_prompt: "endomarketing_v5" (a padrão, com o tom de voz, os termos proibidos, a assinatura do kit em uso e a
    lista dos benefícios escolhidos no pedido) ou "endomarketing_v3" (o histórico, sem eles).
    O guardrail de injeção confere o destaque em duas camadas (ADR-147):
    1. a lista de frases, antes de tudo: o destaque suspeito nem chega à IA;
    2. com a IA real, o detector do Bedrock Guardrails, que roda AO MESMO TEMPO que a preparação do rascunho, para a
       checagem não somar o tempo dela à espera do especialista. O rascunho só é guardado depois do "normal"; no
       "suspeito", ele é descartado e vale a mesma recusa.
    """
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de material desconhecido: {tipo}.")
    if canal not in CANAIS:
        raise ValueError(f"Canal desconhecido: {canal}.")
    destaque = (destaque or "").strip()
    # Guardrail, 1ª camada: destaque com cara de instrução para a IA nem chega a ela
    if destaque and guardrail_injecao.e_suspeito(destaque):
        return _destaque_recusado()
    # O número do rascunho, já agora: a checagem do destaque vai para a Telemetria com o mesmo identificador
    material_id = uuid.uuid4().hex[:10]
    # Guardrail, 2ª camada (só com a IA real e com destaque): o detector checa enquanto o rascunho é preparado
    checagem = guardrail_injecao.comecar_checagem(destaque)
    try:
        resultado = _preparar_o_rascunho(conexao, empresa_id, tipo, destaque, cliente, busca, canal, beneficios,
                                         versao_prompt)
    finally:
        # Espera a checagem (no máximo o tempo dela) e grava na Telemetria, mesmo que a preparação tenha falhado
        identificador = processamento_id or f"endomarketing-{material_id}"
        destaque_suspeito = guardrail_injecao.terminar_checagem(checagem, conexao, identificador, empresa_id)
    # O detector achou o destaque suspeito: o rascunho preparado é descartado, e vale a mesma recusa
    if destaque_suspeito:
        return _destaque_recusado()
    # Sem rascunho pronto (sem o índice, sem evidência, a resposta fora do formato): o motivo volta como está
    if resultado.situacao != GERADO:
        return resultado
    return _guardar_o_rascunho(conexao, empresa_id, tipo, usuario, processamento_id, material_id, resultado,
                               versao_prompt)


def _destaque_recusado() -> ResultadoDoPedido:
    """A recusa do destaque com cara de ordem para a IA: a mesma para a lista de frases e para o detector."""
    return ResultadoDoPedido(RECUSADO, "O destaque tem uma frase com cara de instrução para o Agente de "
                                       "Endomarketing. Descreva só o assunto que você quer destacar.")


def _preparar_o_rascunho(conexao, empresa_id: str, tipo: str, destaque: str, cliente: LLMClient | None, busca,
                         canal: str, beneficios: list[str] | None, versao_prompt: str) -> ResultadoDoPedido:
    """A parte do pedido que roda junto com a checagem do destaque: busca os trechos, pede o texto à IA e confere.

    Não grava nada: o rascunho só é guardado por _guardar_o_rascunho, depois do resultado da checagem.
    Devolve: o ResultadoDoPedido. GERADO = o rascunho pronto para guardar (ainda sem o número); as outras situações
    (sem o índice, sem evidência, a resposta fora do formato) voltam como estão.
    """
    try:
        if beneficios is None:
            # Jeito antigo (avaliação): as buscas de cada tipo vão ao catálogo pelo RAG
            trechos, nao_encontrados = _trechos_do_material(empresa_id, tipo, destaque, busca)
        else:
            # O especialista escolheu os benefícios: só eles (e o atendimento) entram no material
            trechos = _trechos_dos_beneficios_escolhidos(conexao, empresa_id, beneficios)
            nao_encontrados = _destaques_fora_da_escolha(empresa_id, destaque, trechos, busca)
    except busca_rag.IndiceAusente:
        # Sem o índice do catálogo (ex.: servidor novo, antes do build_index), não há onde buscar: avisa, sem quebrar
        return ResultadoDoPedido(INDISPONIVEL, "O catálogo de benefícios ainda não está pronto neste servidor. "
                                               "Tente de novo mais tarde.")
    observacoes = []
    for assunto in nao_encontrados:
        observacoes.append(f"Os benefícios escolhidos no catálogo desta empresa não trazem informação sobre "
                           f"\"{assunto}\": nada foi escrito sobre isso.")
    if not trechos:
        return ResultadoDoPedido(SEM_EVIDENCIA, "Não encontrei no catálogo desta empresa informação para este "
                                                "material. Confira o catálogo de benefícios dela.",
                                 observacoes=observacoes)
    # A versão padrão leva também o tom de voz, os termos proibidos, a assinatura do kit em uso e a lista dos benefícios
    # escolhidos; a v3, só os trechos e o destaque
    contexto, beneficios_escolhidos = None, None
    if versao_prompt == VERSAO_PROMPT:
        contexto = contexto_das_kbs(conexao, empresa_id)
        beneficios_escolhidos = list(beneficios or [])
    pedido = _montar_pedido(tipo, canal, destaque, trechos, contexto, beneficios_escolhidos)
    material, modelo = _pedir_o_material(cliente or cliente_padrao(), pedido, _sistema(versao_prompt))
    # Duas respostas fora do formato combinado: nenhum rascunho, e a tela pede para tentar de novo
    if material is None:
        return ResultadoDoPedido(FALHA, "Não consegui montar o rascunho agora. Tente de novo.",
                                 observacoes=observacoes, modelo=modelo)
    return _conferir_o_rascunho(conexao, material, trechos, tipo, canal, list(beneficios or []), observacoes, modelo)


def _pedir_o_material(cliente: LLMClient, pedido: str, sistema: str) -> tuple[MaterialGerado | None, str]:
    """Pede o rascunho à IA no formato garantido e lê a resposta, com uma segunda tentativa se ela vier fora do formato.

    Recebe: o cliente de IA; o pedido montado; o sistema (o papel do agente, da versão do prompt).
    Devolve: (o material lido, ou None depois de duas respostas fora do formato; o modelo que respondeu, ou "mock").
    Como no Interpretador, a segunda tentativa leva o motivo da recusa da primeira. Com o formato garantido, isso fica
    raro: ele vale no Bedrock pela API Converse. Num provedor que não aceita o esquema, o prompt continua pedindo o JSON
    no texto, e a segunda tentativa é a rede de proteção.
    """
    pedido_da_tentativa = pedido
    modelo = "mock"
    for tentativa in range(1, TENTATIVAS_DO_FORMATO + 1):
        resposta = cliente.gerar(TAREFA, pedido_da_tentativa, sistema, temperatura=0.0,
                                 esquema_json=esquema_da_resposta())
        # Quem redigiu: o nome do modelo com a IA real; "mock" na simulação
        modelo = resposta.modelo if resposta.modo == "llm" else "mock"
        try:
            return ler_resposta(resposta.texto), modelo
        except ValueError as erro:
            # A tentativa seguinte leva o motivo, para a IA corrigir o formato
            pedido_da_tentativa = (pedido + f"\n\nA resposta da tentativa {tentativa} não veio no formato combinado "
                                   f"({erro}). Responda só com o JSON pedido.")
    return None, modelo


def _conferir_o_rascunho(conexao, material: MaterialGerado, trechos: list[dict], tipo: str, canal: str,
                         beneficios: list[str], observacoes: list[str], modelo: str) -> ResultadoDoPedido:
    """As conferências do código sobre o que a IA escreveu, e o material no tamanho do canal.

    Recebe: o material lido; os trechos do pedido; o tipo e o canal; os benefícios escolhidos (vazio no jeito antigo);
    as observações que já vieram da busca (as novas se somam a elas); o modelo que redigiu.
    Devolve: GERADO com o rascunho, ou SEM_EVIDENCIA se nenhum bloco da IA passou nas conferências.
    A ordem: as fontes, os números e os links de cada bloco; os termos proibidos; o que a IA não achou; os benefícios
    escolhidos que ficaram sem bloco; o tamanho do canal; e, por fim, os números e os links do título.
    """
    blocos, observacoes_da_conferencia = conferir_material(material, trechos)
    observacoes.extend(observacoes_da_conferencia)
    # O termo proibido é barrado no título e nos blocos, com a lista da KB de termos proibidos publicada (a mesma da
    # trava das KBs). Vale nas duas versões do prompt: é uma conferência do código, e não um pedido à IA
    termos = kbs_endomarketing.termos_proibidos(conexao)
    titulo, blocos, observacoes_dos_termos = conferir_termos_proibidos(material.titulo, blocos, termos,
                                                                       TIPOS[tipo]["nome"])
    observacoes.extend(observacoes_dos_termos)
    for assunto in material.nao_encontrado:
        observacoes.append(f"O Agente de Endomarketing não encontrou no catálogo: \"{assunto}\".")
    if not blocos:
        return ResultadoDoPedido(SEM_EVIDENCIA, "Nenhum trecho do rascunho passou na conferência (as fontes, os "
                                                "números e os termos proibidos).",
                                 observacoes=observacoes, modelo=modelo)
    # Todo benefício escolhido fica no material: o que ficou sem bloco ganha a frase do catálogo
    blocos, observacoes_dos_beneficios = completar_os_beneficios(blocos, beneficios, trechos, termos)
    observacoes.extend(observacoes_dos_beneficios)
    # O canal limita o número de blocos sem tirar conteúdo: os blocos a mais se juntam ao último que cabe
    blocos, observacoes_do_canal = ajustar_ao_canal(blocos, canal)
    observacoes.extend(observacoes_do_canal)
    # O título passa pela mesma conferência de números e links dos blocos; parte do título que já passou pelos termos
    # proibidos, para as duas conferências valerem juntas
    titulo, observacoes_do_titulo = conferir_titulo(titulo, tipo, trechos)
    observacoes.extend(observacoes_do_titulo)
    # O conteúdo guardado: o texto, as observações, o canal e os benefícios escolhidos (vazio no jeito antigo)
    conteudo = {"titulo": titulo, "blocos": blocos, "observacoes": observacoes, "canal": canal,
                "beneficios": beneficios}
    return ResultadoDoPedido(GERADO, "Rascunho pronto: confira o texto e a arte e publique para a empresa.",
                             material=conteudo, observacoes=observacoes, modelo=modelo)


def _guardar_o_rascunho(conexao, empresa_id: str, tipo: str, usuario: str, processamento_id: str | None,
                        material_id: str, preparado: ResultadoDoPedido, versao_prompt: str) -> ResultadoDoPedido:
    """Guarda o rascunho preparado, com o número dele, e devolve o resultado com esse número.

    Só é chamado depois que o destaque passou pelas duas camadas do guardrail (ADR-147).
    """
    _preparar(conexao)
    # Guardado como RASCUNHO: a empresa só vê depois que o especialista publicar
    conexao.execute("INSERT INTO materiais_endomarketing (material_id, empresa_id, tipo, conteudo, status, "
                    "processamento_id, modelo, versao_prompt, criado_em, criado_por) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (material_id, empresa_id, tipo, json.dumps(preparado.material, ensure_ascii=False), RASCUNHO,
                     processamento_id, preparado.modelo, versao_prompt, _agora(), usuario))
    conexao.commit()
    # O resultado passa a ter o número do rascunho guardado
    preparado.material_id = material_id
    return preparado


# ---------------- Sugestão de kit de boas-vindas ----------------

def sugestoes_de_kit(conexao, empresa_id: str) -> list[dict]:
    """Inclusões homologadas que ainda não têm kit de boas-vindas: a tela do banco sugere gerar um para cada."""
    ja_com_kit = set()
    for material in listar(conexao, empresa_id):
        # Um kit descartado não conta: a sugestão volta, para o especialista gerar outro
        if material["status"] == DESCARTADO:
            continue
        if material["tipo"] == "kit_boas_vindas" and material["processamento_id"]:
            ja_com_kit.add(material["processamento_id"])
    sugestoes = []
    for envio in processamentos.listar(conexao, empresa_id):
        if envio.tipo_carga != TipoCarga.INCLUSAO or envio.status != EstadoProcessamento.HOMOLOGADO:
            continue
        if envio.processamento_id in ja_com_kit:
            continue
        homologado = homologacao.obter(conexao, envio.processamento_id)
        novos = homologado["relatorio"]["registros_homologados"] if homologado else 0
        sugestoes.append({"processamento_id": envio.processamento_id, "arquivo": envio.nome_arquivo,
                          "funcionarios_novos": novos})
    return sugestoes


# ---------------- MOCK: o simulador que faz o papel do LLM ----------------

def _titulo_da_secao(fonte: str) -> str:
    """O nome da seção a partir da fonte ("Pacote ... v1 › Conta salário" vira "Conta salário")."""
    return fonte.split("›")[-1].strip()


def _simular_material(pedido: str) -> str:
    """MOCK: monta o rascunho copiando os trechos do catálogo, cada bloco com a sua fonte.

    Segue a regra do canal do prompt: no canal com limite de blocos (o WhatsApp), cada trecho entra só com a primeira
    frase, e os trechos se juntam em até o limite de blocos, com as fontes de todos. Assim, todo benefício escolhido
    cabe no canal.
    """
    tipo = re.search(r"^Tipo de material: (\w+)$", pedido, re.M).group(1)
    canal = re.search(r"^Canal: (\w+)$", pedido, re.M).group(1)
    bloco_dos_trechos = re.search(r"<trechos>\n(.*?)\n</trechos>", pedido, re.S).group(1)
    # Quantos blocos cabem no canal (None = sem limite)
    maximo = CANAIS[canal]["maximo_de_blocos"]
    blocos = []
    for linha in bloco_dos_trechos.splitlines():
        partes = re.match(r"^\[([^\]]+)\] (.*)$", linha)
        if partes is None:
            continue
        fonte, conteudo = partes.group(1), partes.group(2).replace("**", "")
        # No canal com limite, as frases são curtas: só a primeira de cada trecho
        if maximo is not None:
            conteudo = _primeira_frase(conteudo)
        secao = _titulo_da_secao(fonte)
        if tipo == "faq":
            texto = f"Como funciona: {secao}? {conteudo}"
        elif tipo == "kit_boas_vindas":
            texto = f"Primeiros passos — {secao}: {conteudo}"
        else:
            texto = f"{secao}: {conteudo}"
        blocos.append({"texto": texto, "fontes": [fonte]})
    # No canal com limite, os blocos se juntam em grupos, até o limite
    if maximo is not None:
        blocos = _juntar_em_grupos(blocos, maximo)
    return json.dumps({"titulo": TITULO_PADRAO_DO_TIPO[tipo], "blocos": blocos, "nao_encontrado": []},
                      ensure_ascii=False)


def _juntar_em_grupos(blocos: list[dict], quantidade_de_grupos: int) -> list[dict]:
    """Junta os blocos, em ordem, em até N blocos de tamanhos parecidos (usado pelo simulador no canal com limite).

    Exemplo: 7 blocos em 3 grupos → um bloco com os 3 primeiros, um com os 2 seguintes e um com os 2 últimos.
    """
    # Até o limite, nada a juntar
    if len(blocos) <= quantidade_de_grupos:
        return blocos
    # O tamanho de cada grupo: a divisão inteira, e os primeiros grupos levam um bloco a mais quando sobra
    tamanho_base = len(blocos) // quantidade_de_grupos
    sobra = len(blocos) % quantidade_de_grupos
    juntados = []
    inicio = 0
    for numero_do_grupo in range(quantidade_de_grupos):
        tamanho = tamanho_base
        if numero_do_grupo < sobra:
            tamanho += 1
        juntados.append(_juntar_blocos(blocos[inicio:inicio + tamanho]))
        inicio += tamanho
    return juntados


def cliente_padrao() -> LLMClient:
    """Cliente do modo configurado; no MOCK, o material é montado pelo simulador."""
    return LLMClient(respostas_mock={TAREFA: _simular_material})

