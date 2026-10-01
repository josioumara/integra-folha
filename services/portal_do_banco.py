"""Portal do Banco no novo front: as telas do especialista com dados reais (ADR-69).

Para que serve: dá às telas do Portal do Banco (front/banco_*.html) os dados que a aplicação já tem:
    - Início (carteira e fila do dia) e Empresas (ficha, usuários do RH e catálogo);
    - Planejamento (antigo Cockpit);
    - Telemetria: o uso das empresas (acessos, funil, linha do tempo) e o desempenho da IA (execuções dos agentes).
No Planejamento, a tela precisa dos mesmos números do motor de planejamento. Este arquivo NÃO faz conta nova: chama services/planejamento.py (as somas do motor de
planejamento, sempre agregadas, e a fórmula do ganho) e devolve tudo num formato simples para a tela (JSON: dinheiro
em texto, para não perder centavos).

Regras que continuam valendo, porque vêm dos serviços de sempre:
    - só números agregados, nunca pessoas (ADR-25);
    - o potencial só é projetado com a taxa de conquista e a % que já é correntista informadas, nunca com um valor
      padrão (ADR-26); o simulador muda as premissas só na simulação, nunca as oficiais;
    - salvar simulação é uma operação do perfil BANCO (services/permissoes.py).

Os filtros chegam como texto; texto vazio quer dizer "todos" (None para o serviço).
"""
# O arquivo da Visão geral (os funcionários da empresa em CSV): o escritor de CSV e o texto em memória
import csv
import io
import re
import secrets
from datetime import datetime, timedelta, timezone

from models.contratos import Perfil
from services import (acesso, acompanhamento, auditoria, auth, avaliacao_do_banco, catalogo, contas_abertas, dados_mock,
                      painel, planejamento, sessoes, teto_de_gasto)
from services import empresas as cadastro_de_empresas
from services import aceitacao_dos_agentes
# A proteção contra fórmula do Excel, a mesma do arquivo final da homologação ("CSV injection")
from services import homologacao

# Quantas execuções recentes a sub-aba Desempenho da IA mostra
EXECUCOES_RECENTES = 20

# Os campos de uma execução que a sub-aba Desempenho da IA mostra (nada de dado de pessoa: só etapa, agente, tempo e custo)
CAMPOS_DA_EXECUCAO = ("inicio", "empresa_id", "etapa", "agente", "modelo", "status", "duracao_s", "tokens_entrada",
                      "custo_usd", "origem")

# Os filtros que a tela pode mandar, na ordem dos parâmetros de services/planejamento.py (o segmento saiu com a base
# do banco: nada mais diz o segmento de cada pessoa)
NOMES_DOS_FILTROS = ("empresa_id", "uf", "data_referencia")


def filtros_limpos(filtros: dict) -> dict:
    """Deixa só os filtros conhecidos, com texto vazio virando None ("todos").

    Recebe: filtros — o que a tela mandou (ex.: {"empresa_id": "EMP001", "uf": ""}).
    Devolve: {"empresa_id": "EMP001", "uf": None, "data_referencia": None}.
    """
    limpos = {}
    for nome in NOMES_DOS_FILTROS:
        valor = filtros.get(nome)
        # Vazio, só espaços ou ausente: sem filtro
        if not valor or not str(valor).strip():
            limpos[nome] = None
        else:
            limpos[nome] = str(valor).strip()
    return limpos


def filtros_do_planejamento(conexao) -> dict:
    """As opções das listas de filtro: só os valores que existem nos números do motor.

    Recebe: conexao. Devolve: {empresas: [{id, nome}], ufs: [...], datas: [...]}.
    """
    # As empresas com números, com o nome para a tela
    empresas = []
    for empresa_id in planejamento.valores_para_filtro(conexao, "empresa_id"):
        empresas.append({"id": empresa_id, "nome": dados_mock.nome_da_empresa(empresa_id)})
    return {
        "empresas": empresas,
        "ufs": planejamento.valores_para_filtro(conexao, "uf"),
        "datas": planejamento.valores_para_filtro(conexao, "data_referencia"),
    }


def numeros_do_planejamento(conexao, filtros: dict) -> dict:
    """Os números da tela com os filtros: indicadores, resumo, por empresa e por região.

    Recebe: conexao; filtros (da tela). Devolve: um dicionário pronto para virar JSON.
    """
    # Os filtros no formato do serviço
    limpos = filtros_limpos(filtros)
    empresa, uf, data = limpos["empresa_id"], limpos["uf"], limpos["data_referencia"]
    return {
        "indicadores": planejamento.indicadores(conexao, empresa, uf, data),
        "resumo": planejamento.resumir(conexao, empresa, uf, data),
        # "Por empresa" respeita todos os filtros: com uma empresa escolhida no filtro do alto, só ela
        "por_empresa": planejamento.por_empresa(conexao, uf, data, empresa),
        # "Por região" respeita a empresa escolhida
        "por_regiao": planejamento.por_regiao(conexao, empresa, data),
    }


def _ids_das_empresas(empresa_id: str | None) -> list[str]:
    """As empresas de uma simulação: a escolhida, ou todas as da carteira (empresa_id None).

    Levanta ValueError se a empresa escolhida não é da carteira. Ex.: "EMP001" → ["EMP001"]; None → todas.
    """
    ids_da_carteira = []
    for empresa in dados_mock.empresas():
        ids_da_carteira.append(empresa["empresa_id"])
    if empresa_id is None:
        return ids_da_carteira
    if empresa_id not in ids_da_carteira:
        raise ValueError("Empresa não encontrada na carteira.")
    return [empresa_id]


def base_da_empresa(conexao, empresa_id: str | None) -> dict:
    """Os clientes que a empresa enviou, para a seção travada do simulador: os cadastrados e os em análise pelo banco.

    Recebe: conexao; empresa_id (None: todas as empresas da carteira).
    Devolve: {"empresa_id", "cadastrados", "em_analise", "enviados"} (enviados = cadastrados + em análise).
    Por quê numa rota própria: contar os em análise monta a lista inteira de funcionários de cada empresa (conta que
    custa). A tela pede uma vez, quando a empresa muda, e manda o número em cada simulação (não a cada tecla).
    Exemplo: 300 cadastrados e 12 em análise → enviados 312.
    """
    cadastrados = 0
    em_analise = 0
    for identificador in _ids_das_empresas(empresa_id):
        cadastrados = cadastrados + len(acompanhamento.funcionarios_da_empresa(conexao, identificador))
        em_analise = em_analise + acompanhamento.pessoas_em_analise_pelo_banco(conexao, identificador)
    return {"empresa_id": empresa_id, "cadastrados": cadastrados, "em_analise": em_analise,
            "enviados": cadastrados + em_analise}


def _base_da_simulacao(simulacao: dict, clientes_da_empresa) -> dict:
    """A base de clientes da simulação: a estimativa da especialista substitui o que a empresa enviou.

    Recebe: simulacao (de planejamento.premissas_do_simulador); clientes_da_empresa (o número que a tela recebeu de
    base_da_empresa, em texto ou número). Devolve: {"clientes", "origem" ("estimativa" ou "empresa")}.
    Levanta ValueError se o número da empresa não é um inteiro válido. Ex.: estimativa 1200 → {1200, "estimativa"}.
    """
    # A estimativa da especialista, quando digitada, é a base (ela substitui o número da empresa)
    if simulacao["clientes_estimados"] is not None:
        return {"clientes": simulacao["clientes_estimados"], "origem": "estimativa"}
    # Senão, os clientes que a empresa enviou (conferidos como a estimativa: inteiro de 0 ao máximo)
    clientes = planejamento.clientes_conferidos({"clientes": clientes_da_empresa}, "clientes")
    return {"clientes": clientes or 0, "origem": "empresa"}


def simular(conexao, filtros: dict, valores: dict, clientes_da_empresa=None) -> dict:
    """O Simulador de Rentabilidade, sem gravar nada: a base de clientes × as três taxas × as premissas globais.

    Recebe: conexao; filtros ({"empresa_id"} ou vazio: todas); valores — o que a especialista mudou (premissas
    globais, as três taxas, a estimativa de clientes); clientes_da_empresa — os enviados (de base_da_empresa).
    Devolve: {"valores", "alteradas", "versao_premissas", "base": {clientes, origem}, "simulacao": {clientes, linhas,
    total, falta}, "confirmado": o que o retorno do banco já confirmou (referência, com as taxas observadas)}.
    Levanta ValueError (400) com a mensagem para a pessoa se um valor for inválido. As premissas oficiais não mudam.
    """
    limpos = filtros_limpos(filtros)
    simulacao = planejamento.premissas_do_simulador(conexao, valores)
    base = _base_da_simulacao(simulacao, clientes_da_empresa)
    resultado = planejamento.simular_rentabilidade(base["clientes"], simulacao["taxas"], simulacao["premissas"])
    # A referência: o que o retorno do banco já confirmou para a mesma empresa (ou para todas)
    resumo = planejamento.resumir(conexao, limpos["empresa_id"], None, None)
    confirmado = planejamento.retorno_confirmado(resumo, simulacao["premissas"])
    return {"valores": simulacao["valores"], "alteradas": simulacao["alteradas"],
            "versao_premissas": simulacao["premissas"].versao, "base": base, "simulacao": resultado,
            "confirmado": confirmado}


def salvar_simulacao(conexao, usuario, nome: str, filtros: dict, valores: dict, clientes_da_empresa=None) -> dict:
    """Guarda a simulação com o nome dado, quem simulou, a empresa, os valores, a base e o resultado. Devolve a salva.

    Recebe: os mesmos dados de simular, mais usuario (services/acesso.py confere que é do banco) e nome (obrigatório).
    As premissas oficiais não mudam.
    """
    limpos = filtros_limpos(filtros)
    simulacao = planejamento.premissas_do_simulador(conexao, valores)
    base = _base_da_simulacao(simulacao, clientes_da_empresa)
    resultado = planejamento.simular_rentabilidade(base["clientes"], simulacao["taxas"], simulacao["premissas"])
    acesso.salvar_simulacao(conexao, usuario, nome, simulacao, base, resultado, limpos)
    # A salva é a mais recente da lista
    return simulacoes_salvas(conexao)[0]


def simulacoes_salvas(conexao) -> list[dict]:
    """As simulações salvas, da mais recente para a mais antiga: nome, quem, quando, empresa, valores, base e ganho.

    Devolve: [{id, nome, criado_em, usuario, filtros, versao_premissas, valores, base, ganho_total, simulacao (o
    detalhe por grupo, para a janela "Visualizar")}] (dinheiro em texto; ganho_total None quando faltou taxa). Simulação antiga, de antes do nome, vem com o nome vazio (a tela diz
    "Simulação sem nome"); de antes do Simulador de Rentabilidade, vem sem base (None).
    """
    return planejamento.simulacoes(conexao)


# ---------------- Início do Portal do Banco ----------------

def _situacao_da_empresa(resumo: dict) -> dict:
    """A situação da empresa na carteira, com a cor do selo.

    Recebe: resumo — o de acompanhamento.resumo_da_empresa. Devolve: {texto, classe}.
    Sem envio nenhum: "Sem carga" (laranja: precisa de contato). Com pendência: "Com pendência" (laranja).
    Com envio em andamento: "Em andamento". O resto: "Em dia" (verde).
    """
    if resumo["envios"] == 0:
        return {"texto": "Sem carga", "classe": "selo-atencao"}
    if resumo["com_pendencia"] > 0:
        return {"texto": "Com pendência", "classe": "selo-atencao"}
    if resumo["em_andamento"] > 0:
        return {"texto": "Em andamento", "classe": "selo-marca"}
    return {"texto": "Em dia", "classe": "selo-sucesso"}


def carteira(conexao) -> list[dict]:
    """As empresas da carteira, uma linha por empresa, com os números de cadastro e a situação.

    Recebe: conexao. Devolve: lista de {id, nome, setor, cidade, cadastrados, envios, em_andamento, com_pendencia,
    ultimo_envio, situacao, contas}. Só contagens: nenhum funcionário aparece aqui (contas: {cadastrados, com_conta,
    percentual, arquivo_recebido}, da baixa do arquivo semanal do banco).
    """
    linhas = []
    for empresa in dados_mock.empresas():
        # Os números da empresa (os mesmos que ela vê em Acompanhar cadastros)
        resumo = acompanhamento.resumo_da_empresa(conexao, empresa["empresa_id"])
        envios = acompanhamento.envios_da_empresa(conexao, empresa["empresa_id"])
        # O envio mais recente (a lista já vem do mais recente para o mais antigo)
        ultimo_envio = None
        if envios:
            ultimo_envio = envios[0]["enviado_em"]
        linhas.append({
            "id": empresa["empresa_id"],
            "nome": empresa["nome"],
            "setor": empresa["setor"],
            "cidade": empresa["municipio"] + "/" + empresa["uf"],
            "cadastrados": resumo["cadastrados"],
            "envios": resumo["envios"],
            "em_andamento": resumo["em_andamento"],
            "com_pendencia": resumo["com_pendencia"],
            "ultimo_envio": ultimo_envio,
            "situacao": _situacao_da_empresa(resumo),
            "contas": contas_abertas.numeros_de_contas(conexao, empresa["empresa_id"]),
        })
    return linhas


def _contas_da_carteira(linhas_da_carteira: list[dict]) -> dict:
    """As contas abertas somadas da carteira: {cadastrados, com_conta, percentual, arquivo_recebido}."""
    cadastrados = 0
    com_conta = 0
    arquivo_recebido = False
    for linha in linhas_da_carteira:
        cadastrados = cadastrados + linha["contas"]["cadastrados"]
        com_conta = com_conta + linha["contas"]["com_conta"]
        # O arquivo de contas é subido por empresa (ADR-122): a carteira já recebeu se alguma empresa recebeu
        if linha["contas"]["arquivo_recebido"]:
            arquivo_recebido = True
    percentual = 0
    if cadastrados:
        percentual = round(100 * com_conta / cadastrados)
    return {"cadastrados": cadastrados, "com_conta": com_conta, "percentual": percentual,
            "arquivo_recebido": arquivo_recebido}


def _fila_do_dia(linhas_da_carteira: list[dict], envios_para_avaliar: list[dict]) -> list[dict]:
    """"O que precisa de você": primeiro os envios esperando a sua avaliação, depois as empresas sem carga, as com
    pendência e as em andamento.

    Recebe: as linhas da carteira; os envios esperando o banco (da fila da aba Envios).
    Devolve: lista de {titulo, detalhe, urgente, empresa_id, envio_id}.
    """
    avaliar = []
    for envio in envios_para_avaliar:
        # Atrasado é urgente; dentro do prazo, entra antes das empresas, mas sem a marca de urgente
        avaliar.append({"titulo": "Avaliar o envio da " + envio["empresa"], "empresa_id": envio["empresa_id"],
                        "envio_id": envio["id"], "urgente": envio["prazo"]["classe"] == "selo-atencao",
                        "detalhe": envio["tipo"] + " · " + envio["prazo"]["texto"]})
    sem_carga, com_pendencia, em_andamento = [], [], []
    for linha in linhas_da_carteira:
        if linha["envios"] == 0:
            sem_carga.append({"titulo": "Falar com a " + linha["nome"], "empresa_id": linha["id"], "urgente": True,
                              "detalhe": "Contrato assinado e nenhuma carga enviada"})
        elif linha["com_pendencia"] > 0:
            com_pendencia.append({"titulo": "Ajudar a " + linha["nome"] + " com as pendências", "empresa_id": linha["id"],
                                  "urgente": False,
                                  "detalhe": str(linha["com_pendencia"]) + " envio(s) parados em pendências de dados"})
        elif linha["em_andamento"] > 0:
            em_andamento.append({"titulo": "Acompanhar o envio da " + linha["nome"], "empresa_id": linha["id"],
                                 "urgente": False, "detalhe": str(linha["em_andamento"]) + " envio(s) em andamento"})
    return avaliar + sem_carga + com_pendencia + em_andamento


def inicio_do_banco(conexao) -> dict:
    """Tudo o que o Início do Portal do Banco mostra: os números, a fila do dia e a carteira.

    Recebe: conexao. Devolve: {numeros: {empresas, cadastrados, envios_em_andamento, empresas_sem_carga,
    envios_para_avaliar, envios_atrasados}, fila: [...], carteira: [...]}.
    """
    linhas = carteira(conexao)
    # Os envios que esperam a avaliação do banco (e quantos passaram do prazo)
    envios_para_avaliar = []
    atrasados = 0
    for envio in avaliacao_do_banco.fila_sem_conferir_perfil(conexao):
        if envio["situacao"] == "aguardando":
            envios_para_avaliar.append(envio)
            if envio["prazo"]["classe"] == "selo-atencao":
                atrasados = atrasados + 1
    # Os números de cima, somados da carteira
    cadastrados, em_andamento, sem_carga = 0, 0, 0
    for linha in linhas:
        cadastrados = cadastrados + linha["cadastrados"]
        em_andamento = em_andamento + linha["em_andamento"]
        if linha["envios"] == 0:
            sem_carga = sem_carga + 1
    return {
        "numeros": {"empresas": len(linhas), "cadastrados": cadastrados, "envios_em_andamento": em_andamento,
                    "empresas_sem_carga": sem_carga, "envios_para_avaliar": len(envios_para_avaliar),
                    "envios_atrasados": atrasados, "contas": _contas_da_carteira(linhas)},
        "fila": _fila_do_dia(linhas, envios_para_avaliar),
        "carteira": linhas,
    }


# ---------------- Telemetria: uso das empresas ----------------

# As etapas do funil real, na ordem, com o evento da auditoria que conta cada uma (um por envio)
ETAPAS_DO_FUNIL_REAL = (
    ("Mandaram um arquivo", "RECEBIDO"),
    ("Os agentes leram as colunas", "MAPEAMENTO_PROPOSTO"),
    ("Conferiram as colunas", "MAPEAMENTO_APROVADO"),
    ("Cadastrados", "HOMOLOGADO"),
)

# Como cada evento aparece na linha do tempo da empresa
NOME_DO_EVENTO = {
    "RECEBIDO": "mandou um arquivo",
    "MAPEAMENTO_PROPOSTO": "os agentes leram as colunas",
    "MAPEAMENTO_APROVADO": "conferiu e aceitou as colunas",
    "ENVIADO_AO_BANCO": "enviou ao banco",
    "DEVOLVIDO_PELO_BANCO": "o banco devolveu com um motivo",
    "HOMOLOGADO": "cadastro concluído",
    "REJEITADO": "leitura descartada",
    "REENVIO_IDENTICO": "mandou de novo o mesmo arquivo",
}


def _acessos_por_empresa(conexao) -> dict:
    """Quantas vezes as pessoas de cada empresa entraram no portal e quando foi a última vez.

    Recebe: conexao. Devolve: {empresa_id: {"acessos": N, "ultimo_acesso": texto ou None}}.
    Cada login cria uma sessão (services/sessoes.py): contar as sessões é contar as entradas.
    """
    # Garante que as tabelas de usuários e de sessões existem (numa aplicação nova, ninguém entrou ainda)
    auth.preparar_tabela(conexao)
    sessoes.preparar_tabela(conexao)
    consulta = conexao.execute(
        "SELECT usuarios.empresa_id, COUNT(*), MAX(sessoes.criada_em) FROM sessoes "
        "JOIN usuarios ON usuarios.login = sessoes.login WHERE usuarios.empresa_id IS NOT NULL "
        "GROUP BY usuarios.empresa_id")
    acessos = {}
    for empresa_id, quantidade, ultimo in consulta:
        acessos[empresa_id] = {"acessos": quantidade, "ultimo_acesso": ultimo}
    return acessos


def _eventos_por_empresa(todos_os_eventos: list[dict]) -> dict:
    """Os eventos da auditoria que contam no uso, separados por empresa e em ordem.

    Recebe: todos_os_eventos — os da auditoria (auditoria.eventos), na ordem em que aconteceram.
    Devolve: {empresa_id: [evento, ...]}. Só os tipos de NOME_DO_EVENTO (nada de detalhe pessoal).
    """
    por_empresa = {}
    for evento in todos_os_eventos:
        if evento["tipo"] in NOME_DO_EVENTO:
            por_empresa.setdefault(evento["empresa_id"], []).append(evento)
    return por_empresa


def _funil(eventos: list[dict]) -> list[int]:
    """Quantos envios chegaram a cada etapa do funil (cada envio conta uma vez por etapa).

    Recebe: os eventos de uma empresa. Devolve: uma contagem por etapa, na ordem de ETAPAS_DO_FUNIL_REAL.
    """
    contagens = []
    for _, tipo in ETAPAS_DO_FUNIL_REAL:
        envios_que_chegaram = set()
        for evento in eventos:
            if evento["tipo"] == tipo:
                envios_que_chegaram.add(evento["processamento_id"])
        contagens.append(len(envios_que_chegaram))
    return contagens


# ---------------- Telemetria: tempo até a avaliação do banco ----------------

# Os eventos da auditoria que marcam a decisão do banco sobre um envio: aprovar (os funcionários ficam cadastrados)
# ou devolver com um motivo (gravados por workflows/fluxo_empresa.py, na etapa avaliar_no_banco)
EVENTOS_DA_DECISAO_DO_BANCO = ("APROVADO_PELO_BANCO", "DEVOLVIDO_PELO_BANCO")
# O horário de Brasília (3 horas atrás do horário universal; o Brasil não tem horário de verão desde 2019).
# A auditoria grava no horário universal, mas é no horário do Brasil que se sabe se o dia é sábado ou domingo.
FUSO_DE_BRASILIA = timezone(timedelta(hours=-3))
# Quantos segundos tem um dia inteiro (24 horas)
SEGUNDOS_POR_DIA = 24 * 60 * 60
# O período que os cartões do uso cobrem: todos contam desde o começo (não só o mês)
PERIODO_DO_USO = "desde o começo"


def dias_uteis_entre(inicio_em_texto: str, fim_em_texto: str) -> float:
    """Quanto tempo passou entre dois momentos, contando só os dias úteis (segunda a sexta).

    Recebe: inicio_em_texto e fim_em_texto — datas e horas como a auditoria grava (ex.: "2026-09-25T13:00:00+00:00").
    Devolve: os dias úteis que passaram, com fração (12 horas de uma terça-feira = 0,5 dia útil).
    Sábado e domingo não contam; os feriados ainda contam como dia útil nesta versão (a tela avisa).
    Exemplo: enviado na sexta às 10h e avaliado na segunda às 10h → 1.0 (o fim de semana não conta).
    """
    # As duas datas no horário de Brasília
    momento = datetime.fromisoformat(inicio_em_texto).astimezone(FUSO_DE_BRASILIA)
    fim = datetime.fromisoformat(fim_em_texto).astimezone(FUSO_DE_BRASILIA)
    # Os segundos que caíram em dia útil, somados dia a dia
    segundos_uteis = 0.0
    # Anda um dia de cada vez, do começo até o fim
    while momento < fim:
        # A meia-noite em que começa o dia seguinte
        meia_noite_de_hoje = momento.replace(hour=0, minute=0, second=0, microsecond=0)
        comeco_do_dia_seguinte = meia_noite_de_hoje + timedelta(days=1)
        # O pedaço deste dia que está dentro do intervalo: até a meia-noite, ou até o fim, o que vier antes
        fim_do_pedaco = min(comeco_do_dia_seguinte, fim)
        # weekday(): 0 é segunda e 4 é sexta; 5 (sábado) e 6 (domingo) não contam
        if momento.weekday() < 5:
            segundos_uteis = segundos_uteis + (fim_do_pedaco - momento).total_seconds()
        # Passa para o próximo pedaço
        momento = fim_do_pedaco
    # Converte os segundos em dias
    return segundos_uteis / SEGUNDOS_POR_DIA


def avaliacoes_do_banco(todos_os_eventos: list[dict]) -> list[dict]:
    """Cada decisão do banco sobre um envio: quando o envio chegou ao banco e quando o banco decidiu.

    Recebe: todos_os_eventos — os da auditoria (auditoria.eventos), na ordem em que aconteceram.
    Devolve: [{processamento_id, empresa_id, enviado_em, decidido_em}], uma por decisão.
    Um envio devolvido e mandado de novo conta duas vezes (cada ida ao banco é uma avaliação). O envio que ainda
    espera o banco não entra: só os já decididos.
    """
    # Os envios que chegaram ao banco e ainda esperam a decisão: {processamento_id: quando chegou}
    esperando_o_banco = {}
    avaliacoes = []
    for evento in todos_os_eventos:
        processamento_id = evento["processamento_id"]
        # A empresa mandou o envio ao banco: começa a contar o tempo
        if evento["tipo"] == "ENVIADO_AO_BANCO":
            esperando_o_banco[processamento_id] = evento["criado_em"]
            continue
        # Não é uma decisão do banco: não interessa aqui
        if evento["tipo"] not in EVENTOS_DA_DECISAO_DO_BANCO:
            continue
        # Decisão sem o envio ao banco antes (não deveria acontecer): não há de onde contar
        if processamento_id not in esperando_o_banco:
            continue
        # O banco decidiu: fecha a conta deste envio e tira ele da espera
        enviado_em = esperando_o_banco.pop(processamento_id)
        avaliacoes.append({"processamento_id": processamento_id, "empresa_id": evento["empresa_id"],
                           "enviado_em": enviado_em, "decidido_em": evento["criado_em"]})
    return avaliacoes


def tempo_ate_a_avaliacao(todos_os_eventos: list[dict]) -> dict:
    """O cartão "tempo até a avaliação do banco": a média, em dias úteis, entre o envio ao banco e a decisão do banco.

    Recebe: todos_os_eventos — os da auditoria, na ordem em que aconteceram.
    Devolve: {"media_em_dias_uteis": a média com uma casa decimal (ex.: 1.3), ou None se o banco ainda não decidiu
    nenhum envio; "avaliacoes": quantas decisões entraram na média; "soma_em_dias_uteis": a soma dos dias (para
    juntar empresas); "periodo": PERIODO_DO_USO}.
    Exemplo: duas avaliações, uma de 1 dia útil e outra de 2 → {"media_em_dias_uteis": 1.5, "avaliacoes": 2, ...}.
    """
    avaliacoes = avaliacoes_do_banco(todos_os_eventos)
    # Nenhuma decisão do banco no período: sem número (nunca um zero inventado)
    if not avaliacoes:
        return {"media_em_dias_uteis": None, "avaliacoes": 0, "soma_em_dias_uteis": 0.0, "periodo": PERIODO_DO_USO}
    # Soma os dias úteis de cada avaliação
    soma_dos_dias = 0.0
    for avaliacao in avaliacoes:
        soma_dos_dias = soma_dos_dias + dias_uteis_entre(avaliacao["enviado_em"], avaliacao["decidido_em"])
    # A média, com uma casa decimal (a tela mostra "1,3")
    media = round(soma_dos_dias / len(avaliacoes), 1)
    # A soma vai junto: a tela junta várias empresas pela média ponderada (soma dos dias ÷ soma das avaliações)
    return {"media_em_dias_uteis": media, "avaliacoes": len(avaliacoes), "soma_em_dias_uteis": round(soma_dos_dias, 3),
            "periodo": PERIODO_DO_USO}


def cnpjs_para_a_busca(conexao, empresa: dict) -> list[str]:
    """Todos os CNPJs de uma empresa da carteira, para a busca por CNPJ no funil do envio e na lista de empresas do
    Endomarketing (services/endomarketing_do_banco.py).

    Recebe: conexao; empresa — a da lista da carteira (dados_mock.empresas()), com o CNPJ principal em "cnpj".
    Devolve: os CNPJs só com os números, o principal primeiro e depois os de filiais e do grupo (ADR-77).
    Exemplo: ["10433218000193", "10433218000274"].
    """
    # O principal (a sede) vem do cadastro da empresa
    cnpjs = [empresa["cnpj"]]
    # Depois os de filiais e de empresas do grupo que o banco (ou a empresa, ao confirmar num envio) registrou
    for registrado in cadastro_de_empresas.cnpjs_da_empresa(conexao, empresa["empresa_id"]):
        cnpjs.append(registrado["cnpj"])
    return cnpjs


def uso_das_empresas(conexao) -> dict:
    """O uso do Portal Empresa por empresa: acessos, envios, descartes, funil, linha do tempo, os CNPJs de cada
    empresa (para a busca no funil) e o tempo até a avaliação do banco.

    Recebe: conexao. Devolve: {etapas: [nomes], carteira: {funil}, tempo_ate_a_avaliacao: {media_em_dias_uteis,
    avaliacoes, soma_em_dias_uteis, periodo}, empresas: [{id, nome, uf (da sede), cnpjs, tempo_ate_a_avaliacao,
    ultimo_acesso, acessos, envios, descartes, onde_parou, funil, linha_do_tempo}]}. Com o tempo e a UF de cada
    empresa, a tela refaz os números para as empresas escolhidas no filtro do alto do painel. Nada de funcionário: só o uso do portal pelo RH e as datas das decisões do banco.
    """
    acessos = _acessos_por_empresa(conexao)
    # Os eventos da auditoria são lidos uma vez só e servem ao funil, à linha do tempo e ao tempo da avaliação
    todos_os_eventos = auditoria.eventos(conexao)
    eventos = _eventos_por_empresa(todos_os_eventos)
    linhas_da_carteira = {}
    for linha in carteira(conexao):
        linhas_da_carteira[linha["id"]] = linha
    empresas = []
    funil_da_carteira = [0] * len(ETAPAS_DO_FUNIL_REAL)
    for empresa in dados_mock.empresas():
        empresa_id = empresa["empresa_id"]
        eventos_da_empresa = eventos.get(empresa_id, [])
        funil = _funil(eventos_da_empresa)
        # Soma no funil da carteira
        for posicao in range(len(funil)):
            funil_da_carteira[posicao] = funil_da_carteira[posicao] + funil[posicao]
        # Descartes: leituras encerradas sem cadastrar
        descartes = 0
        for evento in eventos_da_empresa:
            if evento["tipo"] == "REJEITADO":
                descartes = descartes + 1
        # A linha do tempo: cada evento com a data e o que aconteceu
        linha_do_tempo = []
        for evento in eventos_da_empresa:
            linha_do_tempo.append({"quando": evento["criado_em"], "o_que": NOME_DO_EVENTO[evento["tipo"]]})
        acesso = acessos.get(empresa_id, {"acessos": 0, "ultimo_acesso": None})
        # Os eventos só desta empresa, para o tempo até a avaliação dela (o filtro do alto do painel escolhe empresas)
        eventos_so_desta_empresa = []
        for evento in todos_os_eventos:
            if evento["empresa_id"] == empresa_id:
                eventos_so_desta_empresa.append(evento)
        empresas.append({
            "id": empresa_id,
            "nome": empresa["nome"],
            # A UF da sede: o filtro de estado do painel escolhe as empresas do uso por ela
            "uf": empresa["uf"],
            "cnpjs": cnpjs_para_a_busca(conexao, empresa),
            "tempo_ate_a_avaliacao": tempo_ate_a_avaliacao(eventos_so_desta_empresa),
            "ultimo_acesso": acesso["ultimo_acesso"],
            "acessos": acesso["acessos"],
            "envios": linhas_da_carteira[empresa_id]["envios"],
            "descartes": descartes,
            "onde_parou": linhas_da_carteira[empresa_id]["situacao"]["texto"],
            "funil": funil,
            "linha_do_tempo": linha_do_tempo,
        })
    etapas = []
    for nome, _ in ETAPAS_DO_FUNIL_REAL:
        etapas.append(nome)
    return {"etapas": etapas, "carteira": {"funil": funil_da_carteira},
            "tempo_ate_a_avaliacao": tempo_ate_a_avaliacao(todos_os_eventos), "empresas": empresas}


# ---------------- Empresas (a ficha de cada empresa) ----------------

def _ultimo_acesso_por_login(conexao) -> dict:
    """Quando cada pessoa entrou no portal pela última vez.

    Recebe: conexao. Devolve: {login: data e hora da última sessão}. Quem nunca entrou não aparece.
    """
    # Garante que a tabela de sessões existe (numa aplicação nova, ninguém entrou ainda)
    sessoes.preparar_tabela(conexao)
    ultimos = {}
    for login, ultima_entrada in conexao.execute("SELECT login, MAX(criada_em) FROM sessoes GROUP BY login"):
        ultimos[login] = ultima_entrada
    return ultimos


def _usuarios_das_empresas(conexao) -> dict:
    """Os usuários de cada empresa (perfil EMPRESA), com a situação e o último acesso.

    Recebe: conexao. Devolve: {empresa_id: [{login, ativo, ultimo_acesso, suspensao, senha_provisoria,
    senha_provisoria_vencida}, ...]}. Nunca a senha. senha_provisoria: o banco resetou a senha (ou convidou) e a
    pessoa ainda não cadastrou a dela; senha_provisoria_vencida: essa senha passou das 48 horas (ADR-154), e a pessoa
    só entra com uma nova. suspensao: "sem_uso", "vencido" ou None (ADR-146); a tela mostra o selo e o botão
    "Reativar", que renova o acesso.
    """
    # Garante que a tabela de usuários existe
    auth.preparar_tabela(conexao)
    ultimos_acessos = _ultimo_acesso_por_login(conexao)
    por_empresa = {}
    for usuario in auth.listar_usuarios(conexao):
        # Só as pessoas das empresas: o banco não é usuário de uma empresa
        if usuario.perfil != Perfil.EMPRESA:
            continue
        por_empresa.setdefault(usuario.empresa_id, []).append({
            "login": usuario.login,
            "ativo": usuario.ativo,
            "ultimo_acesso": ultimos_acessos.get(usuario.login),
            # Suspenso pelas regras da validade (sem uso ou vencido), mesmo com a marca "ativo" (ADR-146)
            "suspensao": auth.suspensao_do_acesso(conexao, usuario.login),
            # O banco resetou a senha e a pessoa ainda não cadastrou uma nova (a tela mostra "Senha resetada")
            "senha_provisoria": usuario.senha_provisoria,
            # Essa senha provisória passou das 48 horas: a tela mostra "Senha provisória vencida" (ADR-154)
            "senha_provisoria_vencida": auth.senha_provisoria_venceu(usuario),
        })
    return por_empresa


def _titulos_das_secoes(conteudo_md: str) -> list[str]:
    """Os títulos das seções de um documento do catálogo (a divisão em seções é do services/catalogo.py).

    Recebe: o texto Markdown. Devolve: a lista de títulos, na ordem.
    Exemplo: "# Pacote\\n## Conta salário\\n...\\n## Crédito consignado" → ["Conta salário", "Crédito consignado"].
    """
    titulos = []
    for secao in catalogo.secoes_do_documento(conteudo_md):
        titulos.append(secao["titulo"])
    return titulos


def _catalogo_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os documentos vigentes do catálogo de benefícios da empresa, com as seções de cada um.

    Recebe: conexao; empresa_id. Devolve: [{titulo, versao, vigencia_inicio, vigencia_fim, secoes}].
    """
    documentos = []
    for documento in catalogo.documentos_vigentes(conexao, empresa_id):
        documentos.append({
            "titulo": documento["titulo"],
            "versao": documento["versao"],
            "vigencia_inicio": documento["vigencia_inicio"],
            "vigencia_fim": documento["vigencia_fim"],
            "secoes": _titulos_das_secoes(documento["conteudo_md"]),
        })
    return documentos


def empresas_da_carteira(conexao) -> list[dict]:
    """A ficha de cada empresa: dados, números do contrato, usuários e catálogo de benefícios.

    Recebe: conexao. Devolve: [{id, nome, setor, cidade, situacao, cadastrados, envios, com_pendencia, ultimo_envio,
    contas, usuarios, catalogo, dados, outros_cnpjs, cadastrada_em}] — dados: o cadastro da empresa (CNPJ principal,
    endereço da sede, domínio de e-mail, contrato e kit de endomarketing); outros_cnpjs: filiais e grupo (ADR-77);
    cadastrada_em: quando a empresa entrou na carteira (a lista da tela mostra só as últimas cadastradas). Nenhum
    funcionário: só a empresa e as pessoas do RH que entram no portal.
    """
    usuarios = _usuarios_das_empresas(conexao)
    cadastro_por_empresa = {}
    for empresa in cadastro_de_empresas.listar(conexao):
        cadastro_por_empresa[empresa["empresa_id"]] = empresa
    # Quando cada empresa entrou na carteira (a lista mostra as últimas cadastradas)
    datas_de_cadastro = cadastro_de_empresas.datas_de_cadastro(conexao)
    fichas = []
    for linha in carteira(conexao):
        # A linha da carteira já traz os números e a situação; a ficha acrescenta usuários e catálogo
        fichas.append({
            "id": linha["id"],
            "nome": linha["nome"],
            "setor": linha["setor"],
            "cidade": linha["cidade"],
            "situacao": linha["situacao"],
            "cadastrados": linha["cadastrados"],
            "envios": linha["envios"],
            "com_pendencia": linha["com_pendencia"],
            "ultimo_envio": linha["ultimo_envio"],
            "contas": linha["contas"],
            "usuarios": usuarios.get(linha["id"], []),
            "catalogo": _catalogo_da_empresa(conexao, linha["id"]),
            "dados": cadastro_por_empresa[linha["id"]],
            # Os CNPJs de filiais e do grupo (ADR-77), com quem registrou (banco ou a empresa, ao confirmar num envio)
            "outros_cnpjs": cadastro_de_empresas.cnpjs_da_empresa(conexao, linha["id"]),
            # Quando a empresa entrou na carteira
            "cadastrada_em": datas_de_cadastro.get(linha["id"]),
        })
    return fichas


def convidar_usuario(conexao, usuario_logado, empresa_id: str, email: str) -> dict:
    """O especialista dá acesso a uma pessoa do RH: o login é o e-mail, com uma senha provisória.

    Recebe: conexao; usuario_logado (só o BANCO, conferido na porta de acesso); empresa_id; email — do DOMÍNIO da
    empresa (ninguém de fora, nem e-mail pessoal). Devolve: {login, senha_provisoria}.
    A aplicação não manda e-mail: a senha provisória aparece UMA vez para o especialista entregar à pessoa, que é
    obrigada a trocá-la no primeiro acesso, antes de usar o sistema (ADR-109). Levanta ValueError (e-mail de fora do
    domínio, já com acesso) ou KeyError.
    """
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    login = (email or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]+@[a-z0-9.-]+", login):
        raise ValueError("Escreva o e-mail da pessoa (ex.: nome@" + empresa["dominio_email"] + ").")
    if not login.endswith("@" + empresa["dominio_email"]):
        raise ValueError("Use um e-mail do domínio da empresa (@" + empresa["dominio_email"] + ").")
    auth.preparar_tabela(conexao)
    for existente in auth.listar_usuarios(conexao):
        if existente.login == login:
            raise ValueError("Esta pessoa já tem acesso.")
    senha_provisoria = secrets.token_urlsafe(9)
    # Marcada como provisória: a pessoa troca no primeiro acesso (o especialista viu esta senha)
    acesso.cadastrar_usuario(conexao, usuario_logado, login, senha_provisoria, Perfil.EMPRESA, empresa_id,
                             senha_provisoria=True)
    return {"login": login, "senha_provisoria": senha_provisoria}


def _reindexar_catalogo(conexao) -> None:
    """Refaz o índice de busca do catálogo (os trechos que o Agente de Endomarketing consulta), só dele.

    Os documentos são poucos e o modelo de embeddings roda na própria máquina: leva alguns segundos e não custa nada.
    """
    from rag.busca import COLECAO_CATALOGO, gravar_colecao
    from rag.trechos import trechos_catalogo
    gravar_colecao(COLECAO_CATALOGO, trechos_catalogo(catalogo.documentos_mais_recentes(conexao)))


def nova_versao_do_catalogo(conexao, usuario_logado, empresa_id: str, titulo: str, vigencia_inicio: str,
                            vigencia_fim: str, conteudo_md: str) -> dict:
    """O especialista sobe uma nova versão (ou um documento novo) do catálogo de benefícios de uma empresa.

    Recebe: conexao; usuario_logado (só o BANCO); empresa_id; titulo (o mesmo título cria uma nova versão); vigência
    (AAAA-MM-DD); conteudo_md (o texto em Markdown, com as seções "## ..."). Devolve: {versao, indice_atualizado}.
    O guardrail recusa documento com frase de ordem para a IA. A versão anterior fica guardada. Depois de gravar, o
    índice de busca do catálogo é refeito; se não der (ex.: modelo de embeddings ausente), a versão fica gravada e a
    resposta avisa.
    """
    cadastro_de_empresas.obter(conexao, empresa_id)
    if not (titulo or "").strip():
        raise ValueError("Dê um título ao documento (o mesmo título cria uma nova versão).")
    versao = acesso.adicionar_documento(conexao, usuario_logado, empresa_id, titulo, vigencia_inicio, vigencia_fim,
                                        conteudo_md)
    indice_atualizado = True
    try:
        _reindexar_catalogo(conexao)
    except Exception:  # noqa: BLE001 (qualquer falha do índice não desfaz a versão gravada; a tela avisa)
        indice_atualizado = False
    return {"versao": versao, "indice_atualizado": indice_atualizado,
            "incompletos": beneficios_incompletos(conteudo_md)}


def beneficios_incompletos(conteudo_md: str) -> list[dict]:
    """Os benefícios do documento que não têm tudo o que a vitrine da empresa mostra (a versão grava assim mesmo).

    Recebe: o Markdown do catálogo. Devolve: [{beneficio, falta: [...]}], só dos incompletos.
    Exemplo: "## Seguro de vida" só com texto corrido → [{"beneficio": "Seguro de vida", "falta": ["Categoria",
    "Como funciona", "Quem pode usar", "Como contratar"]}].
    As seções de atendimento ("Onde consultar", "Canais de dúvidas") não são benefícios e ficam de fora.
    """
    incompletos = []
    for secao in catalogo.secoes_do_documento(conteudo_md):
        if secao["titulo"] in catalogo.SECOES_DE_ATENDIMENTO:
            continue
        falta = catalogo.o_que_falta_no_beneficio(secao["texto"])
        if falta:
            incompletos.append({"beneficio": secao["titulo"], "falta": falta})
    return incompletos


def ativar_ou_desativar_usuario_da_empresa(conexao, usuario_logado, login_alvo: str, ativo: bool) -> None:
    """O banco desativa (ou reativa) uma pessoa de uma empresa. Desativada, ela sai do portal na hora.

    Recebe: conexao; usuario_logado (quem pede, conferido em services/acesso.py); login_alvo; ativo.
    Devolve: nada. Levanta ValueError se o login não for de uma pessoa de empresa: esta tela não mexe no banco.
    """
    # Procura o alvo entre os usuários das empresas
    for usuarios_da_empresa in _usuarios_das_empresas(conexao).values():
        for usuario in usuarios_da_empresa:
            if usuario["login"] == login_alvo:
                # Achou: a porta de acesso confere o perfil de quem pede e derruba as sessões do desativado
                acesso.definir_ativo(conexao, usuario_logado, login_alvo, ativo)
                return
    raise ValueError("Usuário de empresa não encontrado.")


def visao_geral_da_empresa(conexao, usuario_logado, empresa_id: str) -> dict:
    """O que o especialista vê ao abrir uma empresa na aba Empresas: os números e a lista de funcionários (ADR-112).

    Recebe: conexao; usuario_logado (só o BANCO, conferido na porta de acesso); empresa_id.
    Devolve: {resumo, contas, funcionarios} — resumo: cadastrados, envios, em andamento, com pendência e as pessoas em
    análise pelo banco (os mesmos números que a empresa vê em Acompanhar cadastros); contas: o total de contas abertas; funcionarios: a mesma lista da
    consulta da empresa (todos os campos do parâmetro, situação, conta e quem incluiu).
    A abertura da lista fica registrada nos acessos a dados pessoais da empresa (quem, quando e quantas pessoas; nunca o
    CPF), como quando o especialista abre as pessoas de um envio. Levanta KeyError se a empresa não existe.
    """
    acesso.autorizar(usuario_logado, "consultar_funcionarios")
    # A empresa precisa existir na carteira (KeyError vira "não encontrado")
    cadastro_de_empresas.obter(conexao, empresa_id)
    funcionarios = acompanhamento.todos_os_funcionarios_da_empresa(conexao, empresa_id)
    # Quem do banco viu os dados das pessoas desta empresa, e quantas (a prestação de contas da LGPD)
    acompanhamento.registrar_acesso(conexao, empresa_id, usuario_logado.login, acompanhamento.ACESSO_LISTA,
                                    len(funcionarios))
    # Os números, com as pessoas em análise pelo banco (os mesmos de Acompanhar cadastros)
    resumo = acompanhamento.resumo_da_empresa(conexao, empresa_id)
    resumo["pessoas_em_analise"] = acompanhamento.contar_em_analise(funcionarios)
    return {"resumo": resumo,
            "contas": contas_abertas.contas_para_a_empresa(conexao, empresa_id),
            "funcionarios": funcionarios}


# ---------------- O "Baixar CSV" da Visão geral ----------------

# As colunas do arquivo que vêm depois dos campos do parâmetro: a situação da pessoa, a conta que o banco enviou ao
# final da integração (ADR-113; o código do banco só existe nas contas gravadas antes do ADR-149) e quem da empresa
# incluiu a pessoa, e quando. São as mesmas informações que a grade da Visão geral mostra.
COLUNAS_DEPOIS_DOS_CAMPOS_NO_ARQUIVO = ("Situação", "Código do banco", "Agência", "Conta salário",
                                        "Conta salário aberta em", "Incluído em", "Incluído por")


def _alguem_tem_valor(funcionarios: list[dict], campo: str) -> bool:
    """Diz se pelo menos uma pessoa da lista tem valor no campo (espaços não contam).

    Recebe: funcionarios — a lista da Visão geral; campo — o nome técnico (ex.: "nome_completo"). Devolve: True ou False.
    Ex.: ([{"nome_completo": "Ana"}, {"nome_completo": ""}], "nome_completo") → True.
    """
    for pessoa in funcionarios:
        # O valor em texto, sem os espaços das pontas (None vira texto vazio)
        if str(pessoa.get(campo) or "").strip():
            return True
    return False


def _colunas_do_arquivo_da_empresa(colunas: list[dict], funcionarios: list[dict]) -> list[dict]:
    """As colunas do parâmetro que entram no arquivo: todas as obrigatórias e as opcionais que vieram.

    Recebe: colunas — as do parâmetro vigente (acompanhamento.colunas_da_consulta), na ordem do layout; funcionarios —
    a lista da Visão geral. Devolve: primeiro as obrigatórias, depois as opcionais que têm valor em pelo menos uma
    pessoa da empresa, cada grupo na ordem do layout. Uma opcional que não veio para ninguém fica de fora (seria uma
    coluna vazia inteira).
    Ex.: no parâmetro de hoje, CPF, Código cbo, Data admissão e Valor renda e, se veio para alguém, Nome completo.
    A escolha vem da marca "obrigatorio" do parâmetro, nunca de uma lista escrita aqui.
    """
    obrigatorias = []
    opcionais_que_vieram = []
    for coluna in colunas:
        # A obrigatória entra sempre, mesmo sem valor (a pendência dela aparece na situação)
        if coluna["obrigatorio"]:
            obrigatorias.append(coluna)
        # A opcional entra só se veio para alguém
        elif _alguem_tem_valor(funcionarios, coluna["campo"]):
            opcionais_que_vieram.append(coluna)
    return obrigatorias + opcionais_que_vieram


def _linha_do_arquivo_da_empresa(pessoa: dict, colunas: list[dict]) -> list[str]:
    """A linha de uma pessoa no arquivo: o valor de cada coluna escolhida e, depois, a situação, a conta e a inclusão.

    Recebe: pessoa — um funcionário da Visão geral; colunas — as de _colunas_do_arquivo_da_empresa.
    Devolve: a lista de textos, já protegidos contra fórmula do Excel. Valor que não veio vira texto vazio.
    Os valores vão como a grade os recebe do servidor (a data AAAA-MM-DD, o valor com ponto, o CPF pontuado).
    Ex.: {"cpf": "529.982.247-25", "situacao": "Cadastrado", "incluido_em": "2026-09-24T10:00:00+00:00", ...} →
    ["529.982.247-25", ..., "Cadastrado", "", "", "", "", "2026-09-24", "rh.aurora"].
    """
    valores = []
    # Os campos do parâmetro, na ordem das colunas
    for coluna in colunas:
        valores.append(pessoa.get(coluna["campo"]))
    # A situação e a conta no banco (vazia enquanto o banco não a envia; a pessoa em andamento nem tem esses campos)
    valores.append(pessoa.get("situacao"))
    valores.append(pessoa.get("codigo_banco"))
    valores.append(pessoa.get("agencia"))
    valores.append(pessoa.get("conta"))
    valores.append(pessoa.get("conta_aberta_em"))
    # Quando a empresa incluiu a pessoa (só a data, sem a hora, como no arquivo que a empresa baixa) e quem incluiu
    valores.append(str(pessoa.get("incluido_em") or "")[:10])
    valores.append(pessoa.get("incluido_por"))
    # Cada valor em texto, protegido contra fórmula do Excel
    linha = []
    for valor in valores:
        linha.append(homologacao.neutralizar_formula(str(valor or "")))
    return linha


def arquivo_dos_funcionarios_da_empresa(conexao, usuario_logado, empresa_id: str) -> tuple[bytes, str]:
    """O arquivo (CSV para o Excel) com os funcionários de UMA empresa, como a Visão geral do especialista os mostra,
    com todas as colunas do cadastro.

    Recebe: conexao; usuario_logado (só o BANCO, conferido na porta de acesso); empresa_id — a empresa aberta na tela.
    Devolve: (os bytes do arquivo, o nome dele). Ex. de nome: "funcionarios_EMP001.csv".
    As colunas: os campos obrigatórios do parâmetro, os opcionais que vieram para alguém da empresa, a situação, a conta
    no banco e a inclusão. As pessoas: a MESMA lista da grade (cadastrados, em análise, pendentes e aguardando envio),
    só desta empresa. O padrão dos outros arquivos que o sistema baixa: separador ";", UTF-8 com a marca que o Excel
    reconhece e a proteção contra fórmula. O download fica registrado nos acessos a dados pessoais da empresa (quem,
    quando e quantas pessoas; nunca o CPF).
    Levanta KeyError se a empresa não existe e ValueError se ela ainda não tem funcionários.
    """
    acesso.autorizar(usuario_logado, "consultar_funcionarios")
    # A empresa precisa existir na carteira (KeyError vira "não encontrado")
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    # A mesma lista da grade da Visão geral, só desta empresa
    funcionarios = acompanhamento.todos_os_funcionarios_da_empresa(conexao, empresa["empresa_id"])
    # Sem ninguém: não há o que baixar (a tela esconde o botão nesse caso)
    if not funcionarios:
        raise ValueError("Esta empresa ainda não tem funcionários para baixar.")
    # As colunas do parâmetro que entram: as obrigatórias e as opcionais que vieram
    colunas = _colunas_do_arquivo_da_empresa(acompanhamento.colunas_da_consulta(conexao), funcionarios)
    # O cabeçalho: o rótulo de cada campo (como na grade) e as colunas do fim
    cabecalho = []
    for coluna in colunas:
        cabecalho.append(coluna["rotulo"])
    for titulo in COLUNAS_DEPOIS_DOS_CAMPOS_NO_ARQUIVO:
        cabecalho.append(titulo)
    # O arquivo em memória: separador ";" (o do Excel em português) e uma pessoa por linha
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(cabecalho)
    for pessoa in funcionarios:
        escritor.writerow(_linha_do_arquivo_da_empresa(pessoa, colunas))
    # Quem do banco baixou os dados das pessoas desta empresa, e quantas (a prestação de contas da LGPD)
    acompanhamento.registrar_acesso(conexao, empresa["empresa_id"], usuario_logado.login, acompanhamento.ACESSO_DOWNLOAD,
                                    len(funcionarios))
    nome_do_arquivo = "funcionarios_" + empresa["empresa_id"] + ".csv"
    # "﻿" no começo avisa o Excel que o arquivo é UTF-8 (senão os acentos saem errados)
    return ("﻿" + saida.getvalue()).encode("utf-8"), nome_do_arquivo


def gerar_nova_senha_provisoria(conexao, usuario_logado, login_alvo: str) -> dict:
    """A pessoa da empresa esqueceu a senha: o banco gera uma nova, provisória, que aparece UMA vez (ADR-109).

    Recebe: conexao; usuario_logado (só o BANCO, conferido na porta de acesso); login_alvo — uma pessoa de empresa.
    Devolve: {login, senha_provisoria}. As sessões abertas da pessoa caem na hora, e ela é obrigada a trocar a senha no
    próximo acesso. Levanta ValueError se o login não for de uma pessoa de empresa: esta tela não mexe no banco.
    Ex.: ("rh@aurora.com.br") → {"login": "rh@aurora.com.br", "senha_provisoria": "Xy3..."}.
    """
    # Procura o alvo entre os usuários das empresas
    for usuarios_da_empresa in _usuarios_das_empresas(conexao).values():
        for usuario in usuarios_da_empresa:
            if usuario["login"] == login_alvo:
                # A mesma forma de senha do convite: 12 caracteres sorteados, difíceis de adivinhar
                senha_provisoria = secrets.token_urlsafe(9)
                # A porta de acesso confere o perfil de quem pede e derruba as sessões da pessoa
                acesso.redefinir_senha(conexao, usuario_logado, login_alvo, senha_provisoria, senha_provisoria=True)
                return {"login": login_alvo, "senha_provisoria": senha_provisoria}
    raise ValueError("Usuário de empresa não encontrado.")


# ---------------- Telemetria: desempenho da IA (a antiga aba Técnico) ----------------

def telemetria_da_ia(conexao, usuario, de: str = "", ate: str = "") -> dict:
    """As execuções dos agentes e a aceitação de cada um, no período, para a tela Acompanhamento dos agentes (perfil
    BANCO; o serviço confere).

    Recebe: conexao; usuario (o serviço confere a permissão); de e ate — as datas do período no endereço
    (AAAA-MM-DD, inclusive; vazio = sem limite; as duas vazias = tudo). Levanta ValueError (vira 400) com data
    inválida ou com o começo depois do fim.
    Só o que aconteceu de verdade entra: as execuções simuladas (a IA em MOCK) ficam de fora de todos os números, e a
    aceitação conta só as propostas feitas com o modelo real (services/aceitacao_dos_agentes.py).
    Devolve: {periodo, visao, por_agente, custo_por_etapa, recentes, cartoes_por_agente, teto_de_gasto}; tudo dentro
    do período, menos o teto de gasto, que é sempre o de hoje e o do mês corrente:
      - periodo: {de, ate} como ficou valendo (None = sem limite);
      - visao: os cards (execuções, envios, erros ou bloqueios, guardrails, intervenções humanas, tokens e custo,
        com "não medido" quando nada foi medido: nunca um zero inventado);
      - por_agente: execuções, duração média e erros de cada agente;
      - custo_por_etapa: o custo da IA por agente e etapa, com tokens e o custo médio (ADR-131);
      - teto_de_gasto: o gasto com IA de hoje e do mês, com os tetos ({dia, gasto_dia_usd, teto_dia_usd,
        gasto_mes_usd, teto_mes_usd, atingido}; services/teto_de_gasto.py);
      - recentes: as últimas execuções, só com os campos técnicos (nenhum dado de pessoa);
      - cartoes_por_agente: um cartão por agente de IA, na ordem do fluxo, com o que ele faz, como trabalhou e a
        aceitação das propostas dele (ver services/painel.py, AGENTES_DE_IA, e services/aceitacao_dos_agentes.py).
    Ex.: telemetria_da_ia(conexao, especialista, "2026-09-01", "2026-09-30").
    """
    desde, ate_o_dia = painel.periodo_do_endereco(de, ate)
    # A permissão é conferida aqui (antes de qualquer outra consulta)
    todas_do_periodo = acesso.execucoes_do_painel(conexao, usuario, desde=desde, ate=ate_o_dia)
    # Só as execuções de verdade: as simuladas (MOCK) não entram em nenhum número da tela
    lista = painel.so_execucoes_reais(todas_do_periodo)
    # Quanto as pessoas aceitaram do que cada agente propôs com o modelo real, no mesmo período (só contagens)
    aceitacao = aceitacao_dos_agentes.aceitacao_por_agente(conexao, desde, ate_o_dia)
    # As mais recentes primeiro, só os campos técnicos
    recentes = []
    for execucao in sorted(lista, key=_inicio_da_execucao, reverse=True)[:EXECUCOES_RECENTES]:
        linha = {}
        for campo in CAMPOS_DA_EXECUCAO:
            linha[campo] = execucao.get(campo)
        linha["empresa"] = dados_mock.nome_da_empresa(execucao.get("empresa_id", ""))
        recentes.append(linha)
    # O período como ficou valendo, em texto (None = sem limite), para a tela conferir o que recebeu
    periodo = {"de": None, "ate": None}
    if desde is not None:
        periodo["de"] = desde.isoformat()
    if ate_o_dia is not None:
        periodo["ate"] = ate_o_dia.isoformat()
    return {"periodo": periodo, "visao": painel.visao_agregada(lista), "por_agente": painel.latencia_por_agente(lista),
            "custo_por_etapa": painel.custo_por_etapa(lista), "recentes": recentes,
            # Um cartão por agente de IA (os que nunca trabalharam também aparecem, com zeros e "não medido")
            "cartoes_por_agente": painel.cartoes_por_agente(lista, aceitacao),
            # O gasto de hoje e do mês × os tetos (vale para a aplicação inteira; não segue o período escolhido)
            "teto_de_gasto": teto_de_gasto.situacao_dos_tetos(conexao)}


def _inicio_da_execucao(execucao: dict) -> str:
    """O horário de início de uma execução, para ordenar (texto AAAA-MM-DD... ordena igual a data)."""
    return execucao["inicio"]
