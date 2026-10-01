"""Apoio dos testes: o parâmetro do layout com os campos obrigatórios de que o teste precisa (ADR-143).

Desde a ADR-143, um campo opcional não abre pendência, sem exceção. Por isso:
- os testes de um RECURSO (a conversa, os cartões, a confirmação, a dúvida de formato) que usavam um campo opcional
  do layout_v1 como exemplo de pendência (o estado civil "Solteirx", a efetivação antes da admissão, a matrícula)
  marcam esse campo como obrigatório no parâmetro do teste, e o recurso continua testado do mesmo jeito;
- os testes dos gabaritos esperam só os erros injetados num campo obrigatório do layout (os gabaritos não mudam).
O layout_v1 (data/contratos/layout_v1.csv) também não muda: ele é a base dos testes.
"""
from eval.avaliacao_do_fluxo import REGRA_DO_GABARITO
from models.contratos import carregar_layout
from services import parametros

# O layout_v1, a base dos testes
CAMPOS_DO_LAYOUT = carregar_layout()
# Os campos obrigatórios do layout_v1
OBRIGATORIOS_DO_LAYOUT = set()
for campo_do_layout in CAMPOS_DO_LAYOUT:
    if campo_do_layout.obrigatorio:
        OBRIGATORIOS_DO_LAYOUT.add(campo_do_layout.campo)
# Os obrigatórios do parâmetro da ADR-143 que existem no layout_v1 (o 4º, o codigo_cbo, não está nele)
OBRIGATORIOS_DA_ADR_143 = {"cpf", "valor_renda", "data_admissao"}
# O campo em que o Validador prende a pessoa repetida no arquivo: o CPF (ADR-124), mesmo quando o gabarito marca a
# matrícula (a linha copiada repete as duas)
CAMPO_DA_PESSOA_DUPLICADA = "cpf"


def layout_com(obrigatorios: set) -> list:
    """O layout_v1 com exatamente estes campos obrigatórios; os outros ficam opcionais.

    Ex.: layout_com(OBRIGATORIOS_DA_ADR_143) é o parâmetro da ADR-143; layout_com(OBRIGATORIOS_DO_LAYOUT | {"matricula"})
    é o layout_v1 com a matrícula obrigatória.
    """
    campos = []
    for campo in CAMPOS_DO_LAYOUT:
        # Uma cópia do campo, obrigatório só se estiver na lista
        campos.append(campo.model_copy(update={"obrigatorio": campo.campo in obrigatorios}))
    return campos


def marcar_como_obrigatorios(conexao, *nomes_dos_campos: str, so_estes: bool = False) -> int:
    """Grava uma versão nova do parâmetro com estes campos obrigatórios.

    Recebe: a conexão do banco de teste, os nomes técnicos dos campos e so_estes (True deixa todos os outros opcionais;
    False, o padrão, deixa os outros como estavam). Devolve: o número da versão gravada.
    Ex.: marcar_como_obrigatorios(conexao, "estado_civil") → o "Solteirx" volta a ser pendência neste banco de teste;
    marcar_como_obrigatorios(conexao, "cpf", "codigo_cbo", "valor_renda", "data_admissao", so_estes=True) → o
    parâmetro da ADR-143.
    """
    _, campos = parametros.layout_ativo(conexao)
    campos_em_dicionario = []
    for campo in campos:
        # O campo como o parâmetro guarda (o tipo vira texto, ex.: "CPF")
        dados_do_campo = campo.model_dump(mode="json")
        # O campo que o teste pediu passa a ser obrigatório; com so_estes, os outros ficam opcionais
        if campo.campo in nomes_dos_campos:
            dados_do_campo["obrigatorio"] = True
        elif so_estes:
            dados_do_campo["obrigatorio"] = False
        campos_em_dicionario.append(dados_do_campo)
    return parametros.salvar_layout(conexao, campos_em_dicionario, "teste")


def erros_que_viram_pendencia(gabarito: dict) -> set:
    """Os erros injetados que o Validador aponta: só os de campo obrigatório do layout (ADR-143).

    Recebe: o gabarito de um arquivo (o gabarito não muda). Devolve: os pares (registro, regra do Validador).
    Ex.: a matrícula repetida da Vale Verde fica de fora, porque a matrícula é opcional; o CPF inválido da Aurora fica.
    """
    pares = set()
    for erro in gabarito["erros"]:
        regra = REGRA_DO_GABARITO[erro["tipo"]]
        # O campo do achado: o do gabarito, menos na pessoa repetida, que é achada pelo CPF
        campo = erro["campo"]
        if regra == "PESSOA_DUPLICADA":
            campo = CAMPO_DA_PESSOA_DUPLICADA
        if campo in OBRIGATORIOS_DO_LAYOUT:
            pares.add((erro["linha"], regra))
    return pares
