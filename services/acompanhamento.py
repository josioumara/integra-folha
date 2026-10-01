"""Acompanhar cadastros: o que a empresa vê dos próprios envios e funcionários (novo front, ADR-69).

Para que serve: a tela "Acompanhar cadastros" do Portal Empresa mostra os envios da empresa, os funcionários já
cadastrados e um resumo. Este arquivo monta esses dados a partir do que a aplicação JÁ guarda, sem tabela nova:
    - os envios vêm da tabela de processamentos (quando, quem enviou, quantas linhas, em que situação);
    - os funcionários vêm dos arquivos finais das homologações (o CSV no layout do banco, um por envio aprovado).

Regras de privacidade que valem em todas as funções:
    - tudo é SEMPRE filtrado pela empresa informada. Quem chama (a API) passa a empresa da SESSÃO de quem está
      logado, nunca uma empresa escolhida na tela: assim a Empresa A nunca vê a Empresa B;
    - o CPF aparece inteiro e formatado ("246.813.579-54"): a empresa vê os dados que ela mesma enviou (ADR-97).
      Só os campos que a tela usa saem
      (minimização), e abrir a lista, a ficha ou baixar o arquivo fica registrado (registrar_acesso);
    - a conta aberta de cada funcionário (data, agência e número) aparece na lista, na ficha e no download: é nela
      que a empresa paga o salário (ADR-102).

Exemplo de uso:
    envios = envios_da_empresa(conexao, "EMP001")
    funcionarios = funcionarios_da_empresa(conexao, "EMP001")
"""
import csv
import io
import re
from datetime import datetime, timezone

from agents import redator_de_perguntas
from models.contratos import EstadoProcessamento, TipoCarga
from services import (auditoria, conversas_das_pendencias, correcoes, dados_da_empresa_no_envio, homologacao,
                      idas_e_voltas, normalizador, parametros, pendencias_em_grupo, pergunta_da_pendencia,
                      perguntas_das_pendencias, processamentos, validador)
# O que a IA achou sem ter certeza do campo vai para o detalhe de cada pessoa (ADR-143, Parte 1)
from services import informacoes_sem_rotulo

# As etapas da linha do tempo de um envio, na ordem, com o evento da auditoria que marca cada uma como feita.
# Os nomes e a ordem: "Arquivo carregado" (e não "Enviado", que se confundia com o envio
# ao banco) e "Aprovação das contas enviadas" (o especialista do banco aprova o envio). Depois delas vem a última
# etapa, ETAPA_DAS_CONTAS, que não é um evento da auditoria. A tela mostra as 6 lado a lado (front/css/estilos.css).
ETAPAS_DA_LINHA_DO_TEMPO = (
    ("Arquivo carregado", "RECEBIDO"),
    ("Lido pelos agentes", "MAPEAMENTO_PROPOSTO"),
    ("Conferido por você", "MAPEAMENTO_APROVADO"),
    ("Enviado ao banco", "ENVIADO_AO_BANCO"),
    ("Aprovação das contas enviadas", "HOMOLOGADO"),
)
# A última etapa: o arquivo semanal de contas abertas do banco trouxe a conta de funcionários deste envio (ADR-113)
ETAPA_DAS_CONTAS = "Contas abertas"
# As etapas de antes da avaliação do banco: no envio de devolução, elas vêm do envio de origem (ADR-121)
TIPOS_ANTES_DO_BANCO = ("RECEBIDO", "MAPEAMENTO_PROPOSTO", "MAPEAMENTO_APROVADO", "ENVIADO_AO_BANCO")

# Como cada tipo de carga aparece para a empresa
TIPO_PARA_A_EMPRESA = {
    TipoCarga.INICIAL: "Carga inicial",
    TipoCarga.INCLUSAO: "Inclusão",
}

# Como cada situação do processamento aparece para a empresa, em linguagem simples
SITUACAO_PARA_A_EMPRESA = {
    EstadoProcessamento.RECEBIDO: "Recebido",
    EstadoProcessamento.PERFILADO: "Recebido",
    EstadoProcessamento.MAPEAMENTO_PENDENTE: "Esperando você conferir as colunas",
    EstadoProcessamento.MAPEAMENTO_APROVADO: "Colunas conferidas",
    EstadoProcessamento.NORMALIZADO: "Pronto para enviar",
    EstadoProcessamento.VALIDACAO_PENDENTE: "Com pendências para corrigir",
    EstadoProcessamento.AGUARDANDO_BANCO: "Em análise pelo banco",
    EstadoProcessamento.DEVOLVIDO: "Devolvido pelo banco",
    EstadoProcessamento.HOMOLOGADO: "Cadastrado",
    EstadoProcessamento.REJEITADO: "Descartado",
}

# Palavras dos nomes técnicos que ganham acento (ou forma própria) no rótulo da tela. Ex.: "data_admissao" vira
# "Data admissão". Palavra que não está aqui fica como está (um campo novo do banco aparece do mesmo jeito)
PALAVRAS_DO_ROTULO = {
    "admissao": "admissão", "mae": "mãe", "emissao": "emissão", "orgao": "órgão", "emissor": "emissor",
    "efetivacao": "efetivação", "referencia": "referência", "municipio": "município", "numero": "número",
    "codigo": "código", "matricula": "matrícula", "email": "e-mail", "cpf": "CPF", "cnpj": "CNPJ", "uf": "UF",
    "cep": "CEP", "nis": "NIS", "pis": "PIS",
    "cbo": "CBO",   # o código da profissão (ADR-143): "codigo_cbo" vira "Código CBO"
}


def rotulo_do_campo(campo: str) -> str:
    """O nome do campo do jeito que uma pessoa lê, a partir do nome técnico do layout.

    Ex.: "data_admissao" → "Data admissão"; "cnpj_empregador" → "CNPJ empregador"; "nis_pis" → "NIS PIS".
    """
    palavras = []
    for palavra in campo.split("_"):
        palavras.append(PALAVRAS_DO_ROTULO.get(palavra, palavra))
    rotulo = " ".join(palavras)
    # Só a primeira letra em maiúscula (as siglas já estão em maiúsculas)
    return rotulo[:1].upper() + rotulo[1:]


def campos_para_a_empresa(conexao) -> list[str]:
    """Os campos que a consulta de funcionários mostra: TODOS os campos do parâmetro vigente, na ordem do layout.

    ADR-111: a empresa vê todos os dados que ela mesma enviou, para conferir o que a IA identificou em cada campo,
    sem uma lista fixa que esconda alguns (nome da mãe, PIS, documento...).
    Ex.: ["matricula", "nome_completo", "cpf", ...] (45 campos no layout v1).
    """
    _, campos_do_layout = parametros.layout_ativo(conexao)
    nomes = []
    for campo in campos_do_layout:
        nomes.append(campo.campo)
    return nomes


def colunas_da_consulta(conexao) -> list[dict]:
    """As colunas da grade de consulta de funcionários: uma por campo do parâmetro vigente (ADR-111).

    Recebe: conexao. Devolve: [{campo, rotulo, grupo, tipo, obrigatorio, descricao}, ...], na ordem do layout.
    "obrigatorio" marca a coluna na tela; "descricao" é o texto que o banco escreveu no parâmetro (aparece ao passar o
    mouse no cabeçalho); "tipo" diz como mostrar o valor (data, dinheiro...).
    """
    _, campos_do_layout = parametros.layout_ativo(conexao)
    colunas = []
    for campo in campos_do_layout:
        colunas.append({"campo": campo.campo, "rotulo": rotulo_do_campo(campo.campo), "grupo": campo.grupo,
                        "tipo": campo.tipo.value, "obrigatorio": campo.obrigatorio, "descricao": campo.descricao})
    return colunas


def quando_e_quem_enviou(conexao, empresa_id: str) -> dict:
    """Para cada envio da empresa: quando foi criado e por qual usuário.

    Recebe: conexao; empresa_id. Devolve: {processamento_id: (criado_em, criado_por)}.
    O retrato do envio (FileProfile) não guarda essas duas informações; elas ficam em colunas próprias.
    """
    # Garante que a tabela de processamentos existe
    processamentos._preparar(conexao)
    # Só os envios desta empresa
    consulta = conexao.execute(
        "SELECT processamento_id, criado_em, criado_por FROM processamentos WHERE empresa_id = ?", (empresa_id,))
    # Monta o dicionário
    quando_e_quem = {}
    for processamento_id, criado_em, criado_por in consulta:
        quando_e_quem[processamento_id] = (criado_em, criado_por)
    return quando_e_quem


def _datas_das_etapas(conexao, perfil) -> tuple[dict, dict]:
    """A data de cada tipo de evento que marca uma etapa, e a última devolução do banco, lidas na trilha de auditoria.

    Recebe: conexao; perfil (o retrato do envio). Devolve: (datas, devolucao):
      - datas: {tipo do evento: quando}. Vale a PRIMEIRA vez de cada evento, menos o "Enviado ao banco", que mostra a
        ÚLTIMA vez (o envio pode ir de novo depois de uma devolução, ADR-121);
      - devolucao: {"quando", "pessoas", "por_pessoa"} da devolução do banco que ainda espera a empresa mandar de
        novo, ou {} se não há.
    No envio de devolução, as etapas de antes do banco (arquivo, IA, conferência, envio) vêm do envio de origem: as
    pessoas passaram por elas lá.
    """
    datas = {}
    # O envio de origem primeiro (as etapas de antes do banco), depois o próprio envio
    envios_da_historia = []
    if perfil.envio_de_origem:
        envios_da_historia.append((perfil.envio_de_origem, False))
    envios_da_historia.append((perfil.processamento_id, True))
    devolucao = {}
    for processamento_id, e_o_proprio in envios_da_historia:
        for evento in auditoria.eventos(conexao, processamento_id):
            tipo = evento["tipo"]
            # Do envio de origem, só as etapas de antes da avaliação do banco
            if not e_o_proprio and tipo not in TIPOS_ANTES_DO_BANCO:
                continue
            # O envio ao banco: a última vez vale; um envio novo atende a devolução que estava em aberto
            if tipo == "ENVIADO_AO_BANCO":
                datas[tipo] = evento["criado_em"]
                if e_o_proprio:
                    devolucao = {}
                continue
            # A devolução do próprio envio fica em aberto até ele ir de novo ao banco
            if tipo == "DEVOLVIDO_PELO_BANCO" and e_o_proprio:
                devolucao = {"quando": evento["criado_em"], "pessoas": evento["detalhe"].get("pessoas"),
                             "por_pessoa": bool(evento["detalhe"].get("envio_de_origem"))}
                continue
            # As outras etapas: a primeira vez vale
            if tipo not in datas:
                datas[tipo] = evento["criado_em"]
    return datas, devolucao


def _texto_da_devolucao(devolucao: dict) -> str:
    """O que a etapa de aprovação diz quando o banco devolveu. Ex.: "Devolvido: 2 pessoas" ou "Devolvido: o envio
    inteiro"."""
    if devolucao["por_pessoa"]:
        return "Devolvido: " + idas_e_voltas.texto_de_pessoas(devolucao["pessoas"] or 0)
    return "Devolvido: o envio inteiro"


def linha_do_tempo(conexao, processamento_id: str) -> list[dict]:
    """As etapas de um envio, com a data em que cada uma aconteceu (tirada da trilha de auditoria).

    Recebe: conexao; processamento_id (de um envio que já se sabe ser da empresa).
    Devolve: uma lista de {nome, feito, atual, quando, detalhe, parcial, devolvido}, uma por etapa. "atual" marca a
    primeira etapa ainda não feita (onde o envio está parado agora). "detalhe" e "parcial" valem na última ("22 de 35
    contas (62%)") e na aprovação de um envio que o banco aprovou em parte ("33 de 35 aprovadas · 2 devolvidas",
    ADR-121). "devolvido" é True só na aprovação, enquanto a devolução do banco espera a empresa mandar de novo: a
    linha continua andando para a frente, e a etapa diz "Devolvido: 2 pessoas" (a história inteira fica nas "Idas e
    voltas com o banco", services/idas_e_voltas.py). Exemplo: [{"nome": "Arquivo carregado", "feito": True,
    "atual": False, "quando": "2026-09-24T10:12:00+00:00", "detalhe": None, "parcial": False, "devolvido": False},
    ..., {"nome": "Contas abertas", ...}].
    """
    perfil = processamentos.obter(conexao, processamento_id)
    datas, devolucao = _datas_das_etapas(conexao, perfil)
    # Monta as etapas
    etapas = []
    ja_marcou_a_atual = False
    for nome_da_etapa, tipo_do_evento in ETAPAS_DA_LINHA_DO_TEMPO:
        # Envio cadastrado antes de a avaliação do banco existir: não passou pelo banco, então essa etapa não aparece
        if tipo_do_evento == "ENVIADO_AO_BANCO" and tipo_do_evento not in datas and "HOMOLOGADO" in datas:
            continue
        # A data da etapa (ou None, se ainda não aconteceu)
        quando = datas.get(tipo_do_evento)
        etapa = {"nome": nome_da_etapa, "feito": quando is not None, "atual": False, "quando": quando,
                 "detalhe": None, "parcial": False, "devolvido": False}
        # A aprovação: devolvida pelo banco (esperando a empresa) ou aprovada em parte (ADR-121)
        if tipo_do_evento == "HOMOLOGADO":
            _completar_a_aprovacao(conexao, perfil, etapa, devolucao)
        # A atual é a primeira que ainda não foi feita
        if not etapa["feito"] and not ja_marcou_a_atual:
            etapa["atual"] = True
            ja_marcou_a_atual = True
        etapas.append(etapa)
    # A última etapa: as contas que o arquivo semanal do banco já trouxe para os funcionários deste envio
    etapa_das_contas = _etapa_das_contas(conexao, processamento_id, ja_marcou_a_atual)
    etapa_das_contas["devolvido"] = False
    etapas.append(etapa_das_contas)
    # Devolve as etapas na ordem
    return etapas


def _completar_a_aprovacao(conexao, perfil, etapa: dict, devolucao: dict) -> None:
    """Acrescenta à etapa "Aprovação das contas enviadas" a devolução do banco ou a aprovação em parte (ADR-121).

    Recebe: conexao; perfil (o envio); etapa (o dicionário da etapa, que é mudado aqui); devolucao (de
    _datas_das_etapas). Devolve: nada.
    """
    # Devolvido e ainda não mandado de novo: a etapa fica por fazer, em laranja, com a data da devolução
    if devolucao and not etapa["feito"]:
        etapa["devolvido"] = True
        etapa["quando"] = devolucao["quando"]
        etapa["detalhe"] = _texto_da_devolucao(devolucao)
        return
    # Aprovado em parte: quantas pessoas já foram aprovadas, somando as rodadas
    if etapa["feito"]:
        conta = idas_e_voltas.aprovacao_em_rodadas(conexao, perfil)
        if conta is not None:
            etapa["detalhe"] = conta["detalhe"]
            etapa["parcial"] = conta["parcial"]


def _etapa_das_contas(conexao, processamento_id: str, ja_marcou_a_atual: bool) -> dict:
    """A etapa "Contas abertas": feita quando o arquivo de contas abertas do banco trouxe a conta de alguém do envio.

    Recebe: conexao; processamento_id; ja_marcou_a_atual (se uma etapa anterior já é a atual).
    Devolve: {nome, feito, atual, quando, detalhe, parcial}. "quando" é a primeira baixa de conta de alguém do envio,
    "detalhe" diz quantos já têm conta, com o percentual (ex.: "22 de 35 contas (62%)"), e "parcial" é True enquanto
    nem todos têm conta. Nada é suposto: sem o arquivo do banco, a etapa fica por fazer e sem número (ADR-113).
    """
    # Importado aqui dentro porque contas_abertas também usa este arquivo (importar lá em cima faria um laço)
    from services import contas_abertas
    # Garante que as tabelas existem (numa aplicação nova, ninguém foi cadastrado nem teve conta aberta)
    processamentos._preparar(conexao)
    contas_abertas._preparar(conexao)
    # Os funcionários cadastrados por este envio, pelo CPF só com dígitos (e a empresa deles)
    cpfs_do_envio = set()
    empresa_do_envio = None
    for empresa_id, cpf in conexao.execute(
            "SELECT empresa_id, cpf FROM funcionarios_homologados WHERE processamento_id = ?", (processamento_id,)):
        cpfs_do_envio.add(contas_abertas._somente_digitos(cpf))
        empresa_do_envio = empresa_id
    # Quantos deles já têm conta e a data da primeira baixa
    com_conta = 0
    primeira_baixa = None
    # Só as contas com o tipo: a mesma regra da conta única (contas_abertas.retorno_da_empresa)
    for cpf, baixa_em in conexao.execute("SELECT cpf, baixa_em FROM contas_abertas WHERE empresa_id = ? "
                                         "AND tipo_conta IS NOT NULL", (empresa_do_envio,)):
        # Só conta quem veio neste envio
        if cpf not in cpfs_do_envio:
            continue
        com_conta = com_conta + 1
        # Os horários são texto no padrão internacional: o menor texto é o mais antigo
        if primeira_baixa is None or baixa_em < primeira_baixa:
            primeira_baixa = baixa_em
    # Feita quando chegou a conta de pelo menos um funcionário do envio
    feito = com_conta > 0
    # Parcial: já chegou alguma conta, mas nem todos do envio têm conta (a tela pinta de verde clarinho)
    parcial = feito and com_conta < len(cpfs_do_envio)
    detalhe = None
    if feito:
        # "22 de 35 contas (62%)": quantos do envio já têm conta, de quantos foram cadastrados. O percentual é
        # arredondado para baixo, para nunca mostrar 100% antes de todos terem conta (34 de 35 = 97%)
        percentual = (100 * com_conta) // len(cpfs_do_envio)
        detalhe = str(com_conta) + " de " + str(len(cpfs_do_envio)) + " contas (" + str(percentual) + "%)"
    # A atual, se nenhuma etapa anterior ficou parada
    atual = not feito and not ja_marcou_a_atual
    return {"nome": ETAPA_DAS_CONTAS, "feito": feito, "atual": atual, "quando": primeira_baixa, "detalhe": detalhe,
            "parcial": parcial}


def linha_do_tempo_do_envio(conexao, empresa_id: str, processamento_id: str) -> list[dict]:
    """A linha do tempo de um envio DA EMPRESA DA SESSÃO, para o histórico da ficha do funcionário.

    Recebe: conexao; empresa_id (da sessão); o envio. Devolve: as etapas (ver linha_do_tempo).
    Levanta KeyError se o envio não é da empresa (sem dizer se ele existe em outra).
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    return linha_do_tempo(conexao, processamento_id)


def quem_e_quando_descartou(conexao, processamento_id: str) -> dict | None:
    """Quem descartou o envio e quando (da trilha de auditoria), ou None se a empresa não descartou.

    Recebe: conexao; processamento_id. Devolve: {"por": login, "quando": data e hora} ou None.
    Exemplo: {"por": "rh.aurora", "quando": "2026-09-27T10:12:00+00:00"}.
    """
    for evento in auditoria.eventos(conexao, processamento_id):
        # O descarte é registrado uma vez só, pelo services/cadastro.descartar
        if evento["tipo"] == "DESCARTADO_PELA_EMPRESA":
            return {"por": evento["detalhe"].get("por"), "quando": evento["criado_em"]}
    return None


def motivo_da_devolucao(conexao, processamento_id: str) -> str | None:
    """O motivo da última devolução do banco (o recado para a empresa), ou None se o envio nunca foi devolvido.

    Recebe: conexao; processamento_id. Devolve: o texto do motivo, ou None.
    """
    motivo = None
    for evento in auditoria.eventos(conexao, processamento_id):
        # Os eventos vêm em ordem: fica o último
        if evento["tipo"] == "DEVOLVIDO_PELO_BANCO":
            motivo = evento["detalhe"].get("motivo")
    return motivo


def envios_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os envios da empresa, do mais recente para o mais antigo, com a situação em linguagem simples.

    Recebe: conexao; empresa_id (da sessão). Devolve: lista de dicionários, um por envio, com
    processamento_id, nome_arquivo (com "(v1)", "(v2)" quando o nome se repete), tipo_carga (INICIAL ou INCLUSAO),
    tipo ("Carga inicial" ou "Inclusão"), enviado_em,
    enviado_por, linhas, situacao, cadastrados (só nos homologados), linha_do_tempo (as etapas com as datas),
    motivo_da_devolucao (só nos devolvidos pelo banco) e descarte ({por, quando}, só nos descartados pela empresa).
    """
    # Quando e por quem cada envio foi feito
    quando_e_quem = quando_e_quem_enviou(conexao, empresa_id)
    # O nome de cada arquivo como a tela mostra (arquivos diferentes com o mesmo nome ganham "(v1)", "(v2)")
    nomes_dos_arquivos = processamentos.nomes_na_tela(conexao, empresa_id)
    # Os retratos dos envios da empresa (já vêm do mais recente para o mais antigo), cada um em linguagem simples
    envios = []
    for perfil in processamentos.listar(conexao, empresa_id):
        envios.append(_envio_para_a_tela(conexao, perfil, quando_e_quem, nomes_dos_arquivos))
    return envios


# A maior página de envios que a tela pode pedir de uma vez
ENVIOS_POR_PAGINA_NO_MAXIMO = 50


def pagina_de_envios(conexao, empresa_id: str, inicio: int = 0, quantidade: int = 5) -> dict:
    """Uma página dos envios da empresa, para "Mostrar mais envios" (uma empresa pode ter centenas).

    Recebe: conexao; empresa_id (da sessão); inicio (quantos pular, a partir de 0); quantidade (1 a 50).
    Devolve: {envios: [os da página, no formato de envios_da_empresa], total: quantos a empresa tem, inicio,
    quantidade}. Só os envios da página são montados (a linha do tempo de cada um é a parte cara).
    Levanta ValueError com início negativo ou quantidade fora de 1 a 50.
    Exemplo: 12 envios, inicio=10, quantidade=5 → os 2 últimos e total=12.
    """
    if inicio < 0 or quantidade < 1 or quantidade > ENVIOS_POR_PAGINA_NO_MAXIMO:
        raise ValueError("Peça de 1 a " + str(ENVIOS_POR_PAGINA_NO_MAXIMO) + " envios, a partir do início 0.")
    quando_e_quem = quando_e_quem_enviou(conexao, empresa_id)
    # O nome de cada arquivo como a tela mostra (arquivos diferentes com o mesmo nome ganham "(v1)", "(v2)")
    nomes_dos_arquivos = processamentos.nomes_na_tela(conexao, empresa_id)
    envios = []
    for perfil in processamentos.listar_pagina(conexao, empresa_id, inicio, quantidade):
        envios.append(_envio_para_a_tela(conexao, perfil, quando_e_quem, nomes_dos_arquivos))
    return {"envios": envios, "total": processamentos.contar(conexao, empresa_id), "inicio": inicio,
            "quantidade": quantidade}


def _envio_para_a_tela(conexao, perfil, quando_e_quem: dict, nomes_dos_arquivos: dict) -> dict:
    """Um envio em linguagem simples, com o nome do arquivo (sem ele, a empresa não
    reconhece os próprios envios, e o "(v1)" de um arquivo com nome repetido não apareceria em lugar nenhum).

    Recebe: conexao; perfil (o retrato do envio); quando_e_quem ({processamento_id: (criado_em, criado_por)});
    nomes_dos_arquivos (processamentos.nomes_na_tela: o nome com a versão quando ele se repete).
    Devolve: o dicionário descrito em envios_da_empresa.
    """
    enviado_em, enviado_por = quando_e_quem[perfil.processamento_id]
    # Quantos foram cadastrados: só existe depois da homologação
    cadastrados = None
    if perfil.status == EstadoProcessamento.HOMOLOGADO:
        homologado = homologacao.obter(conexao, perfil.processamento_id)
        cadastrados = homologado["relatorio"]["registros_homologados"]
    return {
        "processamento_id": perfil.processamento_id,
        # O nome do arquivo, com a versão quando a empresa enviou outro arquivo com o mesmo nome
        # (ex.: "aurora.xlsx (v1)")
        "nome_arquivo": nomes_dos_arquivos[perfil.processamento_id],
        "tipo_carga": perfil.tipo_carga.value,
        "tipo": TIPO_PARA_A_EMPRESA[perfil.tipo_carga],
        "enviado_em": enviado_em,
        "enviado_por": enviado_por,
        "linhas": perfil.n_linhas,
        "situacao": SITUACAO_PARA_A_EMPRESA[perfil.status],
        "cadastrados": cadastrados,
        "linha_do_tempo": linha_do_tempo(conexao, perfil.processamento_id),
        "motivo_da_devolucao": _motivo_se_devolvido(conexao, perfil),
        "descarte": quem_e_quando_descartou(conexao, perfil.processamento_id),
        # O envio de devolução diz de onde veio (ADR-121); nos outros, None
        "origem": _origem_para_a_tela(conexao, perfil),
        # As idas e voltas com o banco (vazia quando o banco nunca devolveu nada)
        "idas_e_voltas": idas_e_voltas.idas_e_voltas(conexao, perfil.processamento_id),
    }


def _origem_para_a_tela(conexao, perfil) -> dict | None:
    """De onde veio um envio de devolução: {processamento_id, enviado_em, texto}, ou None nos outros envios.

    Exemplo: {"processamento_id": "94a3322a4416", "enviado_em": "2026-09-28T13:10:00+00:00",
    "texto": "Devolução do envio de 28/09 (2 pessoas)"}.
    """
    if not perfil.envio_de_origem:
        return None
    enviado_em = conexao.execute("SELECT criado_em FROM processamentos WHERE processamento_id = ?",
                                 (perfil.envio_de_origem,)).fetchone()[0]
    return {"processamento_id": perfil.envio_de_origem, "enviado_em": enviado_em,
            "texto": idas_e_voltas.texto_da_origem(conexao, perfil)}


def _motivo_se_devolvido(conexao, perfil) -> str | None:
    """O motivo da devolução do envio inteiro, enquanto a empresa ainda não mandou de novo (depois, o recado já foi
    atendido). Continua à vista mesmo depois de a empresa começar a corrigir (ADR-121).

    O envio de devolução (só algumas pessoas) não tem motivo aqui: o pedido do banco está na pendência de cada pessoa.
    """
    if perfil.envio_de_origem:
        return None
    _, devolucao = _datas_das_etapas(conexao, perfil)
    if not devolucao:
        return None
    return motivo_da_devolucao(conexao, perfil.processamento_id)


def _registros_do_arquivo_final(conteudo: bytes) -> list[dict]:
    """Lê o CSV final de uma homologação (separador ";", UTF-8) e devolve as linhas como dicionários.

    Recebe: conteudo — os bytes do arquivo. Devolve: uma lista de {campo: valor}.
    """
    # O texto do arquivo
    texto = conteudo.decode("utf-8")
    # O leitor de CSV usa a primeira linha (os nomes dos campos) como chaves
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    # Transforma em lista, anotando a posição de cada pessoa no arquivo (1 = primeira)
    registros = []
    posicao = 0
    for registro in leitor:
        posicao = posicao + 1
        registro["_posicao"] = posicao
        registros.append(registro)
    return registros


def _tirar_apostrofo_de_protecao(valor: str) -> str:
    """Tira o apóstrofo que a homologação põe na frente de textos com cara de fórmula (proteção do Excel).

    Recebe: valor. Devolve: o valor sem o apóstrofo do começo. Exemplo: "'=SOMA(1)" → "=SOMA(1)".
    Na tela o texto aparece como texto (nunca é executado), então o apóstrofo só atrapalharia a leitura.
    """
    # Só o apóstrofo do começo sai
    if valor.startswith("'"):
        return valor[1:]
    return valor


def _cadastrados_por_cpf(conexao, empresa_id: str) -> dict:
    """Os cadastrados da empresa pelo CPF inteiro: {cpf: pessoa}, a pessoa com o CPF formatado.

    O CPF inteiro fica só na chave (para funcionarios_da_empresa e a consulta de todos não repetirem a pessoa); ele
    nunca vai dentro da pessoa, que é o que sai para a tela.
    """
    # Importado aqui dentro porque contas_abertas também usa este arquivo (importar lá em cima faria um laço)
    from services import contas_abertas
    # Quando e por quem cada envio foi feito
    quando_e_quem = quando_e_quem_enviou(conexao, empresa_id)
    # A conta de quem já abriu, pelo CPF só com dígitos (o arquivo semanal do banco)
    contas_por_cpf = contas_abertas.contas_da_empresa(conexao, empresa_id)
    # Pessoas já vistas, pelo CPF (para não repetir)
    pessoas_por_cpf = {}
    # Todos os campos do parâmetro vigente (ADR-111)
    nomes_dos_campos = campos_para_a_empresa(conexao)
    # As informações sem rótulo de cada cadastrado, pelo CPF (guardadas no cadastro; ADR-143, Parte 1)
    sem_rotulo_por_cpf = informacoes_sem_rotulo.do_cadastro_da_empresa(conexao, empresa_id)
    # Os envios da empresa, do mais antigo para o mais recente (o mais recente sobrescreve)
    envios = processamentos.listar(conexao, empresa_id)
    envios.reverse()
    for perfil in envios:
        # Só envios homologados têm arquivo final
        if perfil.status != EstadoProcessamento.HOMOLOGADO:
            continue
        # O arquivo final do envio
        homologado = homologacao.obter(conexao, perfil.processamento_id)
        # Quando e quem
        enviado_em, enviado_por = quando_e_quem[perfil.processamento_id]
        # Uma pessoa por linha do arquivo final
        for registro in _registros_do_arquivo_final(homologado["arquivo"]):
            # Todos os campos do parâmetro vigente (ADR-111); campo que não veio no arquivo fica vazio
            pessoa = {}
            for campo in nomes_dos_campos:
                pessoa[campo] = _tirar_apostrofo_de_protecao(registro.get(campo, ""))
            # O CPF só com os dígitos é a chave (para não repetir a pessoa); na lista, vai formatado
            cpf_completo = pessoa["cpf"]
            pessoa["cpf"] = formatar_cpf(cpf_completo)
            # Quem incluiu e quando (a rastreabilidade que a tela mostra na coluna "Incluído")
            pessoa["incluido_em"] = enviado_em
            pessoa["incluido_por"] = enviado_por
            # Em que tipo de envio a pessoa entrou ("Carga inicial" ou "Inclusão"), para o histórico da ficha
            pessoa["tipo_de_envio"] = TIPO_PARA_A_EMPRESA[perfil.tipo_carga]
            # A conta no banco (vazia enquanto a pessoa não abriu): é onde a empresa paga o salário (ADR-102)
            conta = contas_por_cpf.get(_somente_digitos(cpf_completo), CONTA_AINDA_NAO_ABERTA)
            pessoa["conta_aberta_em"] = conta["data_abertura"]
            pessoa["codigo_banco"] = conta["codigo_banco"]
            pessoa["agencia"] = conta["agencia"]
            pessoa["conta"] = conta["conta"]
            # "Conta aberta" (conta nova) ou "Já é correntista" (já era cliente); vazio enquanto o banco não informou
            pessoa["situacao_da_conta"] = conta["situacao_na_empresa"]
            # O identificador da pessoa: o envio e a posição dela no arquivo final (ex.: "94a3322a4416.7").
            # É com ele que a tela pede a ficha completa e o download, sem nunca mandar o CPF pelo endereço
            posicao_no_arquivo = registro["_posicao"]
            pessoa["id"] = perfil.processamento_id + "." + str(posicao_no_arquivo)
            # O envio em que a pessoa entrou (a ficha busca a linha do tempo dele para o histórico)
            pessoa["envio"] = perfil.processamento_id
            # O que a IA achou sem ter certeza do campo: vai para o detalhe, nunca para a grade (ADR-143, Parte 1)
            guardadas_da_pessoa = sem_rotulo_por_cpf.get(cpf_completo, [])
            pessoa["informacoes_sem_rotulo"] = informacoes_sem_rotulo.para_a_tela(guardadas_da_pessoa)
            # Guarda pela chave do CPF
            pessoas_por_cpf[cpf_completo] = pessoa
    return pessoas_por_cpf


def funcionarios_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os funcionários já cadastrados (homologados) da empresa, com o CPF formatado e quem os incluiu.

    Recebe: conexao; empresa_id (da sessão).
    Devolve: lista de dicionários com todos os campos do parâmetro vigente (o cpf formatado), mais incluido_em,
    incluido_por, tipo_de_envio, id (o identificador para pedir a ficha e o download) e informacoes_sem_rotulo (o que a
    IA achou sem ter certeza do campo, só para o detalhe; ADR-143, Parte 1). Ordenada por nome.
    Uma pessoa que aparece em dois envios (ex.: carga e inclusão) conta uma vez só: vale o envio mais recente.
    """
    funcionarios = list(_cadastrados_por_cpf(conexao, empresa_id).values())
    funcionarios.sort(key=nome_para_ordenar)
    return funcionarios


# As situações de uma pessoa na consulta de funcionários, na ordem da jornada: Pendente → Em análise → Cadastrado →
# Conta aberta ou Já é correntista (a última: o banco mandou, no arquivo de contas, a conta da pessoa e o tipo; ADR-113
# e ADR-123). Os textos das duas últimas vêm de services/contas_abertas.py (SITUACAO_NA_EMPRESA_DO_TIPO).
SITUACAO_CADASTRADO, SITUACAO_EM_ANALISE, SITUACAO_PENDENTE = "Cadastrado", "Em análise", "Pendente"
# A pessoa sem nenhuma pendência (a IA achou tudo), num envio que a empresa ainda não mandou ao banco porque está
# corrigindo as pendências de outras pessoas (ADR-114)
SITUACAO_AGUARDANDO_ENVIO = "Aguardando envio"
# O que fica entre o envio e a linha no identificador de download de quem ainda não foi cadastrado (ADR-155).
# Ex.: "94a3322a4416" + ".linha" + "7" → "94a3322a4416.linha7"
MARCA_DA_LINHA_NO_IDENTIFICADOR = ".linha"


def situacao_do_cadastrado(pessoa: dict) -> str:
    """A situação de quem já foi cadastrado: a que o banco informou no arquivo de contas; senão, "Cadastrado".

    Ex.: {"situacao_da_conta": "Já é correntista", ...} → "Já é correntista"; {"situacao_da_conta": "", ...} →
    "Cadastrado". "Conta aberta" é a conta nova (tipo 1); "Já é correntista", quem já era cliente (tipo 2).
    """
    if pessoa.get("situacao_da_conta"):
        return pessoa["situacao_da_conta"]
    return SITUACAO_CADASTRADO
ESTADOS_PENDENTES_NA_CONSULTA = (EstadoProcessamento.NORMALIZADO, EstadoProcessamento.VALIDACAO_PENDENTE,
                                 EstadoProcessamento.DEVOLVIDO)


def todos_os_funcionarios_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Todos os funcionários da empresa: cadastrados, em análise pelo banco e pendentes (item 106 da seção 10).

    Recebe: conexao; empresa_id (da sessão). Devolve: a lista de funcionarios_da_empresa (os cadastrados, com
    situacao "Cadastrado" e o id para a ficha e o download) mais as pessoas dos envios ainda não cadastrados:
      - "Em análise": o envio foi mandado ao banco e espera a avaliação;
      - "Pendente": o envio ainda está com a empresa (ou foi devolvido pelo banco), com a primeira pendência da
        pessoa em "pendencia";
      - "Aguardando envio": a pessoa do envio que ainda está com a empresa, mas sem nenhuma pendência dela (o envio
        espera as correções das outras pessoas para ir ao banco).
    Essas pessoas vêm sem id (a ficha é só de quem já foi cadastrado). Todas, cadastradas ou não, trazem o
    id_para_baixar: o "Baixar lista" manda o de cada pessoa que aparece na grade e o arquivo sai igual a ela (ADR-155).
    A mesma pessoa (pelo CPF) aparece uma vez só, na situação mais adiantada. Envio descartado não entra.
    """
    funcionarios = []
    cpfs_vistos = set()
    # Os cadastrados, pelo CPF inteiro (a chave só serve para não repetir a pessoa)
    for cpf_completo, pessoa in _cadastrados_por_cpf(conexao, empresa_id).items():
        # Cadastrado, ou Conta aberta / Já é correntista se o banco já mandou a conta da pessoa (a última situação)
        pessoa["situacao"] = situacao_do_cadastrado(pessoa)
        pessoa["pendencia"] = None
        # O cadastrado é baixado pelo mesmo id da ficha (envio.posição no arquivo final)
        pessoa["id_para_baixar"] = pessoa["id"]
        funcionarios.append(pessoa)
        cpfs_vistos.add(cpf_completo)
    quando_e_quem = quando_e_quem_enviou(conexao, empresa_id)
    # Os envios em análise primeiro (situação mais adiantada), depois os pendentes; o mais recente de cada um primeiro
    for estados, situacao in (((EstadoProcessamento.AGUARDANDO_BANCO,), SITUACAO_EM_ANALISE),
                              (ESTADOS_PENDENTES_NA_CONSULTA, SITUACAO_PENDENTE)):
        for perfil in processamentos.listar(conexao, empresa_id):
            if perfil.status not in estados:
                continue
            for pessoa in _pessoas_do_envio_em_andamento(conexao, perfil, quando_e_quem[perfil.processamento_id]):
                cpf_completo = pessoa.pop("_cpf_completo")
                # A pessoa já apareceu numa situação mais adiantada (ou em outro envio): não repete
                if cpf_completo and cpf_completo in cpfs_vistos:
                    continue
                if cpf_completo:
                    cpfs_vistos.add(cpf_completo)
                pessoa["situacao"] = situacao
                if situacao == SITUACAO_EM_ANALISE:
                    pessoa["pendencia"] = None
                # No envio com a empresa, quem não tem pendência própria só espera o envio ir ao banco
                if situacao == SITUACAO_PENDENTE and not pessoa["pendencia"]:
                    pessoa["situacao"] = SITUACAO_AGUARDANDO_ENVIO
                funcionarios.append(pessoa)
    funcionarios.sort(key=nome_para_ordenar)
    return funcionarios


def _pessoas_do_envio_em_andamento(conexao, perfil, quando_e_quem: tuple) -> list[dict]:
    """As pessoas de um envio ainda não cadastrado, como a consulta mostra (CPF formatado, sem id).

    Recebe: conexao; perfil (o envio); quando_e_quem ((criado_em, criado_por) do envio). Devolve: [pessoa], cada uma
    com _cpf_completo (só para não repetir a pessoa; sai antes de ir para a tela), a primeira pendência dela, as
    informações sem rótulo (ADR-143, Parte 1) e o id_para_baixar (o envio e a linha do arquivo; ADR-155).
    Envio ainda sem padronização (antes do aceite das colunas) não tem pessoas para mostrar.
    """
    try:
        registros = correcoes.dados_atuais(conexao, perfil.processamento_id).registros
    except ValueError:
        return []
    pendencia_por_linha = _primeira_pendencia_por_linha(conexao, perfil.processamento_id)
    pessoas = []
    # Todos os campos do parâmetro vigente (ADR-111)
    nomes_dos_campos = campos_para_a_empresa(conexao)
    for registro in registros:
        pessoa = {}
        # Os campos do parâmetro, em texto (campo vazio vira texto vazio)
        for campo in nomes_dos_campos:
            valor = registro.get(campo)
            pessoa[campo] = ""
            if valor is not None:
                pessoa[campo] = str(valor)
        # O CPF só com os dígitos, para não repetir a pessoa (sai antes de ir para a tela); na lista, formatado
        pessoa["_cpf_completo"] = pessoa["cpf"]
        if pessoa["cpf"]:
            pessoa["cpf"] = formatar_cpf(pessoa["cpf"])
        pessoa["incluido_em"], pessoa["incluido_por"] = quando_e_quem
        pessoa["tipo_de_envio"] = TIPO_PARA_A_EMPRESA[perfil.tipo_carga]
        pessoa["id"] = None
        # O identificador para o download: o envio e a linha do arquivo (ex.: "94a3322a4416.linha7"). A marca "linha"
        # nunca se confunde com o id de um cadastrado (envio.posição no arquivo final): depois do cadastro, o
        # identificador antigo não acha ninguém, em vez de trazer outra pessoa
        pessoa["id_para_baixar"] = perfil.processamento_id + MARCA_DA_LINHA_NO_IDENTIFICADOR + str(registro["_linha"])
        pessoa["envio"] = perfil.processamento_id
        # A primeira pendência da pessoa; sem pendência, None (ela vai para "Aguardando envio", ADR-114)
        pessoa["pendencia"] = pendencia_por_linha.get(registro["_linha"])
        # O que a IA achou sem ter certeza do campo: vai para o detalhe, nunca para a grade (ADR-143, Parte 1)
        pessoa["informacoes_sem_rotulo"] = informacoes_sem_rotulo.do_registro_para_a_tela(registro)
        pessoas.append(pessoa)
    return pessoas


def _primeira_pendencia_por_linha(conexao, processamento_id: str) -> dict:
    """{linha do arquivo: a primeira pendência dela, em texto}, das pendências que pedem ação (bloqueante ou alerta
    ainda não confirmado). Exemplo: {5: "CPF com dígito verificador inválido."}.
    """
    relatorio = validador.obter(conexao, processamento_id)
    pendencias = {}
    if relatorio is None:
        return pendencias
    for achado in relatorio.achados:
        # Pede ação: bloqueante, ou alerta que a empresa ainda não confirmou
        alerta_em_aberto = achado.severidade == validador.ALERTA and not achado.resolvido
        pede_acao = achado.severidade == validador.BLOQUEANTE or alerta_em_aberto
        # Só a primeira pendência de cada linha
        if pede_acao and achado.linha is not None and achado.linha not in pendencias:
            pendencias[achado.linha] = achado.mensagem
    return pendencias


def nome_para_ordenar(pessoa: dict) -> str:
    """O nome da pessoa em minúsculas, usado para ordenar a lista. Exemplo: {"nome_completo": "Ana"} → "ana"."""
    return pessoa["nome_completo"].lower()


def nome_de_cada_registro(conexao, processamento_id: str) -> dict:
    """O nome de cada funcionário do envio, pela posição no arquivo (1 = primeiro), com as correções já aplicadas.

    Recebe: conexao; processamento_id. Devolve: {posição: nome}. Exemplo: {1: "Ana Souza", 2: "Bruno Alves"}.
    """
    # Os dados atuais do envio (padronizados e com as correções aprovadas)
    dados = correcoes.dados_atuais(conexao, processamento_id)
    # Posição → nome
    nomes = {}
    posicao = 0
    for registro in dados.registros:
        posicao = posicao + 1
        nomes[posicao] = registro.get("nome_completo") or ""
    return nomes


# As regras do Validador que são dúvida de formato de uma coluna inteira (resolvem-se decidindo o formato)
REGRAS_DE_FORMATO = ("DATA_AMBIGUA", "ZEROS_A_ESQUERDA")


def coluna_da_duvida_de_formato(conexao, processamento_id: str, regra_id: str, mensagem: str) -> str | None:
    """A coluna de uma dúvida de formato (datas ambíguas ou zeros da matrícula), ou None nas outras pendências.

    Recebe: conexao; processamento_id; a regra e a mensagem do achado do Validador. Devolve: o nome da coluna.
    Por quê: a dúvida é da coluna inteira; a escolha do formato vale para ela (e não para uma linha só).
    """
    if regra_id not in REGRAS_DE_FORMATO:
        return None
    normalizacao = normalizador.obter(conexao, processamento_id)
    if normalizacao is None:
        return None
    for pendencia in normalizacao.pendencias_de_coluna:
        # O Validador escreve a mensagem como "Coluna X: ..." (services/validador.py)
        if mensagem == "Coluna " + pendencia["coluna"] + ": " + pendencia["mensagem"]:
            return pendencia["coluna"]
    return None


# ------------- O valor lido, as sugestões e a pergunta de cada pendência (pendências por conversa) -------------

# Quantos valores da coluna aparecem como exemplo numa dúvida de formato (ex.: as datas que não dizem dia ou mês)
EXEMPLOS_DA_COLUNA = 3


def _data_brasileira(texto: str) -> str:
    """A data padronizada no jeito brasileiro: "2026-09-12" → "12/09/2026". Outro formato volta como veio."""
    pedacos = texto.split("-")
    # Só a data padronizada (AAAA-MM-DD) é virada
    if len(pedacos) == 3 and len(pedacos[0]) == 4 and texto.replace("-", "").isdigit():
        return pedacos[2] + "/" + pedacos[1] + "/" + pedacos[0]
    return texto


def _dinheiro_brasileiro(texto: str) -> str:
    """A renda padronizada em reais: "5200.00" → "R$ 5.200,00". Texto que não é número volta como veio."""
    from decimal import Decimal, InvalidOperation
    from services.formatacao import em_reais
    try:
        return em_reais(Decimal(texto))
    except InvalidOperation:
        # Ex.: o valor que o Normalizador não reconheceu ("cinco mil"): mostra como a empresa escreveu
        return texto


def valor_lido_para_a_tela(campo: str | None, valor: str | None) -> str | None:
    """O valor que gerou a pendência, como a empresa o reconhece, ou None quando o arquivo veio sem ele.

    Recebe: o campo do layout e o valor guardado no achado do Validador (ADR-101: o valor real).
    Exemplos: ("cpf", "12345678900") → "123.456.789-00"; ("data_nascimento", "2030-01-05") → "05/01/2030";
    ("valor_renda", "5200.00") → "R$ 5.200,00"; ("cargo", None) → None.
    """
    if valor in (None, ""):
        return None
    if campo == "cpf":
        return formatar_cpf(valor)
    if campo and campo.startswith("data_"):
        return _data_brasileira(valor)
    if campo == "valor_renda":
        return _dinheiro_brasileiro(valor)
    return valor


def exemplos_da_coluna(conexao, processamento_id: str, coluna: str | None) -> str | None:
    """Alguns valores da coluna como vieram no arquivo, para a dúvida de formato. Ex.: "03/04/1990, 05/06/1985".

    Devolve None se a coluna não existe ou está vazia.
    """
    if not coluna:
        return None
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    if coluna not in leitura.cabecalhos:
        return None
    posicao = leitura.cabecalhos.index(coluna)
    # Os primeiros valores preenchidos
    exemplos = []
    for linha in leitura.linhas:
        valor = linha[posicao].strip()
        if valor:
            exemplos.append(valor)
        if len(exemplos) == EXEMPLOS_DA_COLUNA:
            break
    return ", ".join(exemplos) or None


# O máximo de respostas rápidas num cartão: mais que isso vira uma parede de botões
MAXIMO_DE_SUGESTOES = 8
# A regra do valor fora da lista (a única que ganha palpite e as opções da lista)
REGRA_VALOR_NAO_CONVERTIDO = "VALOR_NAO_CONVERTIDO"
# A regra da coluna obrigatória que o arquivo inteiro não trouxe
REGRA_OBRIGATORIO_SEM_COLUNA = "OBRIGATORIO_SEM_COLUNA"
# O botão que descarta a leitura e abre um envio novo (a tela faz a ação; js/assistente_de_correcao.js)
ACAO_DESCARTAR_E_ENVIAR_OUTRO = "descartar_e_enviar_outro"
# O botão que abre, dentro do cartão, a lista para informar o valor de cada pessoa (ADR-124, alternativa B)
ACAO_INFORMAR_PESSOA_A_PESSOA = "informar_pessoa_a_pessoa"
# A resposta rápida de quem diz que o dado da empresa não é o mesmo para todos (o agente explica os dois caminhos)
TEXTO_NAO_E_A_MESMA = "Não é a mesma para todos"


def _sugestao(texto: str, envia: bool) -> dict:
    """Uma resposta rápida da conversa. envia: True manda na hora; False só põe na caixa (a pessoa completa)."""
    return {"texto": texto, "envia": envia}


def _botao_de_acao(texto: str, acao: str) -> dict:
    """Uma resposta rápida que faz algo na tela, sem mandar mensagem ao agente. Ex.: abrir a lista pessoa a pessoa."""
    return {"texto": texto, "envia": False, "acao": acao}


def _sugestoes_da_coluna_que_falta(igual_para_todos: bool) -> list[dict]:
    """As respostas rápidas do cartão da coluna que o arquivo inteiro não trouxe (ADR-124).

    Os dois caminhos quando o valor não serve para todos: informar pessoa a pessoa (uma lista no cartão) ou mandar o
    arquivo de novo com a coluna. No dado da empresa, antes, "Não é a mesma para todos" (o agente explica os dois); o
    valor para todos a pessoa escreve na caixa.
    """
    botoes = [_botao_de_acao("Informar pessoa a pessoa", ACAO_INFORMAR_PESSOA_A_PESSOA),
              _botao_de_acao("Descartar a leitura e enviar outro arquivo", ACAO_DESCARTAR_E_ENVIAR_OUTRO)]
    if igual_para_todos:
        return [_sugestao(TEXTO_NAO_E_A_MESMA, True)] + botoes
    return botoes


def texto_do_sim_ao_palpite(palpite: str) -> str:
    """A resposta rápida que aceita o palpite do agente. Ex.: "Solteiro" → 'Sim, use "Solteiro"'.

    O agente (agents/assistente_correcao.py) entende exatamente esta frase como corrigir com o palpite.
    """
    return f'Sim, use "{palpite}"'


def _sugestoes_de_resposta(regra_id: str, tipo: str) -> list[dict]:
    """As respostas rápidas que não são valores: confirmar um alerta e escolher o formato de uma coluna.

    "Não cadastrar" e "deixar em branco" NÃO entram: quem quiser isso diz na conversa, e o agente pede
    confirmação.
    """
    # Dúvida de formato da coluna inteira
    if regra_id == "DATA_AMBIGUA":
        return [_sugestao("As datas estão em dia/mês (DD/MM/AAAA)", True),
                _sugestao("As datas estão em mês/dia (MM/DD/AAAA)", True)]
    if regra_id == "ZEROS_A_ESQUERDA":
        return [_sugestao("A matrícula tem ... dígitos", False)]
    # Confirmar um alerta (ou responder a pergunta da IA); um valor fora da lista não se confirma
    if tipo == "confirmar" and regra_id != REGRA_VALOR_NAO_CONVERTIDO:
        if regra_id == validador.REGRA_CNPJ_DO_GRUPO:
            return [_sugestao("Sim, é do nosso grupo", True)]
        return [_sugestao("Está certo assim", True)]
    return []


def _valores_da_lista(campo: str | None) -> list[str]:
    """Os valores aceitos do campo de lista fechada (do parâmetro), ou vazio se o campo não é de lista.

    Ex.: "estado_civil" → ["Solteiro", "Casado", "Divorciado", "Viúvo", "União estável"]; "cargo" → [].
    """
    if not campo:
        return []
    regra = normalizador.carregar_dominios().get(campo)
    if regra is None:
        return []
    return list(regra["valores"])


def sugestoes_da_pendencia(regra_id: str, tipo: str, linha: int | None, campo: str | None,
                           palpite: str | None = None, igual_para_todos: bool = True,
                           do_cadastro_da_empresa: str | None = None) -> list[dict]:
    """As respostas rápidas da conversa de uma pendência (botões em forma de pílula).

    Recebe: a regra, o tipo ("corrigir" ou "confirmar"), a linha (None = arquivo inteiro), o campo, o palpite seguro
    do agente num campo de lista (None se não há) e se a informação pode ser a mesma para todos (a marcação do
    parâmetro; False: é de cada pessoa); do_cadastro_da_empresa — o texto do botão "Usar o CNPJ da empresa (...)" ou
    "Usar o endereço da empresa (...)", quando o cadastro da empresa sabe o valor do campo (ADR-127; None se não).
    Devolve: [{texto, envia}] (e {texto, envia, acao} no botão que faz algo na tela), no máximo
    MAXIMO_DE_SUGESTOES:
      - primeiro, o botão do cadastro da empresa, se houver (o dado que o sistema já sabe vem antes de tudo);
      - na coluna que o arquivo inteiro não trouxe (ADR-124): "Informar pessoa a pessoa" e "Descartar a leitura e
        enviar outro arquivo" (botões de ação); no dado da empresa, antes deles, "Não é a mesma para todos";
      - num valor fora da lista de uma pessoa: primeiro 'Sim, use "<palpite>"' (se houver), depois os outros valores
        aceitos da lista (um clique responde com o valor);
      - num alerta: "Está certo assim" ("Sim, é do nosso grupo" no CNPJ do grupo);
      - numa dúvida de formato: as escolhas do formato.
    Ex.: estado civil "Solteiro(a)", palpite "Solteiro" → Sim, use "Solteiro"; Casado; Divorciado; Viúvo; União estável.
    """
    # O que o cadastro da empresa já sabe (o CNPJ ou o endereço): antes de tudo, e um clique resolve
    do_cadastro = []
    if do_cadastro_da_empresa:
        do_cadastro.append(_sugestao(do_cadastro_da_empresa, True))
    # A coluna que o arquivo inteiro não trouxe: os caminhos quando o valor não serve para todos (a informação de
    # cada pessoa nunca recebe um valor para todos)
    if regra_id == REGRA_OBRIGATORIO_SEM_COLUNA:
        return do_cadastro + _sugestoes_da_coluna_que_falta(igual_para_todos)
    sugestoes = do_cadastro
    # O palpite do agente, primeiro
    if palpite:
        sugestoes.append(_sugestao(texto_do_sim_ao_palpite(palpite), True))
    # Os valores da lista, só num valor de uma pessoa (a dúvida de formato e o arquivo inteiro têm respostas próprias)
    if linha is not None:
        for valor in _valores_da_lista(campo):
            if valor != palpite:
                sugestoes.append(_sugestao(valor, True))
    # Confirmar ou escolher o formato
    for resposta in _sugestoes_de_resposta(regra_id, tipo):
        sugestoes.append(resposta)
    return sugestoes[:MAXIMO_DE_SUGESTOES]


# As regras do dado que falta (a coluna que o arquivo não trouxe, ou a célula vazia): só nelas o cadastro da empresa
# completa o dado (um valor que veio errado a empresa corrige, porque pode ser de uma filial)
REGRAS_DO_DADO_QUE_FALTA = (REGRA_OBRIGATORIO_SEM_COLUNA, "OBRIGATORIO_VAZIO")


def _botao_do_cadastro(achado, valores_do_cadastro: dict[str, str]) -> str | None:
    """O texto do botão "Usar o CNPJ da empresa (...)" ou "Usar o endereço da empresa (...)" do cartão, ou None.

    Só no dado que falta e só quando o cadastro da empresa sabe o valor deste campo (ADR-127).
    """
    if achado.regra_id not in REGRAS_DO_DADO_QUE_FALTA:
        return None
    return dados_da_empresa_no_envio.texto_do_botao(achado.campo, valores_do_cadastro)


def envios_parados_nas_colunas(conexao, empresa_id: str) -> list[dict]:
    """Os envios da empresa que esperam a conferência das colunas (ADR-127): nunca "Tudo em dia" com um deles.

    Para que serve: na conversa de uma pendência, o agente pode devolver o envio à leitura das colunas (ele pede para
    reler uma coluna); as pendências do envio somem até as colunas serem conferidas de novo. Sem isso, o Acompanhar
    diria "Tudo em dia! Nenhum cadastro está esperando por você" com o envio parado.
    Recebe: conexao; empresa_id (da sessão).
    Devolve: [{processamento_id, nome_arquivo, voltou_da_conversa, titulo, texto}], do mais recente para o mais
    antigo. voltou_da_conversa: True se o envio já teve conversa de pendência (ele voltou; não é um envio novo).
    Ex.: [{"titulo": "Voltou para a leitura das colunas", "texto": 'O arquivo "folha.xlsx" voltou ...', ...}].
    """
    nomes_dos_arquivos = processamentos.nomes_na_tela(conexao, empresa_id)
    parados = []
    for perfil in processamentos.listar(conexao, empresa_id):
        if perfil.status != EstadoProcessamento.MAPEAMENTO_PENDENTE:
            continue
        nome = nomes_dos_arquivos[perfil.processamento_id]
        # Já teve conversa de pendência: ele passou da validação e voltou para as colunas
        voltou = bool(conversas_das_pendencias.conversas_do_envio(conexao, perfil.processamento_id))
        if voltou:
            titulo = "Voltou para a leitura das colunas"
            texto = (f'O arquivo "{nome}" voltou para a leitura das colunas, a pedido da conversa com o Agente de '
                     "validação. As pendências dele voltam depois que você conferir as colunas.")
        else:
            titulo = "Esperando você conferir as colunas"
            texto = f'O arquivo "{nome}" ainda não teve as colunas conferidas. As pendências dele aparecem depois disso.'
        parados.append({"processamento_id": perfil.processamento_id, "nome_arquivo": nome,
                        "voltou_da_conversa": voltou, "titulo": titulo, "texto": texto})
    return parados


def palpite_do_achado(achado) -> str | None:
    """O palpite seguro do agente para um valor fora da lista (services/normalizador.palpite_na_lista), ou None."""
    if achado.regra_id != REGRA_VALOR_NAO_CONVERTIDO or not achado.campo:
        return None
    return normalizador.palpite_na_lista(achado.valor, achado.campo, normalizador.carregar_dominios())


def descricoes_dos_campos(conexao) -> dict[str, str]:
    """A descrição de cada campo no parâmetro vigente (o que o banco escreveu).

    Ex.: {"tipo_renda": "Natureza da renda"}.

    Campo sem descrição fica de fora (a fala do agente usa o rótulo curto).
    """
    _, campos_do_layout = parametros.layout_ativo(conexao)
    descricoes = {}
    for campo_do_layout in campos_do_layout:
        if campo_do_layout.descricao:
            descricoes[campo_do_layout.campo] = campo_do_layout.descricao
    return descricoes


def pergunta_do_achado(achado, valor_lido: str | None, pessoa: str | None = None, palpite: str | None = None,
                       descricao: str | None = None, quantidade: int = 1, igual_para_todos: bool = True) -> str:
    """A fala do agente sobre a pendência (services/pergunta_da_pendencia.py), com o valor lido dentro.

    Recebe: o achado do Validador; o valor lido já no jeito da empresa; o nome da pessoa (None no arquivo inteiro);
    o palpite seguro (palpite_do_achado); a descrição do campo no parâmetro (descricoes_dos_campos); quantas pessoas
    vieram com o mesmo valor (mais de 1: a pergunta do grupo, ADR-120); se a informação pode ser a mesma para todos
    (a marcação do parâmetro; False: é de cada pessoa). Devolve: a frase.
    Ex.: CPF inválido → 'O CPF de Maria veio "123.456.789-00", e o dígito verificador não bate. Qual é o CPF certo?'
    """
    rotulo = rotulo_do_campo(achado.campo) if achado.campo else ""
    return pergunta_da_pendencia.perguntar(achado.regra_id, achado.severidade, achado.campo, rotulo, valor_lido,
                                           achado.mensagem, pessoa=pessoa, palpite=palpite, descricao=descricao,
                                           quantidade=quantidade, igual_para_todos=igual_para_todos)


# ---------------- O título do cartão (ADR-120) ----------------

# As regras que falam da pessoa inteira, e não de uma informação dela: o Validador as prende ao CPF (é por ele que
# acha a pessoa), mas o problema não é o CPF. Sem isso, "CPF inválido" e "está em outro arquivo" da mesma pessoa
# ganhavam o mesmo título e pareciam um cartão só com dois problemas (ADR-120: um cartão trata
# um problema só).
REGRAS_DA_PESSOA = ("PESSOA_DUPLICADA", "PESSOA_EM_OUTRO_ENVIO")

# O problema de cada regra, em poucas palavras, para a linha "Problema: ..." do cartão (um cartão, um problema)
PROBLEMA_POR_REGRA = {
    "CPF_INVALIDO": "CPF com o dígito verificador errado",
    "CNPJ_INVALIDO": "CNPJ com o dígito verificador errado",
    "CNPJ_DE_OUTRA_EMPRESA": "CNPJ que não é da sua empresa",
    "CNPJ_DO_GRUPO_A_CONFIRMAR": "CNPJ que não está no cadastro da sua empresa",
    "CEP_INVALIDO": "CEP com o número de dígitos errado",
    "OBRIGATORIO_VAZIO": "informação obrigatória que veio vazia",
    "OBRIGATORIO_SEM_COLUNA": "informação obrigatória que o arquivo não trouxe",
    "VALOR_NAO_CONVERTIDO": "valor que o sistema não reconheceu",
    "NASCIMENTO_NO_FUTURO": "data de nascimento no futuro",
    "ADMISSAO_ANTES_DO_NASCIMENTO": "admissão antes do nascimento",
    "ADMISSAO_ANTES_DOS_14": "admissão antes dos 14 anos",
    "EFETIVACAO_ANTES_DA_ADMISSAO": "efetivação antes da admissão",
    "PESSOA_DUPLICADA": "a mesma pessoa aparece duas vezes neste arquivo",
    "MATRICULA_DUPLICADA": "matrícula repetida neste arquivo",
    "MATRICULA_JA_HOMOLOGADA": "matrícula de outra pessoa já cadastrada",
    "PESSOA_EM_OUTRO_ENVIO": "a pessoa também está em outro arquivo que ainda não foi ao banco",
    "RENDA_NAO_POSITIVA": "renda zerada ou negativa",
    "RENDA_FORA_DO_CARGO": "renda fora do comum para o cargo",
    "VALOR_FORA_DA_FAIXA": "valor fora da faixa esperada pelo banco",
    "DATA_AMBIGUA": "datas que podem estar em dia/mês ou mês/dia",
    "ZEROS_A_ESQUERDA": "matrículas que podem ter perdido zeros à esquerda",
    "CONFERENCIA_DE_TOTAIS": "a leitura não bateu com o total de linhas do arquivo",
}


def campo_em_revisao(achado) -> str | None:
    """A informação que a ficha completa destaca ("Em revisão"): o campo da pendência, ou None nos problemas da pessoa
    inteira (repetida, em outro arquivo), que o Validador prende ao CPF sem que o problema seja o CPF.

    Ex.: CPF inválido → "cpf"; pessoa em outro arquivo → None (a ficha não destaca nada).
    """
    if achado.regra_id in REGRAS_DA_PESSOA:
        return None
    return achado.campo


def problema_do_cartao(regra_id: str, mensagem: str) -> str:
    """O problema do cartão, numa frase curta e só dele (a linha "Problema: ..." embaixo do título).

    Recebe: a regra e a mensagem do Validador. Devolve: a frase (vem depois de "Problema: ", na tela).
    Ex.: "CPF_INVALIDO" → "CPF com o dígito verificador errado"; "PESSOA_EM_OUTRO_ENVIO" com o arquivo na mensagem →
    'a pessoa também está em outro arquivo que ainda não foi ao banco ("folha_set.xlsx")'.
    """
    # A pergunta que a IA fez ao ler um documento
    if regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA):
        return "Dúvida dos agentes ao ler o documento"
    problema = PROBLEMA_POR_REGRA.get(regra_id)
    # Regra sem frase própria: a mensagem do Validador, sem o ponto final
    if problema is None:
        return mensagem.strip().rstrip(".")
    # O arquivo da outra pessoa, quando o Validador diz qual é
    if regra_id == "PESSOA_EM_OUTRO_ENVIO":
        arquivo = re.search(r"\(arquivo (.+)\)\.?$", mensagem)
        if arquivo:
            problema = f'{problema} ("{arquivo.group(1)}")'
    # A outra linha, na pessoa repetida
    if regra_id == "PESSOA_DUPLICADA":
        outra_linha = re.search(r"linha (\d+)", mensagem)
        if outra_linha:
            problema = f"{problema} (a outra é a linha {outra_linha.group(1)})"
    return problema

def titulo_do_cartao(regra_id: str, campo: str | None, tipo: str, pessoa: str | None, descricao: str | None,
                     coluna_do_formato: str | None = None, quantidade: int = 1) -> str:
    """O título do cartão da pendência, que diz de que se trata: o que fazer, a informação e de quem.

    Recebe: a regra; o campo técnico (None se a pendência não é de um campo); o tipo ("corrigir" ou "confirmar"); o
    nome da pessoa (None ou "Arquivo inteiro" na pendência do arquivo); a descrição do campo no parâmetro; a coluna da
    dúvida de formato (se for uma); quantas pessoas (mais de 1 no cartão do grupo).
    Devolve: o título. Exemplos:
        'Ajuste na informação "Estado civil" de Ana Lima';
        'Conferir a informação "Valor da renda" de Ana Lima' (um alerta: pode estar certo);
        'Ajuste na informação "Código da unidade onde o funcionário trabalha" no arquivo inteiro';
        'Ajuste no formato da coluna "Admissão" no arquivo inteiro';
        'Ajuste na informação "Estado civil" de 4 pessoas'.
    O valor fora da lista é sempre "Ajuste" (não se confirma um valor que não está entre as opções).
    """
    # A dúvida de formato é da coluna inteira
    if coluna_do_formato:
        return f'Ajuste no formato da coluna "{coluna_do_formato}" no arquivo inteiro'
    # O que fazer: conferir um alerta, ou ajustar
    confere = tipo == "confirmar" and regra_id != REGRA_VALOR_NAO_CONVERTIDO
    sem_pessoa = not pessoa or pessoa == pergunta_da_pendencia.SEM_PESSOA
    # Pendência que não é de um campo (ex.: a conferência do total de linhas), ou que é da pessoa inteira mesmo
    # guardando o CPF (a pessoa repetida, a pessoa em outro arquivo): o título não cita a informação
    if not campo or regra_id in REGRAS_DA_PESSOA:
        if sem_pessoa:
            return "Conferir o arquivo inteiro" if confere else "Ajuste no arquivo inteiro"
        return f"Conferir o cadastro de {pessoa}" if confere else f"Ajuste no cadastro de {pessoa}"
    informacao = pergunta_da_pendencia.nome_da_informacao(descricao, rotulo_do_campo(campo))
    comeco = f'Conferir a informação "{informacao}"' if confere else f'Ajuste na informação "{informacao}"'
    # De quem: várias pessoas, o arquivo inteiro ou uma pessoa
    if quantidade > 1:
        return f"{comeco} de {quantidade} pessoas"
    if sem_pessoa:
        return f"{comeco} no arquivo inteiro"
    return f"{comeco} de {pessoa}"


# ---------------- Pendências em grupo (ADR-120) ----------------

def texto_do_sim_ao_palpite_do_grupo(palpite: str, quantidade: int) -> str:
    """A resposta rápida que aceita o palpite para o grupo inteiro. Ex.: ("Divorciado", 23) →
    'Sim, use "Divorciado" para as 23'. O agente (agents/assistente_correcao.py) entende esta frase como o palpite."""
    return f"{texto_do_sim_ao_palpite(palpite)} para as {quantidade}"


def sugestoes_do_grupo(campo: str, palpite: str | None, quantidade: int) -> list[dict]:
    """As respostas rápidas do cartão do grupo: o palpite para todas (se houver) e os outros valores da lista.

    Ex.: estado civil, palpite "Divorciado", 23 pessoas → Sim, use "Divorciado" para as 23; Solteiro; Casado; ...
    Cada valor da lista, clicado no cartão do grupo, vale para todas as pessoas do grupo.
    """
    sugestoes = []
    # O palpite do agente, primeiro, dizendo que vale para todas
    if palpite:
        sugestoes.append(_sugestao(texto_do_sim_ao_palpite_do_grupo(palpite, quantidade), True))
    # Os outros valores aceitos da lista
    for valor in _valores_da_lista(campo):
        if valor != palpite:
            sugestoes.append(_sugestao(valor, True))
    return sugestoes[:MAXIMO_DE_SUGESTOES]


def _grupo_para_a_tela(processamento_id: str, chave: str, achados_do_grupo: list, tipo: str,
                       descricoes: dict) -> dict:
    """O que a tela recebe de um grupo: {chave, quantidade, linha_do_representante, valor_lido, palpite, pergunta,
    sugestoes}. A pergunta é a de reserva; a da IA entra depois (marcar_os_grupos).

    A chave junta o envio, o campo e o valor (ex.: "a1b2|estado_civil|divorciado(a)"); o representante é a primeira
    pessoa do grupo, e é por ela que a conversa chega ao servidor (que refaz o grupo a partir do relatório).
    """
    representante = achados_do_grupo[0]
    quantidade = len(achados_do_grupo)
    valor_lido = valor_lido_para_a_tela(representante.campo, representante.valor)
    palpite = palpite_do_achado(representante)
    pergunta = pergunta_do_achado(representante, valor_lido, None, palpite, descricoes.get(representante.campo),
                                  quantidade)
    titulo = titulo_do_cartao(representante.regra_id, representante.campo, tipo, None,
                              descricoes.get(representante.campo), quantidade=quantidade)
    return {"chave": processamento_id + "|" + chave, "quantidade": quantidade,
            "linha_do_representante": representante.linha, "tipo": tipo, "valor_lido": valor_lido,
            "palpite": palpite, "pergunta": pergunta, "titulo_do_cartao": titulo,
            "problema_do_cartao": problema_do_cartao(representante.regra_id, representante.mensagem),
            "sugestoes": sugestoes_do_grupo(representante.campo, palpite, quantidade)}


def _grupo_para_escrever(grupo: dict, representante, descricoes: dict):
    """O que a IA recebe do grupo para escrever a pergunta dele (sem nome de pessoa; com a quantidade)."""
    informacao = pergunta_da_pendencia.nome_da_informacao(descricoes.get(representante.campo),
                                                          rotulo_do_campo(representante.campo))
    # A chave guardada leva a quantidade: se o grupo muda de tamanho, a pergunta é escrita de novo (tem o número)
    chave = perguntas_das_pendencias.chave_da_pendencia(
        representante.regra_id, None, f"grupo:{grupo['chave']}:{grupo['quantidade']}:{grupo['valor_lido']}",
        representante.campo)
    return redator_de_perguntas.PendenciaParaEscrever(
        id=chave, regra=representante.regra_id, gravidade=representante.severidade, pessoa="",
        informacao=informacao, valor_lido=grupo["valor_lido"] or "",
        o_que_aconteceu=pergunta_da_pendencia.mensagem_sem_nome_tecnico(representante.mensagem, representante.campo,
                                                                         informacao),
        tipo=grupo["tipo"], opcoes=_valores_da_lista(representante.campo), palpite=grupo["palpite"] or "",
        quantidade_de_pessoas=grupo["quantidade"])


def marcar_os_grupos(processamento_id: str, pendencias_e_achados: list, descricoes: dict) -> list:
    """Põe em cada pendência de um grupo o "grupo" dela (o mesmo objeto para todas as pessoas do grupo).

    Recebe: o envio; pendencias_e_achados — [(a pendência como vai para a tela, o achado do Validador)] de todas as
    pendências em aberto do envio; a descrição de cada campo no parâmetro.
    Devolve: [(o grupo, o que a IA recebe dele)], para a IA escrever a pergunta de cada grupo junto com as outras
    (perguntas_escritas_pela_ia troca a "pergunta" do grupo). A lista continua com uma pendência por pessoa: os
    números das telas não mudam; quem junta os cartões é a tela.
    """
    # A pendência de cada achado (pelo próprio objeto do achado)
    pendencia_do_achado = {}
    achados = []
    for pendencia, achado in pendencias_e_achados:
        pendencia_do_achado[id(achado)] = pendencia
        achados.append(achado)
    pares = []
    for chave, achados_do_grupo in pendencias_em_grupo.grupos_do_relatorio(achados).items():
        representante = achados_do_grupo[0]
        tipo = pendencia_do_achado[id(representante)]["tipo"]
        grupo = _grupo_para_a_tela(processamento_id, chave, achados_do_grupo, tipo, descricoes)
        # Todas as pessoas do grupo apontam para o mesmo grupo (a pergunta da IA muda em todas de uma vez)
        for achado in achados_do_grupo:
            pendencia_do_achado[id(achado)]["grupo"] = grupo
        pares.append((grupo, _grupo_para_escrever(grupo, representante, descricoes)))
    return pares


# ---------------- A pergunta que a pessoa viu (o 1º balão da conversa guardada; ADR-120) ----------------

def nome_simples_do_campo(conexao, campo: str | None) -> str:
    """O nome do campo como o cartão mostra: a descrição do parâmetro ou o nome técnico com espaços.

    Ex.: "estado_civil" → "Estado civil do funcionário"; None → "".
    """
    if not campo:
        return ""
    return descricoes_dos_campos(conexao).get(campo) or campo.replace("_", " ")


def pergunta_mostrada(conexao, processamento_id: str, achado, nome: str | None) -> str:
    """A pergunta que a pessoa vê no cartão de uma pendência: a escrita pela IA (se já está guardada) ou a de reserva.

    Recebe: o envio; o achado do Validador; o nome da pessoa (None no arquivo inteiro). Devolve: a frase.
    """
    # O valor lido: exemplos da coluna (dúvida de formato) ou o valor da pessoa
    coluna_do_formato = coluna_da_duvida_de_formato(conexao, processamento_id, achado.regra_id, achado.mensagem)
    if coluna_do_formato:
        valor_lido = exemplos_da_coluna(conexao, processamento_id, coluna_do_formato)
    else:
        valor_lido = valor_lido_para_a_tela(achado.campo, achado.valor)
    descricao = descricoes_dos_campos(conexao).get(achado.campo)
    igual = igual_para_todos_do_achado(achado, parametros.campos_iguais_para_todos(conexao))
    reserva = pergunta_do_achado(achado, valor_lido, nome, palpite_do_achado(achado), descricao,
                                 igual_para_todos=igual)
    # A pergunta que a própria IA fez ao ler um documento não passa pelo redator
    if achado.regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA):
        return reserva
    chave = chave_da_pergunta(achado, valor_lido, igual)
    return perguntas_das_pendencias.guardadas(conexao, processamento_id).get(chave) or reserva


def pergunta_mostrada_do_grupo(conexao, processamento_id: str, achados_do_grupo: list) -> str:
    """A pergunta que a pessoa vê no cartão do grupo: a escrita pela IA (se guardada) ou a de reserva."""
    descricoes = descricoes_dos_campos(conexao)
    representante = achados_do_grupo[0]
    tipo = "corrigir" if representante.severidade == validador.BLOQUEANTE else "confirmar"
    grupo = _grupo_para_a_tela(processamento_id, pendencias_em_grupo.chave_do_grupo(representante), achados_do_grupo,
                               tipo, descricoes)
    dados = _grupo_para_escrever(grupo, representante, descricoes)
    return perguntas_das_pendencias.guardadas(conexao, processamento_id).get(dados.id) or grupo["pergunta"]


def igual_para_todos_do_achado(achado, iguais_para_todos: set[str]) -> bool:
    """Se a informação da pendência pode ser a mesma para todos (a marcação do parâmetro).

    Recebe: o achado; os campos que podem ser iguais para todos (parametros.campos_iguais_para_todos).
    Devolve: True num dado da empresa ou numa pendência sem campo; False numa informação de cada pessoa.
    Ex.: a coluna do CNPJ do empregador que falta → True; a do CPF → False.
    """
    if not achado.campo:
        return True
    return achado.campo in iguais_para_todos


def chave_da_pergunta(achado, valor_lido: str | None, igual_para_todos: bool = True) -> str:
    """A chave da pergunta guardada de uma pendência (e o id que a IA recebe dela).

    Nas regras da pessoa inteira (repetida, em outro arquivo), o valor lido (o CPF) fica de fora: a pergunta não
    depende dele, e o id vai para a IA junto com a pendência (um cartão, um problema). Na coluna que falta de uma
    informação de cada pessoa, a chave ganha "de cada pessoa": a pergunta antiga, guardada quando ela ainda pedia um
    valor para todos, não volta (a marcação do parâmetro).
    """
    if achado.regra_id in REGRAS_DA_PESSOA:
        valor_lido = None
    if achado.regra_id == REGRA_OBRIGATORIO_SEM_COLUNA and not igual_para_todos:
        valor_lido = "de cada pessoa"
    return perguntas_das_pendencias.chave_da_pendencia(achado.regra_id, achado.linha, valor_lido, achado.campo)


def pendencia_para_escrever(achado, tipo: str, valor_lido: str | None, pessoa: str | None, palpite: str | None,
                            descricao: str | None, igual_para_todos: bool = True):
    """O que a IA recebe de uma pendência para escrever a pergunta (tudo em linguagem simples).

    Recebe: o achado do Validador; o tipo ("corrigir" ou "confirmar"); o valor lido; o nome da pessoa; o palpite; a
    descrição do campo no parâmetro. Devolve: uma redator_de_perguntas.PendenciaParaEscrever, com id = a chave.
    """
    rotulo = rotulo_do_campo(achado.campo) if achado.campo else ""
    informacao = pergunta_da_pendencia.nome_da_informacao(descricao, rotulo)
    # Um cartão, um problema: nas regras da pessoa inteira (repetida, em outro arquivo), a IA não recebe o CPF nem o
    # nome da informação, para não misturar "o CPF veio errado" com "a pessoa está em outro arquivo"
    valor_para_a_ia = valor_lido or ""
    if achado.regra_id in REGRAS_DA_PESSOA:
        informacao = ""
        valor_para_a_ia = ""
    return redator_de_perguntas.PendenciaParaEscrever(
        id=chave_da_pergunta(achado, valor_lido, igual_para_todos),
        regra=achado.regra_id, gravidade=achado.severidade, pessoa=pergunta_da_pendencia.primeiro_nome(pessoa) or "",
        informacao=informacao, valor_lido=valor_para_a_ia,
        o_que_aconteceu=pergunta_da_pendencia.mensagem_sem_nome_tecnico(achado.mensagem, achado.campo, informacao),
        tipo=tipo, opcoes=_valores_da_lista(achado.campo) if achado.linha is not None else [], palpite=palpite or "",
        igual_para_todos=igual_para_todos)


def perguntas_escritas_pela_ia(conexao, processamento_id: str, empresa_id: str, pares: list, cliente=None) -> None:
    """Troca a pergunta de reserva de cada pendência do envio pela que a IA escreveu (ou pela guardada).

    Recebe: o envio e a empresa; pares — [(a pendência como vai para a tela, o que a IA recebe dela)]; o cliente da IA.
    Devolve: nada; muda "pergunta" em cada pendência. As perguntas que a própria IA fez ao ler um documento (ADR-73)
    ficam como estão. Com a IA fora ou lenta, a reserva continua (services/perguntas_das_pendencias.py).
    """
    para_escrever = []
    reservas = {}
    for pendencia, dados in pares:
        # As perguntas da própria IA e os pedidos do banco ficam com as palavras de quem perguntou (.get: o grupo,
        # ADR-120, não tem "pergunta_da_ia")
        if pendencia.get("pergunta_da_ia") or pendencia.get("pedido_do_banco"):
            continue
        para_escrever.append(dados)
        reservas[dados.id] = pendencia["pergunta"]
    if not para_escrever:
        return
    perguntas = perguntas_das_pendencias.perguntas_do_envio(conexao, processamento_id, empresa_id, para_escrever,
                                                            reservas, cliente)
    for pendencia, dados in pares:
        if dados.id in perguntas:
            pendencia["pergunta"] = perguntas[dados.id]

def pendencias_da_empresa(conexao, empresa_id: str, cliente=None) -> list[dict]:
    """O que falta a empresa resolver para fechar os cadastros: os achados do Validador ainda em aberto.

    Recebe: conexao; empresa_id (da sessão); cliente — o da IA que escreve as perguntas (os testes passam um falso).
    Devolve: lista de {processamento_id, enviado_em, tipo, severidade, regra_id, linha, nome, problema, acao, campo,
    nome_do_campo, valor_lido, pergunta, palpite, sugestoes, grupo}. grupo: None, ou — quando 2+ pessoas do mesmo
    envio vieram com o mesmo valor fora de uma lista (ADR-120) — o mesmo objeto para todas elas, {chave, quantidade,
    linha_do_representante, tipo, valor_lido, palpite, pergunta, sugestoes} (ver marcar_os_grupos); a lista continua
    com uma pendência por pessoa, e a tela junta o grupo num cartão só. valor_lido é a informação que gerou a
    dúvida, como a empresa a reconhece (ver valor_lido_para_a_tela; None se o arquivo veio sem ela); pergunta, a fala
    do agente no balão, escrita pela IA com a diretriz de tom de voz (ver perguntas_escritas_pela_ia; a reserva é
    pergunta_do_achado);
    palpite, o item da lista que o agente acredita ser o certo, só quando é seguro
    (palpite_do_achado); sugestoes, as respostas rápidas da conversa (sugestoes_da_pendencia).
    nome_do_campo é o campo em linguagem simples (a descrição que o banco escreveu no parâmetro, ex.: "Tipo do documento
    de identificação"), para a empresa saber de que dado se trata.
        regra_id e linha identificam a pendência para corrigir ou confirmar (funções abaixo).
        tipo "corrigir": BLOQUEANTE (o cadastro não passa sem corrigir, ex.: CPF inválido);
        tipo "confirmar": ALERTA ainda não justificado (ex.: salário fora do padrão do cargo).
    AVISO fica de fora (é só informativo) e envio já cadastrado ou descartado não tem pendência.
    """
    # Quando cada envio foi feito
    quando_e_quem = quando_e_quem_enviou(conexao, empresa_id)
    # O nome de cada arquivo como a tela mostra (arquivos diferentes com o mesmo nome ganham "(v1)", "(v2)")
    nomes_dos_arquivos = processamentos.nomes_na_tela(conexao, empresa_id)
    # Os campos obrigatórios do layout (campo obrigatório não pode ser "deixado em branco")
    _, campos_do_layout = parametros.layout_ativo(conexao)
    obrigatorios = set()
    # O nome de cada campo em linguagem simples (a descrição do parâmetro; sem descrição, o nome sem "_")
    nome_simples = {}
    for campo_do_layout in campos_do_layout:
        if campo_do_layout.obrigatorio:
            obrigatorios.add(campo_do_layout.campo)
        nome_simples[campo_do_layout.campo] = campo_do_layout.descricao or campo_do_layout.campo.replace("_", " ")
    # A descrição de cada campo no parâmetro (o nome do campo na fala do agente)
    descricoes = descricoes_dos_campos(conexao)
    # Os campos que podem ser iguais para todos (a marcação do parâmetro; os outros são de cada pessoa)
    iguais_para_todos = parametros.campos_iguais_para_todos(conexao)
    # O que o cadastro da empresa já sabe (o CNPJ e o endereço): vira o botão "Usar o ... da empresa" (ADR-127)
    valores_do_cadastro = dados_da_empresa_no_envio.valores_do_cadastro(conexao, empresa_id)
    # Lista que vai sendo preenchida
    pendencias = []
    for perfil in processamentos.listar(conexao, empresa_id):
        # Envio cadastrado ou descartado: nada pendente
        if perfil.status in (EstadoProcessamento.HOMOLOGADO, EstadoProcessamento.REJEITADO):
            continue
        # O último relatório do Validador (None se o envio ainda não chegou à validação)
        relatorio = validador.obter(conexao, perfil.processamento_id)
        if relatorio is None:
            continue
        # O nome de cada pessoa do envio, para o título do cartão
        nomes = nome_de_cada_registro(conexao, perfil.processamento_id)
        # As pendências deste envio e o que a IA recebe de cada uma (para escrever as perguntas no fim)
        pares_do_envio = []
        # Cada pendência com o seu achado (para achar os grupos de pessoas com o mesmo valor)
        pendencias_e_achados = []
        for achado in relatorio.achados:
            # Só bloqueantes e alertas ainda não justificados
            if achado.severidade == validador.BLOQUEANTE:
                tipo = "corrigir"
            elif achado.severidade == validador.ALERTA and not achado.resolvido:
                tipo = "confirmar"
            else:
                continue
            # O nome da pessoa (achado do arquivo inteiro não tem pessoa)
            nome = "Arquivo inteiro"
            if achado.registro is not None:
                nome = nomes.get(achado.registro) or ("Funcionário da linha " + str(achado.linha))
            # A coluna da dúvida de formato (None nas outras pendências)
            coluna_do_formato = coluna_da_duvida_de_formato(conexao, perfil.processamento_id, achado.regra_id,
                                                            achado.mensagem)
            # O que gerou a dúvida: alguns valores da coluna (formato) ou o valor lido da pessoa
            if coluna_do_formato:
                valor_lido = exemplos_da_coluna(conexao, perfil.processamento_id, coluna_do_formato)
            else:
                valor_lido = valor_lido_para_a_tela(achado.campo, achado.valor)
            # O palpite seguro num valor fora da lista (None nas outras pendências)
            palpite = palpite_do_achado(achado)
            # A informação pode ser a mesma para todos (dado da empresa) ou é de cada pessoa (a marcação do parâmetro)
            igual = igual_para_todos_do_achado(achado, iguais_para_todos)
            pendencia = {
                "processamento_id": perfil.processamento_id,
                # O arquivo da pendência: a tela filtra as pendências por arquivo
                "nome_arquivo": nomes_dos_arquivos[perfil.processamento_id],
                "enviado_em": quando_e_quem[perfil.processamento_id][0],
                "tipo": tipo,
                "severidade": achado.severidade,
                "regra_id": achado.regra_id,
                "linha": achado.linha,
                "nome": nome,
                "problema": achado.mensagem,
                "acao": achado.acao,
                "campo": achado.campo,
                "nome_do_campo": nome_simples.get(achado.campo, ""),
                "coluna_do_formato": coluna_do_formato,
                "obrigatorio": achado.campo in obrigatorios,
                "pergunta_da_ia": achado.regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA),
                # O pedido que o especialista do banco fez sobre esta pessoa (ADR-121): a tela mostra o selo
                "pedido_do_banco": achado.regra_id.startswith(validador.PREFIXO_DO_PEDIDO_DO_BANCO),
                "explicacao_da_ia": None,
                # A informação que gerou a dúvida: a empresa vê o que foi lido
                "valor_lido": valor_lido,
                # A fala do agente no balão: natural, com o valor lido, o campo e a pessoa
                "pergunta": pergunta_do_achado(achado, valor_lido, nome, palpite, descricoes.get(achado.campo),
                                               igual_para_todos=igual),
                # O item da lista que o agente acredita ser o certo (só quando é seguro)
                "palpite": palpite,
                # As respostas rápidas da conversa (botões em forma de pílula)
                "sugestoes": sugestoes_da_pendencia(achado.regra_id, tipo, achado.linha, achado.campo, palpite,
                                                    igual, _botao_do_cadastro(achado, valores_do_cadastro)),
                # O grupo de pessoas com o mesmo valor fora da lista (ADR-120; None se ela está sozinha)
                "grupo": None,
                # O título do cartão: o que fazer, a informação e de quem (ADR-120)
                "titulo_do_cartao": titulo_do_cartao(achado.regra_id, achado.campo, tipo, nome,
                                                     descricoes.get(achado.campo), coluna_do_formato),
                # O problema, numa frase curta e só dele: um cartão nunca trata mais de um problema
                "problema_do_cartao": problema_do_cartao(achado.regra_id, achado.mensagem),
                # A informação em destaque na ficha completa (None nos problemas da pessoa inteira)
                "campo_em_revisao": campo_em_revisao(achado),
            }
            # O pedido do banco aparece com as palavras do especialista (a IA não reescreve o recado do banco)
            if pendencia["pedido_do_banco"]:
                pendencia["pergunta"] = achado.mensagem
            pendencias.append(pendencia)
            pendencias_e_achados.append((pendencia, achado))
            pares_do_envio.append((pendencia, pendencia_para_escrever(achado, tipo, valor_lido, nome, palpite,
                                                                      descricoes.get(achado.campo), igual)))
        # As pessoas com o mesmo valor fora da lista viram um grupo, com uma pergunta só (ADR-120)
        pares_do_envio.extend(marcar_os_grupos(perfil.processamento_id, pendencias_e_achados, descricoes))
        # A fala do agente em cada pendência deste envio: escrita pela IA (uma chamada por envio) ou a reserva
        perguntas_escritas_pela_ia(conexao, perfil.processamento_id, empresa_id, pares_do_envio, cliente)
    # Devolve a lista, com a pergunta da IA sobre um campo a corrigir virando a explicação dessa correção
    return juntar_perguntas_as_correcoes(pendencias)


def juntar_perguntas_as_correcoes(pendencias: list[dict]) -> list[dict]:
    """A pergunta da IA sobre um campo que já tem algo a CORRIGIR (ex.: CPF vazio + "o CPF vem depois") vira a
    explicação dessa correção, num cartão só; ela se resolve junto, quando o campo é corrigido (ADR-73).

    Recebe e devolve a lista de pendências (as outras perguntas da IA continuam como cartão de "confirmar").
    """
    correcao_do_campo = {}
    for pendencia in pendencias:
        if pendencia["tipo"] == "corrigir" and pendencia["campo"]:
            chave = (pendencia["processamento_id"], pendencia["linha"], pendencia["campo"])
            correcao_do_campo[chave] = pendencia
    juntas = []
    for pendencia in pendencias:
        chave = (pendencia["processamento_id"], pendencia["linha"], pendencia["campo"])
        if pendencia["pergunta_da_ia"] and chave in correcao_do_campo:
            correcao_do_campo[chave]["explicacao_da_ia"] = pendencia["problema"]
            continue
        juntas.append(pendencia)
    return juntas


def corrigir_pendencia(conexao, empresa_id: str, login: str, processamento_id: str, linha: int, campo: str,
                       novo_valor: str, motivo: str) -> None:
    """A empresa corrige um dado pela tela: registra o pedido, aplica e valida o envio de novo.

    Recebe: conexao; empresa_id (da sessão); login de quem clicou; o envio, a linha e o campo da pendência;
            o valor novo (digitado do jeito brasileiro, ex.: "12/09/2026" ou "2.450,00") e o motivo.
    Devolve: nada. Levanta KeyError se o envio não é da empresa e ValueError (com a mensagem para a pessoa)
    se o valor não pode ser padronizado, se falta o motivo ou se a linha não existe.
    Por que propor e aplicar juntos: na tela nova, digitar o valor e clicar em "Salvar correção" JÁ é a decisão
    humana (ADR-16). Os dois passos continuam registrados: quem propôs, quem aprovou, antes e depois.
    """
    # O pedido: confere que o envio é da empresa e padroniza o valor (recusa com o motivo, se não der)
    correcao = correcoes.propor(conexao, processamento_id, empresa_id, linha, campo, novo_valor, motivo, login)
    # O clique: aplica e valida o envio de novo (a pendência sai se o valor novo passar nas regras)
    correcoes.decidir(conexao, processamento_id, empresa_id, correcao.correcao_id, True, login)


def preencher_para_todos(conexao, empresa_id: str, login: str, processamento_id: str, campo: str, novo_valor: str,
                         motivo: str) -> int:
    """A empresa preenche um campo com o mesmo valor em todos do envio que estão sem ele (ex.: o CNPJ do empregador,
    que o Word em texto corrido não traz).

    Recebe: conexao; empresa_id (da sessão); login de quem clicou; o envio, o campo, o valor e o motivo.
    Devolve: quantos funcionários foram preenchidos. Quem já tem o campo não muda. O envio é validado de novo.
    """
    # Uma correção por funcionário preenchido: a quantidade é o tamanho da lista
    identificadores = correcoes.preencher_para_todos(conexao, processamento_id, empresa_id, campo, novo_valor, motivo,
                                                     login)
    return len(identificadores)


def confirmar_pendencia(conexao, empresa_id: str, login: str, processamento_id: str, regra_id: str, linha: int | None,
                        justificativa: str) -> None:
    """A empresa confirma que um valor em alerta está certo (ex.: salário alto de um gerente), com justificativa.

    Recebe: conexao; empresa_id (da sessão); login; o envio, a regra e a linha do alerta; a justificativa.
    Devolve: nada. Levanta KeyError (envio de outra empresa) ou ValueError (sem justificativa ou alerta inexistente).
    A confirmação vira rótulo "CONFIRMADO" para um futuro modelo de risco (ADR-14) e o envio é validado de novo.
    """
    # Justifica e revalida (o serviço confere que o envio é da empresa e que o alerta existe)
    validador.justificar_alerta(conexao, processamento_id, empresa_id, regra_id, linha, "CONFIRMADO", justificativa, login)


# ---------------- CPF inteiro: ficha e download, sempre registrados (LGPD) ----------------

# Os tipos de acesso a dados pessoais que ficam registrados
ACESSO_FICHA = "FICHA"         # abriu a ficha de uma pessoa (com o CPF inteiro)
ACESSO_DOWNLOAD = "DOWNLOAD"   # baixou a lista (com o CPF inteiro)
ACESSO_LISTA = "LISTA"         # abriu a lista de funcionários na tela (com o CPF inteiro, ADR-97)

# As colunas do arquivo baixado, na ordem (as mesmas da tabela da tela)
COLUNAS_DO_DOWNLOAD = ("Nome", "CPF", "Matrícula", "Cargo", "Unidade", "Admissão", "Salário", "Incluído em",
                       "Incluído por", "Situação", "Conta salário aberta em", "Código do banco", "Agência",
                       "Conta salário")
# A conta de quem ainda não abriu: tudo vazio
CONTA_AINDA_NAO_ABERTA = {"data_abertura": "", "codigo_banco": "", "agencia": "", "conta": "", "situacao_na_empresa": ""}


def _preparar_acessos(conexao) -> None:
    """Cria a tabela dos acessos a dados pessoais, se ainda não existir.

    Por que uma tabela própria: a trilha de auditoria (services/auditoria.py) é organizada por envio, e abrir uma ficha
    ou baixar a lista não pertence a um envio. Aqui fica quem viu, quando, o quê e quantas pessoas; nunca o CPF.
    """
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS acessos_a_dados (
               id          INTEGER PRIMARY KEY AUTOINCREMENT,
               empresa_id  TEXT NOT NULL,
               login       TEXT NOT NULL,
               tipo        TEXT NOT NULL,
               quantidade  INTEGER NOT NULL,
               criado_em   TEXT NOT NULL
           )"""
    )


def registrar_acesso(conexao, empresa_id: str, login: str, tipo: str, quantidade: int) -> None:
    """Grava que alguém viu dados pessoais (ficha ou download), com quantas pessoas. Nunca grava o CPF.

    Recebe: conexao; empresa_id; login; tipo (ACESSO_FICHA, ACESSO_DOWNLOAD ou ACESSO_LISTA); quantidade de pessoas.
    """
    # Garante que a tabela existe
    _preparar_acessos(conexao)
    # Momento do acesso, no horário universal
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Grava e confirma
    conexao.execute("INSERT INTO acessos_a_dados (empresa_id, login, tipo, quantidade, criado_em) VALUES (?, ?, ?, ?, ?)",
                    (empresa_id, login, tipo, quantidade, agora))
    conexao.commit()


def acessos_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os acessos a dados pessoais da empresa, do mais antigo para o mais recente (para o Painel e os testes).

    Recebe: conexao; empresa_id. Devolve: lista de {login, tipo, quantidade, criado_em}.
    """
    # Garante que a tabela existe
    _preparar_acessos(conexao)
    consulta = conexao.execute("SELECT login, tipo, quantidade, criado_em FROM acessos_a_dados WHERE empresa_id = ? "
                               "ORDER BY id", (empresa_id,))
    acessos = []
    for login, tipo, quantidade, criado_em in consulta:
        acessos.append({"login": login, "tipo": tipo, "quantidade": quantidade, "criado_em": criado_em})
    return acessos


def _somente_digitos(texto: str) -> str:
    """Só os dígitos do texto: "529.982.247-25" → "52998224725"."""
    digitos = ""
    for caractere in texto:
        if caractere.isdigit():
            digitos = digitos + caractere
    return digitos


def formatar_cpf(cpf: str) -> str:
    """Põe a pontuação no CPF inteiro. Exemplo: "24681357954" → "246.813.579-54" (fora de 11 dígitos, volta como veio)."""
    # Só os dígitos
    digitos = ""
    for caractere in cpf:
        if caractere.isdigit():
            digitos = digitos + caractere
    # Tamanho errado: devolve como veio
    if len(digitos) != 11:
        return cpf
    # 3.3.3-2
    return digitos[0:3] + "." + digitos[3:6] + "." + digitos[6:9] + "-" + digitos[9:11]


def _registros_completos_da_empresa(conexao, empresa_id: str) -> dict:
    """Todas as pessoas cadastradas da empresa, com o CPF inteiro, pelo identificador (envio.posição).

    Recebe: conexao; empresa_id. Devolve: {identificador: pessoa}. Uso interno: quem chama registra o acesso.
    Usa a mesma lista da tela (funcionarios_da_empresa) e completa só o CPF, lendo o arquivo final do envio.
    """
    # A lista da tela, por identificador
    pessoas_por_id = {}
    for pessoa in funcionarios_da_empresa(conexao, empresa_id):
        pessoas_por_id[pessoa["id"]] = dict(pessoa)
    # Os envios que aparecem nos identificadores
    envios = set()
    for identificador in pessoas_por_id:
        envios.add(identificador.split(".")[0])
    # Completa o CPF inteiro, lendo o arquivo final de cada envio
    for processamento_id in envios:
        homologado = homologacao.obter(conexao, processamento_id)
        for registro in _registros_do_arquivo_final(homologado["arquivo"]):
            identificador = processamento_id + "." + str(registro["_posicao"])
            if identificador in pessoas_por_id:
                pessoas_por_id[identificador]["cpf"] = formatar_cpf(registro.get("cpf", ""))
    return pessoas_por_id


def ficha_do_funcionario(conexao, empresa_id: str, login: str, identificador: str) -> dict:
    """A ficha de uma pessoa com o CPF inteiro, SÓ da empresa da sessão, e o acesso fica registrado.

    Recebe: conexao; empresa_id (da sessão); login de quem abriu; identificador (ex.: "94a3322a4416.7").
    Devolve: os dados da pessoa (os mesmos campos da lista, com o CPF inteiro).
    Levanta KeyError se a pessoa não existe nesta empresa (identificador de outra empresa também cai aqui).
    """
    # As pessoas da empresa, com o CPF inteiro
    pessoas = _registros_completos_da_empresa(conexao, empresa_id)
    # Não é desta empresa (ou não existe)
    if identificador not in pessoas:
        raise KeyError(identificador)
    # Registra quem viu (uma pessoa) e devolve
    registrar_acesso(conexao, empresa_id, login, ACESSO_FICHA, 1)
    return pessoas[identificador]


def _pessoas_para_baixar(conexao, empresa_id: str) -> dict:
    """As pessoas que a grade de "Acompanhar cadastros" mostra, pelo identificador de download (ADR-155).

    Recebe: conexao; empresa_id (da sessão). Devolve: {identificador: pessoa}. Uso interno: quem chama registra o acesso.
      - os cadastrados, pelo id (envio.posição), com o CPF inteiro lido do arquivo final, como na ficha;
      - quem ainda não foi cadastrado (Em análise, Pendente e Aguardando envio), pelo id_para_baixar (envio.linhaN), na
        situação que a grade mostra. A mesma pessoa aparece uma vez só, como na grade.
    Só a empresa da sessão: o identificador de outra empresa não está aqui, e o download o ignora.
    """
    # Os cadastrados, pelo id
    pessoas = _registros_completos_da_empresa(conexao, empresa_id)
    # Quem ainda não foi cadastrado, da mesma lista que a grade mostra (os cadastrados dela já estão acima)
    for pessoa in todos_os_funcionarios_da_empresa(conexao, empresa_id):
        if pessoa["id"] is None:
            pessoas[pessoa["id_para_baixar"]] = pessoa
    return pessoas


def _situacao_no_arquivo(pessoa: dict) -> str:
    """A situação da pessoa no arquivo baixado: a mesma da grade.

    Recebe: pessoa — uma das de _pessoas_para_baixar. Devolve: o texto da situação.
    Ex.: {"situacao": "Em análise", ...} → "Em análise"; um cadastrado (sem "situacao") → a que o banco informou no
    arquivo de contas, ou "Cadastrado" (situacao_do_cadastrado).
    """
    # Quem ainda não foi cadastrado já vem com a situação da grade
    if pessoa.get("situacao"):
        return pessoa["situacao"]
    # O cadastrado: Cadastrado, Conta aberta ou Já é correntista
    return situacao_do_cadastrado(pessoa)


def lista_para_baixar(conexao, empresa_id: str, login: str, identificadores: list[str]) -> bytes:
    """O CSV para o Excel (separador ";") com as pessoas pedidas, com o CPF inteiro, e o download registrado.

    Recebe: conexao; empresa_id (da sessão); login; identificadores — o id_para_baixar de cada pessoa que está na grade
    (com os filtros), cadastrada ou ainda em andamento (ADR-155).
    Devolve: os bytes do arquivo (UTF-8 com a marca que o Excel reconhece), uma linha por pessoa, com a situação que a
    grade mostra. Identificador de outra empresa é ignorado. Levanta ValueError se nenhuma pessoa da empresa foi pedida.
    Proteção: célula com cara de fórmula é neutralizada, como no arquivo final da homologação ("CSV injection").
    """
    # As pessoas da grade da empresa, pelo identificador de download
    pessoas = _pessoas_para_baixar(conexao, empresa_id)
    # Só as pedidas que são desta empresa, na ordem pedida
    escolhidas = []
    for identificador in identificadores:
        if identificador in pessoas:
            escolhidas.append(pessoas[identificador])
    # Nada para baixar
    if not escolhidas:
        raise ValueError("Nenhum funcionário para baixar com esses filtros.")
    # Monta o CSV
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(COLUNAS_DO_DOWNLOAD)
    for pessoa in escolhidas:
        # Os valores, na ordem das colunas. Quem ainda está em andamento não tem conta no banco: a conta fica vazia
        valores = [pessoa.get("nome_completo"), pessoa.get("cpf"), pessoa.get("matricula"), pessoa.get("cargo"),
                   pessoa.get("nome_unidade"), pessoa.get("data_admissao"), pessoa.get("valor_renda"),
                   str(pessoa.get("incluido_em") or "")[:10], pessoa.get("incluido_por"), _situacao_no_arquivo(pessoa),
                   pessoa.get("conta_aberta_em"), pessoa.get("codigo_banco"), pessoa.get("agencia"), pessoa.get("conta")]
        # Cada valor protegido contra fórmula do Excel
        linha = []
        for valor in valores:
            linha.append(homologacao.neutralizar_formula(str(valor or "")))
        escritor.writerow(linha)
    # Registra quem baixou e quantas pessoas
    registrar_acesso(conexao, empresa_id, login, ACESSO_DOWNLOAD, len(escolhidas))
    # "﻿" no começo avisa o Excel que o arquivo é UTF-8 (senão os acentos saem errados)
    return ("﻿" + saida.getvalue()).encode("utf-8")


def pessoas_em_analise_pelo_banco(conexao, empresa_id: str) -> int:
    """Quantas pessoas da empresa estão "Em análise": o envio delas foi mandado ao banco e espera a avaliação.

    Recebe: conexao; empresa_id (da sessão). Devolve: o número de pessoas. Exemplo: um envio de 5 pessoas mandado ao
    banco → 5; depois que o banco cadastra, elas passam a "Cadastrado" e o número volta a 0.
    Conta na MESMA lista da consulta de funcionários (todos_os_funcionarios_da_empresa), para o cartão bater sempre
    com o filtro "Em análise" da lista: a mesma pessoa em dois envios conta uma vez só, na situação mais adiantada.
    """
    # Todos os funcionários da empresa, já com a situação de cada um (a mesma lista que a tela filtra)
    funcionarios = todos_os_funcionarios_da_empresa(conexao, empresa_id)
    # Conta quem está "Em análise"
    return contar_em_analise(funcionarios)


def contar_em_analise(funcionarios: list[dict]) -> int:
    """Quantas pessoas de uma lista já montada estão na situação "Em análise".

    Recebe: funcionarios — a lista de todos_os_funcionarios_da_empresa. Devolve: o número de pessoas.
    Separada para quem já tem a lista em mãos (ex.: a Visão geral do banco) não montá-la duas vezes.
    Exemplo: [{"situacao": "Em análise"}, {"situacao": "Cadastrado"}] → 1.
    """
    # Conta só quem está na situação "Em análise"
    quantidade_em_analise = 0
    for pessoa in funcionarios:
        if pessoa["situacao"] == SITUACAO_EM_ANALISE:
            quantidade_em_analise = quantidade_em_analise + 1
    return quantidade_em_analise


def resumo_da_empresa(conexao, empresa_id: str) -> dict:
    """Os números do alto da tela: cadastrados, envios, envios em andamento e envios com pendência.

    Recebe: conexao; empresa_id (da sessão). Devolve: um dicionário com os 4 números.
    As pessoas em análise pelo banco NÃO entram aqui: a carteira do banco chama esta função para cada empresa e não
    usa esse número, que custa montar a lista inteira. A rota de "Acompanhar cadastros" o acrescenta
    (pessoas_em_analise_pelo_banco).
    """
    # Os envios da empresa
    envios = envios_da_empresa(conexao, empresa_id)
    # Contadores
    em_andamento = 0
    com_pendencia = 0
    for envio in envios:
        # Em andamento: nem cadastrado nem descartado
        if envio["situacao"] not in ("Cadastrado", "Descartado"):
            em_andamento = em_andamento + 1
        # Com pendência: a validação encontrou o que corrigir
        if envio["situacao"] == "Com pendências para corrigir":
            com_pendencia = com_pendencia + 1
    # Os 4 números
    return {
        "cadastrados": len(funcionarios_da_empresa(conexao, empresa_id)),
        "envios": len(envios),
        "em_andamento": em_andamento,
        "com_pendencia": com_pendencia,
    }
