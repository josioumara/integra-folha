"""Números de planejamento para o especialista do banco (ADR-25, ADR-26, ADR-27).

Só números agregados: quantos funcionários foram cadastrados, quantos aguardam o retorno do banco, quantas contas
foram abertas, quantos correntistas tiveram a folha marcada, onde (região da unidade de trabalho) e o ganho. Nenhuma
lista de pessoas sai daqui.

De onde vêm os números (sem a base do banco):
    - as pessoas: o motor de planejamento (services/motor_planejamento.py) registra cada funcionário homologado,
      com o hash do CPF, a região e a data de referência da carga;
    - o tipo de cada pessoa: o arquivo de contas que o banco devolve (services/contas_abertas.py, retorno_por_cpf).
      O CPF do retorno vira hash e é comparado com o hash guardado pelo motor. Classificação de cada Cadastrado:
        * AGUARDANDO_RETORNO: o banco ainda não devolveu a conta dele;
        * CONTA_ABERTA: o banco abriu uma conta nova (tipo 1 no arquivo);
        * CORRENTISTA_MARCADO: já era correntista, e o banco marcou a folha (tipo 2).
      O banco sempre informa o tipo no arquivo: uma conta
      sem o tipo só existe se foi gravada antes da coluna do tipo, e conta como AGUARDANDO_RETORNO, porque o banco
      ainda não disse o status dela; quando ela vier de novo num arquivo, ganha o tipo (services/contas_abertas.py).
      Desde o ADR-149, o arquivo só traz o CPF e o tipo: o correntista é um grupo só, sem a divisão
      entre ativos e inativos e sem a folha já identificada (o que ficou gravado dessas colunas não é mais lido).

O ganho (estimativa, não receita; o falso não folha é a premissa do business case, e a conta nova é informativa,
porque o sistema tem a visão do todo):
    - realizado (o que o retorno do banco já confirmou) = correntistas × (MOB folha − MOB não folha) + contas novas ×
      MOB cliente novo. O correntista que chega pelo projeto é o cliente que já estava no banco e passa a ter a folha
      reconhecida: a premissa do business case (ADR-149; antes, o arquivo separava o falso não folha ATIVO de quem já
      era folha e do inativo, e só ele somava);
    - Simulador de Rentabilidade, sobre uma base de N clientes (os que a empresa enviou, ou a
      estimativa da especialista), com quatro taxas estimadas por ela:
          N × % novas contas × MOB cliente novo
        + N × % correntista não folha × % ativos × (MOB folha − MOB não folha).
      O correntista folha (já traz o MOB maior), o inativo e o resto da base não rendem nada novo. As taxas não têm
      valor oficial nem padrão: sem uma delas, a simulação diz o que falta.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

from services import contas_abertas, dados_mock, motor_planejamento, parametros, processamentos
from services.parametros import Premissas

# As classificações de cada Cadastrado, pelo retorno do banco
AGUARDANDO_RETORNO = "AGUARDANDO_RETORNO"
CONTA_ABERTA = "CONTA_ABERTA"
CORRENTISTA_MARCADO = "CORRENTISTA_MARCADO"

# Os tipos como vêm do retorno do banco (services/contas_abertas.py)
TIPO_NOVA_CONTA = "NOVA_CONTA"
TIPO_CORRENTISTA = "CORRENTISTA"

# As contagens que o painel mostra (as chaves do resumo, por empresa e por região). O correntista é um grupo só
# (ADR-149: o arquivo do banco traz só o CPF e o tipo)
CAMPOS_CONTAGEM = ("cadastrados", "aguardando_retorno", "contas_abertas", "correntistas_marcados")

# As colunas que podem ser usadas como filtro no painel (o segmento saiu: vinha da base do banco)
COLUNAS_DE_FILTRO = ("empresa_id", "uf", "data_referencia")

# Para arredondar dinheiro em centavos
CENTAVOS = Decimal("0.01")

# O maior tamanho do nome de uma simulação
TAMANHO_MAXIMO_DO_NOME = 80

# As premissas globais que o simulador mostra (as oficiais, travadas) e deixa mudar só na simulação
TITULOS_DAS_PREMISSAS_GLOBAIS = {
    "horizonte_meses": "Horizonte da projeção",
    "mob_cliente_folha": "MOB cliente folha",
    "mob_cliente_nao_folha": "MOB cliente não folha",
    "mob_cliente_novo_conquistado": "MOB cliente novo conquistado",
}
# As taxas estimadas pela especialista (de 0 a 100), sem valor oficial nem padrão: as três
# primeiras dividem a base (juntas, até 100%); a % ativos diz, dos correntistas, quantos são ativos
TITULOS_DAS_TAXAS = {
    "percentual_novas_contas": "% novas contas",
    "percentual_nao_folha": "% correntista (não folha)",
    "percentual_folha": "% correntista (folha)",
    "percentual_ativos": "% ativos entre os correntistas",
}
# As taxas que são partes da mesma base de clientes (a soma delas não passa de 100%)
TAXAS_QUE_DIVIDEM_A_BASE = ("percentual_novas_contas", "percentual_nao_folha", "percentual_folha")
# Todos os campos do simulador que a tela manda, com o nome que aparece para a pessoa
TITULOS_DO_SIMULADOR = dict(TITULOS_DAS_PREMISSAS_GLOBAIS)
TITULOS_DO_SIMULADOR.update(TITULOS_DAS_TAXAS)
TITULOS_DO_SIMULADOR["clientes_estimados"] = "Clientes (sua estimativa)"
# O maior número de clientes que uma simulação aceita (a carteira inteira do business case tem ~1,04 milhão)
MAXIMO_DE_CLIENTES = 10000000


# ============================== 1. As pessoas e o retorno do banco ==============================

def _filtro_sql(empresa_id, uf, data_referencia) -> tuple[str, tuple]:
    """O trecho WHERE para os filtros. None em um filtro quer dizer "todos"."""
    # "(? IS NULL OR coluna = ?)": com o filtro vazio, a condição é sempre verdadeira
    trecho = "WHERE (? IS NULL OR empresa_id = ?) AND (? IS NULL OR uf = ?) AND (? IS NULL OR data_referencia = ?)"
    return trecho, (empresa_id, empresa_id, uf, uf, data_referencia, data_referencia)


def _pessoas(conexao, colunas_do_grupo: list[str], empresa_id, uf, data_referencia) -> list[dict]:
    """As pessoas registradas pelo motor, com os filtros: empresa, hash do CPF e as colunas do grupo pedido.

    Recebe: colunas_do_grupo — ex.: ["uf", "municipio", "nome_unidade"] (ou [] para o total).
    Devolve: [{"empresa_id": "EMP001", "cpf_hash": "9f2c...", "uf": "SP", ...}]. É interno: nunca sai deste arquivo.
    """
    motor_planejamento.preparar_tabelas(conexao)
    filtro, parametros_do_filtro = _filtro_sql(empresa_id, uf, data_referencia)
    # As colunas lidas: empresa e hash sempre (para cruzar com o retorno), mais as do grupo
    colunas = ["empresa_id", "cpf_hash"]
    for coluna in colunas_do_grupo:
        if coluna not in colunas:
            colunas.append(coluna)
    consulta = conexao.execute(f"SELECT {', '.join(colunas)} FROM planejamento_funcionario {filtro}",
                               parametros_do_filtro)
    pessoas = []
    for valores in consulta:
        pessoas.append(dict(zip(colunas, valores)))
    return pessoas


def retorno_por_hash(conexao, empresa_ids: list[str]) -> dict:
    """O retorno do banco de cada pessoa, pelo hash do CPF, empresa por empresa.

    Recebe: empresa_ids — as empresas das pessoas contadas. Devolve: {(empresa_id, cpf_hash): {"tipo_conta"}}. Por
    empresa porque a mesma pessoa pode estar em duas empresas, com contas diferentes.
    O CPF vira hash aqui mesmo e não é guardado.
    """
    retornos = {}
    for empresa_id in empresa_ids:
        # O retorno só desta empresa: {cpf: {"tipo_conta": ...}}
        for cpf, retorno in contas_abertas.retorno_por_cpf(conexao, [empresa_id]).items():
            retornos[(empresa_id, motor_planejamento.hash_do_cpf(cpf))] = retorno
    return retornos


def classificar(retorno: dict | None) -> str:
    """A classificação de um Cadastrado pelo retorno do banco.

    Recebe: retorno — {"tipo_conta"} ou None (o banco ainda não devolveu a conta).
    Devolve: AGUARDANDO_RETORNO, CONTA_ABERTA ou CORRENTISTA_MARCADO.
    """
    if retorno is not None and retorno.get("tipo_conta") == TIPO_NOVA_CONTA:
        return CONTA_ABERTA
    if retorno is not None and retorno.get("tipo_conta") == TIPO_CORRENTISTA:
        return CORRENTISTA_MARCADO
    # Sem retorno, ou uma conta gravada antes da coluna do tipo: o banco ainda não disse o status (nada é assumido)
    return AGUARDANDO_RETORNO


def _contagem_vazia() -> dict:
    """Todas as contagens em zero."""
    contagem = {}
    for campo in CAMPOS_CONTAGEM:
        contagem[campo] = 0
    return contagem


def _contar_pessoa(contagem: dict, retorno: dict | None) -> None:
    """Soma uma pessoa na contagem, pela classificação dela: aguardando o retorno, conta nova ou correntista (um grupo
    só, ADR-149)."""
    contagem["cadastrados"] += 1
    classificacao = classificar(retorno)
    if classificacao == AGUARDANDO_RETORNO:
        contagem["aguardando_retorno"] += 1
        return
    if classificacao == CONTA_ABERTA:
        contagem["contas_abertas"] += 1
        return
    contagem["correntistas_marcados"] += 1


def _empresas_das_pessoas(pessoas: list[dict]) -> list[str]:
    """As empresas que aparecem na lista de pessoas, sem repetir, em ordem."""
    empresas = set()
    for pessoa in pessoas:
        empresas.add(pessoa["empresa_id"])
    return sorted(empresas)


# ============================== 2. As somas ==============================

def resumir(conexao, empresa_id: str | None = None, uf: str | None = None, data_referencia: str | None = None) -> dict:
    """Soma as contagens, com os filtros escolhidos.

    Devolve: {"cadastrados": 35, "aguardando_retorno": 20, "contas_abertas": 9, "correntistas_marcados": 6}.
    """
    pessoas = _pessoas(conexao, [], empresa_id, uf, data_referencia)
    retornos = retorno_por_hash(conexao, _empresas_das_pessoas(pessoas))
    contagem = _contagem_vazia()
    for pessoa in pessoas:
        _contar_pessoa(contagem, retornos.get((pessoa["empresa_id"], pessoa["cpf_hash"])))
    return contagem


def _agrupar(conexao, colunas_do_grupo: list[str], empresa_id, uf, data_referencia) -> list[dict]:
    """As contagens somadas por grupo (ex.: por empresa, ou por UF + município + unidade), em ordem do grupo."""
    pessoas = _pessoas(conexao, colunas_do_grupo, empresa_id, uf, data_referencia)
    retornos = retorno_por_hash(conexao, _empresas_das_pessoas(pessoas))
    # Cada grupo (a tupla dos valores das colunas) e a contagem dele
    contagens_por_grupo = {}
    for pessoa in pessoas:
        grupo = []
        for coluna in colunas_do_grupo:
            grupo.append(pessoa[coluna])
        chave_do_grupo = tuple(grupo)
        if chave_do_grupo not in contagens_por_grupo:
            contagens_por_grupo[chave_do_grupo] = _contagem_vazia()
        _contar_pessoa(contagens_por_grupo[chave_do_grupo], retornos.get((pessoa["empresa_id"], pessoa["cpf_hash"])))
    # Uma linha por grupo, na ordem dos valores do grupo
    linhas = []
    for chave_do_grupo in sorted(contagens_por_grupo):
        linha = dict(zip(colunas_do_grupo, chave_do_grupo))
        linha.update(contagens_por_grupo[chave_do_grupo])
        linhas.append(linha)
    return linhas


def por_empresa(conexao, uf: str | None = None, data_referencia: str | None = None,
                empresa_id: str | None = None) -> list[dict]:
    """Uma linha somada por empresa, para a tabela do painel.

    Recebe: os filtros (UF da unidade, data de referência e, quando escolhida no filtro do alto, a empresa).
    Devolve: [{empresa_id, empresa (o nome), cadastrados, aguardando_retorno, ...}]. Com uma empresa escolhida, só ela.
    """
    tabela = []
    for linha in _agrupar(conexao, ["empresa_id"], empresa_id, uf, data_referencia):
        id_da_empresa = linha.pop("empresa_id")
        linha_da_tabela = {"empresa_id": id_da_empresa, "empresa": dados_mock.nome_da_empresa(id_da_empresa)}
        linha_da_tabela.update(linha)
        tabela.append(linha_da_tabela)
    return tabela


def por_regiao(conexao, empresa_id: str | None = None, data_referencia: str | None = None) -> list[dict]:
    """"Onde": uma linha por UF, município e unidade de trabalho (endereço comercial, ADR-27)."""
    return _agrupar(conexao, ["uf", "municipio", "nome_unidade"], empresa_id, None, data_referencia)


def indicadores(conexao, empresa_id: str | None = None, uf: str | None = None,
                data_referencia: str | None = None) -> dict:
    """Os números de cima do painel: empresas integradas e funcionários processados, com os filtros."""
    motor_planejamento.preparar_tabelas(conexao)
    filtro, parametros_do_filtro = _filtro_sql(empresa_id, uf, data_referencia)
    empresas, funcionarios = conexao.execute(
        f"SELECT COUNT(DISTINCT empresa_id), COUNT(*) FROM planejamento_funcionario {filtro}",
        parametros_do_filtro).fetchone()
    return {"empresas_integradas": empresas, "funcionarios_processados": funcionarios}


def por_arquivo(conexao, empresa_id: str | None = None, uf: str | None = None,
                data_referencia: str | None = None) -> list[dict]:
    """A fonte dos números: cada arquivo homologado e quantas pessoas ele trouxe ao planejamento."""
    motor_planejamento.preparar_tabelas(conexao)
    filtro, parametros_do_filtro = _filtro_sql(empresa_id, uf, data_referencia)
    consulta = conexao.execute(
        f"SELECT processamento_id, empresa_id, data_referencia, COUNT(*) FROM planejamento_funcionario {filtro} "
        "GROUP BY processamento_id, empresa_id, data_referencia ORDER BY data_referencia, empresa_id",
        parametros_do_filtro)
    tabela = []
    for processamento_id, empresa, data_referencia_da_carga, quantidade in consulta:
        perfil = processamentos.obter(conexao, processamento_id)
        tabela.append({"arquivo": perfil.nome_arquivo if perfil else processamento_id,
                       "carga": perfil.tipo_carga.value if perfil else "",
                       "empresa": dados_mock.nome_da_empresa(empresa), "data_referencia": data_referencia_da_carga,
                       "funcionarios": quantidade, "processamento_id": processamento_id})
    return tabela


def valores_para_filtro(conexao, coluna: str) -> list[str]:
    """Os valores que existem numa coluna das pessoas registradas (ex.: as UFs), para as listas de filtro da tela."""
    if coluna not in COLUNAS_DE_FILTRO:
        raise ValueError(f"Coluna sem filtro: {coluna}")
    motor_planejamento.preparar_tabelas(conexao)
    valores = []
    for (valor,) in conexao.execute(f"SELECT DISTINCT {coluna} FROM planejamento_funcionario ORDER BY {coluna}"):
        valores.append(valor)
    return valores


# ============================== 3. As premissas e o ganho ==============================

def taxa_da_porcentagem(porcentagem) -> Decimal:
    """Converte uma porcentagem (ex.: 20, de 20%) na fração usada na conta (0,20), em Decimal."""
    return Decimal(str(porcentagem)) / 100


def premissas_da_versao(conexao, numero_da_versao: int) -> Premissas:
    """As premissas de uma versão escolhida, para reproduzir um cenário antigo."""
    return parametros.premissas_da_versao(conexao, numero_da_versao)


def projetar_ganho(resumo: dict, premissas: Premissas) -> dict:
    """O ganho REALIZADO no horizonte das premissas (ADR-26, ADR-123, ADR-149): o que o retorno do banco já confirmou.

    Recebe: resumo — as contagens (resumir); premissas — os MOB e o horizonte.
    Devolve: {"realizado": {"correntistas", "contas_abertas", "total"}, "versao_premissas", "horizonte_meses"}, com o
    dinheiro em Decimal (centavos). O potencial é do Simulador de Rentabilidade (simular_rentabilidade).
    Fórmula: correntistas × (MOB folha − MOB não folha) + contas novas × MOB cliente novo. Desde o ADR-149, o arquivo
    do banco traz só o CPF e o tipo: o correntista é um grupo só, o cliente que já estava no banco e passa a ter a
    folha reconhecida pelo projeto (a premissa do business case). Exemplo (MOB folha 2.090,62; não folha 1.724,00;
    novo 2.090,62): 1 correntista e 2 contas novas → 1 × 366,62 + 2 × 2.090,62 = 4.547,86.
    """
    # Quanto a margem sobe quando a folha passa a ser reconhecida (o correntista vira cliente folha)
    diferenca_de_mob = premissas.mob_cliente_folha - premissas.mob_cliente_nao_folha
    ganho_dos_correntistas = (resumo["correntistas_marcados"] * diferenca_de_mob).quantize(CENTAVOS)
    ganho_das_contas_abertas = (resumo["contas_abertas"] * premissas.mob_cliente_novo_conquistado).quantize(CENTAVOS)
    realizado = {"correntistas": ganho_dos_correntistas, "contas_abertas": ganho_das_contas_abertas,
                 "total": ganho_dos_correntistas + ganho_das_contas_abertas}
    return {"realizado": realizado, "versao_premissas": premissas.versao, "horizonte_meses": premissas.horizonte_meses}


def ganho_em_texto(ganho: dict) -> dict:
    """O ganho realizado com o dinheiro em texto (o JSON não tem Decimal; texto não perde centavos). Ex.: "4547.86"."""
    em_texto = dict(ganho)
    em_texto["realizado"] = {}
    for chave, valor in ganho["realizado"].items():
        em_texto["realizado"][chave] = str(valor)
    return em_texto


def clientes_conferidos(valores: dict, nome: str) -> int | None:
    """Um número de clientes digitado (inteiro de 0 ao máximo), ou None quando veio vazio.

    Recebe: valores (o que a tela mandou); nome (a chave). Levanta ValueError com o recado para a pessoa.
    Ex.: {"clientes_estimados": "1200"} → 1200; {"clientes_estimados": ""} → None; "12,5" → ValueError.
    """
    valor = valores.get(nome)
    # Vazio: sem valor (a base fica a que a empresa enviou)
    if valor is None or str(valor).strip() == "":
        return None
    texto_do_valor = str(valor).strip()
    # Só algarismos: um número inteiro de pessoas
    if not texto_do_valor.isdigit():
        raise ValueError("O número de clientes precisa ser inteiro, sem pontos nem vírgulas (ex.: 1200).")
    clientes = int(texto_do_valor)
    if clientes > MAXIMO_DE_CLIENTES:
        raise ValueError("O número de clientes passa do máximo aceito numa simulação (10 milhões).")
    return clientes


def premissas_do_simulador(conexao, valores: dict) -> dict:
    """O que a simulação usa: as premissas globais (as oficiais, trocadas pelas que a especialista mudou), as quatro
    taxas estimadas e a estimativa de clientes.

    Recebe: valores — o que a tela mandou, em texto. Premissa global que não veio: vale a oficial. As taxas e a
    estimativa de clientes não têm valor oficial: sem valor, ficam None (nada é suposto). Tudo o que veio é conferido
    (horizonte de 1 a 60 meses; MOB maior que zero, com centavos; taxas de 0 a 100; clientes inteiros).
    Ex.: {"mob_cliente_folha": "2200", "percentual_novas_contas": "30", "clientes_estimados": "1200"}.
    Devolve: {"premissas": Premissas (com a versão oficial de onde partiu), "taxas": {nome: fração ou None},
              "clientes_estimados": int ou None, "valores": os valores como a tela mostra, "alteradas": as premissas
              globais diferentes das oficiais}. Nada é gravado.
    Levanta ValueError se % novas contas + % correntista (não folha) + % correntista (folha) passam de 100% (a base
    não comporta).
    """
    oficiais = parametros.premissas_ativas(conexao)
    usados = {
        "horizonte_meses": oficiais.horizonte_meses,
        "mob_cliente_folha": str(oficiais.mob_cliente_folha.quantize(CENTAVOS)),
        "mob_cliente_nao_folha": str(oficiais.mob_cliente_nao_folha.quantize(CENTAVOS)),
        "mob_cliente_novo_conquistado": str(oficiais.mob_cliente_novo_conquistado.quantize(CENTAVOS)),
    }
    # Guarda as oficiais para saber, no fim, quais a especialista mudou
    oficiais_em_texto = dict(usados)
    # As premissas globais que vieram da tela trocam as oficiais, depois de conferidas
    if valores.get("horizonte_meses") is not None:
        usados["horizonte_meses"] = parametros.horizonte_conferido(valores)
    for nome in parametros.PREMISSAS_EM_DINHEIRO:
        if valores.get(nome) is not None:
            usados[nome] = parametros.dinheiro_conferido(nome, valores)
    # As quatro taxas: vazias = sem valor
    taxas = {}
    for nome, titulo in TITULOS_DAS_TAXAS.items():
        usados[nome] = parametros.percentual_conferido(nome, titulo, valores)
        taxas[nome] = None
        if usados[nome] is not None:
            taxas[nome] = taxa_da_porcentagem(usados[nome])
    # Novas contas, correntista não folha e correntista folha são partes da mesma base: juntas, não passam de 100%
    soma_das_partes = Decimal("0")
    for nome in TAXAS_QUE_DIVIDEM_A_BASE:
        if taxas[nome] is not None:
            soma_das_partes = soma_das_partes + taxas[nome]
    if soma_das_partes > 1:
        raise ValueError("% novas contas + % correntista (não folha) + % correntista (folha) passam de 100%: a base "
                         "de clientes não comporta. Confira as três taxas.")
    usados["clientes_estimados"] = clientes_conferidos(valores, "clientes_estimados")
    # As premissas globais que ficaram diferentes das oficiais
    alteradas = []
    for nome in TITULOS_DAS_PREMISSAS_GLOBAIS:
        if usados[nome] != oficiais_em_texto[nome]:
            alteradas.append(nome)
    premissas = Premissas(versao=oficiais.versao, horizonte_meses=usados["horizonte_meses"],
                          mob_cliente_folha=Decimal(usados["mob_cliente_folha"]),
                          mob_cliente_nao_folha=Decimal(usados["mob_cliente_nao_folha"]),
                          mob_cliente_novo_conquistado=Decimal(usados["mob_cliente_novo_conquistado"]))
    return {"premissas": premissas, "taxas": taxas, "clientes_estimados": usados["clientes_estimados"],
            "valores": usados, "alteradas": alteradas}


def _linha_da_simulacao(grupo: str, pessoas: Decimal, conta: str, ganho: Decimal, rende: bool) -> dict:
    """Uma linha do resultado da simulação, com os números em texto (o JSON não tem Decimal).

    Recebe: grupo (o nome do grupo de pessoas); pessoas (a estimativa, em Decimal); conta (a conta em palavras); ganho
    (Decimal); rende (True se o grupo traz rentabilidade nova). Devolve: {"grupo", "pessoas" (uma casa), "conta",
    "ganho" (centavos), "rende"}. Ex.: pessoas 93.6 → "93.6".
    """
    return {"grupo": grupo, "pessoas": str(pessoas.quantize(Decimal("0.1"))), "conta": conta,
            "ganho": str(ganho.quantize(CENTAVOS)), "rende": rende}


def simular_rentabilidade(clientes: int, taxas: dict, premissas: Premissas) -> dict:
    """O Simulador de Rentabilidade: quanto uma base de clientes pode render, pelas quatro taxas estimadas.

    Recebe: clientes — a base (N: os que a empresa enviou, ou a estimativa da especialista); taxas — {"percentual_novas_
    contas", "percentual_nao_folha", "percentual_folha", "percentual_ativos"}, frações ou None; premissas — os MOB e o
    horizonte. Devolve: {"clientes", "linhas": [{grupo, pessoas, conta, ganho, rende}], "total" (texto) ou None,
    "falta": [os títulos das taxas sem valor]}. Sem uma das taxas, não há linhas nem total (nada é suposto).
    Conta (a nova conta traz a rentabilidade; o folha identificado, a diferença; o inativo, nada):
        novas contas               = N × % novas contas                    × MOB cliente novo
        não folha ativos           = N × % não folha × % ativos            × (MOB folha − MOB não folha)
        não folha inativos         = N × % não folha × (1 − % ativos)      → sem rentabilidade (inativo)
        folha ativos               = N × % folha × % ativos                → já traz o MOB folha: nada novo
        folha inativos             = N × % folha × (1 − % ativos)          → sem rentabilidade (inativo)
        o resto da base            = N × (1 − as três partes)              → não abre conta: nada
    Exemplo: N = 312, 30%, 40%, 20% e 75% ativos → 93,6 × 2.090,62 + 93,6 × 366,62 = R$ 229.997,66.
    """
    faltando = []
    for nome, titulo in TITULOS_DAS_TAXAS.items():
        if taxas[nome] is None:
            faltando.append(titulo)
    resultado = {"clientes": clientes, "linhas": [], "total": None, "falta": faltando}
    if faltando:
        return resultado
    diferenca_de_mob = premissas.mob_cliente_folha - premissas.mob_cliente_nao_folha
    mob_novo = premissas.mob_cliente_novo_conquistado
    base = Decimal(clientes)
    # As partes da base
    novas_contas = base * taxas["percentual_novas_contas"]
    nao_folha = base * taxas["percentual_nao_folha"]
    folha = base * taxas["percentual_folha"]
    resto_da_base = base - novas_contas - nao_folha - folha
    # Cada grupo de correntistas separado em ativos e inativos
    nao_folha_ativos = nao_folha * taxas["percentual_ativos"]
    folha_ativos = folha * taxas["percentual_ativos"]
    linhas = [
        _linha_da_simulacao("Novas contas", novas_contas,
                            "× MOB cliente novo (R$ " + str(mob_novo.quantize(CENTAVOS)) + ")",
                            novas_contas * mob_novo, True),
        _linha_da_simulacao("Correntistas não folha · ativos (folha identificada)", nao_folha_ativos,
                            "× (MOB folha − MOB não folha) = R$ " + str(diferenca_de_mob.quantize(CENTAVOS)),
                            nao_folha_ativos * diferenca_de_mob, True),
        _linha_da_simulacao("Correntistas não folha · inativos", nao_folha - nao_folha_ativos,
                            "inativo: sem rentabilidade", Decimal("0"), False),
        _linha_da_simulacao("Correntistas folha · ativos", folha_ativos,
                            "já traz o MOB folha: sem rentabilidade nova", Decimal("0"), False),
        _linha_da_simulacao("Correntistas folha · inativos", folha - folha_ativos,
                            "inativo: sem rentabilidade", Decimal("0"), False),
        _linha_da_simulacao("Resto da base (não abrem conta)", resto_da_base, "sem rentabilidade", Decimal("0"),
                            False),
    ]
    # O total é a soma das linhas, já em centavos (a mesma conta que a tela mostra linha a linha)
    total = Decimal("0")
    for linha in linhas:
        total = total + Decimal(linha["ganho"])
    resultado["linhas"] = linhas
    resultado["total"] = str(total)
    return resultado


def _porcentagem_observada(parte: int, todo: int) -> str | None:
    """Quanto a parte é do todo, em % com uma casa, como texto; None quando o todo é zero (sem divisão por zero).

    Ex.: (3, 10) → "30.0"; (1, 0) → None.
    """
    if todo == 0:
        return None
    return str((Decimal(100 * parte) / todo).quantize(Decimal("0.1")))


def retorno_confirmado(resumo: dict, premissas: Premissas) -> dict:
    """O que o retorno do banco já confirmou, para a seção de referência do simulador (travada).

    Recebe: resumo (as contagens de resumir); premissas (as da simulação, para o realizado em reais).
    Devolve: {cadastrados, com_retorno, aguardando_retorno, contas_abertas, correntistas, taxas_observadas:
    {novas_contas, correntistas} (% de quem já teve retorno, em texto ou None), realizado}. O correntista é um grupo
    só (ADR-149): o arquivo do banco não diz mais se a folha já era identificada nem se ele é ativo.
    Ex.: 10 com retorno, 3 contas novas e 6 correntistas → "30.0" e "60.0".
    """
    com_retorno = resumo["cadastrados"] - resumo["aguardando_retorno"]
    observadas = {
        "novas_contas": _porcentagem_observada(resumo["contas_abertas"], com_retorno),
        "correntistas": _porcentagem_observada(resumo["correntistas_marcados"], com_retorno),
    }
    realizado = ganho_em_texto(projetar_ganho(resumo, premissas))["realizado"]
    return {"cadastrados": resumo["cadastrados"], "com_retorno": com_retorno,
            "aguardando_retorno": resumo["aguardando_retorno"], "contas_abertas": resumo["contas_abertas"],
            "correntistas": resumo["correntistas_marcados"], "taxas_observadas": observadas, "realizado": realizado}


# ============================== 4. As simulações salvas ==============================

def nome_conferido(nome: str | None) -> str:
    """O nome da simulação, sem espaços nas pontas. Vazio ou grande demais: ValueError com o recado para a pessoa."""
    texto_do_nome = (nome or "").strip()
    if not texto_do_nome:
        raise ValueError("Dê um nome à simulação para salvar.")
    if len(texto_do_nome) > TAMANHO_MAXIMO_DO_NOME:
        raise ValueError(f"O nome da simulação pode ter até {TAMANHO_MAXIMO_DO_NOME} caracteres.")
    return texto_do_nome


def salvar_simulacao(conexao, nome: str, simulacao: dict, base: dict, resultado: dict, filtros: dict,
                     usuario: str) -> None:
    """Guarda a simulação com o nome dado: os valores usados, a base de clientes e o resultado. Não muda as oficiais.

    Recebe: nome (obrigatório); simulacao (o que premissas_do_simulador devolve); base — {"clientes", "origem"
    ("empresa" ou "estimativa")}; resultado (o que simular_rentabilidade devolve); filtros (a empresa); usuario.
    """
    nome_da_simulacao = nome_conferido(nome)
    motor_planejamento.preparar_tabelas(conexao)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # A coluna taxa_conquista é das simulações de antes do Simulador de Rentabilidade: nas novas, fica vazia
    conexao.execute("INSERT INTO simulacao_ganho (criado_em, usuario, filtros, taxa_conquista, versao_premissas, "
                    "resultado, nome, premissas) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (agora, usuario, json.dumps(filtros, ensure_ascii=False), "", simulacao["premissas"].versao,
                     json.dumps({"base": base, "simulacao": resultado}), nome_da_simulacao,
                     json.dumps(simulacao["valores"])))
    conexao.commit()


def _valores_da_simulacao_antiga(conexao, versao: str) -> dict:
    """Os valores de uma simulação salva antes do simulador (sem valores próprios): os da versão que ela usou.

    Recebe: versao — ex.: "v1". Devolve: os valores como o simulador mostra (as taxas ficam sem valor).
    """
    premissas = parametros.premissas_da_versao(conexao, int(versao.lstrip("v")))
    valores = {"horizonte_meses": premissas.horizonte_meses,
               "mob_cliente_folha": str(premissas.mob_cliente_folha.quantize(CENTAVOS)),
               "mob_cliente_nao_folha": str(premissas.mob_cliente_nao_folha.quantize(CENTAVOS)),
               "mob_cliente_novo_conquistado": str(premissas.mob_cliente_novo_conquistado.quantize(CENTAVOS)),
               "clientes_estimados": None}
    for nome in TITULOS_DAS_TAXAS:
        valores[nome] = None
    return valores


def _ganho_total_salvo(resultado: dict) -> str | None:
    """O ganho total guardado: o do Simulador de Rentabilidade; nas simulações de antes, o total que elas guardaram."""
    if "simulacao" in resultado:
        return resultado["simulacao"]["total"]
    if "ganho" in resultado:
        return resultado["ganho"].get("ganho_total")
    return resultado.get("ganho_total")


def simulacoes(conexao) -> list[dict]:
    """As simulações salvas, da mais recente para a mais antiga (nome, quem, quando, filtros, valores, base e ganho).

    Cada uma traz também "simulacao": o resultado guardado ({clientes, linhas, total, falta}), que a janela
    "Visualizar" mostra linha a linha; None nas simulações de antes do Simulador de Rentabilidade (só o total).
    """
    motor_planejamento.preparar_tabelas(conexao)
    linhas = conexao.execute("SELECT id, nome, criado_em, usuario, filtros, versao_premissas, resultado, premissas "
                             "FROM simulacao_ganho ORDER BY id DESC").fetchall()
    lista = []
    for identificador, nome, criado_em, usuario, filtros, versao, resultado, premissas in linhas:
        valores = json.loads(premissas)
        # Simulação de antes do simulador de hoje: os valores globais são os da versão oficial que ela usou (as taxas
        # e a estimativa de clientes, que não existiam, ficam sem valor)
        if not valores or "percentual_novas_contas" not in valores:
            valores = _valores_da_simulacao_antiga(conexao, versao)
        resultado_lido = json.loads(resultado)
        lista.append({"id": identificador, "nome": nome, "criado_em": criado_em, "usuario": usuario,
                      "filtros": json.loads(filtros), "versao_premissas": versao, "valores": valores,
                      "base": resultado_lido.get("base"), "ganho_total": _ganho_total_salvo(resultado_lido),
                      "simulacao": resultado_lido.get("simulacao")})
    return lista
