"""A conferência de um valor ANTES de ele entrar no cadastro (ADR-127).

Para que serve: o cartão de pendência só pode dizer "Pronto" quando o valor confere. O QA da jornada, com a IA real,
achou dois furos:
    - o CPF errado: a empresa escreveu o CPF "123.456.789-00" (dígito errado); a conversa respondeu "Pronto: preenchi a
      informação CPF" e só depois nasceu o cartão "CPF com o dígito verificador errado". A padronização aceita o
      número com o dígito errado (quem aponta é o Validador, depois); aqui o dígito é conferido antes;
    - o nome que vira a ficha: "os dados estão todos na coluna transcrição" fez o Nome completo virar a ficha inteira da pessoa, com CPF,
      identidade e nascimento. Um campo de texto aceitava qualquer coisa com uma letra; aqui, um nome de pessoa não
      pode ter dígitos nem ser comprido demais.
A regra vale para os dois caminhos da conversa: o valor que a empresa escreve (motivo_para_recusar) e a coluna que
ela indica (conferir_valores). Na dúvida, o cartão pergunta de novo e nada muda.

Exemplo de uso:
    motivo = motivo_para_recusar(conexao, "cpf", "123.456.789-00")   # → "o dígito verificador está errado"
    conferencia = conferir_valores(["Ana Lima", "Ana; CPF 715.937.364-28"], campo_do_layout_do_nome)
"""
from models.contratos import TipoCampo
from services import normalizador, parametros
from services.documentos import cnpj_valido, cpf_valido

# Os campos com o nome de uma pessoa (o titular e a mãe). O "Nome da unidade" fica de fora: ele pode ter número
# ("Loja 12")
CAMPOS_DE_NOME_DE_PESSOA = ("nome_completo", "nome_mae")
# O maior número de palavras de um nome de pessoa. Ex.: "Maria da Conceição dos Santos Oliveira de Souza Lima" tem 9;
# a ficha inteira numa célula passa disso com folga
MAXIMO_DE_PALAVRAS_NO_NOME = 10
# Quantos exemplos que não passaram a conferência da coluna devolve (o mesmo número do Normalizador)
EXEMPLOS_QUE_NAO_SERVEM = normalizador.EXEMPLOS_QUE_NAO_SERVEM


def motivo_do_nome(valor: str) -> str | None:
    """Por que um valor não pode ser o nome de uma pessoa, ou None se ele pode.

    Recebe: o valor (ex.: o que veio na coluna indicada, ou o que a empresa escreveu).
    Devolve: o motivo em português simples, ou None.
    Ex.: "Elisa Rocha; registro 715.937.364-28" → "um nome não tem números"; "Ana Lima" → None.
    """
    # Um dígito em qualquer lugar: CPF, identidade, data de nascimento... nada disso é nome
    for caractere in valor:
        if caractere.isdigit():
            return "um nome não tem números"
    # Palavras demais: é um texto sobre a pessoa, e não o nome dela
    if len(valor.split()) > MAXIMO_DE_PALAVRAS_NO_NOME:
        return f"um nome não tem mais de {MAXIMO_DE_PALAVRAS_NO_NOME} palavras"
    return None


def campo_do_layout_pelo_nome(conexao, campo: str):
    """O campo do layout vigente pelo nome técnico, ou None se ele não existe."""
    for campo_do_layout in parametros.layout_ativo(conexao)[1]:
        if campo_do_layout.campo == campo:
            return campo_do_layout
    return None


def _motivo_do_digito(convertido: str, tipo: TipoCampo) -> str | None:
    """ "o dígito verificador está errado" no CPF ou no CNPJ com o dígito errado; None nos outros casos."""
    if tipo == TipoCampo.CPF and not cpf_valido(convertido):
        return "o dígito verificador está errado"
    if tipo == TipoCampo.CNPJ and not cnpj_valido(convertido):
        return "o dígito verificador está errado"
    return None


def motivo_para_recusar(conexao, campo: str | None, valor: str | None) -> str | None:
    """Por que o valor não pode entrar no campo, ou None se ele confere. Não grava nada.

    Recebe: conexao (para ler o layout vigente); o campo da pendência; o valor que a empresa escreveu.
    Devolve: o motivo, ou None. Valor vazio ou campo que não está no layout: None (quem decide é quem chama; deixar em
    branco tem a sua própria confirmação).
    Confere, em ordem: a padronização do campo (a mesma do arquivo), o dígito verificador do CPF e do CNPJ e a regra
    do nome de pessoa.
    Ex.: ("cpf", "123.456.789-00") → "o dígito verificador está errado"; ("cpf", "529.982.247-25") → None.
    """
    if not campo or not (valor or "").strip():
        return None
    campo_do_layout = campo_do_layout_pelo_nome(conexao, campo)
    if campo_do_layout is None:
        return None
    # A padronização do campo (ex.: CPF sem 11 dígitos, data que não existe, valor fora da lista)
    try:
        convertido = normalizador.converter_valor(valor, campo_do_layout)
    except normalizador.NaoConvertido as motivo:
        return str(motivo)
    # O dígito verificador (a padronização aceita o número com o dígito errado)
    motivo_do_digito = _motivo_do_digito(convertido, campo_do_layout.tipo)
    if motivo_do_digito:
        return motivo_do_digito
    # O nome de uma pessoa: sem números e sem palavras demais
    if campo in CAMPOS_DE_NOME_DE_PESSOA:
        return motivo_do_nome(convertido)
    return None


def conferir_valores(valores: list[str], campo_do_layout) -> dict:
    """Confere os valores de uma coluna para um campo: a conferência do Normalizador, com o dígito verificador, mais a
    regra do nome de pessoa.

    Recebe: os valores da coluna (vazios são ignorados); o campo do layout.
    Devolve: {"preenchidos": N, "nao_servem": N, "exemplos": [{"valor", "motivo"}]}, o formato do Normalizador.
    Ex.: 3 fichas inteiras na coluna indicada como o Nome completo → {"preenchidos": 3, "nao_servem": 3, ...}.
    """
    # Os outros campos: a conferência do Normalizador, com o dígito do CPF e do CNPJ
    if campo_do_layout.campo not in CAMPOS_DE_NOME_DE_PESSOA:
        return normalizador.conferir_valores_para_o_campo(valores, campo_do_layout, conferir_digito=True)
    # O nome de uma pessoa: valor por valor, para cada um contar uma vez só (o do Normalizador ou o do nome)
    preenchidos = 0
    nao_servem = 0
    exemplos = []
    for valor in valores:
        if not valor.strip():
            continue
        preenchidos = preenchidos + 1
        # Primeiro, a conferência de texto do Normalizador (ex.: um valor sem nenhuma letra)
        do_normalizador = normalizador.conferir_valores_para_o_campo([valor], campo_do_layout)
        if do_normalizador["exemplos"]:
            motivo = do_normalizador["exemplos"][0]["motivo"]
        else:
            motivo = motivo_do_nome(valor.strip())
        if motivo is None:
            continue
        nao_servem = nao_servem + 1
        if len(exemplos) < EXEMPLOS_QUE_NAO_SERVEM:
            exemplos.append({"valor": valor, "motivo": motivo})
    return {"preenchidos": preenchidos, "nao_servem": nao_servem, "exemplos": exemplos}
