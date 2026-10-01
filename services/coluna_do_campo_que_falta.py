"""A informação que o arquivo inteiro não trouxe pode estar em outra coluna (ADR-124).

Para que serve: no cartão "o arquivo não trouxe o CPF", a empresa pode responder "na verdade, a matrícula é o CPF"
(ou "a coluna Registro é o CPF"). Sem isso, o agente recusaria ("Aqui eu só ajusto a informação CPF"), porque a
conversa só trataria a coluna do próprio campo, e o CPF não tem coluna nenhuma. Antes de trocar qualquer coisa:
    1. conferir: os valores da coluna passam pelas regras do campo da pendência, com o dígito verificador no CPF e no
       CNPJ, e a conversa diz quantos passaram;
    2. a troca só é oferecida quando a MAIORIA passa; os que não passam viram um cartão de revisão
       para cada pessoa depois da troca;
    3. usar_coluna, depois do "Sim" da empresa: a coluna passa para o campo da pendência, o campo que ela alimentava
       fica sem coluna (e ganha um cartão de revisão, se for obrigatório), e a leitura é refeita pelo caminho de
       sempre do aceite das colunas (padronização e conferências). O "Sim" da conversa vale como o aceite dessa
       coluna, sem voltar ao Cadastrar.
O Desfazer usa a mesma troca, de volta para o campo de antes.

Exemplo de uso:
    conferencia = conferir(conexao, "a1b2", "Registro", "cpf")
    if conferencia["maioria"]:
        campo_de_antes = usar_coluna(conexao, "EMP001", "rh.aurora", "a1b2", "Registro", "cpf")   # → "matricula"
"""
from models.contratos import StatusMapeamento, TipoCampo
from services import cadastro, conferencia_do_valor, mapeamentos, parametros, processamentos

# Os tipos de campo com dígito verificador (a conferência confere o dígito também)
TIPOS_COM_DIGITO = (TipoCampo.CPF, TipoCampo.CNPJ)


def _campo_do_layout(conexao, campo: str):
    """O campo do layout vigente pelo nome técnico. Levanta ValueError se ele não existe."""
    for campo_do_layout in parametros.layout_ativo(conexao)[1]:
        if campo_do_layout.campo == campo:
            return campo_do_layout
    raise ValueError(f"O campo {campo!r} não existe no layout.")


def _valores_da_coluna(conexao, processamento_id: str, coluna: str) -> list[str]:
    """Os valores da coluna no arquivo, um por linha, como vieram. Levanta ValueError se a coluna não existe."""
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    if coluna not in leitura.cabecalhos:
        raise ValueError(f'Não achei a coluna "{coluna}" no arquivo.')
    posicao = leitura.cabecalhos.index(coluna)
    valores = []
    for linha in leitura.linhas:
        valores.append(str(linha[posicao] or ""))
    return valores


def campo_de_hoje_da_coluna(conexao, processamento_id: str, coluna: str) -> str | None:
    """O campo que a coluna alimenta no mapeamento do envio (None se ela está de fora).

    Ex.: ("a1b2", "Registro") → "matricula".
    """
    atual = mapeamentos.obter(conexao, processamento_id)
    if atual is None:
        return None
    for item in atual[0].itens:
        if item.coluna == coluna and item.status != StatusMapeamento.NAO_MAPEADO:
            return item.campo
    return None


def conferir(conexao, processamento_id: str, coluna: str, campo: str) -> dict:
    """Confere os valores de uma coluna do arquivo com as regras do campo da pendência, sem gravar nada.

    Recebe: o envio; a coluna do arquivo; o campo da pendência (ex.: "cpf").
    Devolve: {coluna, campo, campo_de_hoje, preenchidos, validos, exemplos, maioria, com_digito}. campo_de_hoje: o
    campo que a coluna alimenta hoje (None se está de fora); exemplos: os primeiros valores que não passaram,
    [{valor, motivo}]; maioria: True se mais da metade dos valores preenchidos passou (só assim a troca é oferecida);
    com_digito: True se a conferência olhou o dígito verificador (CPF e CNPJ).
    Ex.: a coluna "Registro", hoje a matrícula, com 35 CPFs certos → {..., "validos": 35, "maioria": True}.
    Levanta ValueError se a coluna não existe no arquivo ou o campo não existe no layout.
    """
    campo_do_layout = _campo_do_layout(conexao, campo)
    valores = _valores_da_coluna(conexao, processamento_id, coluna)
    # A mesma conferência da tela de colunas, com o dígito verificador do CPF e do CNPJ e a regra do nome de pessoa
    # (ADR-127: a ficha inteira numa célula não pode virar o Nome completo)
    conferencia = conferencia_do_valor.conferir_valores(valores, campo_do_layout)
    validos = conferencia["preenchidos"] - conferencia["nao_servem"]
    return {"coluna": coluna, "campo": campo,
            "campo_de_hoje": campo_de_hoje_da_coluna(conexao, processamento_id, coluna),
            "preenchidos": conferencia["preenchidos"], "validos": validos, "exemplos": conferencia["exemplos"],
            "maioria": validos * 2 > conferencia["preenchidos"],
            "com_digito": campo_do_layout.tipo in TIPOS_COM_DIGITO}


def usar_coluna(conexao, empresa_id: str, login: str, processamento_id: str, coluna: str, campo: str | None,
                cliente=None, busca=None) -> str | None:
    """Troca o campo da coluna e refaz a leitura: o "Sim" da conversa vale como o aceite dessa coluna.

    Recebe: o envio; a coluna; o campo novo (None = a coluna fica de fora, no Desfazer de uma coluna que estava de
    fora); cliente e busca (os do fluxo; os testes passam versões falsas).
    Devolve: o campo que a coluna alimentava antes (None se estava de fora).
    Levanta KeyError (outra empresa) ou ValueError (coluna que não existe ou dividida em partes, ou o aceite recusado:
    aí o envio fica em "Conferir as colunas", e a mensagem diz por quê).
    """
    campo_de_antes = mapeamentos.trocar_o_campo_da_coluna(conexao, processamento_id, empresa_id, coluna, campo,
                                                          f"Agente de validação (para {login})")
    escolha = campo or mapeamentos.IGNORAR
    # O aceite pelo caminho de sempre: o fluxo volta ao aceite, aplica a escolha, padroniza e valida de novo
    leitura = cadastro.aceitar_mapeamento(conexao, empresa_id, login, processamento_id, {coluna: escolha},
                                          cliente=cliente, busca=busca)
    if leitura.get("erro"):
        raise ValueError(f'Não deu para trocar a coluna direto: {leitura["erro"]} Confira as colunas no Cadastrar.')
    return campo_de_antes
