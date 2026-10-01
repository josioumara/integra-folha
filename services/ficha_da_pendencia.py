"""A ficha completa de uma pessoa de um envio ainda com a empresa, aberta a partir do cartão de uma pendência
(ADR-120).

Para que serve: no cartão "Ajuste na informação "Estado civil" de Ana Lima", o botão "Ver a ficha completa" mostra
tudo o que o sistema está considerando para a Ana naquele envio, com a informação em revisão em destaque. Assim a
empresa decide olhando o contexto (ex.: o cargo e a data de nascimento ajudam a conferir um salário fora do comum).

O que a ficha traz:
    - os campos que o sistema está considerando: os que têm coluna no arquivo, mais os que têm pendência nesta linha,
      na ordem do parâmetro e agrupados pelo grupo dele (ex.: "Funcionário", "Endereço comercial");
    - o valor de cada campo como vai para o banco, já com as correções aplicadas, no jeito da empresa ler (CPF com
      pontos, data dd/mm/aaaa, renda em reais);
    - quais campos ainda têm pendência nesta linha (os problemas da pessoa inteira, como estar em outro arquivo, não
      marcam o CPF) e, quando o sistema não conseguiu entender o valor, o que veio no arquivo ("valor_lido").

As regras: só a empresa dona do envio (KeyError → 404, sem dizer se o envio existe em outra empresa); a linha tem de
existir no envio (ValueError → 400); cada abertura fica registrada, como a ficha dos funcionários cadastrados (LGPD).

Exemplo de uso:
    ficha = ficha_da_linha(conexao, "EMP001", "rh.aurora", "a1b2c3", 8)
    # {"linha": 8, "nome": "Ana Lima", "grupos": [{"grupo": "Funcionário", "campos": [...]}]}
"""
from services import (acompanhamento, correcoes, mapeamentos, parametros, pendencias_em_grupo, pergunta_da_pendencia,
                      processamentos, validador)


def _registro_da_linha(conexao, processamento_id: str, linha: int) -> dict:
    """O registro da linha, com as correções aplicadas. Levanta ValueError se a linha não está no envio."""
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] == linha:
            return registro
    raise ValueError(f"A linha {linha} não está neste envio.")


def _campos_com_coluna(conexao, processamento_id: str) -> set[str]:
    """Os campos do layout que têm uma coluna no arquivo (o mapeamento aceito do envio)."""
    campos = set()
    mapeamento = mapeamentos.obter(conexao, processamento_id)
    if mapeamento is None:
        return campos
    for item in mapeamento[0].itens:
        if item.campo:
            campos.add(item.campo)
    return campos


def _pendencias_da_linha(conexao, processamento_id: str, linha: int) -> dict[str, str | None]:
    """Os campos com pendência em aberto nesta linha: {campo: o que veio no arquivo (ou None)}."""
    pendencias = {}
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return pendencias
    for achado in relatorio.achados:
        if achado.linha != linha or not achado.campo or not pendencias_em_grupo.achado_em_aberto(achado):
            continue
        # Os problemas da pessoa inteira (repetida, em outro arquivo) ficam presos ao CPF só para achar a pessoa: o
        # CPF não tem problema por causa deles (um cartão, um problema: ADR-120)
        if achado.regra_id in acompanhamento.REGRAS_DA_PESSOA:
            continue
        # O que veio no arquivo: vale quando o sistema não conseguiu entender o valor
        pendencias[achado.campo] = achado.valor or pendencias.get(achado.campo)
    return pendencias


def _campo_para_a_ficha(campo_do_layout, registro: dict, pendencias: dict) -> dict:
    """Um campo como a ficha mostra: {campo, nome, valor, obrigatorio, com_pendencia, valor_lido}."""
    campo = campo_do_layout.campo
    valor = registro.get(campo)
    valor_na_tela = ""
    if valor not in (None, ""):
        valor_na_tela = acompanhamento.valor_lido_para_a_tela(campo, str(valor)) or str(valor)
    com_pendencia = campo in pendencias
    # O que veio no arquivo só aparece quando é diferente do valor que o sistema está considerando
    valor_lido = None
    if com_pendencia and pendencias[campo] and pendencias[campo] != valor:
        valor_lido = pendencias[campo]
    nome = pergunta_da_pendencia.nome_da_informacao(campo_do_layout.descricao, acompanhamento.rotulo_do_campo(campo))
    return {"campo": campo, "nome": nome, "valor": valor_na_tela, "obrigatorio": campo_do_layout.obrigatorio,
            "com_pendencia": com_pendencia, "valor_lido": valor_lido}


def ficha_da_linha(conexao, empresa_id: str, login: str, processamento_id: str, linha: int) -> dict:
    """A ficha completa de uma pessoa do envio (ver o texto do alto).

    Recebe: conexao; empresa_id e login (da sessão); o envio; a linha do arquivo.
    Devolve: {linha, nome, grupos: [{grupo, campos: [{campo, nome, valor, obrigatorio, com_pendencia, valor_lido}]}]}.
    Levanta KeyError (envio de outra empresa ou inexistente) ou ValueError (linha que não está no envio).
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    registro = _registro_da_linha(conexao, processamento_id, linha)
    campos_com_coluna = _campos_com_coluna(conexao, processamento_id)
    pendencias = _pendencias_da_linha(conexao, processamento_id, linha)
    # Os campos considerados, na ordem do parâmetro, agrupados pelo grupo dele (os grupos na ordem em que aparecem)
    grupos = []
    grupo_pelo_nome = {}
    for campo_do_layout in parametros.layout_ativo(conexao)[1]:
        considerado = campo_do_layout.campo in campos_com_coluna or campo_do_layout.campo in pendencias
        if not considerado:
            continue
        if campo_do_layout.grupo not in grupo_pelo_nome:
            grupo_pelo_nome[campo_do_layout.grupo] = {"grupo": campo_do_layout.grupo, "campos": []}
            grupos.append(grupo_pelo_nome[campo_do_layout.grupo])
        grupo_pelo_nome[campo_do_layout.grupo]["campos"].append(
            _campo_para_a_ficha(campo_do_layout, registro, pendencias))
    # A abertura fica registrada, como a ficha dos funcionários cadastrados (LGPD)
    acompanhamento.registrar_acesso(conexao, empresa_id, login, acompanhamento.ACESSO_FICHA, 1)
    nome = registro.get("nome_completo") or f"Pessoa da linha {linha}"
    return {"linha": linha, "nome": nome, "grupos": grupos}
