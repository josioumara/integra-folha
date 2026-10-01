"""A lista de conferência da base viva: tabela a tabela e tela a tela, nada vazio nem incoerente (desenho §3.8).

Para que serve: depois da carga (scripts/carregar_base_viva.py), confere no banco de dados que cada tabela que as telas
leem ficou como o roteiro manda, e chama as mesmas funções que as telas chamam (Início, Envios, Empresas, Telemetria,
Planejamento e o portal de cada empresa), para nenhuma quebrar nem ficar vazia. Confere também o que a base viva NÃO
pode ter: nenhuma execução de agente de IA, nenhum par no histórico de mapeamentos (o conhecimento da IA), nenhuma
sessão que ainda valha, e o Endomarketing e o catálogo vazios (a IA não é inventada).

Cada item da lista diz a tabela (ou a tela), o que foi conferido, o esperado, o encontrado e se bateu. Serve à carga no
PostgreSQL (V2) e aos testes (no SQLite). Nada é gravado aqui: só leituras.

Para rodar (na pasta integra-folha, com o .env do banco que recebeu a base):
    python scripts/conferir_base_viva.py
Sai com o código 1 se algum item não bater.
"""
import csv
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A conferência nunca chama a IA (algumas telas escrevem perguntas com ela): o modo MOCK antes de ler o .env
os.environ["MODE"] = "mock"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from models.contratos import EstadoProcessamento, MappingPlan  # noqa: E402
from scripts import carregar_base_viva, gerar_base_viva  # noqa: E402
from services import (acompanhamento, avaliacao_do_banco, banco, faixa_salarial_cbo, homologacao,  # noqa: E402
                      portal_do_banco, tabela_cbo)
from workflows import fluxo_empresa  # noqa: E402

# A situação do envio no banco de dados para cada destino do roteiro
SITUACAO_DE_CADA_DESTINO = {
    "CADASTRADO": EstadoProcessamento.HOMOLOGADO.value,
    "EM_ANALISE": EstadoProcessamento.AGUARDANDO_BANCO.value,
    "PENDENTE": EstadoProcessamento.VALIDACAO_PENDENTE.value,
    "PRONTO": EstadoProcessamento.NORMALIZADO.value,
    "DEVOLVIDO": EstadoProcessamento.DEVOLVIDO.value,
    "NO_ACEITE": EstadoProcessamento.MAPEAMENTO_PENDENTE.value,
}
# As origens de coluna que contam como proposta de um agente de IA (services/aceitacao_dos_agentes.py)
ORIGENS_DE_IA = ("llm", "handoff", "leitor", "humano")
# Os eventos que toda linha do tempo de envio precisa ter, pela etapa em que o envio está
EVENTOS_DE_CADA_DESTINO = {
    "NO_ACEITE": ("RECEBIDO", "MAPEAMENTO_PROPOSTO"),
    "PENDENTE": ("RECEBIDO", "MAPEAMENTO_PROPOSTO", "MAPEAMENTO_APROVADO", "VALIDADO"),
    "PRONTO": ("RECEBIDO", "MAPEAMENTO_PROPOSTO", "MAPEAMENTO_APROVADO", "VALIDADO"),
    "EM_ANALISE": ("RECEBIDO", "MAPEAMENTO_PROPOSTO", "MAPEAMENTO_APROVADO", "ENVIADO_AO_BANCO"),
    "DEVOLVIDO": ("RECEBIDO", "MAPEAMENTO_PROPOSTO", "MAPEAMENTO_APROVADO", "ENVIADO_AO_BANCO",
                  "DEVOLVIDO_PELO_BANCO"),
    "CADASTRADO": ("RECEBIDO", "MAPEAMENTO_PROPOSTO", "MAPEAMENTO_APROVADO", "ENVIADO_AO_BANCO", "HOMOLOGADO",
                   "APROVADO_PELO_BANCO", "PLANEJAMENTO_LIBERADO"),
}
# As tabelas do conteúdo gerado pela IA que a base viva deixa vazias de propósito (Endomarketing e catálogo)
TABELAS_QUE_FICAM_VAZIAS = ("materiais_endomarketing", "catalogo_documentos", "kbs_endomarketing", "kbs_publicacoes")
# O tipo de KB que não é conteúdo da IA: o kit da marca (a escolha, as cores e o logo), que a carga grava publicado,
# porque a KB do kit é a fonte única do kit da empresa
TIPO_DE_KB_QUE_NAO_E_DA_IA = "kit_da_marca"
# Quantos dias corridos a história da base viva cobre, no máximo (uns 3 meses e meio, com folga)
DIAS_DA_HISTORIA = 110


def _item(onde: str, o_que: str, esperado, encontrado) -> dict:
    """Um item da lista: bate quando o encontrado é igual ao esperado."""
    return {"onde": onde, "o_que": o_que, "esperado": esperado, "encontrado": encontrado,  # o item e se ele bateu
            "bateu": esperado == encontrado}


def _contar(conexao, tabela: str, filtro: str = "", valores: tuple = ()) -> int:
    """Quantas linhas a tabela tem com o filtro (0 se a tabela nem existe neste banco)."""
    # A tabela ainda não existe (nenhum serviço a criou neste banco): nenhuma linha
    if not banco.colunas_da_tabela(conexao, tabela):
        return 0  # nenhuma linha
    # A contagem, com o filtro quando houver
    comando = f"SELECT COUNT(*) FROM {tabela}"
    if filtro:  # com filtro, só as linhas que casam
        comando = comando + " WHERE " + filtro  # acrescenta o filtro
    return conexao.execute(comando, valores).fetchone()[0]  # o número de linhas


def _filtro_das_empresas(ids: list[str]) -> str:
    """O filtro SQL "empresa_id IN (?, ?, ...)" para a lista de empresas."""
    return f"empresa_id IN ({carregar_base_viva._marcadores(len(ids))})"  # um "?" por empresa


# ================================ As tabelas ================================

def _empresas_e_logins(conexao, roteiro: dict, ids: list[str]) -> list[dict]:
    """Empresas (cadastro, região, CNPJ, domínio), outros CNPJs, logins e sessões."""
    # As empresas criadas pela carga: uma por empresa do roteiro
    itens = [_item("empresas", "empresas criadas pela carga", len(roteiro["empresas"]), len(ids))]
    # O cadastro completo: UF, município, CNPJ de 14 dígitos e o domínio reservado
    completas = 0
    for empresa_id, uf, municipio, cnpj, dominio in conexao.execute(
            f"SELECT empresa_id, uf, municipio, cnpj, dominio_email FROM empresas WHERE {_filtro_das_empresas(ids)}",
            tuple(ids)).fetchall():
        if uf and municipio and len(cnpj) == 14 and dominio.endswith(".example"):  # o cadastro está completo
            completas = completas + 1  # mais uma empresa completa
    itens.append(_item("empresas", "com UF, município, CNPJ e domínio .example", len(ids), completas))
    # Os CNPJs de filiais e do grupo que o roteiro manda cadastrar
    esperados = 0  # nenhum esperado, por enquanto
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        esperados = esperados + len(empresa["cnpjs_extras"])  # os CNPJs extras desta empresa
    itens.append(_item("cnpjs_das_empresas", "filiais e empresa do grupo", esperados,
                       _contar(conexao, "cnpjs_das_empresas", _filtro_das_empresas(ids), tuple(ids))))
    # Um login do RH por empresa, ativo e com a senha definitiva (não pede troca)
    ativos = _contar(conexao, "usuarios", _filtro_das_empresas(ids) + " AND ativo = 1 AND senha_provisoria = 0 "
                     "AND perfil = 'EMPRESA'", tuple(ids))
    itens.append(_item("usuarios", "logins do RH ativos, com a senha definitiva", len(ids), ativos))
    itens.extend(_sessoes(conexao, roteiro))  # os itens das sessões
    return itens  # a lista de itens desta parte


def _sessoes(conexao, roteiro: dict) -> list[dict]:
    """As entradas no portal: as do roteiro, e nenhuma sessão que ainda valha (todas encerradas e vencidas)."""
    # Os logins do RH e quantos acessos o roteiro tem
    logins, esperadas = [], 0
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        logins.append(empresa["login"])  # o login do RH desta empresa
        esperadas = esperadas + len(empresa["acessos"])  # os acessos desta empresa
    filtro = f"login IN ({carregar_base_viva._marcadores(len(logins))})"
    # Uma sessão "vale" se não foi encerrada e ainda não venceu
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    valendo = 0  # nenhuma sessão valendo, por enquanto
    for expira_em, revogada in conexao.execute(f"SELECT expira_em, revogada FROM sessoes WHERE {filtro}",
                                               tuple(logins)).fetchall():
        if not revogada and expira_em > agora:  # não encerrada e ainda não vencida
            valendo = valendo + 1  # mais uma sessão que ainda vale
    return [_item("sessoes", "acessos do RH ao portal", esperadas, _contar(conexao, "sessoes", filtro, tuple(logins))),
            _item("sessoes", "sessões da carga que ainda valem", 0, valendo)]


def _envios(conexao, roteiro: dict, ids: list[str]) -> list[dict]:
    """Os envios: quantos, em que situação, o mapeamento sem IA, a padronização e a validação."""
    # Quantos envios em cada situação: o que o roteiro manda e o que está no banco
    esperadas, encontradas = {}, {}
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        for envio in empresa["envios"]:  # cada envio da empresa
            situacao = SITUACAO_DE_CADA_DESTINO[envio["destino"]]  # a situação que o destino deixa no banco
            esperadas[situacao] = esperadas.get(situacao, 0) + 1  # mais um envio nesta situação
    for (situacao,) in conexao.execute(f"SELECT status FROM processamentos WHERE {_filtro_das_empresas(ids)}",
                                       tuple(ids)).fetchall():
        encontradas[situacao] = encontradas.get(situacao, 0) + 1  # mais um envio nesta situação, no banco
    total = sum(esperadas.values())  # todos os envios do roteiro
    itens = [_item("processamentos", "envios, por situação", esperadas, encontradas),
             _item("mapeamentos", "mapeamentos (um por envio)", total,
                   _contar(conexao, "mapeamentos", _filtro_das_empresas(ids), tuple(ids)))]
    # Nenhuma coluna pode estar atribuída a um agente de IA (a carga usa só "regra" e "reuso")
    colunas_de_ia = 0
    for (plano,) in conexao.execute(f"SELECT plano FROM mapeamentos WHERE {_filtro_das_empresas(ids)}",
                                    tuple(ids)).fetchall():
        for coluna in MappingPlan.model_validate_json(plano).itens:  # cada coluna do mapeamento
            if coluna.origem in ORIGENS_DE_IA:  # a coluna foi proposta por um agente de IA
                colunas_de_ia = colunas_de_ia + 1  # mais uma coluna de IA (não pode haver nenhuma)
    itens.append(_item("mapeamentos", "colunas atribuídas a um agente de IA", 0, colunas_de_ia))
    # A padronização e a validação: todos os envios, menos o parado no aceite das colunas
    padronizados = total - esperadas.get(EstadoProcessamento.MAPEAMENTO_PENDENTE.value, 0)
    envios = _envios_das_empresas(conexao, ids)  # os envios das empresas da base viva
    itens.append(_item("normalizacoes", "padronizações (todos, menos o parado no aceite)", padronizados,
                       _contar_por_envio(conexao, "normalizacoes", envios)))
    itens.append(_item("validacoes", "validações (todos, menos o parado no aceite)", padronizados,
                       _contar_por_envio(conexao, "validacoes", envios)))
    return itens  # a lista de itens desta parte


def _envios_das_empresas(conexao, ids: list[str]) -> list[str]:
    """Os identificadores de todos os envios das empresas."""
    envios = []  # nenhum envio, por enquanto
    for empresa_id in ids:  # cada empresa da base viva
        envios.extend(carregar_base_viva._envios_da_empresa(conexao, empresa_id))  # os envios desta empresa
    return envios  # todos os envios


def _contar_por_envio(conexao, tabela: str, envios: list[str]) -> int:
    """Quantas linhas da tabela são destes envios."""
    # Sem envio, nenhuma linha
    if not envios:
        return 0  # nenhuma linha
    return _contar(conexao, tabela, f"processamento_id IN ({carregar_base_viva._marcadores(len(envios))})",
                   tuple(envios))


def _cadastrados(conexao, roteiro: dict, ids: list[str]) -> list[dict]:
    """Os cadastrados: homologações, arquivo final em disco, funcionários com CBO válido e o planejamento."""
    # Quantos envios o roteiro leva ao cadastro e quantas pessoas eles cadastram
    envios_cadastrados, pessoas_esperadas = 0, 0
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        for envio in empresa["envios"]:  # cada envio da empresa
            if envio["destino"] == "CADASTRADO":  # o envio chega ao cadastro
                envios_cadastrados = envios_cadastrados + 1  # mais um envio cadastrado
                pessoas_esperadas = pessoas_esperadas + envio["pessoas_novas"]  # as pessoas que ele cadastra
    filtro, valores = _filtro_das_empresas(ids), tuple(ids)  # o filtro das empresas da base viva
    itens = [_item("homologacoes", "envios cadastrados", envios_cadastrados, _contar(conexao, "homologacoes", filtro,
                                                                                         valores)),
             _item("funcionarios_homologados", "funcionários cadastrados", pessoas_esperadas,
                   _contar(conexao, "funcionarios_homologados", filtro, valores)),
             _item("planejamento_funcionario", "funcionários no planejamento", pessoas_esperadas,
                   _contar(conexao, "planejamento_funcionario", filtro, valores))]
    # O arquivo final de cada cadastro: está em disco e cada pessoa tem um código CBO que existe
    arquivos_ok, cbo_valido, pessoas_no_arquivo = 0, 0, 0
    for processamento_id, caminho in conexao.execute(f"SELECT processamento_id, arquivo_final FROM homologacoes "
                                                     f"WHERE {filtro}", valores).fetchall():
        # Sem o arquivo em disco, a lista de funcionários da tela quebraria
        if not Path(caminho).exists():
            continue  # pula este
        arquivos_ok = arquivos_ok + 1  # mais um arquivo final em disco
        # O arquivo final é um CSV com ";" (services/homologacao.py)
        for linha in csv.DictReader(io.StringIO(homologacao.obter(conexao, processamento_id)["arquivo"].decode("utf-8")),
                                    delimiter=";"):
            pessoas_no_arquivo = pessoas_no_arquivo + 1  # mais uma pessoa no arquivo final
            if tabela_cbo.existe(tabela_cbo.codigo_normalizado(linha.get("codigo_cbo") or "")):  # o código CBO existe na tabela oficial
                cbo_valido = cbo_valido + 1  # mais uma pessoa com CBO válido
    itens.append(_item("homologacoes", "arquivo final guardado em disco", envios_cadastrados, arquivos_ok))
    itens.append(_item("arquivo final", "cadastrados com código CBO válido", pessoas_no_arquivo, cbo_valido))
    itens.append(_regiao_do_planejamento(conexao, ids))  # o item da região do planejamento
    return itens  # a lista de itens desta parte


def _regiao_do_planejamento(conexao, ids: list[str]) -> dict:
    """A região do planejamento é a do cadastro da empresa (UF e município), em todos os funcionários."""
    fora_da_regiao = 0  # ninguém fora da região, por enquanto
    for empresa_id in ids:  # cada empresa da base viva
        # A UF e o município do cadastro da empresa
        uf, municipio = conexao.execute("SELECT uf, municipio FROM empresas WHERE empresa_id = ?",
                                        (empresa_id,)).fetchone()
        # Quem está no planejamento com outra região
        fora_da_regiao = fora_da_regiao + _contar(conexao, "planejamento_funcionario",
                                                  "empresa_id = ? AND (uf <> ? OR municipio <> ?)",
                                                  (empresa_id, uf, municipio))
    return _item("planejamento_funcionario", "funcionários fora da região do cadastro da empresa", 0, fora_da_regiao)


def _profissoes_e_contas(conexao, roteiro: dict, ids: list[str], minimo_de_profissoes_ligadas: int) -> list[dict]:
    """A profissão de cada cargo (a faixa das outras empresas ligada) e as contas abertas.

    minimo_de_profissoes_ligadas: quantas profissões, pelo menos, já têm a faixa das outras empresas (2 empresas e 10
    pessoas, ADR-129). Com a base viva inteira, são mais de 20; nos testes, com poucas pessoas, pode ser nenhuma.
    """
    filtro, valores = _filtro_das_empresas(ids), tuple(ids)  # o filtro das empresas da base viva
    # A validação grava a profissão de cada cargo que veio com o código CBO: toda empresa com envio validado a tem
    com_cargos, com_envio_validado = 0, 0
    for empresa_id in ids:  # cada empresa da base viva
        if _contar(conexao, "cbo_dos_cargos", "empresa_id = ?", (empresa_id,)) > 0:  # a empresa tem profissões
            com_cargos = com_cargos + 1  # mais uma empresa com a profissão dos cargos
        if _contar_por_envio(conexao, "validacoes", carregar_base_viva._envios_da_empresa(conexao, empresa_id)) > 0:
            com_envio_validado = com_envio_validado + 1  # mais uma empresa com envio validado
    itens = [_item("cbo_dos_cargos", "empresas com envio validado que têm a profissão dos cargos",
                   com_envio_validado, com_cargos)]
    # A faixa das outras empresas (ADR-129), como uma empresa de fora da base viva a veria
    ligadas = 0
    for (codigo,) in conexao.execute("SELECT DISTINCT codigo_cbo FROM cbo_dos_cargos WHERE " + filtro,
                                     valores).fetchall():
        if faixa_salarial_cbo.faixa_das_outras_empresas(conexao, "EMP001", codigo) is not None:  # a faixa das outras empresas existe
            ligadas = ligadas + 1  # mais uma profissão com a faixa ligada
    itens.append({"onde": "cbo_dos_cargos", "o_que": "profissões com a faixa das outras empresas ligada",
                  "esperado": f"{minimo_de_profissoes_ligadas} ou mais", "encontrado": ligadas,
                  "bateu": ligadas >= minimo_de_profissoes_ligadas})
    # As contas e os arquivos de contas que o roteiro manda dar baixa
    contas_esperadas, arquivos_esperados = 0, 0
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        for envio in empresa["envios"]:  # cada envio da empresa
            if envio["contas"] is not None:  # o banco já devolveu as contas deste envio
                arquivos_esperados = arquivos_esperados + 1  # mais um arquivo de contas
                contas_esperadas = contas_esperadas + len(envio["contas"]["pessoas"])  # as contas deste arquivo
    itens.append(_item("contas_abertas", "contas abertas e correntistas", contas_esperadas,
                       _contar(conexao, "contas_abertas", filtro, valores)))
    itens.append(_item("arquivos_de_contas", "arquivos de contas confirmados", arquivos_esperados,
                       _contar(conexao, "arquivos_de_contas", filtro + " AND situacao = 'CONFIRMADO'", valores)))
    return itens  # a lista de itens desta parte


def _trilhas_e_fluxos(conexao, roteiro: dict, ids: list[str]) -> list[dict]:
    """A trilha de cada envio (os eventos da etapa), as datas (nada no futuro) e o fluxo parado na etapa certa."""
    trilhas_completas, fluxos_certos, total = 0, 0, 0  # as contagens começam em zero
    for empresa_id, empresa in zip(_ids_na_ordem_do_roteiro(conexao, roteiro), roteiro["empresas"]):
        # Os envios da empresa na ordem em que chegaram (a mesma do roteiro)
        envios = conexao.execute("SELECT processamento_id FROM processamentos WHERE empresa_id = ? "
                                 "ORDER BY criado_em, rowid", (empresa_id,)).fetchall()
        for (processamento_id,), envio in zip(envios, empresa["envios"]):
            total = total + 1  # mais um envio conferido
            # Os tipos de evento da trilha do envio
            tipos = set()
            for (tipo,) in conexao.execute("SELECT tipo FROM eventos WHERE processamento_id = ?",
                                           (processamento_id,)).fetchall():
                tipos.add(tipo)  # o tipo deste evento
            # A trilha tem todos os eventos da etapa em que o envio está
            if set(EVENTOS_DE_CADA_DESTINO[envio["destino"]]) <= tipos:
                trilhas_completas = trilhas_completas + 1  # mais uma trilha completa
            # O fluxo parado na pausa do destino (o cadastrado terminou: nenhuma pausa)
            pausa = carregar_base_viva.PAUSA_DE_CADA_DESTINO.get(envio["destino"])
            if fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"] == pausa:
                fluxos_certos = fluxos_certos + 1  # mais um fluxo na etapa certa
    # As datas dos eventos: nenhuma no futuro e nenhuma antes do começo da história
    agora = datetime.now(timezone.utc)
    mais_antiga = (agora - timedelta(days=DIAS_DA_HISTORIA)).isoformat(timespec="seconds")  # o começo mais antigo possível da história
    fora_do_periodo = 0  # nenhum evento fora, por enquanto
    for (quando,) in conexao.execute(f"SELECT criado_em FROM eventos WHERE {_filtro_das_empresas(ids)}",
                                     tuple(ids)).fetchall():
        if quando > agora.isoformat(timespec="seconds") or quando < mais_antiga:  # no futuro ou antigo demais
            fora_do_periodo = fora_do_periodo + 1  # mais um evento fora do período
    return [_item("eventos", "envios com a trilha completa da etapa", total, trilhas_completas),
            _item("eventos", "eventos no futuro ou antes de ~3 meses e meio", 0, fora_do_periodo),
            _item("pontos de salvamento", "envios com o fluxo parado na etapa certa (ou encerrado)", total,
                  fluxos_certos)]


def _ids_na_ordem_do_roteiro(conexao, roteiro: dict) -> list[str]:
    """O id de cada empresa do roteiro, na ordem do roteiro (achado pelo CNPJ)."""
    ids = []  # nenhuma empresa, por enquanto
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        # O id depende de quantas empresas já existiam: a empresa é achada pelo CNPJ
        linha = conexao.execute("SELECT empresa_id FROM empresas WHERE cnpj = ?", (empresa["cnpj"],)).fetchone()
        ids.append(linha[0] if linha else None)  # o id, ou None se a empresa não está no banco
    return ids  # os ids na ordem do roteiro


def _o_que_a_base_viva_nao_tem(conexao, ids: list[str]) -> list[dict]:
    """Nenhuma execução de IA, nenhum par no histórico de mapeamentos e o conteúdo da IA vazio (de propósito)."""
    filtro, valores = _filtro_das_empresas(ids), tuple(ids)  # o filtro das empresas da base viva
    itens = [_item("execucoes_agentes", "execuções de agentes de IA da base viva", 0,
                   _contar(conexao, "execucoes_agentes", filtro, valores)),
             _item("historico_mapeamentos", "pares no histórico (o conhecimento da IA)", 0,
                   _contar(conexao, "historico_mapeamentos", filtro, valores))]
    for tabela in TABELAS_QUE_FICAM_VAZIAS:  # cada tabela do conteúdo da IA
        colunas = banco.colunas_da_tabela(conexao, tabela)  # as colunas dela (vazio se não existe)
        # A tabela com a empresa: nenhuma linha das empresas da base viva
        if "empresa_id" in colunas:
            itens.append(_item(tabela, "vazio de propósito (conteúdo da IA)", 0, _contar(conexao, tabela, filtro, valores)))
        # As KBs têm um "dono" (a empresa): nenhuma das empresas da base viva, fora a KB do kit (não é da IA)
        elif "dono" in colunas:
            filtro_das_kbs = f"dono IN ({carregar_base_viva._marcadores(len(ids))}) AND tipo <> ?"  # sem a KB do kit
            itens.append(_item(tabela, "vazio de propósito (conteúdo da IA)", 0,
                               _contar(conexao, tabela, filtro_das_kbs, valores + (TIPO_DE_KB_QUE_NAO_E_DA_IA,))))
    return itens  # a lista de itens desta parte


def _conversas_e_acessos(conexao, roteiro: dict, ids: list[str]) -> list[dict]:
    """As conversas com o banco e as aberturas da lista de funcionários."""
    # O que o roteiro manda: mensagens, conversas resolvidas e aberturas da lista
    mensagens, resolvidas, acessos = 0, 0, 0
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        acessos = acessos + len(empresa["acessos_aos_dados"])  # as aberturas da lista desta empresa
        if empresa["conversa"] is not None:  # a empresa escreveu ao banco
            mensagens = mensagens + len(empresa["conversa"]["mensagens"])  # as mensagens da conversa
            resolvidas = resolvidas + (1 if empresa["conversa"]["resolvida"] else 0)  # a conversa resolvida conta 1
    filtro, valores = _filtro_das_empresas(ids), tuple(ids)  # o filtro das empresas da base viva
    return [_item("mensagens_de_ajuda", "mensagens do \"Posso ajudar?\"", mensagens,
                  _contar(conexao, "mensagens_de_ajuda", filtro, valores)),
            _item("conversas_resolvidas", "conversas marcadas como resolvidas", resolvidas,
                  _contar(conexao, "conversas_resolvidas", filtro, valores)),
            _item("acessos_a_dados", "aberturas e downloads da lista de funcionários", acessos,
                  _contar(conexao, "acessos_a_dados", filtro, valores))]


# ================================ As telas ================================

def _telas(conexao, roteiro: dict, ids: list[str]) -> list[dict]:
    """As funções que as telas chamam, com a base viva: rodam, mostram números e quanto tempo levam."""
    itens = []  # nenhum item, por enquanto
    # O Início do banco: a carteira inteira, e quanto tempo leva para montar
    inicio = time.time()
    numeros = portal_do_banco.inicio_do_banco(conexao)["numeros"]  # os números do alto do Início
    itens.append(_item("tela Início do banco", "empresas da carteira (as 17 contam)", True, numeros["empresas"] >= len(ids)))
    segundos = time.time() - inicio  # quanto tempo o Início levou
    itens.append({"onde": "tela Início do banco", "o_que": "tempo para montar", "esperado": "menos de 15 s",
                  "encontrado": f"{segundos:.1f} s", "bateu": segundos < 15})
    # A fila da aba Envios: os envios da base viva que esperam o banco
    aguardando = 0
    for envio in avaliacao_do_banco.fila_sem_conferir_perfil(conexao):  # cada envio da fila do banco
        if envio["empresa_id"] in ids and envio["situacao"] == "aguardando":  # da base viva, esperando o banco
            aguardando = aguardando + 1  # mais um esperando o banco
    esperados = 0  # nenhum esperado, por enquanto
    for empresa in roteiro["empresas"]:  # cada empresa do roteiro
        for envio in empresa["envios"]:  # cada envio da empresa
            if envio["destino"] == "EM_ANALISE":  # o roteiro deixa este envio em análise
                esperados = esperados + 1  # mais um em análise
    itens.append(_item("tela Envios", "envios da base viva esperando o banco", esperados, aguardando))
    # A Telemetria (uso das empresas): cada empresa com acessos e envios no funil
    uso = portal_do_banco.uso_das_empresas(conexao)
    com_uso = 0  # nenhuma empresa com uso, por enquanto
    for empresa in uso["empresas"]:  # cada empresa do uso
        if empresa["id"] in ids and empresa["acessos"] > 0 and empresa["funil"][0] > 0:  # com acessos e envios
            com_uso = com_uso + 1  # mais uma empresa com uso
    itens.append(_item("tela Telemetria (uso das empresas)", "empresas com acessos e envios", len(ids), com_uso))
    # O Planejamento: cadastrados e contas nos números
    resumo = portal_do_banco.numeros_do_planejamento(conexao, {})["resumo"]
    itens.append(_item("tela Planejamento", "cadastrados e contas nos números", True,
                       resumo["cadastrados"] > 0 and resumo["contas_abertas"] > 0))
    # O portal de cada empresa: o resumo e a lista de funcionários montam sem erro
    portais_ok = 0
    for empresa_id in ids:  # cada empresa da base viva
        resumo_da_empresa = acompanhamento.resumo_da_empresa(conexao, empresa_id)  # o resumo do alto do portal
        acompanhamento.todos_os_funcionarios_da_empresa(conexao, empresa_id)  # a lista de funcionários monta
        if resumo_da_empresa["envios"] > 0:  # o portal mostra envios
            portais_ok = portais_ok + 1  # mais um portal com envios
    itens.append(_item("tela Acompanhar cadastros (empresa)", "portais das 17 com envios", len(ids), portais_ok))
    return itens  # a lista de itens desta parte


def conferir(conexao, roteiro: dict, minimo_de_profissoes_ligadas: int = 10) -> list[dict]:
    """A lista de conferência inteira. Devolve os itens: {onde, o_que, esperado, encontrado, bateu}.

    minimo_de_profissoes_ligadas: veja _profissoes_e_contas (a base inteira liga mais de 20).
    """
    # As empresas da base viva (as da marca da carga)
    ids = []  # nenhuma empresa, por enquanto
    for empresa in carregar_base_viva.empresas_da_base_viva(conexao):  # cada empresa da marca da carga
        ids.append(empresa["empresa_id"])  # o id dela
    # Nada carregado: um item só, que não bate
    if not ids:
        return [_item("empresas", "empresas criadas pela carga", len(roteiro["empresas"]), 0)]
    # As tabelas, o que a base viva não pode ter e as telas
    itens = []  # nenhum item, por enquanto
    itens.extend(_empresas_e_logins(conexao, roteiro, ids))
    itens.extend(_envios(conexao, roteiro, ids))
    itens.extend(_cadastrados(conexao, roteiro, ids))
    itens.extend(_profissoes_e_contas(conexao, roteiro, ids, minimo_de_profissoes_ligadas))
    itens.extend(_trilhas_e_fluxos(conexao, roteiro, ids))
    itens.extend(_conversas_e_acessos(conexao, roteiro, ids))
    itens.extend(_o_que_a_base_viva_nao_tem(conexao, ids))
    itens.extend(_telas(conexao, roteiro, ids))
    return itens  # a lista de itens desta parte


def em_tabela(itens: list[dict]) -> str:
    """A lista em Markdown (uma linha por item), para o relatório."""
    linhas = ["| Onde | O que | Esperado | Encontrado | Bateu |", "|---|---|---|---|---|"]  # o cabeçalho da tabela
    for item in itens:  # cada item da lista
        # O esperado e o encontrado em JSON (os dicionários ficam legíveis numa linha)
        linhas.append(f"| {item['onde']} | {item['o_que']} | {json.dumps(item['esperado'], ensure_ascii=False)} | "
                      f"{json.dumps(item['encontrado'], ensure_ascii=False)} | {'sim' if item['bateu'] else 'NÃO'} |")
    return "\n".join(linhas)  # a tabela inteira, uma linha por item


def main() -> None:
    """Confere a base viva no banco do .env e escreve a lista. Sai com 1 se algum item não bateu."""
    # O roteiro da base viva (o que devia estar no banco)
    roteiro = json.loads((gerar_base_viva.PASTA_DA_BASE_VIVA / gerar_base_viva.NOME_DO_ROTEIRO).read_text(
        encoding="utf-8"))
    conexao = banco.conectar()  # o banco do .env
    try:
        itens = conferir(conexao, roteiro)  # a lista de conferência inteira
    finally:
        conexao.close()  # fecha o banco, mesmo se der erro
    print(em_tabela(itens))  # a lista, em tabela
    # Quantos itens não bateram
    falhas = 0
    for item in itens:  # cada item da lista
        if not item["bateu"]:  # este item não bateu
            falhas = falhas + 1  # mais uma falha
    print(f"\n{len(itens) - falhas} de {len(itens)} itens bateram.")
    # A saída 1 avisa quem chamou que algo não bateu
    if falhas:
        sys.exit(1)  # a saída 1: algo não bateu


if __name__ == "__main__":
    main()  # roda a conferência
