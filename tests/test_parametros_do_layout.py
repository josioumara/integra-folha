"""ADR-128: as decisões sobre o parâmetro do layout, cada uma com variações novas.

1. Tipo de renda: "Mensal", "Horária" (e parecidos) nunca viram CLT sozinhos; a lista ganha OUTROS.
2. Matrícula: fica no parâmetro, OPCIONAL; a empresa que não usa matrícula envia sem ela, e o funcionário é
   identificado pelo CPF. Regra geral junto: um campo que o banco tira do parâmetro nunca é proposto pela IA.
3. Sexo: obrigatório; sem ele (vazio, "não informado" ou sem coluna), nasce uma pendência.
4. Mínimo e máximo: opcionais nos campos de valor; o salário começa com o piso de R$ 500,00; fora da faixa, ALERTA.

Os valores dos testes são inventados aqui (nenhum vem das bases de teste): cada regra é provada com pelo menos três
jeitos de escrever que ninguém usou antes.
"""
from decimal import Decimal

import pytest

from agents import interpretador
from models.contratos import CampoLayout, ColunaPerfil, carregar_layout
from rag.indice_do_layout import CAMINHO_HISTORICO
from rag.trechos import trechos_historico, trechos_layout
from scripts import aplicar_parametro_adr_128
from services import acompanhamento, auth, normalizador, parametros, pergunta_da_pendencia, validador
from services.normalizador import Normalizacao, NaoConvertido
from services.validador import ALERTA, BLOQUEANTE

# O layout v1, como sai dos arquivos do projeto
CAMPOS = carregar_layout()
CAMPO_POR_NOME = {}
for campo_do_layout in CAMPOS:
    CAMPO_POR_NOME[campo_do_layout.campo] = campo_do_layout


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste (o parâmetro nasce dos arquivos do projeto)."""
    return auth.conectar(tmp_path / "teste.db")


# ============================== O parâmetro v1 ==============================

def test_layout_v1_tem_a_matricula_opcional_e_45_campos():
    """A matrícula continua no parâmetro, mas é opcional (ADR-128)."""
    assert CAMPO_POR_NOME["matricula"].obrigatorio is False
    assert len(CAMPOS) == 45


def test_sexo_e_obrigatorio_no_layout_v1():
    """O sexo passou a ser obrigatório (decisão c)."""
    assert CAMPO_POR_NOME["sexo"].obrigatorio is True


def test_salario_comeca_com_o_piso_de_500_e_sem_maximo():
    """O salário tem o mínimo de R$ 500,00 e nenhum máximo (decisão d)."""
    assert CAMPO_POR_NOME["valor_renda"].minimo == Decimal("500.00")
    assert CAMPO_POR_NOME["valor_renda"].maximo is None


def test_so_o_salario_tem_faixa_no_layout_v1():
    """Os outros campos nascem sem mínimo e sem máximo."""
    for campo in CAMPOS:
        if campo.campo != "valor_renda":
            assert campo.minimo is None and campo.maximo is None, campo.campo


# ============================== Mínimo e máximo no contrato ==============================

@pytest.mark.parametrize("digitado, esperado", [
    ("500", Decimal("500.00")),
    ("500,00", Decimal("500.00")),
    ("R$ 1.500,50", Decimal("1500.50")),
    ("  2.000  ", Decimal("2000.00")),
    ("1.250.000", Decimal("1250000.00")),
    ("1500.5", Decimal("1500.50")),
    (1234.5, Decimal("1234.50")),
])
def test_limite_aceita_o_jeito_de_escrever_da_pessoa(digitado, esperado):
    """O mínimo escrito com vírgula, ponto de milhar, "R$" ou como número vira o mesmo valor com duas casas."""
    campo = CampoLayout(campo="valor_x", grupo="Renda", tipo="DECIMAL_MONETARIO", obrigatorio="N", sensivel="N",
                        uso_comercial_permitido="N", minimo=digitado)
    assert campo.minimo == esperado


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_limite_vazio_e_sem_limite(vazio):
    """Vazio (ou nada) é sem limite daquele lado."""
    campo = CampoLayout(campo="valor_x", grupo="Renda", tipo="DECIMAL_MONETARIO", obrigatorio="N", sensivel="N",
                        uso_comercial_permitido="N", minimo=vazio, maximo=vazio)
    assert campo.minimo is None and campo.maximo is None


@pytest.mark.parametrize("tipo", ["TEXTO", "CPF", "DATA", "DOMINIO"])
def test_limite_so_vale_em_campo_de_valor(tipo):
    """Um nome, um CPF, uma data ou uma lista não têm faixa: o contrato recusa."""
    with pytest.raises(ValueError, match="só valem para campos de valor"):
        CampoLayout(campo="qualquer", grupo="Titular", tipo=tipo, obrigatorio="N", sensivel="N",
                    uso_comercial_permitido="N", minimo="10")


@pytest.mark.parametrize("minimo, maximo", [("900", "800"), ("1.000,01", "1.000,00"), ("R$ 5,00", "4")])
def test_minimo_maior_que_o_maximo_e_recusado(minimo, maximo):
    """O mínimo não pode passar do máximo."""
    with pytest.raises(ValueError, match="mínimo não pode ser maior"):
        CampoLayout(campo="valor_x", grupo="Renda", tipo="DECIMAL_MONETARIO", obrigatorio="N", sensivel="N",
                    uso_comercial_permitido="N", minimo=minimo, maximo=maximo)


@pytest.mark.parametrize("texto", ["quinhentos", "5OO", "R$ --"])
def test_limite_que_nao_e_numero_e_recusado(texto):
    """Um limite escrito por extenso ou com letra no lugar de número é recusado, com a explicação."""
    with pytest.raises(ValueError, match="escreva um número"):
        CampoLayout(campo="valor_x", grupo="Renda", tipo="DECIMAL_MONETARIO", obrigatorio="N", sensivel="N",
                    uso_comercial_permitido="N", maximo=texto)


# ============================== A tela Parâmetros (serviço) ==============================

def _campos_em_dicionario(conexao) -> list[dict]:
    """Os campos da versão vigente como a tela os manda."""
    campos = []
    for campo in parametros.layout_ativo(conexao)[1]:
        campos.append(campo.model_dump(mode="json"))
    return campos


def _campos_vigentes(conexao) -> dict:
    """Os campos da versão vigente, pelo nome técnico."""
    por_nome = {}
    for campo in parametros.layout_ativo(conexao)[1]:
        por_nome[campo.campo] = campo
    return por_nome


def test_tela_grava_o_maximo_e_o_registro_diz_em_reais(conexao):
    """Gravar um máximo pela tela vira versão nova, e o registro mostra o antes e o depois em reais."""
    campos = _campos_em_dicionario(conexao)
    for campo in campos:
        if campo["campo"] == "valor_renda":
            campo["maximo"] = "80.000,00"
    resultado = parametros.salvar_layout_pela_tela(conexao, campos, "especialista")
    assert "valor_renda · máximo: sem limite → R$ 80.000,00" in resultado["mudancas"]
    assert _campos_vigentes(conexao)["valor_renda"].maximo == Decimal("80000.00")


def test_tela_tira_o_minimo_e_o_registro_diz_sem_limite(conexao):
    """Apagar o mínimo na janela grava "R$ 500,00 → sem limite"."""
    campos = _campos_em_dicionario(conexao)
    for campo in campos:
        if campo["campo"] == "valor_renda":
            campo["minimo"] = None
    resultado = parametros.salvar_layout_pela_tela(conexao, campos, "especialista")
    assert resultado["mudancas"] == ["valor_renda · mínimo: R$ 500,00 → sem limite"]


def test_tela_mesmo_minimo_escrito_de_outro_jeito_nao_e_mudanca(conexao):
    """ "500", "500,00" e "R$ 500,00" são o mesmo mínimo: nada mudou, nenhuma versão nova."""
    for jeito in ("500", "500,00", "R$ 500,00"):
        campos = _campos_em_dicionario(conexao)
        for campo in campos:
            if campo["campo"] == "valor_renda":
                campo["minimo"] = jeito
        with pytest.raises(ValueError, match="Nada mudou"):
            parametros.salvar_layout_pela_tela(conexao, campos, "especialista")


def test_tela_recusa_faixa_num_campo_de_texto_com_mensagem_simples(conexao):
    """Uma faixa no cargo (texto) é recusada com o nome do campo na mensagem."""
    campos = _campos_em_dicionario(conexao)
    for campo in campos:
        if campo["campo"] == "cargo":
            campo["minimo"] = "10"
    with pytest.raises(ValueError, match='Confira o campo "cargo"') as recusa:
        parametros.salvar_layout_pela_tela(conexao, campos, "especialista")
    # A mensagem é da pessoa: sem o "Value error" da biblioteca
    assert "Value error" not in str(recusa.value)


# ============================== O alerta de faixa (Validador) ==============================

def _normalizacao(registros: list[dict]) -> Normalizacao:
    """Uma padronização mínima com os registros dados (cada um com _linha); a conferência bate."""
    plano = []
    for nome in registros[0]:
        if nome != "_linha":
            plano.append({"coluna": nome, "campo": nome})
    return Normalizacao(registros=registros, plano=plano, log=[],
                        conferencia={"linhas_conferem": True, "vazios_conferem": True})


def _achados_da_regra(valores_de_renda: list[str], campos: list[CampoLayout], regra: str) -> list:
    """Valida só o valor da renda de várias pessoas e devolve os achados da regra pedida."""
    registros = []
    for posicao, valor in enumerate(valores_de_renda, start=2):
        registros.append({"_linha": posicao, "valor_renda": valor})
    campos_da_renda = []
    for campo in campos:
        if campo.campo == "valor_renda":
            campos_da_renda.append(campo)
    relatorio = validador.validar(_normalizacao(registros), campos_da_renda, "EMP001")
    achados = []
    for achado in relatorio.achados:
        if achado.regra_id == regra:
            achados.append(achado)
    return achados


@pytest.mark.parametrize("valor", ["350.00", "499.99", "1.00", "120.50"])
def test_salario_abaixo_do_piso_e_alerta(valor):
    """Abaixo de R$ 500,00: ALERTA (não recusa), com o limite em reais na mensagem."""
    achados = _achados_da_regra([valor], CAMPOS, validador.REGRA_VALOR_FORA_DA_FAIXA)
    assert len(achados) == 1
    assert achados[0].severidade == ALERTA
    assert "abaixo do mínimo do parâmetro (R$ 500,00)" in achados[0].mensagem


@pytest.mark.parametrize("valor", ["500.00", "500.01", "1412.00", "98000.00"])
def test_salario_no_piso_ou_acima_nao_e_alerta(valor):
    """No piso ou acima, e sem máximo: nenhum alerta de faixa."""
    assert _achados_da_regra([valor], CAMPOS, validador.REGRA_VALOR_FORA_DA_FAIXA) == []


@pytest.mark.parametrize("valor", ["0.00", "-10.00"])
def test_salario_zerado_ou_negativo_nao_repete_o_alerta_de_faixa(valor):
    """Zerado ou negativo já bloqueia (RENDA_NAO_POSITIVA): o alerta de faixa não aparece junto."""
    assert _achados_da_regra([valor], CAMPOS, validador.REGRA_VALOR_FORA_DA_FAIXA) == []
    assert len(_achados_da_regra([valor], CAMPOS, "RENDA_NAO_POSITIVA")) == 1


def test_maximo_do_parametro_vira_alerta_acima():
    """Com um máximo no parâmetro, o valor acima dele é ALERTA, e o do meio da faixa passa."""
    campo_com_teto = CAMPO_POR_NOME["valor_renda"].model_copy(update={"maximo": Decimal("30000.00")})
    achados = _achados_da_regra(["30000.01", "15000.00", "45000.00"], [campo_com_teto],
                                validador.REGRA_VALOR_FORA_DA_FAIXA)
    assert achados[0].linha == 2 and achados[1].linha == 4 and len(achados) == 2
    assert "acima do máximo do parâmetro (R$ 30.000,00)" in achados[0].mensagem


def test_sem_faixa_no_parametro_nao_ha_alerta():
    """O banco tirou o mínimo: nenhum salário gera alerta de faixa (a regra segue o parâmetro, não o código)."""
    campo_sem_faixa = CAMPO_POR_NOME["valor_renda"].model_copy(update={"minimo": None})
    assert _achados_da_regra(["10.00", "200.00", "499.00"], [campo_sem_faixa],
                             validador.REGRA_VALOR_FORA_DA_FAIXA) == []


# ============================== O cartão do alerta de faixa ==============================

@pytest.mark.parametrize("mensagem, lado", [
    ("Valor de valor_renda abaixo do mínimo do parâmetro (R$ 500,00).", "abaixo do mínimo do parâmetro (R$ 500,00)"),
    ("Valor de valor_renda acima do máximo do parâmetro (R$ 30.000,00).",
     "acima do máximo do parâmetro (R$ 30.000,00)"),
    ("Valor de outro_valor abaixo do mínimo do parâmetro (R$ 1,00).", "abaixo do mínimo do parâmetro (R$ 1,00)"),
])
def test_pergunta_do_cartao_da_faixa_diz_o_limite_e_pede_confirmacao(mensagem, lado):
    """A pergunta cita o valor, o lado e o limite, termina com "Está certo?" e nunca mostra o nome técnico."""
    dados = pergunta_da_pendencia.DadosDaPendencia(
        severidade=ALERTA, campo="valor_renda", informacao="Salário bruto mensal", valor="R$ 320,00",
        mensagem=mensagem, pessoa="Lívia", palpite=None)
    pergunta = pergunta_da_pendencia.PERGUNTA_POR_REGRA["VALOR_FORA_DA_FAIXA"](dados)
    assert pergunta == f'Para Lívia, a informação "Salário bruto mensal" veio como "R$ 320,00", {lado}. Está certo?'
    assert "valor_renda" not in pergunta


def _textos(sugestoes: list[dict]) -> list[str]:
    """O texto de cada botão de resposta rápida do cartão."""
    textos = []
    for sugestao in sugestoes:
        textos.append(sugestao["texto"])
    return textos


def test_cartao_da_faixa_tem_a_linha_do_problema_e_o_botao_de_confirmar():
    """O cartão diz o problema em poucas palavras e oferece "Está certo assim" (é um alerta)."""
    assert acompanhamento.PROBLEMA_POR_REGRA["VALOR_FORA_DA_FAIXA"] == "valor fora da faixa esperada pelo banco"
    sugestoes = acompanhamento.sugestoes_da_pendencia("VALOR_FORA_DA_FAIXA", "confirmar", 5, "valor_renda")
    assert "Está certo assim" in _textos(sugestoes)


# ============================== Tipo de renda (decisão a) ==============================

@pytest.mark.parametrize("valor", ["Mensal", "Horária", "horista", "Mensalista", "Comissionado", "por hora",
                                   "salário mensal"])
def test_tipo_de_renda_nunca_vira_clt_sozinho(valor):
    """Nenhum jeito de dizer "mensal" ou "por hora" vira CLT: a empresa precisa informar."""
    with pytest.raises(NaoConvertido):
        normalizador.converter_valor(valor, CAMPO_POR_NOME["tipo_renda"])


@pytest.mark.parametrize("valor", ["Mensal", "Horária", "Comissionada", "mensalista", "hora trabalhada"])
def test_tipo_de_renda_sem_palpite_de_clt(valor):
    """O agente também não "acredita" que seja CLT: sem palpite, a pessoa escolhe entre as opções."""
    palpite = normalizador.palpite_na_lista(valor, "tipo_renda", normalizador.carregar_dominios())
    assert palpite != "CLT"


@pytest.mark.parametrize("valor", ["Outros", "outro", "OUTRA", " outros "])
def test_tipo_de_renda_aceita_outros(valor):
    """A lista ganhou OUTROS, a saída para a renda que não é CLT nem pró-labore."""
    assert normalizador.converter_valor(valor, CAMPO_POR_NOME["tipo_renda"]) == "OUTROS"


def test_cartao_do_tipo_de_renda_oferece_as_tres_opcoes():
    """Num valor fora da lista, os botões do cartão são as opções da lista, com OUTROS."""
    sugestoes = acompanhamento.sugestoes_da_pendencia("VALOR_NAO_CONVERTIDO", "corrigir", 7, "tipo_renda")
    assert _textos(sugestoes)[:3] == ["CLT", "PRO_LABORE", "OUTROS"]


# ============================== Sexo obrigatório (decisão c) ==============================

def _achados_do_sexo(valores: list[str | None], nao_convertidos: list[dict] | None = None,
                     com_coluna: bool = True) -> list:
    """Valida só o sexo de várias pessoas e devolve os achados."""
    registros = []
    for posicao, valor in enumerate(valores, start=2):
        registros.append({"_linha": posicao, "sexo": valor})
    normalizacao = _normalizacao(registros)
    if not com_coluna:
        normalizacao.plano = []
    normalizacao.nao_convertidos = nao_convertidos or []
    return validador.validar(normalizacao, [CAMPO_POR_NOME["sexo"]], "EMP001").achados


def test_sexo_vazio_vira_pendencia_que_bloqueia():
    """Cada pessoa sem o sexo ganha uma pendência (a empresa precisa informar)."""
    achados = _achados_do_sexo(["F", None, "M", None])
    assert [(achado.regra_id, achado.severidade, achado.linha) for achado in achados] == [
        ("OBRIGATORIO_VAZIO", BLOQUEANTE, 3), ("OBRIGATORIO_VAZIO", BLOQUEANTE, 5)]


@pytest.mark.parametrize("valor", ["N", "Não informado", "prefiro não dizer", "X", "-"])
def test_sexo_nao_informado_nao_e_aceito(valor):
    """ "Não informado" (e parecidos) não está na lista: a padronização não converte, e a pendência bloqueia."""
    with pytest.raises(NaoConvertido):
        normalizador.converter_valor(valor, CAMPO_POR_NOME["sexo"])
    achados = _achados_do_sexo([None], [{"linha": 2, "campo": "sexo", "valor": valor, "motivo": "fora da lista"}])
    assert [(achado.regra_id, achado.severidade) for achado in achados] == [("VALOR_NAO_CONVERTIDO", BLOQUEANTE)]


def test_arquivo_sem_a_coluna_do_sexo_pede_a_coluna_de_cada_pessoa():
    """Sem a coluna, a pendência é do arquivo inteiro, e o sexo é de cada pessoa (nunca um valor para todos)."""
    achados = _achados_do_sexo([None, None], com_coluna=False)
    assert [achado.regra_id for achado in achados] == ["OBRIGATORIO_SEM_COLUNA"]
    assert "única por funcionário" in achados[0].acao


@pytest.mark.parametrize("valor, esperado", [("Feminino", "F"), ("masc", "M"), ("mulher", "F"), ("m", "M")])
def test_sexo_escrito_por_extenso_continua_convertido(valor, esperado):
    """Os sinônimos de sempre continuam valendo."""
    assert normalizador.converter_valor(valor, CAMPO_POR_NOME["sexo"]) == esperado


# ============================== Matrícula opcional (decisão b) ==============================

# O layout como ficaria se o banco tirasse a matrícula na tela Parâmetros (para provar a regra geral)
CAMPOS_SEM_MATRICULA = []
for campo_do_layout in CAMPOS:
    if campo_do_layout.campo != "matricula":
        CAMPOS_SEM_MATRICULA.append(campo_do_layout)


def _perfil_das_colunas(nomes: list[str]) -> list[ColunaPerfil]:
    """Colunas com amostras inventadas (só o nome importa aqui)."""
    colunas = []
    for posicao, nome in enumerate(nomes, start=1):
        colunas.append(ColunaPerfil(posicao=posicao, nome=nome, tipo_provavel="TEXTO", vazias=0,
                                    amostras=["00731", "01288", "10044"]))
    return colunas


def _status_no_simulador(colunas_do_arquivo: list[str], campos: list[CampoLayout]) -> dict:
    """O que o simulador (MOCK) responde para cada coluna, já conferido: {coluna: (status, campo)}."""
    colunas = _perfil_das_colunas(colunas_do_arquivo)
    _, pedido, _ = interpretador.montar_prompt(colunas, campos, "B1")
    itens, _ = interpretador.conferir_saida(interpretador.ler_resposta(interpretador.simular_llm(pedido)), colunas,
                                            campos, [])
    resposta = {}
    for item in itens:
        resposta[item.coluna] = (item.status.value, item.campo)
    return resposta


@pytest.mark.parametrize("coluna", ["Matrícula", "Nº Registro", "Cód. Funcionário", "Código do Colaborador"])
def test_coluna_de_matricula_continua_sendo_lida(coluna):
    """Quem manda a matrícula tem ela lida: a coluna é proposta para o campo matricula."""
    assert _status_no_simulador([coluna, "CPF"], CAMPOS)[coluna] == ("PROPOSTO", "matricula")


@pytest.mark.parametrize("coluna", ["Matrícula", "Nº Registro", "Cód. Funcionário", "Código do Colaborador"])
def test_campo_que_o_banco_tirou_nunca_e_proposto(coluna):
    """Regra geral: se o banco tirar um campo do parâmetro, a coluna dele fica de fora, sem virar dúvida."""
    resposta = _status_no_simulador([coluna, "CPF"], CAMPOS_SEM_MATRICULA)
    assert resposta[coluna] == ("NAO_MAPEADO", None)
    assert resposta["CPF"] == ("PROPOSTO", "cpf")


def test_plano_de_emergencia_so_sugere_campos_do_layout_vigente():
    """Com a IA fora, o dicionário só sugere campos que o parâmetro tem."""
    nomes_com, nomes_sem = set(), set()
    for campo in CAMPOS:
        nomes_com.add(campo.campo)
    for campo in CAMPOS_SEM_MATRICULA:
        nomes_sem.add(campo.campo)
    colunas = _perfil_das_colunas(["Matrícula", "Registro", "Nome"])
    candidatos_com, candidatos_sem = {}, {}
    for item in interpretador.plano_de_emergencia(colunas, nomes_com):
        candidatos_com[item.coluna] = item.candidatos
    for item in interpretador.plano_de_emergencia(colunas, nomes_sem):
        candidatos_sem[item.coluna] = item.candidatos
    assert candidatos_com["Matrícula"] == ["matricula"] and candidatos_com["Nome"] == ["nome_completo"]
    assert candidatos_sem["Matrícula"] == [] and candidatos_sem["Registro"] == []


def _campos_dos_trechos(trechos: list) -> set[str]:
    """Os campos que os trechos de mapeamento ensinam."""
    campos = set()
    for trecho in trechos:
        campos.add(trecho.metadados["campo"])
    return campos


def _descricoes(campos: list[CampoLayout]) -> dict:
    """Campo -> descrição, como o índice do layout monta."""
    descricoes = {}
    for campo in campos:
        descricoes[campo.campo] = campo.descricao
    return descricoes


def test_conhecimento_da_ia_so_ensina_campos_do_layout_vigente():
    """O histórico de mapeamentos entra só para os campos do parâmetro vigente (o mesmo filtro dos aprovados)."""
    assert "matricula" in _campos_dos_trechos(trechos_historico(CAMINHO_HISTORICO, _descricoes(CAMPOS)))
    assert "matricula" not in _campos_dos_trechos(trechos_historico(CAMINHO_HISTORICO,
                                                                    _descricoes(CAMPOS_SEM_MATRICULA)))


def _achados_da_matricula(matriculas: list[str | None], com_coluna: bool = True,
                          matricula_obrigatoria: bool = False) -> list:
    """Valida CPF e matrícula de várias pessoas (CPFs válidos e inventados) e devolve os achados.

    matricula_obrigatoria: True marca a matrícula como obrigatória no parâmetro do teste (no layout, ela é opcional).
    """
    cpfs = ["52998224725", "11144477735", "12345678909", "98765432100"]
    registros = []
    for posicao, matricula in enumerate(matriculas):
        registros.append({"_linha": posicao + 2, "cpf": cpfs[posicao], "matricula": matricula})
    normalizacao = _normalizacao(registros)
    if not com_coluna:
        normalizacao.plano = [{"coluna": "CPF", "campo": "cpf"}]
        for registro in registros:
            registro["matricula"] = None
    matricula = CAMPO_POR_NOME["matricula"].model_copy(update={"obrigatorio": matricula_obrigatoria})
    campos = [CAMPO_POR_NOME["cpf"], matricula]
    return validador.validar(normalizacao, campos, "EMP001").achados


@pytest.mark.parametrize("matriculas, com_coluna", [
    ([None, None, None], False),           # o arquivo não tem a coluna
    ([None, None], True),                  # a coluna veio vazia
    ([None, "00731", None, "01288"], True),  # só algumas pessoas têm matrícula
])
def test_sem_matricula_nao_ha_pendencia(matriculas, com_coluna):
    """A empresa que não usa matrícula (ou não tem de todos) envia sem pendência: o CPF identifica a pessoa."""
    assert _achados_da_matricula(matriculas, com_coluna) == []


@pytest.mark.parametrize("repetida", ["00012", "A-77", "9"])
def test_matricula_repetida_so_bloqueia_quando_e_obrigatoria(repetida):
    """A matrícula é opcional no layout (ADR-128), e um campo opcional não abre pendência (ADR-143): repetida no
    arquivo, não pede nada. Com a matrícula obrigatória no parâmetro, ela continua única: repetida é BLOQUEANTE."""
    assert _achados_da_matricula([repetida, "55555", repetida]) == []
    achados = _achados_da_matricula([repetida, "55555", repetida], matricula_obrigatoria=True)
    assert [(achado.regra_id, achado.severidade, achado.linha) for achado in achados] == [
        ("MATRICULA_DUPLICADA", BLOQUEANTE, 4)]


def test_trecho_do_salario_diz_a_faixa():
    """O trecho do salário no índice do RAG diz a faixa esperada, para o agente explicar o alerta."""
    trechos = trechos_layout(3, [CAMPO_POR_NOME["valor_renda"], CAMPO_POR_NOME["cpf"]])
    assert "Faixa esperada: a partir de R$ 500,00" in trechos[0].texto
    assert "Faixa esperada" not in trechos[1].texto


# ============================== O script do banco que já existe ==============================

def _versao_antiga(conexao) -> None:
    """Grava uma versão como a do banco antes do ADR-128: matrícula obrigatória, sexo opcional e sem mínimo, mais uma edição
    que o banco fez na tela (a descrição do cargo), que o script precisa manter."""
    campos = _campos_em_dicionario(conexao)
    antigos = []
    for campo in campos:
        if campo["campo"] == "matricula":
            campo["obrigatorio"] = True
        if campo["campo"] == "sexo":
            campo["obrigatorio"] = False
        if campo["campo"] == "valor_renda":
            campo["minimo"] = None
        if campo["campo"] == "cargo":
            campo["descricao"] = "Cargo, como o banco escreveu na tela"
        antigos.append(campo)
    parametros.salvar_layout(conexao, antigos, "especialista")


def test_script_grava_a_versao_nova_e_mantem_o_que_o_banco_editou(conexao):
    """O script deixa a matrícula opcional, liga o sexo e o piso, e não desfaz a edição do banco."""
    _versao_antiga(conexao)
    resultado = aplicar_parametro_adr_128.aplicar(conexao)
    assert "matricula · obrigatório: sim → não" in resultado["mudancas"]
    assert "sexo · obrigatório: não → sim" in resultado["mudancas"]
    assert "valor_renda · mínimo: sem limite → R$ 500,00" in resultado["mudancas"]
    vigente = _campos_vigentes(conexao)
    assert vigente["matricula"].obrigatorio is False
    assert vigente["cargo"].descricao == "Cargo, como o banco escreveu na tela"
    assert parametros.registro_do_layout(conexao)[0]["criado_por"] == "sistema (ADR-128)"


def test_script_rodado_de_novo_nao_grava_nada(conexao):
    """A segunda vez (ou num banco novo, que já nasce assim) não grava versão nenhuma."""
    assert aplicar_parametro_adr_128.aplicar(conexao) is None
    _versao_antiga(conexao)
    assert aplicar_parametro_adr_128.aplicar(conexao) is not None
    assert aplicar_parametro_adr_128.aplicar(conexao) is None


# ============================== O conhecimento da IA (RAG) ==============================

@pytest.fixture(scope="module")
def pasta_do_indice(tmp_path_factory):
    """Os índices do RAG montados numa pasta temporária (o índice de verdade não é tocado)."""
    from scripts import build_index
    raiz = tmp_path_factory.mktemp("rag_adr_128")
    build_index.main(caminho_banco=raiz / "teste.db", pasta=raiz / "indices")
    return raiz / "indices"


@pytest.mark.parametrize("pergunta", ["Valor abaixo do piso do parâmetro vira alerta?",
                                      "Mínimo e máximo de um campo de valor",
                                      "O teto fixo de um valor em reais"])
def test_busca_acha_a_regra_do_minimo_e_maximo(pasta_do_indice, pergunta):
    """Perguntas sobre o piso e o teto trazem a regra do mínimo e máximo do parâmetro (ou o trecho do salário)."""
    from rag import busca
    fontes = []
    for resultado in busca.search_rules(pergunta, pasta=pasta_do_indice):
        fontes.append(resultado["fonte"])
    assert "Regras de validação v1 › Mínimo e máximo do parâmetro" in fontes or any(
        fonte.endswith("› valor_renda") for fonte in fontes), fontes


@pytest.mark.parametrize("pergunta", ["A empresa não usa matrícula, precisa enviar?",
                                      "Matrícula do funcionário é obrigatória?",
                                      "O campo matrícula pode ficar vazio?"])
def test_busca_sobre_matricula_traz_o_que_o_parametro_diz(pasta_do_indice, pergunta):
    """Perguntas sobre a matrícula trazem o campo ou a regra dela, que dizem que ela é opcional."""
    from rag import busca
    textos = []
    for resultado in busca.search_rules(pergunta, pasta=pasta_do_indice):
        if resultado["campo"] == "matricula" or resultado["fonte"].endswith("Tipo MATRICULA"):
            textos.append(resultado["texto"])
    assert textos, pergunta
    assert "pcional" in " ".join(textos)
