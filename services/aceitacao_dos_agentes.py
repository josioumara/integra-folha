"""Aceitação por agente: quanto as pessoas aceitaram do que cada agente de IA propôs (tela Acompanhamento dos agentes).

Para que serve:
cada cartão de agente mostra, no período escolhido, quantas propostas dele foram
    - APROVADAS sem mudança (a pessoa ficou com o que o agente propôs),
    - CORRIGIDAS (a pessoa mudou o que ele propôs) e
    - RECUSADAS (a pessoa desfez, ignorou ou descartou),
e o percentual das aprovadas sem mudança. É a ACURÁCIA NA OPERAÇÃO: medida no uso de verdade, pelo que as pessoas
fizeram. É diferente da acurácia contra gabarito dos experimentos (ex.: EXP-008), em que as respostas certas já eram
conhecidas antes.

Tudo sai do que a aplicação já grava; nada novo é gravado aqui. Onde fica cada proposta e o que a pessoa fez:
    - Interpretador e Leitor de documentos: cada coluna dos mapeamentos ACEITOS (tabela mapeamentos). No aceite, a
      coluna que a empresa mudou passa a ter a origem "humano"; a que ela manteve fica com a origem de quem propôs
      ("llm"/"handoff" = Interpretador; "leitor" = Leitor). A justificativa da coluna não muda no aceite e diz de quem
      era a proposta (ver _quem_propos_a_coluna);
    - Assistente de Correção: as correções que ele fez em nome da empresa (tabela correcoes, proposta_por
      "assistente (para <login>)") e o que aconteceu depois com cada uma;
    - Conferidor da leitura: cada suspeita dele virou uma pergunta para a empresa (no perfil do envio); a empresa
      corrigiu o valor (a suspeita valeu) ou confirmou que estava certo (alarme falso);
    - Endomarketing: cada material gerado e o que o especialista fez (publicou, descartou ou retirou).
Sem fonte ("não medido", nunca um zero inventado):
    - Agente de validação (perguntas): ele escreve a pergunta de cada pendência, mas não sugere a resposta.

Só contam as propostas feitas com o MODELO REAL. A proposta da simulação (a IA em MOCK, que devolve uma resposta pronta)
e o dado carregado sem agente nenhum (ex.: uma carga de dados sintéticos) ficam de fora. Como se sabe de onde veio:
    - Interpretador: o plano do mapeamento diz qual modelo respondeu ("mock" na simulação);
    - Leitor de documentos e Conferidor da leitura: o envio tem uma execução deles que deu certo com o modelo real;
    - Assistente de Correção: a rodada da conversa que fez a correção (a última dele no envio, até a hora da correção)
      foi com o modelo real;
    - Endomarketing: o material guarda o modelo que o escreveu ("mock" na simulação).

Nenhum dado de pessoa sai daqui: só contagens por agente.

Exemplo de uso:
    aceitacao = aceitacao_por_agente(conexao, date(2026, 9, 1), date(2026, 9, 30))
    aceitacao["interpretador"]
      → {"aceitacao": {"aprovadas": 40, "corrigidas": 3, "recusadas": 1, "percentual_aprovadas": 90.9,
                       "fonte": "..."}, "sem_medida_porque": None}
"""
import json
from datetime import date, datetime, timezone

from agents import endomarketing
from models.contratos import MappingPlan
from services import correcoes, divisao_da_coluna, execucoes, mapeamentos, painel, processamentos, validador

# O modelo gravado quando a IA está em MOCK: a proposta é da simulação e não conta na aceitação
MODELO_SIMULADO = "mock"

# ---------------- Como reconhecer de quem era a proposta de uma coluna ----------------
# As justificativas que services/mapeamentos.py escreve nas colunas que NÃO vieram do Interpretador. Se o texto de lá
# mudar, o teste tests/test_cartoes_dos_agentes.py avisa (ele gera as colunas pelas funções de lá).
# A coluna reaproveitada de um mapeamento já aprovado (sem IA)
JUSTIFICATIVA_DO_REUSO = "Mesma coluna de um mapeamento já aprovado por vocês."
# Os começos da justificativa das colunas que o Leitor de documentos leu num Word em texto corrido
COMECOS_DA_JUSTIFICATIVA_DO_LEITOR = ("O Agente Leitor leu este dado no seu documento",
                                      "O Agente Leitor achou este dado pelo lugar no texto",
                                      # Os de antes da troca de "IA" pelo nome do agente: os
                                      # mapeamentos já gravados continuam contando para o Leitor
                                      "A IA leu este dado no seu documento",
                                      "A IA achou este dado pelo lugar no texto")
# O começo da justificativa do plano de emergência (a IA caiu e o dicionário sem IA sugeriu)
COMECO_DA_JUSTIFICATIVA_DE_EMERGENCIA = "Agente Interpretador indisponível"
# O começo de antes da troca de "IA" pelo nome do agente: os mapeamentos já gravados continuam fora
COMECO_DA_JUSTIFICATIVA_DE_EMERGENCIA_ANTIGO = "IA indisponível"
COMECOS_DA_JUSTIFICATIVA_DE_EMERGENCIA = (COMECO_DA_JUSTIFICATIVA_DE_EMERGENCIA,
                                          COMECO_DA_JUSTIFICATIVA_DE_EMERGENCIA_ANTIGO)
# O pedaço da justificativa das partes de uma coluna que a própria pessoa dividiu ("separada por você")
TRECHO_DA_DIVISAO_FEITA_PELA_PESSOA = "separada por você"

# Os começos da pergunta que nasce de uma suspeita do Conferidor da leitura (agents/conferidor_da_leitura.py,
# pergunta_da_suspeita; o teste confere que os textos continuam iguais): o de hoje (v2, ADR-131) e o da v1, para as
# perguntas dos envios antigos continuarem contando
COMECO_DA_PERGUNTA_DO_CONFERIDOR = "Confira este valor:"
COMECO_DA_PERGUNTA_DO_CONFERIDOR_V1 = "Uma segunda IA desconfia deste valor:"
COMECOS_DA_PERGUNTA_DO_CONFERIDOR = (COMECO_DA_PERGUNTA_DO_CONFERIDOR, COMECO_DA_PERGUNTA_DO_CONFERIDOR_V1)
# O começo do nome gravado nas correções feitas pelo Assistente de Correção ("assistente (para rh.aurora)")
COMECO_DE_QUEM_PROPOS_PELO_ASSISTENTE = "assistente"

# ---------------- O que a tela lê sobre cada fonte ----------------
FONTE_DO_INTERPRETADOR = ("Colunas dos mapeamentos aceitos pela empresa: mantida como o Agente Interpretador "
                          "propôs = aprovada; trocada de campo = corrigida; ignorada = recusada.")
FONTE_DO_LEITOR = ("Campos que o Leitor leu no Word, nos mapeamentos aceitos pela empresa: mantido = aprovado; trocado "
                   "= corrigido; ignorado = recusado.")
FONTE_DO_ASSISTENTE = ("Correções que o Assistente fez a pedido da empresa: valeu até o fim = aprovada; mudada de novo "
                       "depois = corrigida; desfeita ou cancelada = recusada.")
FONTE_DO_CONFERIDOR = ("Suspeitas que viraram pergunta para a empresa: ela corrigiu o valor = aprovada; confirmou que "
                       "estava certo = recusada. Não há \"corrigida\": a suspeita não traz um valor.")
FONTE_DO_ENDOMARKETING = ("Materiais gerados para o especialista: publicado = aprovado; descartado ou retirado = "
                          "recusado. Não há \"corrigido\": o texto não é editado na ferramenta.")
# Por que o Agente de validação (perguntas) fica sem medida
SEM_MEDIDA_NA_VALIDACAO = ("O agente escreve a pergunta de cada pendência, mas não sugere a resposta: não há o que "
                           "aprovar ou corrigir.")
# Quando a fonte existe, mas nenhuma proposta feita com o modelo real foi decidida no período
SEM_DECISAO_NO_PERIODO = "Nenhuma proposta deste agente feita com o modelo real foi decidida pelas pessoas no período."
# Por que o Bedrock Guardrails fica sem medida (ADR-147): ele só dá uma nota a cada mensagem
SEM_MEDIDA_NO_GUARDRAIL = ("O detector só dá uma nota a cada mensagem e barra as suspeitas: não propõe nada para as "
                           "pessoas aprovarem ou corrigirem.")


# ---------------- Ajudas pequenas ----------------

def _contagem_vazia() -> dict:
    """As três contagens começando em zero: {"aprovadas": 0, "corrigidas": 0, "recusadas": 0}."""
    return {"aprovadas": 0, "corrigidas": 0, "recusadas": 0}


def _resultado(contagem: dict, fonte: str, tem_corrigidas: bool = True) -> dict:
    """O que o cartão recebe: a aceitação (ou None, quando nada foi decidido) e o porquê de não haver medida.

    Recebe: contagem — {aprovadas, corrigidas, recusadas}; fonte — o texto de onde veio; tem_corrigidas — False quando
    o agente não tem "corrigida" (o cartão mostra "não se aplica", nunca um zero).
    Devolve: {"aceitacao": {aprovadas, corrigidas, recusadas, percentual_aprovadas, fonte} ou None,
    "sem_medida_porque": texto ou None}.
    Ex.: ({"aprovadas": 3, "corrigidas": 1, "recusadas": 0}, "...") → percentual_aprovadas 75.0.
    """
    # Quantas propostas as pessoas decidiram (as que ainda esperam decisão não entram)
    decididas = contagem["aprovadas"] + contagem["corrigidas"] + contagem["recusadas"]
    # Nenhuma decidida no período: "não medido", nunca um percentual inventado
    if decididas == 0:
        return {"aceitacao": None, "sem_medida_porque": SEM_DECISAO_NO_PERIODO}
    # O agente que não tem "corrigida" leva None nesse número (a tela escreve "não se aplica")
    corrigidas = contagem["corrigidas"]
    if not tem_corrigidas:
        corrigidas = None
    # O percentual das aprovadas sem mudança, com uma casa (ex.: 90.9)
    percentual = round(contagem["aprovadas"] * 100 / decididas, 1)
    aceitacao = {"aprovadas": contagem["aprovadas"], "corrigidas": corrigidas, "recusadas": contagem["recusadas"],
                 "percentual_aprovadas": percentual, "fonte": fonte}
    return {"aceitacao": aceitacao, "sem_medida_porque": None}


def _sem_fonte(motivo: str) -> dict:
    """O resultado de um agente sem fonte de aceitação: nenhum número, só o porquê."""
    return {"aceitacao": None, "sem_medida_porque": motivo}


# ---------------- Quem trabalhou com o modelo real (as execuções gravadas) ----------------

def _nomes_gravados(identificador: str) -> tuple:
    """Os nomes com que um agente grava as execuções, pelo identificador do cartão (services/painel.py, AGENTES_DE_IA).

    Ex.: "leitor_de_documentos" → ("Leitor de Documentos", "Leitor de documentos"). Identificador desconhecido: ().
    """
    for agente_de_ia in painel.AGENTES_DE_IA:
        if agente_de_ia["agente"] == identificador:
            return agente_de_ia["nomes_gravados"]
    return ()


def _foi_com_o_modelo_real(execucao: dict) -> bool:
    """True se a execução não foi simulada (a origem MOCK é a da IA em modo simulado)."""
    return execucao["origem"] != painel.ORIGEM_SIMULADA


def _envios_com_trabalho_real(execucoes_gravadas: list[dict], identificador: str) -> set:
    """Os envios em que o agente trabalhou com o modelo real: há uma execução dele, que deu certo, fora da simulação.

    Recebe: execucoes_gravadas (execucoes.listar); identificador (ex.: "conferidor_da_leitura").
    Devolve: o conjunto dos números dos envios. Ex.: o Conferidor conferiu o Word do envio "PROC-1" com o modelo real →
    {"PROC-1"}; se só a simulação conferiu, o envio fica de fora.
    """
    nomes = _nomes_gravados(identificador)
    envios = set()
    for execucao in execucoes_gravadas:
        # Uma execução deste agente, que deu certo e não foi simulada
        e_deste_agente = execucao["agente"] in nomes
        if e_deste_agente and execucao["status"] == execucoes.OK and _foi_com_o_modelo_real(execucao):
            envios.add(execucao["processamento_id"])
    return envios


def _ate_o_segundo(momento: str) -> datetime:
    """Um horário gravado (texto ISO) como data e hora em UTC, sem a fração do segundo, para comparar.

    Por quê: as correções são gravadas só até o segundo, e as execuções, até o milésimo; cortando as duas no segundo, a
    rodada e a correção que ela fez no mesmo segundo continuam na ordem certa.
    Ex.: "2026-09-20T10:00:00.418+00:00" → 20/09/2026 10:00:00 (UTC); sem o fuso gravado, vale o UTC.
    """
    horario = datetime.fromisoformat(momento)
    # Horário sem o fuso gravado: é do horário universal, como os outros da aplicação
    if horario.tzinfo is None:
        horario = horario.replace(tzinfo=timezone.utc)
    return horario.astimezone(timezone.utc).replace(microsecond=0)


def _rodadas_do_assistente(execucoes_gravadas: list[dict]) -> dict:
    """As rodadas da conversa com o Assistente de Correção, por envio, em ordem de tempo.

    Devolve: {número do envio: [(começo da rodada até o segundo, foi com o modelo real?), ...]}.
    Ex.: {"PROC-1": [(20/09 10:00:00, False), (20/09 11:30:00, True)]} = a 1ª rodada foi simulada; a 2ª, real.
    """
    nomes = _nomes_gravados("assistente_de_correcao")
    rodadas = {}
    for execucao in execucoes_gravadas:
        # Só as rodadas do Assistente
        if execucao["agente"] not in nomes:
            continue
        envio = execucao["processamento_id"]
        if envio not in rodadas:
            rodadas[envio] = []
        rodadas[envio].append((_ate_o_segundo(execucao["inicio"]), _foi_com_o_modelo_real(execucao)))
    # Cada lista em ordem de tempo (a tupla ordena pelo começo)
    for lista_do_envio in rodadas.values():
        lista_do_envio.sort()
    return rodadas


def _correcao_de_uma_rodada_real(rodadas: dict, correcao: dict) -> bool:
    """True se a correção do Assistente nasceu de uma rodada com o modelo real.

    A rodada que fez a correção é a última do Assistente no mesmo envio que começou até a hora da correção (a correção é
    gravada logo depois da resposta). Sem nenhuma rodada gravada antes: False (não há como dizer que foi o modelo real).
    Ex.: rodadas {"PROC-1": [(10:00:00, True)]} e a correção de "PROC-1" às 10:00:07 → True.
    """
    momento_da_correcao = _ate_o_segundo(correcao["criado_em"])
    rodada_foi_real = False
    # As rodadas estão em ordem: vale a última que começou até a correção
    for comeco, foi_real in rodadas.get(correcao["processamento_id"], []):
        if comeco > momento_da_correcao:
            break
        rodada_foi_real = foi_real
    return rodada_foi_real


# ---------------- Interpretador e Leitor: as colunas dos mapeamentos aceitos ----------------

def _quem_propos_a_coluna(item) -> str | None:
    """De quem era a proposta de uma coluna de um mapeamento aceito: "interpretador", "leitor_de_documentos" ou None.

    Recebe: item — um ItemMapeamento do plano aceito. Devolve None quando a coluna não foi proposta por um desses dois
    agentes (reaproveitada de um mapeamento aprovado, plano de emergência sem IA, ou dividida pela própria pessoa).
    Ex.: origem "llm" → "interpretador"; origem "humano" com a justificativa "A IA leu este dado no seu documento
    (8 de 12 pessoas)." → "leitor_de_documentos" (a empresa trocou o campo que o Leitor leu).
    """
    # A pessoa manteve o que o Interpretador propôs (também quando ele releu a coluna a pedido, o "handoff")
    if item.origem in ("llm", "handoff"):
        return "interpretador"
    # A pessoa manteve o que o Leitor leu no Word
    if item.origem == "leitor":
        return "leitor_de_documentos"
    # Reaproveitada (sem IA) ou sugerida pela regra: não é proposta de nenhum agente de IA
    if item.origem != "humano":
        return None
    # A pessoa mudou a coluna: a justificativa, que não muda no aceite, diz de quem era a proposta
    justificativa = item.justificativa
    # Era uma coluna reaproveitada ou do plano de emergência: não conta
    if justificativa == JUSTIFICATIVA_DO_REUSO or justificativa.startswith(COMECOS_DA_JUSTIFICATIVA_DE_EMERGENCIA):
        return None
    # Uma parte de coluna que a própria pessoa dividiu: não havia proposta de IA nela
    if TRECHO_DA_DIVISAO_FEITA_PELA_PESSOA in justificativa and divisao_da_coluna.SINAL_DA_PARTE in item.coluna:
        return None
    # Era um campo que o Leitor leu
    if justificativa.startswith(COMECOS_DA_JUSTIFICATIVA_DO_LEITOR):
        return "leitor_de_documentos"
    # O resto era proposta do Interpretador
    return "interpretador"


def _o_que_a_pessoa_fez_na_coluna(item) -> str:
    """O que a pessoa fez com a proposta da coluna: "aprovadas", "corrigidas" ou "recusadas" (a chave da contagem).

    Ex.: origem "llm" → "aprovadas"; origem "humano" com campo → "corrigidas" (outro campo); sem campo → "recusadas"
    (a pessoa mandou ignorar a coluna).
    """
    # A coluna ficou como o agente propôs
    if item.origem != "humano":
        return "aprovadas"
    # A pessoa ligou a coluna a outro campo
    if item.campo is not None:
        return "corrigidas"
    # A pessoa mandou ignorar a coluna
    return "recusadas"


def _contagens_dos_mapeamentos(conexao, desde: date | None, ate: date | None, envios_do_leitor_real: set) -> dict:
    """As contagens do Interpretador e do Leitor nos mapeamentos aceitos, propostos dentro do período, só com as
    propostas feitas com o modelo real.

    Recebe: conexao; desde e ate (o período); envios_do_leitor_real — os envios em que o Leitor leu com o modelo real.
    Devolve: {"interpretador": {aprovadas, corrigidas, recusadas}, "leitor_de_documentos": {...}}.
    """
    # Garante que a tabela existe (num banco novo, ainda não há mapeamento)
    mapeamentos._preparar(conexao)
    contagens = {"interpretador": _contagem_vazia(), "leitor_de_documentos": _contagem_vazia()}
    # Só os mapeamentos que a empresa já aceitou (os pendentes ainda não têm decisão)
    consulta = conexao.execute("SELECT processamento_id, plano, criado_em FROM mapeamentos WHERE status = 'APROVADO'")
    for processamento_id, plano_em_json, criado_em in consulta:
        # A proposta foi feita fora do período: não conta
        if not painel.dentro_do_periodo(criado_em, desde, ate):
            continue
        plano = MappingPlan.model_validate_json(plano_em_json)
        # Quem propôs com o modelo real neste envio: o Interpretador, pelo modelo que o plano gravou (a IA foi chamada
        # e não era a simulação); o Leitor, pela execução real dele no envio
        propostas_reais = {"interpretador": plano.chamou_llm and plano.modelo != MODELO_SIMULADO,
                           "leitor_de_documentos": processamento_id in envios_do_leitor_real}
        # Cada coluna é uma proposta
        for item in plano.itens:
            agente = _quem_propos_a_coluna(item)
            # Coluna sem proposta de IA: fica de fora
            if agente is None:
                continue
            # Proposta da simulação: fica de fora
            if not propostas_reais[agente]:
                continue
            contagens[agente][_o_que_a_pessoa_fez_na_coluna(item)] += 1
    return contagens


# ---------------- Assistente de Correção: as correções feitas por ele ----------------

def _contagem_do_assistente(conexao, desde: date | None, ate: date | None, rodadas_do_assistente: dict) -> dict:
    """As correções que o Assistente fez em nome da empresa, pedidas dentro do período numa rodada com o modelo real, e
    o que aconteceu com elas.

    Recebe: conexao; desde e ate (o período); rodadas_do_assistente (ver _rodadas_do_assistente).
    Aprovada: continua valendo e ninguém mudou a mesma célula depois. Corrigida: outra correção aplicada na mesma
    célula (mesmo envio, linha e campo) veio depois. Recusada: a empresa desfez ou cancelou. Ainda esperando a
    confirmação da empresa (PROPOSTA): não conta.
    """
    # Garante que a tabela existe
    correcoes._preparar(conexao)
    # Todas as correções, na ordem em que foram pedidas (para saber o que veio depois)
    consulta = conexao.execute("SELECT processamento_id, linha, campo, status, proposta_por, criado_em "
                               "FROM correcoes ORDER BY criado_em, rowid")
    todas = []
    for processamento_id, linha, campo, status, proposta_por, criado_em in consulta:
        todas.append({"processamento_id": processamento_id, "linha": linha, "campo": campo, "status": status,
                      "proposta_por": proposta_por, "criado_em": criado_em})
    contagem = _contagem_vazia()
    for posicao, correcao in enumerate(todas):
        # Só as do Assistente, pedidas dentro do período
        if not correcao["proposta_por"].startswith(COMECO_DE_QUEM_PROPOS_PELO_ASSISTENTE):
            continue
        if not painel.dentro_do_periodo(correcao["criado_em"], desde, ate):
            continue
        # A correção nasceu de uma rodada simulada (ou sem rodada gravada): fica de fora
        if not _correcao_de_uma_rodada_real(rodadas_do_assistente, correcao):
            continue
        # Desfeita pela empresa, ou retirada que ela cancelou: recusada
        if correcao["status"] in (correcoes.DESFEITA, "CANCELADA"):
            contagem["recusadas"] += 1
        elif correcao["status"] == "APLICADA":
            # Aplicada: corrigida se a mesma célula recebeu outra correção aplicada depois
            if _celula_mudou_depois(todas, posicao):
                contagem["corrigidas"] += 1
            else:
                contagem["aprovadas"] += 1
    return contagem


def _celula_mudou_depois(todas: list[dict], posicao: int) -> bool:
    """True se, depois da correção nesta posição da lista, outra correção APLICADA mexeu na mesma célula.

    Recebe: todas — as correções, na ordem em que foram pedidas; posicao — a da correção que se quer saber.
    """
    correcao = todas[posicao]
    # Só as que vieram depois desta
    for outra in todas[posicao + 1:]:
        mesmo_envio = outra["processamento_id"] == correcao["processamento_id"]
        mesma_celula = outra["linha"] == correcao["linha"] and outra["campo"] == correcao["campo"]
        if mesmo_envio and mesma_celula and outra["status"] == "APLICADA":
            return True
    return False


# ---------------- Conferidor da leitura: as suspeitas que viraram pergunta ----------------

def _contagem_do_conferidor(conexao, desde: date | None, ate: date | None, envios_do_conferidor_real: set) -> dict:
    """As suspeitas do Conferidor em envios recebidos no período, em que ele conferiu com o modelo real, e como a empresa
    respondeu cada uma.

    Recebe: conexao; desde e ate (o período); envios_do_conferidor_real — os envios em que ele conferiu com o modelo
    real. Aprovada: a empresa corrigiu o valor (a suspeita valeu). Recusada: a empresa confirmou que o valor estava
    certo (alarme falso). Sem resposta ainda: não conta.
    """
    # Garante que a tabela dos envios existe
    processamentos._preparar(conexao)
    # Só os envios cujo perfil tem ao menos uma pergunta do Conferidor (o filtro poupa abrir os outros perfis)
    consulta = conexao.execute("SELECT processamento_id, perfil, criado_em FROM processamentos "
                               "WHERE perfil LIKE ? OR perfil LIKE ?",
                               ("%" + COMECO_DA_PERGUNTA_DO_CONFERIDOR + "%",
                                "%" + COMECO_DA_PERGUNTA_DO_CONFERIDOR_V1 + "%"))
    contagem = _contagem_vazia()
    for processamento_id, perfil_em_json, criado_em in consulta:
        # Envio recebido fora do período: não conta
        if not painel.dentro_do_periodo(criado_em, desde, ate):
            continue
        # As suspeitas deste envio vieram da simulação: não contam
        if processamento_id not in envios_do_conferidor_real:
            continue
        perguntas = json.loads(perfil_em_json).get("perguntas_da_ia", [])
        celulas_corrigidas = _celulas_corrigidas(conexao, processamento_id)
        respostas_da_empresa = validador.resolucoes(conexao, processamento_id)
        for pergunta in perguntas:
            # Só as perguntas que nasceram de uma suspeita do Conferidor (as outras são do Leitor)
            if not pergunta["pergunta"].startswith(COMECOS_DA_PERGUNTA_DO_CONFERIDOR):
                continue
            # A empresa corrigiu o valor: a suspeita valeu
            if (pergunta["linha"], pergunta["campo"]) in celulas_corrigidas:
                contagem["aprovadas"] += 1
                continue
            # A empresa confirmou que estava certo: alarme falso
            regra_da_pergunta = validador.PREFIXO_DA_PERGUNTA_DA_IA + (pergunta["campo"] or "PESSOA")
            if respostas_da_empresa.get((regra_da_pergunta, pergunta["linha"])) == "CONFIRMADO":
                contagem["recusadas"] += 1
    return contagem


def _celulas_corrigidas(conexao, processamento_id: str) -> set:
    """As células (linha, campo) do envio que têm uma correção aplicada. Ex.: {(5, "cpf"), (8, "data_admissao")}."""
    celulas = set()
    for correcao in correcoes.listar(conexao, processamento_id, "APLICADA"):
        celulas.add((correcao.linha, correcao.campo))
    return celulas


# ---------------- Endomarketing: os materiais gerados ----------------

def _contagem_do_endomarketing(conexao, desde: date | None, ate: date | None) -> dict:
    """Os materiais gerados no período com o modelo real e o que o especialista fez: publicou (aprovado), descartou ou
    retirou (recusado).

    Rascunho (ainda sem decisão) não conta. "Aprovado pela empresa" é do modelo anterior ao ADR-115 e conta como
    aprovado. O material escrito pela simulação (modelo "mock") não conta.
    """
    # Garante que a tabela existe
    endomarketing._preparar(conexao)
    consulta = conexao.execute("SELECT status, criado_em, modelo FROM materiais_endomarketing")
    contagem = _contagem_vazia()
    for status, criado_em, modelo in consulta:
        # Gerado fora do período: não conta
        if not painel.dentro_do_periodo(criado_em, desde, ate):
            continue
        # Escrito pela simulação: não conta
        if modelo == MODELO_SIMULADO:
            continue
        # Publicado (ou aprovado no modelo anterior): o texto foi aceito como veio
        if status in (endomarketing.PUBLICADO, endomarketing.APROVADO):
            contagem["aprovadas"] += 1
        # Descartado ou retirado: recusado
        elif status in (endomarketing.DESCARTADO, endomarketing.RETIRADO):
            contagem["recusadas"] += 1
    return contagem


# ---------------- Todos os agentes ----------------

def aceitacao_por_agente(conexao, desde: date | None = None, ate: date | None = None) -> dict:
    """A aceitação de cada agente de IA no período (None nas duas datas = tudo), só com as propostas do modelo real.

    Recebe: conexao; desde e ate — as datas do período, inclusive (ou None). Devolve: {identificador do agente:
    {"aceitacao": {aprovadas, corrigidas, recusadas, percentual_aprovadas, fonte} ou None,
    "sem_medida_porque": texto ou None}}, com os identificadores de services/painel.py (AGENTES_DE_IA).
    Só contagens: nenhum dado de pessoa.
    """
    # Todas as execuções gravadas (sem o período: a execução pode ter começado na véspera da proposta): elas dizem em
    # quais envios cada agente trabalhou com o modelo real
    execucoes_gravadas = execucoes.listar(conexao)
    envios_do_leitor_real = _envios_com_trabalho_real(execucoes_gravadas, "leitor_de_documentos")
    envios_do_conferidor_real = _envios_com_trabalho_real(execucoes_gravadas, "conferidor_da_leitura")
    rodadas_do_assistente = _rodadas_do_assistente(execucoes_gravadas)
    # As colunas dos mapeamentos servem a dois agentes: conta uma vez só
    dos_mapeamentos = _contagens_dos_mapeamentos(conexao, desde, ate, envios_do_leitor_real)
    return {
        "leitor_de_documentos": _resultado(dos_mapeamentos["leitor_de_documentos"], FONTE_DO_LEITOR),
        "conferidor_da_leitura": _resultado(_contagem_do_conferidor(conexao, desde, ate, envios_do_conferidor_real),
                                            FONTE_DO_CONFERIDOR, tem_corrigidas=False),
        "interpretador": _resultado(dos_mapeamentos["interpretador"], FONTE_DO_INTERPRETADOR),
        "assistente_de_correcao": _resultado(_contagem_do_assistente(conexao, desde, ate, rodadas_do_assistente),
                                             FONTE_DO_ASSISTENTE),
        "validacao_perguntas": _sem_fonte(SEM_MEDIDA_NA_VALIDACAO),
        "endomarketing": _resultado(_contagem_do_endomarketing(conexao, desde, ate), FONTE_DO_ENDOMARKETING,
                                    tem_corrigidas=False),
        "guardrail_bedrock": _sem_fonte(SEM_MEDIDA_NO_GUARDRAIL),
    }
