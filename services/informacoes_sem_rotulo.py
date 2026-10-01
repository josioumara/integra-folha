"""Informações sem rótulo: o que a IA achou num campo opcional sem ter certeza de qual campo é (ADR-143, Parte 1).

Para que serve: num campo OPCIONAL do parâmetro, a IA tenta achar a coluna. Quando ela
fica em dúvida (ex.: a coluna "C.E.P" pode ser o CEP residencial ou o CEP comercial), a coluna fica de fora do cadastro,
sem pergunta à empresa. Em vez de a informação se perder, o sistema a guarda SEM RÓTULO, junto da pessoa: assim o banco
pode entender depois o que dá para reaproveitar (a tela do banco para rotular é uma evolução, a Parte 2).

A trava da LGPD (minimização), que vale em todo este arquivo:
    - só fica guardada a coluna em que a IA ficou em dúvida entre campos OPCIONAIS que já estão no parâmetro vigente;
    - a coluna desconhecida (a IA não indicou nenhum campo, ex.: "Religião") nunca é guardada;
    - a coluna que a empresa escolheu mapear vira um campo normal e não entra aqui;
    - a dúvida que envolve um campo obrigatório continua como antes: a empresa decide, e o campo obrigatório que fica
      sem coluna vira pendência.
O que fica guardado não entra em nenhuma conta, análise, planejamento, grade ou download, e nunca vira o valor de um
campo: só aparece no detalhe da pessoa, nas telas da empresa e do banco.

Como a dúvida é reconhecida depois do aceite das colunas: no mapeamento aprovado, a coluna ficou de fora e ainda traz os
candidatos que a IA indicou. Só a coluna em dúvida (AMBIGUO) guarda candidatos no mapeamento (services/mapeamentos.py):
assim, a coluna que a IA reconheceu com certeza, e que a empresa deixou de fora, nunca é guardada aqui.

Os dois formatos da lista:
    - guardado junto da pessoa (na padronização, a chave "_sem_rotulo" do registro; no cadastro, a coluna
      informacoes_sem_rotulo da tabela funcionarios_homologados), com os nomes técnicos dos campos:
      [{"coluna": "C.E.P", "valor": "01310-100", "candidatos": ["cep_residencial", "cep_comercial"]}];
    - para a tela (a chave "informacoes_sem_rotulo" de cada pessoa nas listas), com o nome legível de cada campo:
      [{"coluna": "C.E.P", "valor": "01310-100",
        "candidatos": [{"campo": "cep_residencial", "rotulo": "CEP residencial"},
                       {"campo": "cep_comercial", "rotulo": "CEP comercial"}]}].
"""
import json

from models.contratos import CampoLayout, MappingPlan, StatusMapeamento
from services import processamentos
from services.ingestao import Leitura

# A chave da lista no registro de cada pessoa, na padronização. Começa com "_", como a "_linha": não é um campo do
# layout, então nenhuma conta, correção ou arquivo final chega nela
CHAVE_NO_REGISTRO = "_sem_rotulo"


def _candidatos_do_parametro(candidatos: list[str], campos_por_nome: dict) -> list[str]:
    """Os candidatos que existem no parâmetro vigente, cada um uma vez, na ordem em que a IA os indicou.

    Por quê: o Interpretador já descarta o candidato que não está no layout; aqui vale a mesma regra, porque a coluna
    pode vir de um mapeamento antigo reaproveitado numa inclusão, e o banco pode ter mudado o parâmetro desde então.
    Ex.: (["cep_residencial", "fax", "cep_residencial"], campos sem o "fax") → ["cep_residencial"].
    """
    do_parametro = []
    for candidato in candidatos:
        # Só vale o candidato que o banco pede hoje, e o repetido entra uma vez só
        if candidato in campos_por_nome and candidato not in do_parametro:
            do_parametro.append(candidato)
    return do_parametro


def _nenhum_e_obrigatorio(candidatos: list[str], campos_por_nome: dict) -> bool:
    """True se nenhum dos candidatos é um campo obrigatório do parâmetro vigente.

    Ex.: ["cep_residencial", "cep_comercial"], os dois opcionais → True; ["data_admissao", "data_nascimento"], com a
    data de admissão obrigatória → False.
    """
    for candidato in candidatos:
        # Um candidato obrigatório basta: a dúvida é da empresa, e a coluna não fica sem rótulo
        if campos_por_nome[candidato].obrigatorio:
            return False
    return True


def colunas_sem_rotulo(mapeamento: MappingPlan, campos: list[CampoLayout]) -> dict[str, list[str]]:
    """As colunas do arquivo que ficam guardadas sem rótulo, com os candidatos de cada uma.

    Recebe: o mapeamento APROVADO do envio; os campos do parâmetro vigente.
    Devolve: {coluna: [candidatos]}, só das colunas que ficaram de fora (sem campo e sem divisão) com pelo menos um
    candidato do parâmetro vigente e nenhum candidato obrigatório (a trava da LGPD, no alto do arquivo).
    Ex.: "C.E.P" em dúvida entre os dois CEPs opcionais e deixada de fora → {"C.E.P": ["cep_residencial",
    "cep_comercial"]}; "Religião" (sem candidato) não entra; "Data" em dúvida com a data de admissão (obrigatória) não
    entra.
    """
    # Os campos do parâmetro vigente, pelo nome técnico
    campos_por_nome = {}
    for campo in campos:
        campos_por_nome[campo.campo] = campo
    colunas = {}
    for item in mapeamento.itens:
        # Só a coluna que ficou de fora: a mapeada virou um campo normal, e a dividida virou as suas partes
        if item.status != StatusMapeamento.NAO_MAPEADO or item.divisao is not None:
            continue
        candidatos = _candidatos_do_parametro(item.candidatos, campos_por_nome)
        # Sem nenhum candidato, a coluna é desconhecida: nunca é guardada
        if not candidatos:
            continue
        # A dúvida só entre campos opcionais fica guardada sem rótulo
        if _nenhum_e_obrigatorio(candidatos, campos_por_nome):
            colunas[item.coluna] = candidatos
    return colunas


def guardar_nos_registros(leitura: Leitura, mapeamento: MappingPlan, campos: list[CampoLayout],
                          registros: list[dict]) -> None:
    """Põe no registro de cada pessoa a lista das informações sem rótulo dela (a chave CHAVE_NO_REGISTRO).

    Recebe: a tabela lida do arquivo; o mapeamento aprovado; os campos do parâmetro vigente; os registros da
    padronização, um por linha da tabela e na mesma ordem (services/normalizador.py). Devolve: nada (os registros
    ganham a chave).
    O valor vai como veio no arquivo, só sem os espaços das pontas: não há campo para dizer como convertê-lo. A célula
    vazia não é guardada, e o registro sem nada para guardar fica sem a chave.
    Ex.: a pessoa com "01310-100" na coluna "C.E.P" → registro["_sem_rotulo"] = [{"coluna": "C.E.P", "valor":
    "01310-100", "candidatos": ["cep_residencial", "cep_comercial"]}].
    """
    colunas = colunas_sem_rotulo(mapeamento, campos)
    # A posição de cada coluna guardada na tabela, na ordem das colunas do arquivo
    posicoes = {}
    for coluna in colunas:
        if coluna in leitura.cabecalhos:
            posicoes[coluna] = leitura.cabecalhos.index(coluna)
    # Cada registro anda junto com a sua linha da tabela
    for registro, linha in zip(registros, leitura.linhas):
        guardadas_da_pessoa = []
        for coluna, posicao in posicoes.items():
            valor = linha[posicao].strip()
            # Célula vazia: nada a guardar
            if valor:
                guardadas_da_pessoa.append({"coluna": coluna, "valor": valor, "candidatos": list(colunas[coluna])})
        if guardadas_da_pessoa:
            registro[CHAVE_NO_REGISTRO] = guardadas_da_pessoa


def guardadas(registro: dict) -> list[dict]:
    """As informações sem rótulo guardadas no registro de uma pessoa, no formato guardado (vazio quando não há nada).

    Ex.: {"_linha": 2, "cpf": "..."} → []; {"_linha": 3, "_sem_rotulo": [{...}]} → [{...}].
    """
    return registro.get(CHAVE_NO_REGISTRO, [])


def para_a_tela(guardadas_da_pessoa: list[dict]) -> list[dict]:
    """A lista como a tela recebe: cada candidato com o nome técnico e o nome legível.

    Recebe: a lista no formato guardado (da padronização ou do cadastro). Devolve: uma lista nova, no formato da tela.
    Ex.: [{"coluna": "C.E.P", "valor": "01310-100", "candidatos": ["cep_residencial"]}] → [{"coluna": "C.E.P",
    "valor": "01310-100", "candidatos": [{"campo": "cep_residencial", "rotulo": "CEP residencial"}]}].
    """
    # Importado aqui dentro: services/acompanhamento.py usa este arquivo, e importar lá em cima faria um laço
    from services import acompanhamento
    na_tela = []
    for informacao in guardadas_da_pessoa:
        # Cada candidato com o nome que uma pessoa lê (o mesmo das colunas da grade)
        candidatos = []
        for campo in informacao["candidatos"]:
            candidatos.append({"campo": campo, "rotulo": acompanhamento.rotulo_do_campo(campo)})
        na_tela.append({"coluna": informacao["coluna"], "valor": informacao["valor"], "candidatos": candidatos})
    return na_tela


def do_registro_para_a_tela(registro: dict) -> list[dict]:
    """As informações sem rótulo de um registro da padronização, já no formato da tela.

    É o que as listas da empresa (Acompanhar e Cadastrar) e do banco (Envios) põem em cada pessoa, ao lado dos dados
    dela. Ex.: o registro sem nada guardado → [].
    """
    return para_a_tela(guardadas(registro))


def em_texto(guardadas_da_pessoa: list[dict]) -> str | None:
    """A lista em texto JSON, para a coluna informacoes_sem_rotulo do cadastro.

    Devolve None quando não há nada: a coluna fica vazia, e nada é guardado (minimização).
    Ex.: [] → None; [{"coluna": "C.E.P", ...}] → '[{"coluna": "C.E.P", ...}]'.
    """
    if not guardadas_da_pessoa:
        return None
    return json.dumps(guardadas_da_pessoa, ensure_ascii=False)


def do_cadastro_da_empresa(conexao, empresa_id: str) -> dict[str, list[dict]]:
    """As informações sem rótulo das pessoas cadastradas de uma empresa, pelo CPF: {cpf: lista no formato guardado}.

    Recebe: conexao; empresa_id (a da sessão, ou a empresa que o banco abriu). Devolve: só as pessoas com alguma
    informação guardada, numa consulta só, pela chave da tabela (empresa e CPF).
    Ex.: {"52998224725": [{"coluna": "C.E.P", "valor": "01310-100", "candidatos": ["cep_residencial", ...]}]}.
    """
    # Garante que a tabela existe e já tem a coluna nova (bancos antigos ganham a coluna aqui)
    processamentos._preparar(conexao)
    consulta = conexao.execute("SELECT cpf, informacoes_sem_rotulo FROM funcionarios_homologados "
                               "WHERE empresa_id = ? AND informacoes_sem_rotulo IS NOT NULL", (empresa_id,))
    por_cpf = {}
    for cpf, texto in consulta:
        # O texto JSON volta a ser a lista
        por_cpf[cpf] = json.loads(texto)
    return por_cpf
