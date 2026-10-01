"""Contratos do Integra Folha: a "planta" que todas as fases seguem.

Aqui ficam as listas fechadas do sistema (tipos de campo, situações, perfis, tipos de carga) e o
formato dos dados que passam de uma etapa para outra. Nenhuma etapa inventa valores fora destas listas.

"Contrato" é um formato combinado: se um dado não cabe nele, é recusado na hora (a biblioteca Pydantic
faz essa conferência). Alguns contratos mantêm o nome em inglês (FileProfile,
MappingPlan), porque é assim que aparecem nos ADRs e na documentação.
"""
import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator

# Arquivo com a versão 1 do layout (os 44 campos que o banco quer receber)
CAMINHO_LAYOUT_V1 = Path(__file__).resolve().parent.parent / "data" / "contratos" / "layout_v1.csv"


class TipoCampo(str, Enum):
    """A lista fechada de tipos de campo (ADR-04). O tipo decide como converter e como validar."""

    TEXTO = "TEXTO"                            # texto livre (nome, cargo, endereço)
    CPF = "CPF"                                # 11 dígitos com dígito verificador
    CNPJ = "CNPJ"                              # 14 dígitos com dígito verificador
    CEP = "CEP"                                # 8 dígitos
    UF = "UF"                                  # sigla do estado (SP, RJ...)
    TELEFONE = "TELEFONE"                      # DDD e número
    EMAIL = "EMAIL"                            # endereço de e-mail
    MATRICULA = "MATRICULA"                    # identificador do funcionário na empresa (texto, com zeros)
    DECIMAL_MONETARIO = "DECIMAL_MONETARIO"    # dinheiro, sempre com duas casas decimais
    DATA = "DATA"                              # data, guardada como AAAA-MM-DD
    DOMINIO = "DOMINIO"                        # um valor de uma lista (ex.: CLT ou PRO_LABORE)


# Os tipos de campo que aceitam mínimo e máximo no parâmetro (ADR-128): os de número. Hoje, só o dinheiro
TIPOS_COM_FAIXA = (TipoCampo.DECIMAL_MONETARIO,)

# Duas casas decimais: o jeito de guardar o mínimo e o máximo (500 e 500,00 são o mesmo limite)
DUAS_CASAS = Decimal("0.01")


class TipoCarga(str, Enum):
    """Carga inicial (a lista completa, enviada uma vez) ou inclusão (só funcionários novos) (ADR-23)."""

    INICIAL = "INICIAL"
    INCLUSAO = "INCLUSAO"


class EstadoProcessamento(str, Enum):
    """As situações de um arquivo, do recebimento à homologação."""

    RECEBIDO = "RECEBIDO"                          # o arquivo foi lido e registrado
    PERFILADO = "PERFILADO"                        # reservado: retrato do arquivo pronto
    MAPEAMENTO_PENDENTE = "MAPEAMENTO_PENDENTE"    # a proposta de mapeamento espera o aceite da empresa
    MAPEAMENTO_APROVADO = "MAPEAMENTO_APROVADO"    # a empresa aceitou o mapeamento
    NORMALIZADO = "NORMALIZADO"                    # dados padronizados e sem pendência que impeça homologar
    VALIDACAO_PENDENTE = "VALIDACAO_PENDENTE"      # a validação encontrou pendências a resolver
    AGUARDANDO_BANCO = "AGUARDANDO_BANCO"          # a empresa enviou: o especialista do banco avalia (ADR-69, passo 15)
    DEVOLVIDO = "DEVOLVIDO"                        # o banco devolveu com um motivo: a empresa ajusta e envia de novo
    HOMOLOGADO = "HOMOLOGADO"                      # o banco aprovou: funcionários cadastrados, o banco já pode planejar
    REJEITADO = "REJEITADO"                        # reservado: arquivo descartado


class Perfil(str, Enum):
    """Perfis de acesso. O perfil vem do cadastro do usuário, nunca de uma escolha na tela (ADR-32).

    Nesta versão, dois perfis: o que a empresa vê e o que o banco vê (o banco tem a gestão completa). O perfil
    CIENTISTA saiu do sistema (ADR-78); uma gestão de acesso mais fina fica como evolução.
    """

    EMPRESA = "EMPRESA"        # o RH da empresa cliente
    BANCO = "BANCO"            # o especialista do banco (gestão completa, inclusive o desempenho da IA)


# Operações que só acontecem com o clique de uma pessoa (ADR-16)
OPERACOES_COM_APROVACAO_HUMANA = {
    "aceitar_mapeamento": "Aceitar o mapeamento de colunas ambíguas ou críticas",
    "aplicar_correcao": "Aplicar uma correção de dado pedida na conversa",
    "justificar_alerta": "Justificar um alerta, como renda fora do padrão do cargo",
    "homologar_arquivo": "Homologar o arquivo e liberar o motor de planejamento",
    "publicar_endomarketing": "Aprovar um texto do Endomarketing antes de a empresa usar",
    "alterar_parametros": "Gravar nova versão do layout, das premissas ou do catálogo",
}


class CampoLayout(BaseModel):
    """Um campo do layout que o banco quer receber (ADR-03).

    A descrição, a regra, o "não confundir com" e o exemplo são o que a IA lê para entender o campo.
    """

    campo: str                         # nome técnico (ex.: "valor_renda")
    grupo: str                         # grupo do campo (ex.: "Renda", "Endereço comercial")
    tipo: TipoCampo                    # um tipo da lista fechada
    obrigatorio: bool                  # vazio é pendência BLOQUEANTE
    sensivel: bool                     # dado pessoal (LGPD): classificação para o inventário do banco (ADR-101)
    uso_comercial_permitido: bool      # o motor de planejamento só lê campos com True (ADR-29)
    descricao: str = ""                # o que é o campo, em linguagem simples
    regra: str = ""                    # como o valor deve ser
    nao_confundir_com: str = ""        # campos parecidos, para a IA pedir ajuda em vez de chutar (ADR-07)
    exemplo: str = ""                  # um valor de exemplo
    # Pode ser o mesmo para todos os funcionários do arquivo (ex.: o CNPJ do empregador, o endereço comercial)? Só essas
    # informações podem ser informadas uma vez para todos; as do titular são de cada pessoa (ADR-124).
    # None nas versões do parâmetro gravadas antes (vale a lista padrão de parametros.py)
    igual_para_todos: bool | None = None
    # A faixa esperada de um campo numérico (ADR-128; hoje, só o tipo DECIMAL_MONETARIO, ex.: o salário a partir de
    # R$ 500,00). Opcionais: sem valor, não há limite daquele lado. Um valor fora da faixa gera ALERTA, e não recusa:
    # a empresa confirma que está certo ou corrige
    minimo: Decimal | None = None
    maximo: Decimal | None = None

    @field_validator("campo")
    @classmethod
    def nome_tecnico(cls, valor: str) -> str:
        """O nome técnico só pode ter minúsculas, números e "_" (ele vira nome de coluna no sistema)."""
        # Tira espaços das pontas
        valor = valor.strip()
        # Confere caractere por caractere
        so_caracteres_permitidos = True
        for caractere in valor:
            if not (caractere.islower() or caractere.isdigit() or caractere == "_"):
                so_caracteres_permitidos = False
        # Vazio ou com caractere proibido: recusa
        if not valor or not so_caracteres_permitidos:
            raise ValueError(f"nome de campo inválido: {valor!r} (use minúsculas, números e _)")
        return valor

    @field_validator("obrigatorio", "sensivel", "uso_comercial_permitido", mode="before")
    @classmethod
    def sim_ou_nao(cls, valor):
        """No arquivo CSV, os campos de sim/não vêm como "S" ou "N"; aqui viram verdadeiro ou falso."""
        # Só o texto precisa ser traduzido (verdadeiro/falso já vêm prontos)
        if isinstance(valor, str):
            letra = valor.strip().upper()
            # Qualquer coisa diferente de S ou N é recusada
            if letra not in ("S", "N"):
                raise ValueError(f"use S ou N, não {valor!r}")
            return letra == "S"
        return valor

    @field_validator("igual_para_todos", mode="before")
    @classmethod
    def sim_nao_ou_vazio(cls, valor):
        """ "S" ou "N" viram verdadeiro ou falso; vazio vira None (a versão do parâmetro não disse: vale o padrão)."""
        # Vazio ou nada: não disse
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return None
        # Texto: S ou N, como as outras marcações
        if isinstance(valor, str):
            letra = valor.strip().upper()
            if letra not in ("S", "N"):
                raise ValueError(f"use S ou N, não {valor!r}")
            return letra == "S"
        return valor

    @field_validator("minimo", "maximo", mode="before")
    @classmethod
    def valor_do_limite(cls, valor):
        """O mínimo ou o máximo escrito como a pessoa escreve (com vírgula, ponto de milhar e "R$") vira um número.

        Vazio vira None (sem limite). Ex.: "500" → 500.00; "1.500,50" → 1500.50; "R$ 500,00" → 500.00; "2.000" →
        2000.00; "1500.5" → 1500.50; "" → None.
        """
        # Vazio ou nada: sem limite
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return None
        # Número que já veio pronto (da versão gravada ou de um teste): só as duas casas decimais
        if not isinstance(valor, str):
            return Decimal(str(valor)).quantize(DUAS_CASAS)
        # Tira o "R$" e os espaços
        texto = valor.replace("R$", "").strip()
        # Com vírgula, é o jeito brasileiro: o ponto separa o milhar e a vírgula, os centavos
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        # Sem vírgula, pontos seguidos de grupos de 3 dígitos também são o milhar ("2.000" é dois mil, não dois)
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
            texto = texto.replace(".", "")
        try:
            numero = Decimal(texto)
        except InvalidOperation as erro:
            raise ValueError(f"escreva um número, como 500 ou 1.500,00, não {valor!r}") from erro
        return numero.quantize(DUAS_CASAS)

    @model_validator(mode="after")
    def faixa_so_em_campo_numerico(self):
        """O mínimo e o máximo só existem em campo numérico, e o mínimo não pode passar do máximo."""
        tem_limite = self.minimo is not None or self.maximo is not None
        # Um CPF ou um nome não têm faixa: recusa, para o banco não achar que o limite vale
        if tem_limite and self.tipo not in TIPOS_COM_FAIXA:
            raise ValueError("mínimo e máximo só valem para campos de valor (tipo DECIMAL_MONETARIO)")
        # Os dois lados: o mínimo tem de ser menor ou igual ao máximo
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError("o mínimo não pode ser maior que o máximo")
        return self


def carregar_layout(caminho: Path = CAMINHO_LAYOUT_V1) -> list[CampoLayout]:
    """Lê o layout de um CSV e confere cada campo contra o contrato CampoLayout."""
    campos = []
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            campos.append(CampoLayout(**linha))
    return campos


def definir_tipo_carga(empresa_tem_funcionarios_homologados: bool) -> TipoCarga:
    """O tipo de carga é uma regra, não uma pergunta à empresa (ADR-23): com homologados, é inclusão."""
    if empresa_tem_funcionarios_homologados:
        return TipoCarga.INCLUSAO
    return TipoCarga.INICIAL


class ColunaPerfil(BaseModel):
    """Uma coluna do arquivo como chegou: nome, tipo provável e até 3 exemplos reais (ADR-101)."""

    posicao: int                  # posição da coluna no arquivo (1 = primeira)
    nome: str                     # o nome como está no cabeçalho
    tipo_provavel: str            # o tipo que parece ser (CPF, DATA, TEXTO...)
    vazias: int                   # quantas células vazias
    amostras: list[str]           # até 3 valores diferentes da coluna, como estão no arquivo
    aviso: str | None = None      # ex.: "células gravadas como número no Excel"


class FileProfile(BaseModel):
    """O retrato do arquivo recebido, antes de qualquer IA.

    É tudo o que o Interpretador vai ver do arquivo: o nome de cada coluna, o tipo provável e até 3 exemplos
    reais (ADR-101).
    """

    processamento_id: str                    # o identificador do envio
    empresa_id: str                          # de quem é o arquivo
    nome_arquivo: str                        # o nome do arquivo enviado
    formato: str                             # "csv", "txt", "rtf", "xlsx", "xls", "ods", "docx" ou "odt"
    codificacao: str | None                  # codificação do CSV (ex.: "utf-8")
    separador: str | None                    # separador do CSV (ex.: ";")
    linha_do_cabecalho: int                  # em que linha estava o cabeçalho
    n_linhas: int                            # número de funcionários (linhas de dados)
    n_colunas: int                           # número de colunas
    colunas: list[ColunaPerfil]              # o retrato de cada coluna
    hash_sha256: str                         # a impressão digital do arquivo
    tamanho_bytes: int                       # tamanho do arquivo
    tipo_carga: TipoCarga                    # INICIAL ou INCLUSAO
    data_referencia: date                    # a data de referência informada pela empresa
    status: EstadoProcessamento              # a situação atual
    avisos: list[str] = []                   # recados da leitura para a empresa
    alertas_guardrail: list[dict] = []       # onde o guardrail trocou algum texto
    duvidas: list[str] = []                  # trechos do documento que a IA não conseguiu ler (não são de ninguém)
    perguntas_da_ia: list[dict] = []         # perguntas da IA presas a uma pessoa: {linha, campo, pergunta} (ADR-73)
    origem_das_colunas: dict = {}            # texto corrido: {campo: {rotulos, pessoas}}, como a empresa chamou
    envio_de_origem: str | None = None       # no envio de devolução (ADR-121): o envio de onde as pessoas vieram


class StatusMapeamento(str, Enum):
    """Como o Interpretador respondeu sobre uma coluna (ADR-07: pedir ajuda é melhor que chutar)."""

    PROPOSTO = "PROPOSTO"          # a IA propõe um campo do layout
    AMBIGUO = "AMBIGUO"            # pode ser mais de um campo: uma pessoa decide
    NAO_MAPEADO = "NAO_MAPEADO"    # não corresponde a nenhum campo do layout
    DIVIDIR = "DIVIDIR"            # a coluna tem mais de uma informação: a IA propõe dividir (ADR-104)


# As ferramentas que dividem uma coluna (services/divisao.py). A IA escolhe; a regra executa em todas as linhas
FERRAMENTAS_DE_DIVISAO = ("endereco", "cidade_uf", "separador")


class ParteDaDivisao(BaseModel):
    """Uma parte da coluna dividida e o campo do layout que ela alimenta (ex.: parte "cep" → cep_residencial)."""

    parte: str                     # endereço e cidade/UF: logradouro, numero, complemento, bairro, municipio, uf ou
                                   # cep; separador: o nome da posição (ex.: "agência"), na ordem em que aparece
    campo: str | None = None       # o campo do layout (vazio: a parte fica de fora)


class DivisaoProposta(BaseModel):
    """Como dividir uma coluna: a ferramenta, o separador (só na ferramenta "separador") e o campo de cada parte."""

    ferramenta: str                # "endereco", "cidade_uf" ou "separador"
    separador: str = ""            # ex.: "/", " - ", ";" (só na ferramenta "separador")
    partes: list[ParteDaDivisao]   # as partes, cada uma com o seu campo
    refeita: int = 0               # quantas vezes a empresa pediu para refazer com um comentário (limite na tela)


class ItemMapeamento(BaseModel):
    """Uma coluna do arquivo e o campo do layout que ela alimenta."""

    coluna: str                    # o nome da coluna no arquivo
    campo: str | None = None       # o campo do layout (vazio se AMBIGUO ou NAO_MAPEADO)
    status: StatusMapeamento       # PROPOSTO, AMBIGUO ou NAO_MAPEADO
    justificativa: str             # por que a IA (ou a regra) decidiu assim
    fontes: list[str] = []         # trechos do conhecimento usados na decisão
    candidatos: list[str] = []     # para AMBIGUO: os campos possíveis
    divisao: DivisaoProposta | None = None  # para DIVIDIR (e na coluna já dividida): como ela foi dividida
    origem: str = "llm"            # quem decidiu: "llm", "reuso", "humano", "regra", "handoff" ou "leitor" (Word)

    @field_validator("campo")
    @classmethod
    def sem_vazio(cls, valor):
        """Campo vazio ou só com espaços vira "sem campo" (None)."""
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
        return None


def _vazio_no_lugar_de_nulo(valor):
    """A IA às vezes manda null (nulo) onde combinamos texto: vira texto vazio, em vez de derrubar a resposta."""
    if valor is None:
        return ""
    return valor


class BlocoDePessoa(BaseModel):
    """Um pedaço do documento que fala de uma pessoa só: da linha `inicio` até a linha `fim` (contando de 1)."""

    inicio: int                    # primeira linha do bloco
    fim: int                       # última linha do bloco (inclusive)


class RespostaSegmentacao(BaseModel):
    """O formato da divisão do documento em blocos, um por pessoa (ADR-73). Ex.: {"blocos": [{"inicio": 3, "fim": 7}]}"""

    blocos: list[BlocoDePessoa]    # os blocos, na ordem do documento


class CampoLido(BaseModel):
    """Um campo do layout preenchido pela IA, com o trecho do documento de onde ela tirou o valor."""

    campo: str                     # o nome do campo no layout (ex.: "cpf")
    valor: str                     # o valor, copiado do documento
    trecho: str = ""               # o pedaço do documento que justifica o valor (a "prova")
    rotulo: str = ""               # como a empresa chamou o dado no documento (ex.: "Registro do cliente"); ADR-105

    @field_validator("valor", "trecho", "rotulo", mode="before")
    @classmethod
    def sem_nulo(cls, valor):
        """null vira texto vazio."""
        return _vazio_no_lugar_de_nulo(valor)


class DuvidaDoLeitor(BaseModel):
    """Uma pergunta da IA para a empresa sobre um campo que ela não conseguiu preencher com segurança."""

    campo: str = ""                # o campo da dúvida (pode ficar vazio, se a dúvida é sobre a pessoa toda)
    pergunta: str                  # a pergunta, em uma frase educada, que vai para a tela

    @field_validator("campo", mode="before")
    @classmethod
    def sem_nulo(cls, valor):
        """null vira texto vazio."""
        return _vazio_no_lugar_de_nulo(valor)


class FuncionarioLido(BaseModel):
    """Uma pessoa encontrada num bloco: os campos preenchidos e as dúvidas."""

    campos: list[CampoLido]            # os campos que o documento informa
    duvidas: list[DuvidaDoLeitor] = []  # o que a IA não conseguiu decidir sozinha


class RespostaLeitorDeDocumentos(BaseModel):
    """O formato que o Leitor de Documentos devolve para cada bloco (ADR-73). Resposta fora dele é rejeitada.

    Exemplo: {"funcionarios": [{"campos": [{"campo": "cpf", "valor": "[CPF_1]", "trecho": "CPF [CPF_1]"}],
                                "duvidas": []}]}
    """

    funcionarios: list[FuncionarioLido]  # normalmente um só (o bloco é de uma pessoa); pode vir vazio


class RespostaInterpretador(BaseModel):
    """O formato que a IA precisa devolver. Resposta fora dele é rejeitada (ADR-07)."""

    itens: list[ItemMapeamento]    # um item por coluna


class MappingPlan(BaseModel):
    """A proposta completa de mapeamento de um arquivo, com a configuração que a gerou."""

    processamento_id: str          # de qual envio é
    versao_layout: int             # com qual versão do layout foi feito
    configuracao: str              # B1, B2 ou B3 (ADR-05)
    modelo: str                    # qual modelo respondeu ("mock" no modo simulado)
    versao_prompt: str             # qual versão do prompt foi usada
    itens: list[ItemMapeamento]    # a decisão de cada coluna
    chamou_llm: bool               # False quando tudo veio de um mapeamento já aprovado (reuso)
    observacoes: list[str] = []    # ex.: destino recusado pelo guardrail de saída, nova tentativa
