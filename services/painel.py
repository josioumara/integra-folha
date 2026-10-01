"""Consultas do desempenho da IA: o que o banco acompanha na sub-aba "Desempenho da IA".

Tudo sai de duas tabelas que já existem, sem dado pessoal:
- execucoes_agentes (services/execucoes.py): cada etapa executada por um agente, uma regra ou uma pessoa;
- eventos (services/auditoria.py): o que aconteceu com cada arquivo (correção aplicada, handoff,
  injeção barrada, homologação...).

Os números são calculados aqui, nunca na tela. Tokens e custo só aparecem quando foram medidos pelo
provedor; sem medição, o painel diz "não medido" (ADR-36).
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from models.contratos import EstadoProcessamento
from services import auditoria, execucoes, processamentos

# Onde ficam os resultados das avaliações
PASTA_DE_RESULTADOS = Path(__file__).resolve().parent.parent / "data" / "avaliacao" / "resultados"
NAO_MEDIDO = "não medido"
# Eventos da auditoria que contam como "o guardrail agiu"
EVENTOS_DE_GUARDRAIL = ("INJECAO_REMOVIDA", "INJECAO_NO_CHAT")
# A origem gravada numa execução simulada: a IA em MOCK, sem modelo de verdade (services/execucoes.registrar)
ORIGEM_SIMULADA = "MOCK"
# Eventos da auditoria que contam como intervenção humana
EVENTOS_HUMANOS = ("MAPEAMENTO_APROVADO", "CORRECAO_APLICADA", "CORRECAO_CANCELADA", "ALERTA_JUSTIFICADO",
                   "HOMOLOGADO", "REJEITADO", "RETIRADA_CONFIRMADA_PELA_EMPRESA", "RETIRADA_CANCELADA_PELA_EMPRESA")


# O horário de Brasília (UTC−3): as datas do filtro de período são as do calendário da especialista, não as do horário
# universal em que os horários são gravados
FUSO_DE_BRASILIA = timezone(timedelta(hours=-3))


def dia_em_brasilia(momento: str) -> date:
    """O dia, no calendário de Brasília, de um horário gravado (texto no padrão internacional).

    Por quê: os horários são gravados em horário universal (UTC). Às 22h de 28/09 em Brasília já é 29/09 em UTC; sem
    converter, o trabalho feito entre 21h e meia-noite ficaria fora do "até hoje" do filtro.
    Recebe: momento — ex.: "2026-09-29T00:50:00+00:00" (ou só a data, "2026-09-28"). Devolve: a data em Brasília.
    Exemplo: "2026-09-29T00:50:00+00:00" → date(2026, 9, 28); "2026-09-28" → date(2026, 9, 28).
    """
    # Só a data (sem hora): já é o dia
    if len(momento) == 10:
        return date.fromisoformat(momento)
    horario = datetime.fromisoformat(momento)
    # Horário sem o fuso gravado: é do horário universal, como os outros da aplicação
    if horario.tzinfo is None:
        horario = horario.replace(tzinfo=timezone.utc)
    return horario.astimezone(FUSO_DE_BRASILIA).date()


def dentro_do_periodo(momento: str | None, desde: date | None, ate: date | None) -> bool:
    """True se o horário está entre as datas do período (inclusive), no calendário de Brasília. Sem data, sem limite.

    Recebe: momento (texto do horário gravado, ou None); desde e ate (date ou None).
    Ex.: ("2026-09-29T00:50:00+00:00", date(2026, 9, 1), date(2026, 9, 28)) → True (em Brasília ainda é 28/09).
    Sem horário gravado, não dá para dizer que está no período: False.
    """
    if not momento:
        return False
    dia = dia_em_brasilia(momento)
    # Antes do começo ou depois do fim do período
    if desde is not None and dia < desde:
        return False
    if ate is not None and dia > ate:
        return False
    return True


def periodo_do_endereco(de: str, ate: str) -> tuple[date | None, date | None]:
    """As datas do período que vieram no endereço (?de=AAAA-MM-DD&ate=AAAA-MM-DD), prontas para os filtros.

    Recebe: de e ate — textos (vazio = sem limite daquele lado). Devolve: (desde, ate), cada um date ou None.
    Levanta ValueError (a rota responde 400) com data que não existe ou com o começo depois do fim.
    Ex.: ("2026-09-01", "2026-09-30") → (date(2026, 9, 1), date(2026, 9, 30)); ("", "") → (None, None).
    """
    desde = _data_do_endereco(de, "de")
    ate_o_dia = _data_do_endereco(ate, "ate")
    # O começo não pode vir depois do fim
    if desde is not None and ate_o_dia is not None and desde > ate_o_dia:
        raise ValueError("O começo do período vem depois do fim: confira as datas.")
    return desde, ate_o_dia


def _data_do_endereco(texto: str, nome: str) -> date | None:
    """Uma data do endereço (AAAA-MM-DD), ou None se veio vazia. Levanta ValueError se não for uma data.

    Ex.: ("2026-09-28", "de") → date(2026, 9, 28); ("", "ate") → None; ("28/09/2026", "de") → ValueError.
    """
    # Vazio: sem limite
    if not texto or not texto.strip():
        return None
    # try/except: um texto que não é data vira um erro claro, e não uma falha do servidor
    try:
        return date.fromisoformat(texto.strip())
    except ValueError as erro:
        raise ValueError(f"A data \"{nome}\" do período precisa estar no formato AAAA-MM-DD.") from erro


def execucoes_filtradas(conexao, processamento_id: str | None = None, agente: str | None = None,
                        modelo: str | None = None, desde: date | None = None, ate: date | None = None) -> list[dict]:
    """As execuções com os filtros do painel (None = todos)."""
    selecionadas = []
    for execucao in execucoes.listar(conexao, processamento_id):
        if agente is not None and execucao["agente"] != agente:
            continue
        if modelo is not None and execucao["modelo"] != modelo:
            continue
        if not dentro_do_periodo(execucao["inicio"], desde, ate):
            continue
        selecionadas.append(execucao)
    return selecionadas


def so_execucoes_reais(lista: list[dict]) -> list[dict]:
    """Só as execuções que aconteceram de verdade: tira as simuladas (a IA em MOCK).

    Por quê: a tela Acompanhamento dos agentes mostra o trabalho feito com o modelo real. Uma execução simulada devolve
    uma resposta pronta, sem modelo nenhum; contá-la faria um agente parecer que trabalhou quando só a simulação rodou.
    As execuções sem modelo (a Regra, o Validador, o Humano...) continuam: elas aconteceram, só não usam IA.
    Recebe: lista — as execuções (execucoes.listar ou execucoes_filtradas). Devolve: a mesma lista, sem as simuladas.
    Ex.: [{"agente": "Interpretador", "origem": "MOCK"}, {"agente": "Interpretador", "origem": "REAL"}] → só a 2ª.
    """
    reais = []
    for execucao in lista:
        # A execução simulada fica de fora (a origem MOCK sai do modelo "mock"; services/execucoes.registrar)
        if execucao["origem"] == ORIGEM_SIMULADA:
            continue
        reais.append(execucao)
    return reais


def valores_para_filtro(conexao, coluna: str) -> list[str]:
    """Os valores que existem numa coluna das execuções (ex.: os agentes), para as listas de filtro."""
    if coluna not in ("processamento_id", "agente", "modelo"):
        raise ValueError(f"Coluna sem filtro: {coluna}")
    valores = set()
    for execucao in execucoes.listar(conexao):
        if execucao[coluna]:
            valores.add(execucao[coluna])
    return sorted(valores)


def _soma_medida(lista: list[dict], coluna: str):
    """A soma de tokens ou custo; se nenhuma execução foi medida, "não medido" (nunca zero inventado)."""
    medidos = []
    for execucao in lista:
        if execucao[coluna] is not None:
            medidos.append(execucao[coluna])
    if not medidos:
        return NAO_MEDIDO
    return sum(medidos)


def visao_agregada(lista: list[dict]) -> dict:
    """Os cards do topo, calculados da mesma lista de execuções que a tabela mostra."""
    arquivos, com_problema, guardrails, humanas = set(), 0, 0, 0
    for execucao in lista:
        arquivos.add(execucao["processamento_id"])
        if execucao["status"] in (execucoes.ERRO, execucoes.BLOQUEADO):
            com_problema += 1
        if execucao["guardrail_disparado"]:
            guardrails += 1
        if execucao["agente"] == "Humano":
            humanas += 1
    return {"execucoes": len(lista), "processamentos": len(arquivos), "com_erro_ou_bloqueio": com_problema,
            "guardrails_disparados": guardrails, "intervencoes_humanas": humanas,
            "tokens_entrada": _soma_medida(lista, "tokens_entrada"), "custo_usd": _soma_medida(lista, "custo_usd")}


def latencia_por_agente(lista: list[dict]) -> list[dict]:
    """Por agente: quantas execuções, a duração média e quantas deram erro ou foram bloqueadas."""
    por_agente = {}
    for execucao in lista:
        dados = por_agente.setdefault(execucao["agente"], {"agente": execucao["agente"], "execucoes": 0,
                                                             "soma_duracao_s": 0.0, "com_erro_ou_bloqueio": 0})
        dados["execucoes"] += 1
        dados["soma_duracao_s"] += execucao["duracao_s"]
        if execucao["status"] in (execucoes.ERRO, execucoes.BLOQUEADO):
            dados["com_erro_ou_bloqueio"] += 1
    tabela = []
    for agente in sorted(por_agente):
        dados = por_agente[agente]
        tabela.append({"agente": agente, "execucoes": dados["execucoes"],
                       "duracao_media_s": round(dados["soma_duracao_s"] / dados["execucoes"], 3),
                       "com_erro_ou_bloqueio": dados["com_erro_ou_bloqueio"]})
    return tabela


def _etapa_sem_a_situacao(etapa: str) -> str:
    """A etapa sem a situação do fim, para juntar as execuções da mesma etapa.

    Ex.: "conversa:corrigir" → "conversa"; "gerar_material:gerado" → "gerar_material"; "interpretar" → "interpretar".
    """
    return etapa.split(":")[0]


def custo_por_etapa(lista: list[dict]) -> list[dict]:
    """O custo da IA por agente e etapa (ADR-131): execuções, quantas medidas, tokens, custo total e médio.

    Só entram as execuções de IA (as que têm modelo); regras e pessoas não custam IA. O custo médio divide pelo número
    de execuções MEDIDAS (as sem medição não viram zero). Ordem: do maior custo para o menor; sem medição, no fim.
    Ex.: [{"agente": "Leitor de documentos", "etapa": "ler_texto_corrido", "execucoes": 3, "medidas": 3,
           "tokens_entrada": 9100, "tokens_saida": 1200, "custo_usd": 0.0412, "custo_medio_usd": 0.0137}, ...].
    """
    por_etapa = {}
    for execucao in lista:
        # Regra ou pessoa (sem modelo): não há IA para custar
        if not execucao["modelo"]:
            continue
        chave = (execucao["agente"], _etapa_sem_a_situacao(execucao["etapa"]))
        if chave not in por_etapa:
            por_etapa[chave] = {"agente": chave[0], "etapa": chave[1], "execucoes": 0, "medidas": 0,
                                "tokens_entrada": None, "tokens_saida": None, "custo_usd": None}
        dados = por_etapa[chave]
        dados["execucoes"] += 1
        # Só a execução medida soma (vazio é "não medido", nunca zero)
        if execucao["custo_usd"] is not None:
            dados["medidas"] += 1
            dados["custo_usd"] = (dados["custo_usd"] or 0.0) + execucao["custo_usd"]
            dados["tokens_entrada"] = (dados["tokens_entrada"] or 0) + (execucao["tokens_entrada"] or 0)
            dados["tokens_saida"] = (dados["tokens_saida"] or 0) + (execucao["tokens_saida"] or 0)
    tabela = []
    for dados in por_etapa.values():
        dados["custo_medio_usd"] = None
        if dados["medidas"]:
            dados["custo_usd"] = round(dados["custo_usd"], 6)
            dados["custo_medio_usd"] = round(dados["custo_usd"] / dados["medidas"], 6)
        tabela.append(dados)
    tabela.sort(key=_ordem_do_custo)
    return tabela


def _ordem_do_custo(linha: dict) -> tuple:
    """A ordem da tabela de custo: primeiro as medidas, do maior custo para o menor; depois as sem medição."""
    if linha["custo_usd"] is None:
        return (1, 0.0, linha["agente"], linha["etapa"])
    return (0, -linha["custo_usd"], linha["agente"], linha["etapa"])


# ---------------- Cartões dos agentes (tela Acompanhamento dos agentes) ----------------

# Os agentes de IA, na ordem em que entram no trabalho (do arquivo da empresa até o Endomarketing do banco).
# Cada agente tem:
#   - "agente": um identificador fixo, para a tela (nunca muda, mesmo se o nome na tela mudar);
#   - "nome_na_tela" e "o_que_faz": o que a especialista do banco lê no cartão (uma frase simples, sem jargão);
#   - "nomes_gravados": como o agente aparece na coluna "agente" de execucoes_agentes. Um agente pode ter mais de um
#     nome (ex.: "Leitor de Documentos" e "Leitor de documentos", com e sem a maiúscula); os nomes se juntam;
# Ficam de fora "Regra" e "Humano" (não são IA) e as etapas feitas por código sem IA (RAG, Normalizador, Validador,
# Motor de planejamento). O Consultor saiu do sistema (ADR-144): as execuções antigas dele (e as dos subagentes dele)
# continuam na visão geral e na tabela de custo, porque gasto não se apaga, mas não ganham cartão.
#   - "registra_o_trabalho": False quando o agente ainda não grava em execucoes_agentes (o cartão diria que o trabalho
#     ainda não é registrado, em vez de dizer que ele não trabalhou, o que seria falso). Todos gravam: o Leitor de
#     documentos e o Conferidor da leitura também gravam uma execução por leitura de texto corrido
#     (services/processamentos.py grava, com o número do envio).
AGENTES_DE_IA = (
    {"agente": "leitor_de_documentos", "nome_na_tela": "Leitor de documentos",
     "o_que_faz": "Lê os arquivos em texto corrido (um Word sem tabela) e preenche os campos do layout, "
                  "pessoa por pessoa.",
     "nomes_gravados": ("Leitor de Documentos", "Leitor de documentos"), "registra_o_trabalho": True},
    {"agente": "conferidor_da_leitura", "nome_na_tela": "Conferidor da leitura",
     "o_que_faz": "Confere o que o Leitor entendeu e transforma cada suspeita de erro numa pergunta para a empresa.",
     "nomes_gravados": ("Conferidor da Leitura", "Conferidor da leitura"), "registra_o_trabalho": True},
    {"agente": "interpretador", "nome_na_tela": "Interpretador",
     "o_que_faz": "Descobre qual coluna da planilha da empresa corresponde a cada campo do layout do banco.",
     "nomes_gravados": ("Interpretador",), "registra_o_trabalho": True},
    {"agente": "assistente_de_correcao", "nome_na_tela": "Assistente de Correção",
     "o_que_faz": "Conversa com a empresa sobre as pendências e ajuda a corrigi-las, sem aprovar nada sozinho.",
     "nomes_gravados": ("Assistente de Correção",), "registra_o_trabalho": True},
    {"agente": "validacao_perguntas", "nome_na_tela": "Agente de validação (perguntas)",
     "o_que_faz": "Escreve, em linguagem simples, a pergunta que a empresa responde para resolver cada pendência.",
     "nomes_gravados": ("Agente de validação (perguntas)",), "registra_o_trabalho": True},
    {"agente": "endomarketing", "nome_na_tela": "Endomarketing",
     "o_que_faz": "Escreve os materiais de divulgação para os funcionários, com os benefícios que o especialista "
                  "escolheu.",
     "nomes_gravados": ("Endomarketing",), "registra_o_trabalho": True},
    # O detector de ataques do Bedrock Guardrails (ADR-147): cada checagem de mensagem vira uma execução, com o tempo,
    # o resultado e o custo. Fica por último porque confere as mensagens de fora de todas as etapas
    {"agente": "guardrail_bedrock", "nome_na_tela": "Bedrock Guardrails",
     "o_que_faz": "Confere as mensagens escritas por pessoas (o chat, os comentários, o destaque e o documento do "
                  "catálogo) e barra as que tentam dar ordens aos agentes.",
     "nomes_gravados": ("Bedrock Guardrails",), "registra_o_trabalho": True},
)


def _execucao_e_do_agente(agente_de_ia: dict, execucao: dict) -> bool:
    """True se a execução é um trabalho deste agente: o nome gravado é um dos nomes dele.

    Ex.: a execução {"agente": "Leitor de documentos", "etapa": "ler_texto_corrido"} é do Leitor de documentos;
    a {"agente": "Consultor (agente único)", "etapa": "pergunta:RESPONDIDO"}, antiga, não é de nenhum cartão.
    """
    # O nome gravado precisa ser um dos nomes deste agente
    return execucao["agente"] in agente_de_ia["nomes_gravados"]


def _cartao_do_agente(agente_de_ia: dict, lista: list[dict]) -> dict:
    """O cartão de um agente: quantas vezes trabalhou, como terminou, se foi com IA real, tempo e custo.

    Recebe: agente_de_ia (um item de AGENTES_DE_IA); lista (as execuções). Devolve o cartão (ver cartoes_por_agente).
    Sem nenhuma execução, as contagens ficam em zero e duração, última execução e custo em None (nada inventado).
    """
    # O cartão começa zerado, com o que a tela escreve sobre o agente
    cartao = {"agente": agente_de_ia["agente"], "nome_na_tela": agente_de_ia["nome_na_tela"],
              "o_que_faz": agente_de_ia["o_que_faz"],
              "registra_o_trabalho": agente_de_ia["registra_o_trabalho"], "execucoes": 0, "deram_certo": 0, "com_erro": 0,
              "barradas_pelo_guardrail": 0, "com_ia_real": 0, "simuladas": 0, "duracao_media_s": None,
              "ultima_execucao": None, "custo_usd": None}
    soma_da_duracao = 0.0
    custos_medidos = []
    for execucao in lista:
        # Execução de outro agente: não entra neste cartão
        if not _execucao_e_do_agente(agente_de_ia, execucao):
            continue
        cartao["execucoes"] += 1
        # Como terminou: deu certo, travou (erro) ou o guardrail barrou o pedido inteiro
        if execucao["status"] == execucoes.OK:
            cartao["deram_certo"] += 1
        elif execucao["status"] == execucoes.ERRO:
            cartao["com_erro"] += 1
        elif execucao["status"] == execucoes.BLOQUEADO:
            cartao["barradas_pelo_guardrail"] += 1
        # Com IA de verdade (REAL) ou simulada (MOCK), pela coluna origem
        if execucao["origem"] == "MOCK":
            cartao["simuladas"] += 1
        else:
            cartao["com_ia_real"] += 1
        soma_da_duracao += execucao["duracao_s"]
        # O custo só soma quando foi medido: vazio é "não medido", nunca zero
        if execucao["custo_usd"] is not None:
            custos_medidos.append(execucao["custo_usd"])
        # Os horários são texto no padrão internacional: o maior texto é o mais recente
        if cartao["ultima_execucao"] is None or execucao["inicio"] > cartao["ultima_execucao"]:
            cartao["ultima_execucao"] = execucao["inicio"]
    # A duração média só existe se o agente trabalhou ao menos uma vez
    if cartao["execucoes"] > 0:
        cartao["duracao_media_s"] = round(soma_da_duracao / cartao["execucoes"], 3)
    # O custo só existe se ao menos uma execução foi medida
    if custos_medidos:
        cartao["custo_usd"] = round(sum(custos_medidos), 6)
    return cartao


def cartoes_por_agente(lista: list[dict], aceitacao_por_agente: dict | None = None) -> list[dict]:
    """Um cartão por agente de IA, na ordem do fluxo, para a tela Acompanhamento dos agentes.

    Recebe: lista — as execuções (execucoes.listar ou execucoes_filtradas, já no período escolhido);
    aceitacao_por_agente — o que services/aceitacao_dos_agentes.aceitacao_por_agente devolve (ou None: sem aceitação).
    Devolve uma lista de dicionários:
    {agente, nome_na_tela, o_que_faz, registra_o_trabalho, execucoes, deram_certo, com_erro, barradas_pelo_guardrail,
     com_ia_real, simuladas, duracao_media_s, ultima_execucao, custo_usd, aceitacao, aceitacao_sem_medida_porque}.
    "aceitacao" é {aprovadas, corrigidas, recusadas, percentual_aprovadas, fonte} ou None ("não medido" na tela, com o
    porquê em aceitacao_sem_medida_porque). Nenhum dado de pessoa: só contagens, tempos e custo.
    Ex.: [{"agente": "interpretador", "nome_na_tela": "Interpretador", "execucoes": 3, "deram_certo": 3, ...}, ...]
    """
    cartoes = []
    # Todos os agentes aparecem, mesmo os que não trabalharam (a tela diz que não houve execução com o modelo real)
    for agente_de_ia in AGENTES_DE_IA:
        cartao = _cartao_do_agente(agente_de_ia, lista)
        # A aceitação deste agente, quando foi calculada (sem ela, nada inventado: None)
        aceitacao_do_agente = {"aceitacao": None, "sem_medida_porque": None}
        if aceitacao_por_agente is not None and agente_de_ia["agente"] in aceitacao_por_agente:
            aceitacao_do_agente = aceitacao_por_agente[agente_de_ia["agente"]]
        cartao["aceitacao"] = aceitacao_do_agente["aceitacao"]
        cartao["aceitacao_sem_medida_porque"] = aceitacao_do_agente["sem_medida_porque"]
        cartoes.append(cartao)
    return cartoes


def resumo_dos_arquivos(conexao, empresas_ids: list[str]) -> dict:
    """Arquivos recebidos, homologados e a taxa de homologação (só arquivos das empresas informadas)."""
    recebidos, homologados = 0, 0
    for empresa_id in empresas_ids:
        for envio in processamentos.listar(conexao, empresa_id):
            recebidos += 1
            if envio.status == EstadoProcessamento.HOMOLOGADO:
                homologados += 1
    taxa = round(homologados / recebidos, 3) if recebidos else None
    return {"arquivos_recebidos": recebidos, "arquivos_homologados": homologados, "taxa_de_homologacao": taxa}


def linha_do_tempo(conexao, processamento_id: str) -> list[dict]:
    """A história de um processamento: execuções e eventos juntos, na ordem em que aconteceram.

    Mostra as voltas (correções, revalidação, handoff para o Interpretador, injeção barrada) sem nenhum
    dado pessoal: só etapas, quem executou, situação e detalhes técnicos (contagens, nomes de regras).
    """
    momentos = []
    for execucao in execucoes.listar(conexao, processamento_id):
        detalhe = f"{execucao['duracao_s']} s"
        if execucao["tipo_erro"]:
            detalhe += f" · {execucao['tipo_erro']}"
        momentos.append({"momento": execucao["inicio"], "tipo": "execução", "etapa": execucao["etapa"],
                         "quem": execucao["agente"], "situacao": execucao["status"], "detalhe": detalhe})
    for evento in auditoria.eventos(conexao, processamento_id):
        momentos.append({"momento": evento["criado_em"], "tipo": "evento", "etapa": evento["etapa"],
                         "quem": "Humano" if evento["tipo"] in EVENTOS_HUMANOS else "Sistema",
                         "situacao": evento["tipo"], "detalhe": json.dumps(evento["detalhe"], ensure_ascii=False)})
    # Os horários são texto no padrão internacional: a ordem do texto é a ordem do tempo
    momentos.sort(key=_momento)
    return momentos


def _momento(item: dict) -> str:
    """O horário de um item da linha do tempo, só até os segundos (para execuções e eventos se alinharem)."""
    return item["momento"][:19]


def contagem_de_eventos(conexao, processamento_id: str) -> dict:
    """Quantas correções, handoffs, injeções barradas e validações o processamento teve."""
    contagem = {"correcoes_aplicadas": 0, "handoffs": 0, "injecoes_barradas": 0, "validacoes": 0}
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "CORRECAO_APLICADA":
            contagem["correcoes_aplicadas"] += 1
        elif evento["tipo"] == "HANDOFF_REMAPEAMENTO":
            contagem["handoffs"] += 1
        elif evento["tipo"] in EVENTOS_DE_GUARDRAIL:
            contagem["injecoes_barradas"] += 1
        elif evento["tipo"] == "VALIDADO":
            contagem["validacoes"] += 1
    return contagem


# ---------------- Avaliação ----------------

def _ler_resultado(nome: str) -> dict | None:
    """Um arquivo de resultado de avaliação (None se ainda não foi gerado)."""
    caminho = PASTA_DE_RESULTADOS / nome
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def resultados_do_interpretador() -> list[dict]:
    """B0 a B5: o que já foi medido (com IC 95%) e o que espera o provedor de IA."""
    linhas = []
    for configuracao in ("B0", "B1", "B2", "B3", "B4", "B5"):
        resultado = _ler_resultado(f"{configuracao}.json")
        if resultado is None:
            linhas.append({"configuracao": configuracao, "situacao": "aguardando o provedor de IA (Fase 14)",
                           "acuracia_por_campo": None, "ic95": None, "abstencao_recall": None})
            continue
        intervalo = resultado["ic95_acuracia_por_campo"]
        linhas.append({"configuracao": configuracao, "situacao": "medido", "acuracia_por_campo":
                       resultado["acuracia_por_campo"], "ic95": f"{intervalo[0]:.1%} a {intervalo[1]:.1%}",
                       "abstencao_recall": resultado["abstencao_recall"]})
    return linhas


def campos_mais_dificeis(configuracao: str = "B0", quantidade: int = 10) -> list[dict]:
    """Os campos em que a configuração mais erra (do pior para o melhor); lista vazia se não foi medida.

    Exemplo de item: {"campo": "valor_renda", "colunas": 101, "acertos": 0, "acuracia": 0.0}
    """
    resultado = _ler_resultado(f"{configuracao}.json")
    # Configuração não medida, ou medida antes de existir a quebra por campo
    if resultado is None or "acuracia_de_cada_campo" not in resultado:
        return []
    # O resultado já vem do pior para o melhor: basta pegar os primeiros
    return resultado["acuracia_de_cada_campo"][:quantidade]


def resultados_do_rag() -> list[dict]:
    """O hit@k dos dois índices do RAG (medido com as 10 consultas de cada um)."""
    resultado = _ler_resultado("rag.json")
    if resultado is None:
        return []
    linhas = []
    for indice, medicao in resultado.items():
        melhor_k = medicao["k_escolhido"]
        linhas.append({"indice": indice, "k_escolhido": melhor_k,
                       # No JSON, as chaves do hit@k são texto ("1", "2"...)
                       "hit_no_k": medicao["hit_at_k"][str(melhor_k)],
                       "trechos_de_outra_empresa": medicao["trechos_de_outra_empresa"]})
    return linhas


def resultados_do_fluxo() -> list[dict]:
    """Os números do fluxo de ponta a ponta (9 arquivos em MOCK), um indicador por linha; vazio se não medido."""
    resultado = _ler_resultado("fluxo.json")
    if resultado is None:
        return []
    resumo = resultado["resumo"]
    falha = resultado["cenario_de_falha"]
    # O cenário de falha em palavras: o certo é parar, nunca virar sucesso
    if falha["virou_sucesso"]:
        resultado_da_falha = "virou sucesso (ERRO)"
    else:
        resultado_da_falha = f"parou em {falha['parou_em']}, sem falso sucesso"
    # Cada linha: o indicador em palavras e o valor medido
    return [
        {"indicador": "Arquivos homologados", "valor": f"{resumo['concluidos']} de {resumo['arquivos']}"},
        {"indicador": "Erros injetados achados na linha certa",
         "valor": f"{resumo['erros_achados']} de {resumo['erros_injetados']}"},
        {"indicador": "Achados fora do gabarito", "valor": str(resumo["achados_fora_do_gabarito"])},
        {"indicador": "Homologados sem edição manual de valor (proxy)",
         "valor": f"{resumo['homologados_sem_edicao_manual']} de {resumo['concluidos']}"},
        {"indicador": "Intervenções humanas por arquivo", "valor": str(resumo["intervencoes_por_arquivo"])},
        {"indicador": "Ciclos de correção por arquivo", "valor": str(resumo["ciclos_de_correcao_por_arquivo"])},
        {"indicador": "Tempo de máquina até homologar (s, MOCK)",
         "valor": str(resumo["segundos_de_maquina_ate_homologar"])},
        {"indicador": "Etapas refeitas ao retomar", "valor": f"{resumo['etapas_refeitas_na_retomada']} "
                                                             f"em {resumo['retomadas']} retomadas"},
        {"indicador": "Provedor fora do ar", "valor": resultado_da_falha},
    ]


def resultados_do_endomarketing() -> list[dict]:
    """Fidelidade, isolamento, recusa e guardrail de saída do Endomarketing, um indicador por linha."""
    resultado = _ler_resultado("endomarketing.json")
    if resultado is None:
        return []
    resumo = resultado["resumo"]
    distancias = resultado["distancias_de_destaque"]
    return [
        {"indicador": "Materiais gerados (6 empresas x 3 tipos)",
         "valor": f"{resumo['materiais_gerados']} de {resumo['materiais']}"},
        {"indicador": "Fidelidade: blocos que passaram na conferência das fontes",
         "valor": f"{resumo['blocos_aprovados']} de {resumo['blocos_escritos']}"},
        {"indicador": "Fontes de outra empresa nos materiais", "valor": str(resumo["fontes_de_outra_empresa"])},
        {"indicador": "Blocos adulterados barrados (número, fonte inventada, fonte de outra empresa)",
         "valor": resumo["adulterados_barrados"]},
        {"indicador": "Destaque que o catálogo traz: achado na seção certa", "valor": resumo["destaques_no_catalogo"]},
        {"indicador": "Destaque que o catálogo NÃO traz: avisado à empresa",
         "valor": f"{resumo['destaques_fora_do_catalogo']} (a busca sozinha não decide; é papel da IA real)"},
        {"indicador": "Distância da busca: tem × não tem",
         "valor": f"tem até {distancias['maior_quando_tem']}; não tem a partir de "
                  f"{distancias['menor_quando_nao_tem']} (as faixas se cruzam)"},
    ]


def camadas_do_guardrail() -> list[dict]:
    """Na prova: a lista, o Bedrock Guardrails e os dois juntos, uma linha por camada; vazio se não medido."""
    resultado = _ler_resultado("guardrail.json")
    if resultado is None or "camadas_na_prova" not in resultado:
        return []
    # A chave "classificador" continua no arquivo do resultado; desde o ADR-147, a camada é o Bedrock Guardrails
    nomes = {"lista": "Lista de padrões", "classificador": "Bedrock Guardrails",
             "juntos": "Lista + Bedrock Guardrails"}
    linhas = []
    for camada, dados in resultado["camadas_na_prova"].items():
        # Camada ainda não medida: a situação aparece escrita, sem número
        if isinstance(dados, str):
            linhas.append({"camada": nomes[camada], "deteccao": dados, "falso_alarme": dados})
        else:
            linhas.append({"camada": nomes[camada], "deteccao": f"{dados['deteccao']:.0%}",
                           "falso_alarme": f"{dados['falso_alarme']:.0%}"})
    return linhas


def resultados_do_guardrail() -> list[dict]:
    """Detecção e falso alarme do guardrail de injeção, nos conjuntos de desenvolvimento e de prova."""
    resultado = _ler_resultado("guardrail.json")
    if resultado is None:
        return []
    linhas = []
    for conjunto in ("desenvolvimento", "prova"):
        dados = resultado[conjunto]
        linhas.append({"conjunto": conjunto, "ataques": dados["ataques"], "deteccao": dados["deteccao"],
                       "normais": dados["normais"], "falso_alarme": dados["falso_alarme"]})
    return linhas
