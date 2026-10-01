"""Pendências em grupo: o mesmo valor fora da lista em várias pessoas do mesmo arquivo vira UMA pergunta (ADR-120).

Para que serve: quando 23 pessoas vêm com "Divorciado(a)" no estado civil, a empresa não precisa responder 23 cartões
iguais. O Agente de validação pergunta uma vez ("23 pessoas deste arquivo vieram com ... Acredito que o certo é
"Divorciado" para todas. Posso usar?"), e a resposta vale para todas elas, com um Desfazer que volta o grupo inteiro.

Quando as pendências formam um grupo (as quatro condições juntas):
    1. a pendência é de valor fora da lista (VALOR_NAO_CONVERTIDO) de uma pessoa (tem linha);
    2. o campo é de LISTA FECHADA no parâmetro (ex.: estado civil, sexo). Campos livres, como salário, data ou CPF,
       nunca agrupam: cada pessoa tem o seu valor, e uma resposta só estaria errada para quase todas;
    3. o valor lido é o mesmo (sem diferença de maiúsculas e de espaços nas pontas: "divorciado(a) " = "Divorciado(a)");
    4. pelo menos MINIMO_PARA_AGRUPAR pessoas do mesmo arquivo vieram assim, com a pendência ainda em aberto.

O grupo é sempre refeito a partir do relatório do Validador, no servidor: o navegador só diz qual pendência
representa o grupo (a regra e a linha), e nunca a lista de pessoas.

Exemplo de uso:
    grupos = grupos_do_relatorio(relatorio.achados)          # {"estado_civil|divorciado(a)": [achado, achado, ...]}
    achados = grupo_do_achado(relatorio.achados, achado)     # os achados do grupo deste achado ([] se não há grupo)
"""
from services import normalizador, validador

# A partir de quantas pessoas com o mesmo valor a pergunta vira uma só (recomendação: 2, ADR-120)
MINIMO_PARA_AGRUPAR = 2
# A única regra que agrupa: o valor que não está entre as opções da lista
REGRA_DO_GRUPO = "VALOR_NAO_CONVERTIDO"


def achado_em_aberto(achado) -> bool:
    """True se o achado ainda pede ação da empresa: um erro (BLOQUEANTE) ou um alerta ainda não confirmado."""
    # Erro: sempre em aberto enquanto estiver no relatório
    if achado.severidade == validador.BLOQUEANTE:
        return True
    # Alerta: em aberto até a empresa confirmar
    return achado.severidade == validador.ALERTA and not achado.resolvido


def pode_agrupar(achado, dominios: dict) -> bool:
    """True se o achado pode fazer parte de um grupo: valor fora da lista, de uma pessoa, num campo de lista fechada.

    Recebe: o achado do Validador; dominios — as listas fechadas do parâmetro (normalizador.carregar_dominios()).
    Ex.: estado civil "Divorciado(a)" na linha 8 → True; salário "a combinar" → False (campo livre).
    """
    # Só o valor fora da lista, e só de uma pessoa (o arquivo inteiro já é uma pergunta só)
    if achado.regra_id != REGRA_DO_GRUPO or achado.linha is None:
        return False
    # Só campo de lista fechada
    if not achado.campo or achado.campo not in dominios:
        return False
    # Com um valor lido (vazio não é "o mesmo valor")
    return bool((achado.valor or "").strip())


def chave_do_grupo(achado) -> str:
    """A chave que junta os achados iguais: o campo e o valor lido, sem maiúsculas e sem espaços nas pontas.

    Ex.: achado de estado_civil com " Divorciado(a) " → "estado_civil|divorciado(a)".
    """
    return achado.campo + "|" + achado.valor.strip().casefold()


def grupos_do_relatorio(achados: list) -> dict[str, list]:
    """Os grupos de um envio: {chave do grupo: [os achados, na ordem do relatório]}, só com MINIMO_PARA_AGRUPAR ou mais.

    Recebe: os achados do último relatório do Validador do envio. Devolve: o dicionário (vazio se não há grupo).
    """
    dominios = normalizador.carregar_dominios()
    # Primeiro, junta todos os achados que podem agrupar, pela chave
    candidatos = {}
    for achado in achados:
        if achado_em_aberto(achado) and pode_agrupar(achado, dominios):
            candidatos.setdefault(chave_do_grupo(achado), []).append(achado)
    # Depois, fica só com as chaves que têm pessoas suficientes
    grupos = {}
    for chave, achados_do_grupo in candidatos.items():
        if len(achados_do_grupo) >= MINIMO_PARA_AGRUPAR:
            grupos[chave] = achados_do_grupo
    return grupos


def grupo_do_achado(achados: list, achado_escolhido) -> list:
    """Os achados do grupo de um achado (ele incluído), ou [] se ele não faz parte de um grupo.

    Recebe: os achados do relatório; o achado da pendência que a pessoa respondeu.
    Ex.: o achado da linha 8 com "Divorciado(a)" e mais 22 iguais → os 23 achados.
    """
    if not pode_agrupar(achado_escolhido, normalizador.carregar_dominios()):
        return []
    return grupos_do_relatorio(achados).get(chave_do_grupo(achado_escolhido), [])
