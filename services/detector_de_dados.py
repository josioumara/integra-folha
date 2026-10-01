"""Detector de dados pessoais num texto: acha nomes, CPFs, datas, valores, endereços e contatos (ADR-72, ADR-73).

Para que serve HOJE (ADR-101): a IA lê os documentos com os dados reais, porque roda pelo AWS Bedrock (o fornecedor
do modelo não vê o pedido e nada fica guardado, ADR-96). Este detector NÃO esconde nada da IA. Ele só responde "onde
há um dado de pessoa neste texto?", em dois lugares:
1. o aviso de parágrafo esquecido do Leitor de Documentos: um parágrafo com CPF ou data que não entrou em nenhuma
   pessoa vira aviso para a empresa (agents/leitor_de_documentos.py);
2. o simulador do modo MOCK, que imita a IA sem custo.
E a lista de palavras de ligação (so_palavras_de_ligacao) limpa os rótulos: o que a IA devolve no Leitor e os das
fichas do Word.

Como ele marca: numa CÓPIA do texto, cada dado vira uma etiqueta que diz o TIPO do dado.
Exemplo:
    "A Maria Souza, CPF 529.982.247-25, entrou em 05/03/2026 como analista."
vira
    "A [TEXTO_1] [TEXTO_2], CPF [CPF_1], entrou em [DATA_1] como analista."
e o dicionário etiqueta → valor permite voltar ao texto original (desmarcar).

História: até o ADR-101, essa troca era feita ANTES de a IA ler, para ela não ver os dados (ADR-31). O EXP-010 mediu o
preço: 91,3% de acerto com etiquetas contra 98,9% com os dados reais.

O que o detector reconhece, só com regras (ADR-105: sem o modelo de linguagem, que custava 262 MB na imagem e 267 MB de
memória sem ganho medido):
- números: e-mail, CNPJ, CPF, data (inclusive por extenso), valor em dinheiro, CEP, telefone, documento (RG, PIS,
  com pontos e traços) e qualquer outro número. O número é marcado INTEIRO: "44.827.196-3" vira uma etiqueta só;
- palavras com letra maiúscula que parecem nome de pessoa, rua, cidade ou empresa: toda palavra com maiúscula vira
  [TEXTO_n], MENOS as palavras de cadastro da lista fixa (PALAVRAS_QUE_FICAM: "Nome", "Cargo", "Rua", "Admissão"...),
  as siglas de estado ("SP"), as letras sozinhas e as palavras de ligação do português ("A", "Também", "Com"; a lista
  em data/vocabulario/palavras_de_ligacao.txt). Na dúvida, marca: o detector prefere achar um dado a mais do que
  deixar passar um.

Limite conhecido: nome escrito todo em minúsculas ("maria souza") não parece nome e passa.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from services import datas_por_extenso
from services.documentos import cpf_valido

# Siglas dos estados: não identificam ninguém e ajudam a IA a achar o endereço, então ficam no texto
SIGLAS_DOS_ESTADOS = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
                      "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}

# Palavras de cadastro que podem aparecer com maiúscula (rótulos, começo de frase) e não são dado de ninguém.
# Ficam no texto porque a IA precisa delas para entender a frase. Escritas sem acento e em minúsculas.
PALAVRAS_QUE_FICAM = {
    # Rótulos e palavras de cadastro de pessoal
    "nome", "completo", "social", "cpf", "rg", "pis", "pasep", "nis", "cnpj", "cnh", "ctps", "cargo", "funcao",
    "salario", "salarial", "remuneracao", "renda", "bruto", "bruta", "liquido", "vencimento", "vencimentos", "valor",
    "ordenado", "fixo", "mensal", "admissao", "admitido", "admitida", "contratado", "contratada", "contratacao",
    "inicio", "entrada", "nascimento", "nascido", "nascida", "nasc", "data", "mae", "pai", "sexo", "masculino",
    "feminino", "estado", "civil", "solteiro", "solteira", "casado", "casada", "divorciado", "divorciada", "viuvo",
    "viuva", "endereco", "end", "residencial", "residencia", "comercial", "rua", "avenida", "av", "travessa",
    "alameda", "estrada", "rodovia", "praca", "bairro", "cidade", "municipio", "cep", "uf", "numero", "complemento",
    "apto", "apartamento", "casa", "bloco", "torre", "sala", "telefone", "fone", "celular", "cel", "email", "mail",
    "contato", "matricula", "registro", "departamento", "setor", "area", "unidade", "filial", "loja", "empresa",
    "estabelecimento", "documento", "identidade", "carteira", "orgao", "emissor", "expedidor", "funcionario",
    "funcionaria", "funcionarios", "colaborador", "colaboradora", "colaboradores", "empregado", "empregada",
    "trabalhador", "trabalhadora", "pessoa", "pessoas", "lista", "relacao", "dados", "cadastro", "ficha", "fichas",
    "admissoes", "novo", "nova", "novos", "novas", "observacao", "obs", "naturalidade", "natural", "nacionalidade",
    "brasileiro", "brasileira", "escolaridade", "dependente", "dependentes", "conjuge", "esposa", "esposo", "filho",
    "filha", "filhos", "turno", "jornada", "horario", "escala", "clt", "pj", "estagiario", "estagiaria", "aprendiz",
    "temporario", "temporaria", "gerente", "analista", "assistente", "auxiliar", "coordenador", "coordenadora",
    "diretor", "diretora", "supervisor", "supervisora", "tecnico", "tecnica", "operador", "operadora", "vendedor",
    "vendedora", "atendente", "motorista", "junior", "pleno", "senior", "beneficio", "beneficios", "vale",
    "transporte", "refeicao", "alimentacao", "plano", "saude", "comissao", "bonus", "gratificacao", "adicional",
    "premio", "pendencia", "pendencias", "informacoes", "anotacao", "mensagem", "resumo", "admissional",
    # Cargos e ocupações comuns (no começo da frase, aparecem com maiúscula: "Recepcionista. Início...")
    "recepcionista", "enfermeiro", "enfermeira", "vendedora", "tecnica", "supervisora", "coordenadora", "desenvolvedor",
    "desenvolvedora", "designer", "cozinheiro", "cozinheira", "caixa", "estoquista", "repositor", "repositora",
    "porteiro", "zelador", "zeladora", "faxineiro", "faxineira", "professor", "professora", "engenheiro",
    "engenheira", "contador", "contadora", "advogado", "advogada", "medico", "medica", "secretario", "secretaria",
    "eletricista", "mecanico", "mecanica", "pedreiro", "soldador", "separador", "separadora", "promotor",
    "promotora", "consultor", "consultora", "executivo", "executiva", "especialista", "estagio", "trainee",
    "encarregado", "encarregada", "lider", "chefe", "almoxarife", "conferente", "montador", "montadora",
    "cuidador", "cuidadora", "garcom", "garconete", "balconista", "farmaceutico", "farmaceutica", "vigilante",
    "manutencao", "logistica", "financeiro", "financeira", "administrativo", "administrativa", "comercial",
    # Verbos que abrem frase em mensagem de RH
    "contratamos", "contratou", "admitimos", "admitiu", "informamos", "informou", "enviamos", "enviou", "segue",
    "comecou", "iniciou", "inicia", "comeca", "entrou", "entra", "assumiu", "assume", "trabalhara", "possui",
    "reside", "mora", "nasceu", "recebe", "recebera", "ganha", "tem", "falta", "faltam", "confirmar", "conferir",
    # Saudações e fechamento de mensagem
    "ola", "oi", "prezados", "prezado", "prezada", "bom", "boa", "dia", "tarde", "noite", "obrigado", "obrigada",
    "atenciosamente", "abracos", "att",
    # Meses e dias da semana
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
    "novembro", "dezembro", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo", "feira",
}

# A lista das palavras de ligação do português (uma por linha, sem acento; "#" abre um comentário)
ARQUIVO_DAS_PALAVRAS_DE_LIGACAO = Path(__file__).resolve().parent.parent / "data" / "vocabulario" / "palavras_de_ligacao.txt"

# Nomes dos meses (e abreviações), em português e inglês, para reconhecer data com o mês escrito:
# "14 de setembro de 1991", "03 jun 2024", "14-Sep-2024", "Sep 14, 1991"
MESES = r"(?:jan|fev|feb|mar|abr|apr|mai|may|jun|jul|ago|aug|set|sep|out|oct|nov|dez|dec)[a-zç]*\.?"

# Os pedaços do texto que viram etiqueta, do mais específico para o mais geral.
# Cada pedaço tem um nome (o tipo que aparece na etiqueta) e um padrão ("expressão regular": um molde de texto).
# (?<![\d]) e (?![\d]) garantem que o número inteiro foi pego, e não só um pedaço dele.
PADRAO_DOS_DADOS = re.compile(
    r"(?P<EMAIL>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<CNPJ>(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d))"
    r"|(?P<CPF>(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d\w])|(?<!\d)\d{3} \d{3} \d{3} \d{2}(?!\d))"
    r"|(?P<DATA>(?<!\d)(?:\d{1,2}(?:º|°)?\s*(?:de\s+|[-/\s])\s*" + MESES + r"\s*(?:de\s+|[-/,\s])\s*\d{4}"
    r"|(?<![\w])" + MESES + r"\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{2,4}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}/\d{4})(?!\d))"
    r"|(?P<VALOR>R\$\s?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|R\$\s?\d+(?:,\d{1,2})?"
    r"|(?<!\d)\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)|(?<!\d)\d+,\d{2}(?!\d))"
    r"|(?P<CEP>(?<!\d)\d{5}[-\s]\d{3}(?!\d))"
    r"|(?P<TELEFONE>(?:\+55\s?)?(?:\(\d{2}\)\s?|(?<!\d)\d{2}[\s-])9?\d{4}[\s-]?\d{4}(?!\d))"
    r"|(?P<DOCUMENTO>(?<![\w.])\d[\d.]*[-/][\dXx](?:[\d.\-/]*\d)?(?![\w]))"
    r"|(?P<NUMERO_LONGO>(?<![\w.])\d{1,3}(?:\.\d{3,5})+(?![\w,]))"
    r"|(?P<NUMERO>(?<!\d)\d+(?!\d))"
    r"|(?P<PALAVRA>[^\W\d_]+)",
    re.IGNORECASE,
)

# Como uma etiqueta é escrita: um tipo em maiúsculas, sublinhado e um número, entre colchetes. Ex.: [CPF_1]
PADRAO_DA_ETIQUETA = re.compile(
    r"\[(?:EMAIL|CNPJ|CPF|DATA|VALOR|CEP|CELULAR|TELEFONE|DOCUMENTO|NUMERO|TEXTO)_\d+\]")


@dataclass
class TextoMarcado:
    """A cópia do texto com as etiquetas no lugar dos dados, e o dicionário para desfazer a troca."""

    texto: str                                                      # a cópia marcada
    valor_da_etiqueta: dict[str, str] = field(default_factory=dict)  # "[CPF_1]" -> "529.982.247-25" (fica aqui)


# ============================== As palavras de ligação ==============================

@lru_cache(maxsize=1)
def _palavras_de_ligacao() -> frozenset:
    """Artigos, preposições, pronomes... do português (sem acento, em minúsculas), lidos do arquivo uma vez só."""
    palavras = set()
    for linha in ARQUIVO_DAS_PALAVRAS_DE_LIGACAO.read_text(encoding="utf-8").splitlines():
        # Linha vazia ou de comentário não é palavra
        if linha.strip() and not linha.startswith("#"):
            palavras.add(linha.strip())
    return frozenset(palavras)


def so_palavras_de_ligacao(texto: str) -> bool:
    """True se o texto só tem palavras de ligação do português (ou nada). Ex.: "Também temos o" → True; "CPF" → False."""
    for palavra in re.findall(r"[^\W\d_]+", texto):
        if _sem_acento_em_minusculas(palavra) not in _palavras_de_ligacao():
            return False
    return True


# ============================== Decidir se a palavra fica ==============================

def _sem_acento_em_minusculas(palavra: str) -> str:
    """"Salário" vira "salario": é assim que a palavra é procurada nas listas."""
    # Separa as letras dos acentos e joga os acentos fora
    sem_acento = unicodedata.normalize("NFKD", palavra).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def _palavra_fica(palavra: str) -> bool:
    """True se a palavra não é dado de ninguém e fica como está na cópia (regras no começo do arquivo).

    Ex.: "analista", "Rua", "SP", "Também" → True; "Maria", "Campinas" → False.
    """
    # Palavra que começa com minúscula: não é nome próprio
    if not palavra[0].isupper():
        return True
    # Letra sozinha ("A", "E"): começo de frase, não identifica ninguém
    if len(palavra) == 1:
        return True
    # Sigla de estado
    if palavra.upper() in SIGLAS_DOS_ESTADOS and len(palavra) == 2:
        return True
    forma_simples = _sem_acento_em_minusculas(palavra)
    # 1. Palavra de cadastro da lista fixa
    if forma_simples in PALAVRAS_QUE_FICAM:
        return True
    # 2. Palavra de ligação do português
    if forma_simples in _palavras_de_ligacao():
        return True
    # O resto das palavras com maiúscula pode ser nome de alguém (ou de rua, cidade, empresa): vira etiqueta
    return False


def _parece_celular(digitos: str) -> bool:
    """True se os dígitos têm jeito de celular: DDD + 9 dígitos começando com 9 (com ou sem o 55 do Brasil).

    Ex.: "48983985015" → True; "4833221100" (fixo) → False; "5548983985015" → True.
    """
    if len(digitos) == 13 and digitos.startswith("55"):
        digitos = digitos[2:]
    return len(digitos) == 11 and digitos[2] == "9"


def _vem_depois_de_uma_uf(texto: str, posicao: int) -> bool:
    """True se, logo antes da posição, vem uma sigla de estado e uma vírgula, traço ou espaço ("…/SC, 88049739")."""
    antes = texto[max(0, posicao - 6):posicao]
    encontrado = re.search(r"(?<![A-Za-z])([A-Z]{2})[\s,-]+$", antes)
    return encontrado is not None and encontrado.group(1) in SIGLAS_DOS_ESTADOS


def _tipo_do_trecho(tipo_pelo_padrao: str, trecho: str) -> str:
    """O tipo que vai na etiqueta. Um número solto de 11 dígitos com CPF válido também é CPF.

    Exemplo: "52998224725" (11 dígitos, dígito verificador certo) vira CPF; "12345" continua NUMERO;
    "6.700" vira NUMERO (inteiro, sem dizer se é salário ou documento: quem decide é o rótulo ao lado).
    """
    # Número de 11 dígitos que passa na conta do CPF: é um CPF sem pontuação
    if tipo_pelo_padrao == "NUMERO" and len(trecho) == 11 and cpf_valido(trecho):
        return "CPF"
    # Telefone (ou número solto de 11 dígitos que não é CPF) com jeito de celular: a etiqueta diz que é celular.
    # A IA fica sabendo que é celular sem ver o número (EXP-010, rodada 3)
    if tipo_pelo_padrao in ("TELEFONE", "NUMERO") and _parece_celular(re.sub(r"\D", "", trecho)):
        return "CELULAR"
    # Número com pontos de milhar ("6.700", "5.218.440"): pode ser valor ou documento; fica um número só, sem tipo
    if tipo_pelo_padrao == "NUMERO_LONGO":
        return "NUMERO"
    return tipo_pelo_padrao


# ============================== Marcar e desmarcar ==============================

class _Etiquetador:
    """Dá as etiquetas: o mesmo valor ganha sempre a mesma etiqueta, e cada tipo tem a sua numeração."""

    def __init__(self, resultado: TextoMarcado):
        self.resultado = resultado            # onde o dicionário etiqueta → valor é guardado
        self.etiqueta_do_valor = {}           # "529.982.247-25" → "[CPF_1]"
        self.contador_por_tipo = {}           # "CPF" → quantas etiquetas de CPF já existem

    def etiqueta(self, trecho: str, tipo: str) -> str:
        """A etiqueta do trecho: a que ele já tem, ou uma nova ("[CPF_2]")."""
        # O mesmo valor ganha sempre a mesma etiqueta
        if trecho in self.etiqueta_do_valor:
            return self.etiqueta_do_valor[trecho]
        self.contador_por_tipo[tipo] = self.contador_por_tipo.get(tipo, 0) + 1
        etiqueta = f"[{tipo}_{self.contador_por_tipo[tipo]}]"
        self.etiqueta_do_valor[trecho] = etiqueta
        self.resultado.valor_da_etiqueta[etiqueta] = trecho
        return etiqueta


def _etiqueta_de_dado(etiquetador: _Etiquetador, texto: str, posicao: int, trecho: str, tipo_pelo_padrao: str) -> str:
    """O que entra no lugar de um dado que não é palavra (número, data, e-mail...).

    - E-mail: só a parte antes do @ vira etiqueta; o domínio fica ("[EMAIL_1]@gmail.com"), porque diz se o e-mail é
      pessoal ou da empresa e não identifica a pessoa;
    - número de 8 dígitos logo depois de uma UF ("…/SC, 88049739"): é o CEP;
    - o resto: a etiqueta do tipo (com celular separado de telefone, ver _tipo_do_trecho).
    """
    if tipo_pelo_padrao == "EMAIL":
        usuario, dominio = trecho.split("@", 1)
        return etiquetador.etiqueta(usuario, "EMAIL") + "@" + dominio
    if tipo_pelo_padrao == "NUMERO" and len(trecho) == 8 and _vem_depois_de_uma_uf(texto, posicao):
        return etiquetador.etiqueta(trecho, "CEP")
    return etiquetador.etiqueta(trecho, _tipo_do_trecho(tipo_pelo_padrao, trecho))


def marcar(texto: str) -> TextoMarcado:
    """Devolve uma cópia do texto com os dados trocados por etiquetas. O mesmo valor ganha sempre a mesma etiqueta.

    Exemplo:
        marcar("Maria Souza, CPF 529.982.247-25, mora em Campinas.")
        -> texto "[TEXTO_1] [TEXTO_2], CPF [CPF_1], mora em [TEXTO_3]."
    """
    resultado = TextoMarcado(texto="")
    etiquetador = _Etiquetador(resultado)
    # As datas escritas por extenso ("quatorze de setembro de mil novecentos e noventa e um"): viram UMA etiqueta
    fim_da_data_escrita = {}
    for inicio, fim in datas_por_extenso.trechos_de_data_escrita(texto):
        fim_da_data_escrita[inicio] = fim
    partes = []
    # Até onde o texto já foi copiado ou trocado
    posicao = 0
    # Percorre cada pedaço do texto que casou com o molde (números, e-mails, palavras)
    for encontrado in PADRAO_DOS_DADOS.finditer(texto):
        # Pedaço que ficou dentro de uma data por extenso já trocada: pula
        if encontrado.start() < posicao:
            continue
        # Copia o que vem antes do pedaço (espaços, pontuação)
        partes.append(texto[posicao:encontrado.start()])
        trecho = encontrado.group()
        fim_do_trecho = encontrado.end()
        tipo_pelo_padrao = encontrado.lastgroup
        if encontrado.start() in fim_da_data_escrita:
            # Começo de uma data por extenso: a data inteira vira uma etiqueta de data
            fim_do_trecho = fim_da_data_escrita[encontrado.start()]
            partes.append(etiquetador.etiqueta(texto[encontrado.start():fim_do_trecho], "DATA"))
        elif tipo_pelo_padrao == "PALAVRA":
            if _palavra_fica(trecho):
                # Palavra comum fica como está
                partes.append(trecho)
            else:
                # Palavra com maiúscula que pode ser nome de alguém (ou de rua, cidade, empresa)
                partes.append(etiquetador.etiqueta(trecho, "TEXTO"))
        else:
            partes.append(_etiqueta_de_dado(etiquetador, texto, encontrado.start(), trecho, tipo_pelo_padrao))
        posicao = fim_do_trecho
    # O que sobrou depois do último pedaço
    partes.append(texto[posicao:])
    resultado.texto = "".join(partes)
    return resultado


def etiquetas_do_texto(texto: str) -> list[str]:
    """As etiquetas que aparecem num texto, na ordem. Ex.: "[TEXTO_1] [CPF_2]" -> ["[TEXTO_1]", "[CPF_2]"]."""
    return PADRAO_DA_ETIQUETA.findall(texto)


def desmarcar(texto_com_etiquetas: str, valor_da_etiqueta: dict[str, str]) -> str:
    """Troca as etiquetas de volta pelos valores de verdade. Etiqueta desconhecida fica como está.

    Exemplo: desmarcar("[TEXTO_1] [TEXTO_2]", {"[TEXTO_1]": "Maria", "[TEXTO_2]": "Souza"}) -> "Maria Souza".
    """

    def devolver_o_valor(encontrado: re.Match) -> str:
        """Recebe uma etiqueta achada no texto e devolve o valor dela (ou a própria etiqueta, se não conhece)."""
        etiqueta = encontrado.group()
        return valor_da_etiqueta.get(etiqueta, etiqueta)

    # Troca cada etiqueta do texto pelo valor guardado
    return PADRAO_DA_ETIQUETA.sub(devolver_o_valor, texto_com_etiquetas)
