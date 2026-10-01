"""A página "Teto de gasto da IA" do Portal Interno e a retomada automática dos envios pausados (ADR-139).

Para que serve: o teto de gasto com IA (services/teto_de_gasto.py, ADR-131) pausa a IA quando o gasto do dia ou do
mês chega ao limite. Este arquivo dá ao especialista do banco o que ele precisa para cuidar disso:
    - a situação: o gasto de hoje e do mês, os dois tetos, se a IA está pausada (e desde quando) e quantos envios de
      empresas estão esperando a IA voltar (só o número, nunca a lista: ADR-102);
    - o ajuste de um teto, com o registro de cada mudança (o valor antigo, o novo, quem e quando);
    - a retomada automática: quando o teto é ajustado, ou quando o dia (ou o mês) vira, os envios que pararam por
      causa do teto voltam para a análise sozinhos, sem a empresa precisar clicar em "Tentar de novo".

A regra do teto NÃO mora aqui: ler os tetos, gravar um teto (com a conferência do valor), somar o gasto e dizer se
um teto foi atingido são funções de services/teto_de_gasto.py. Este arquivo só as chama.

Analogia: o teto é o limite do cartão; esta página é o aplicativo do banco em que o dono do cartão vê quanto já
gastou, sobe o limite e, com o limite liberado, as compras que ficaram "aguardando" passam sozinhas.

Detalhes:
- "Pausada desde": o momento da primeira chamada à IA que o teto barrou no período atual (hoje, ou o mês), contado a
  partir da última mudança de um teto. Toda chamada barrada fica na tabela das execuções com o tipo
  TetoDeGastoAtingido (services/execucoes.py). Se o teto foi atingido e ninguém chamou a IA ainda, não há "desde".
- Um envio "pausado pelo teto" é o que está parado em "tentar de novo" com o recado da pausa. Um envio parado por
  outra falha não volta sozinho: continua esperando o clique da empresa.
- A retomada roda uma de cada vez (uma trava na memória do servidor) e para assim que o teto for atingido de novo:
  os envios que faltarem continuam guardados para a próxima vez.
- Risco conhecido (ADR-139): se a empresa clicar em "Tentar de novo" no mesmo instante em que a retomada pega o
  mesmo envio, as duas podem se cruzar. A trava vale só para a retomada; o clique da empresa não passa por ela.
"""
import logging
import math
import threading
import time
from datetime import date, datetime, time as hora_do_dia, timezone

from services import cadastro, execucoes, teto_de_gasto
from workflows import fluxo_empresa

# O registro do servidor (log): as falhas da retomada ficam anotadas, sem derrubar nada
registro = logging.getLogger(__name__)

# Quantas mudanças do teto a página mostra no histórico (as mais recentes)
MUDANCAS_NO_HISTORICO = 50
# De quanto em quanto tempo a aplicação confere se o dia (ou o mês) virou e retoma os envios (5 minutos)
INTERVALO_DA_RETOMADA_S = 300
# O nome da etapa em que o envio fica guardado quando a IA pausa (a mesma do fluxo da empresa)
ETAPA_DA_NOVA_TENTATIVA = "aguardar_nova_tentativa"
# Os nomes dos períodos na tela, para os avisos (ex.: "o teto do dia")
NOMES_DOS_PERIODOS = {teto_de_gasto.PERIODO_DIA: "do dia", teto_de_gasto.PERIODO_MES: "do mês"}
# O gasto que a comparação usa em cada período (ex.: o teto do dia compara com o gasto de hoje)
GASTO_DO_PERIODO = {teto_de_gasto.PERIODO_DIA: "gasto_dia_usd", teto_de_gasto.PERIODO_MES: "gasto_mes_usd"}
# Quando a IA volta sozinha, em palavras, para cada teto atingido
QUANDO_A_IA_VOLTA = {teto_de_gasto.PERIODO_DIA: "à meia-noite (horário de Brasília)",
                     teto_de_gasto.PERIODO_MES: "no dia 1º do mês que vem"}

# A trava da retomada: só uma retomada roda de cada vez (a do ajuste e a periódica nunca juntas)
trava_da_retomada = threading.Lock()
# Se a retomada periódica já foi ligada neste servidor (ela é ligada uma vez só, na partida)
retomada_periodica = {"ligada": False}


def _preparar(conexao) -> None:
    """Cria a tabela do histórico das mudanças do teto, se ainda não existir. Só cria: não grava nada."""
    # Uma linha por mudança: o período, o valor de antes, o valor novo, quando e quem
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS mudancas_do_teto_da_ia (
               id                INTEGER PRIMARY KEY AUTOINCREMENT,
               periodo           TEXT NOT NULL,              -- "dia" ou "mes"
               valor_antigo_usd  DOUBLE PRECISION NOT NULL,  -- o teto que valia antes, em dólares
               valor_novo_usd    DOUBLE PRECISION NOT NULL,  -- o teto gravado, em dólares
               alterado_em       TEXT NOT NULL,              -- quando mudou (UTC, ISO)
               alterado_por      TEXT NOT NULL               -- o login de quem mudou
           )"""
    )


# ---------------- A situação, para a página ----------------

def _inicio_do_periodo_em_utc(periodo: str) -> str:
    """O começo do período atual (hoje, ou o mês) no calendário de Brasília, em texto UTC.

    Recebe: "dia" ou "mes". Devolve: ex.: em 29/09, "dia" → "2026-09-29T03:00:00+00:00" (meia-noite em Brasília).
    """
    # Hoje, no calendário de Brasília
    hoje = teto_de_gasto.hoje_em_brasilia()
    # O primeiro dia do período: hoje mesmo, ou o dia 1º do mês
    primeiro_dia = hoje
    if periodo == teto_de_gasto.PERIODO_MES:
        primeiro_dia = date(hoje.year, hoje.month, 1)
    # A meia-noite desse dia em Brasília, passada para UTC (o mesmo padrão das execuções)
    meia_noite = datetime.combine(primeiro_dia, hora_do_dia(0, 0), tzinfo=teto_de_gasto.FUSO_DE_BRASILIA)
    return meia_noite.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _ultimas_mudancas(conexao) -> dict:
    """A última mudança de cada teto: quando e quem, ou None para o teto que ninguém mudou (vale o valor inicial).

    Recebe: a conexão (a tabela dos tetos já preparada por teto_de_gasto.ler_tetos).
    Devolve: {"dia": {"alterado_em", "alterado_por"} ou None, "mes": ...}.
    """
    # Começa sem mudança nenhuma nos dois períodos
    ultimas = {teto_de_gasto.PERIODO_DIA: None, teto_de_gasto.PERIODO_MES: None}
    # Uma linha por período que o banco já mudou
    linhas = conexao.execute("SELECT periodo, alterado_em, alterado_por FROM limites_de_gasto_da_ia").fetchall()
    for linha in linhas:
        ultimas[linha[0]] = {"alterado_em": linha[1], "alterado_por": linha[2]}
    return ultimas


def _pausada_desde(conexao, atingido: str | None, ultimas_mudancas: dict) -> str | None:
    """Desde quando a IA está pausada: a primeira chamada barrada pelo teto no período atual.

    Recebe: a conexão; o teto atingido ("dia", "mes" ou None); as últimas mudanças dos tetos.
    Devolve: o momento em texto UTC (ex.: "2026-09-29T17:32:10.120+00:00"), ou None se a IA não está pausada ou se
    ninguém chamou a IA desde que o teto foi atingido.
    """
    # IA funcionando: não há "desde"
    if atingido is None:
        return None
    # Conta a partir do começo do período atual...
    a_partir_de = _inicio_do_periodo_em_utc(atingido)
    # ...ou da última mudança de um teto, se foi depois (uma pausa de antes do ajuste já acabou)
    for mudanca in ultimas_mudancas.values():
        if mudanca is None:
            continue
        # O momento da mudança no mesmo formato das execuções (com milésimos), para comparar como texto
        momento_da_mudanca = datetime.fromisoformat(mudanca["alterado_em"]).astimezone(timezone.utc)
        momento_em_texto = momento_da_mudanca.isoformat(timespec="milliseconds")
        if momento_em_texto > a_partir_de:
            a_partir_de = momento_em_texto
    # A tabela das execuções pode ainda não existir num banco novo
    execucoes._preparar(conexao)
    # A primeira chamada barrada pelo teto desde então
    linha = conexao.execute("SELECT MIN(inicio) FROM execucoes_agentes WHERE tipo_erro = ? AND inicio >= ?",
                            (execucoes.TIPO_DA_PAUSA_PELO_TETO, a_partir_de)).fetchone()
    return linha[0]


def _historico(conexao) -> list[dict]:
    """As mudanças do teto, da mais recente para a mais antiga (no máximo MUDANCAS_NO_HISTORICO).

    Recebe: a conexão. Devolve: [{periodo, valor_antigo_usd, valor_novo_usd, alterado_em, alterado_por}].
    """
    # Garante a tabela do histórico
    _preparar(conexao)
    linhas = conexao.execute(
        "SELECT periodo, valor_antigo_usd, valor_novo_usd, alterado_em, alterado_por FROM mudancas_do_teto_da_ia "
        "ORDER BY id DESC LIMIT ?", (MUDANCAS_NO_HISTORICO,)).fetchall()
    historico = []
    for linha in linhas:
        historico.append({"periodo": linha[0], "valor_antigo_usd": float(linha[1]), "valor_novo_usd": float(linha[2]),
                          "alterado_em": linha[3], "alterado_por": linha[4]})
    return historico


def envios_pausados_pelo_teto(conexao) -> list[dict]:
    """Os envios de empresas parados em "tentar de novo" porque a IA foi pausada pelo teto.

    Recebe: a conexão. Devolve: [{"processamento_id", "empresa_id"}], em ordem de envio.
    Como acha: toda pausa pelo teto grava uma execução com o tipo TetoDeGastoAtingido. Os candidatos são os envios
    cuja ÚLTIMA execução foi uma pausa (um envio que voltou já tem uma execução depois dela). De cada candidato,
    confere no fluxo se ele ainda está parado em "tentar de novo" com o recado da pausa. Um envio parado por outra
    falha, ou que já voltou, fica de fora. Assim, o fluxo só é montado para os poucos que estão de fato esperando,
    e não para todo envio que pausou algum dia (a página pergunta de minuto em minuto).
    """
    # A tabela das execuções pode ainda não existir num banco novo
    execucoes._preparar(conexao)
    # Os envios cuja última execução foi uma chamada barrada pelo teto (a leitura de Word barrada não é um envio: o
    # fluxo não a encontra e ela fica de fora na conferência abaixo)
    linhas = conexao.execute(
        "SELECT pausa.processamento_id, pausa.empresa_id FROM execucoes_agentes AS pausa "
        "WHERE pausa.tipo_erro = ? AND pausa.id = (SELECT MAX(ultima.id) FROM execucoes_agentes AS ultima "
        "WHERE ultima.processamento_id = pausa.processamento_id) ORDER BY pausa.id",
        (execucoes.TIPO_DA_PAUSA_PELO_TETO,)).fetchall()
    pausados = []
    for linha in linhas:
        # Onde o fluxo deste envio está agora
        situacao = fluxo_empresa.situacao(conexao, linha[0])
        # Só o que está parado em "tentar de novo"
        if situacao["etapa_atual"] != ETAPA_DA_NOVA_TENTATIVA:
            continue
        # E parado pelo teto (o recado da pausa), e não por outra falha
        pergunta = situacao["pergunta"] or {}
        if pergunta.get("erro") != teto_de_gasto.RECADO_PARA_A_EMPRESA:
            continue
        pausados.append({"processamento_id": linha[0], "empresa_id": linha[1]})
    return pausados


def situacao_da_pagina(conexao) -> dict:
    """Tudo o que a página "Teto de gasto da IA" mostra.

    Recebe: a conexão com o banco.
    Devolve: o resumo do teto_de_gasto.situacao_dos_tetos ({dia, gasto_dia_usd, teto_dia_usd, gasto_mes_usd,
    teto_mes_usd, atingido}) e mais:
      - pausada_desde: o momento (UTC) da primeira chamada barrada, ou None;
      - volta_quando: em palavras, quando a IA volta sozinha (ex.: "à meia-noite (horário de Brasília)"), ou None;
      - ultimas_mudancas: {"dia": {alterado_em, alterado_por} ou None, "mes": ...};
      - envios_esperando: quantos envios de empresas esperam a IA voltar (só o número);
      - teto_maximo_usd: o maior teto aceito;
      - historico: as mudanças do teto, da mais recente para a mais antiga.
    Ex.: {"gasto_dia_usd": 20.4, "teto_dia_usd": 20.0, "atingido": "dia", "envios_esperando": 2, ...}.
    """
    # O gasto e os tetos, pela função do teto (garante as tabelas dele)
    situacao = teto_de_gasto.situacao_dos_tetos(conexao)
    # Quem mudou cada teto, e quando
    ultimas_mudancas = _ultimas_mudancas(conexao)
    situacao["ultimas_mudancas"] = ultimas_mudancas
    # Desde quando está pausada, e quando volta sozinha
    situacao["pausada_desde"] = _pausada_desde(conexao, situacao["atingido"], ultimas_mudancas)
    situacao["volta_quando"] = QUANDO_A_IA_VOLTA.get(situacao["atingido"])
    # Só o número de envios esperando (a lista de empresas nunca sai daqui)
    situacao["envios_esperando"] = len(envios_pausados_pelo_teto(conexao))
    situacao["teto_maximo_usd"] = teto_de_gasto.TETO_MAXIMO_USD
    situacao["historico"] = _historico(conexao)
    return situacao


def aviso_do_teto(conexao) -> dict:
    """O que a faixa do alto do Portal Interno precisa: se a IA está pausada, e por qual teto.

    Recebe: a conexão. Devolve: {"atingido": "dia", "mes" ou None}. É leve: não percorre os envios.
    """
    return {"atingido": teto_de_gasto.periodo_atingido(conexao)}


# ---------------- O ajuste de um teto ----------------

def _valor_em_dolares(valor) -> float:
    """Transforma o valor digitado num número, sem conferir a regra do teto (quem confere é o gravar_teto).

    Recebe: um número, ou um texto com ponto ou vírgula (ex.: "25,50"). Devolve: 25.5.
    Recusa (ValueError): vazio, texto que não é número, "infinito" ou "não é número" (NaN), que nenhuma comparação
    com o teto pegaria.
    """
    # Texto: aceita a vírgula do português no lugar do ponto
    if isinstance(valor, str):
        texto = valor.strip().replace(",", ".")
        try:
            valor = float(texto)
        except ValueError:
            raise ValueError("O teto precisa ser um número, em dólares.") from None
    # Verdadeiro/falso e o que não é número ficam para o gravar_teto recusar com o motivo dele
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return valor
    # "Não é número" (NaN) e infinito: recusados aqui, porque passariam pelas comparações
    if not math.isfinite(valor):
        raise ValueError("O teto precisa ser um número, em dólares.")
    return float(valor)


def _avisos_do_ajuste(situacao: dict, periodo: str) -> list[str]:
    """Os avisos para o especialista depois de gravar um teto.

    Recebe: a situação depois da gravação; o período que mudou.
    Devolve: frases, ex.: ["O teto do dia (US$ 5,00) não passa do gasto de hoje (US$ 7,20): a IA continua pausada
    até a meia-noite (horário de Brasília) ou até o teto subir."]. Lista vazia quando está tudo bem.
    """
    avisos = []
    # O teto novo, e o gasto do mesmo período
    teto_novo = situacao["teto_" + periodo + "_usd"]
    gasto = situacao[GASTO_DO_PERIODO[periodo]]
    # O teto novo não passa do gasto: a IA fica (ou continua) pausada
    if teto_novo <= gasto:
        # O gasto que conta: o de hoje (teto do dia) ou o do mês
        onde_do_gasto = "do mês"
        if periodo == teto_de_gasto.PERIODO_DIA:
            onde_do_gasto = "de hoje"
        avisos.append(f"O teto {NOMES_DOS_PERIODOS[periodo]} ({_em_dolares(teto_novo)}) não passa do gasto "
                      f"{onde_do_gasto} ({_em_dolares(gasto)}): os agentes continuam pausados até "
                      f"{_ate_quando(periodo)} ou até o teto subir.")
    # O teto do dia acima do do mês nunca é alcançado: o do mês chega antes
    if situacao["teto_dia_usd"] > situacao["teto_mes_usd"]:
        avisos.append("O teto do dia está maior que o do mês: o do mês é atingido antes, e o do dia nunca chega a "
                      "pausar os agentes.")
    return avisos


def _ate_quando(periodo: str) -> str:
    """Até quando a IA fica pausada por um teto, em palavras. Ex.: "dia" → "a meia-noite (horário de Brasília)"."""
    if periodo == teto_de_gasto.PERIODO_DIA:
        return "a meia-noite (horário de Brasília)"
    return "o dia 1º do mês que vem"


def _em_dolares(valor: float) -> str:
    """Um valor em dólar com 2 casas e a vírgula do português. Ex.: 20 → "US$ 20,00"."""
    return "US$ " + f"{valor:.2f}".replace(".", ",")


def ajustar_teto(conexao, quem: str, periodo: str, valor) -> dict:
    """O especialista do banco muda um teto: grava, registra no histórico e devolve a página atualizada.

    Recebe: a conexão; o login de quem mudou; o período ("dia" ou "mes"); o valor em dólares (número ou texto).
    Devolve: situacao_da_pagina(conexao) mais "avisos" (frases para o especialista; ver _avisos_do_ajuste) e
    "ia_liberada" (True quando, depois da mudança, nenhum teto está atingido: é a hora de retomar os envios).
    Recusa (ValueError, com o motivo em português): valor que não é número, zero ou negativo, acima do máximo, período
    desconhecido (as regras do teto_de_gasto.gravar_teto) e valor igual ao que já vale ("nada mudou").
    Ex.: ajustar_teto(conexao, "especialista", "dia", "35") → {..., "teto_dia_usd": 35.0, "avisos": []}.
    """
    # O valor como número (a regra do teto é conferida pelo gravar_teto)
    valor_em_dolares = _valor_em_dolares(valor)
    # O teto que vale agora, para o histórico e para saber se mudou algo
    tetos_de_antes = teto_de_gasto.ler_tetos(conexao)
    valor_antigo = tetos_de_antes.get(periodo)
    # O mesmo valor: não há mudança para gravar
    if valor_antigo is not None and valor_em_dolares == valor_antigo:
        raise ValueError(f"O teto {NOMES_DOS_PERIODOS[periodo]} já é {_em_dolares(valor_antigo)}: nada mudou.")
    # Período desconhecido ou valor que não é número: o gravar_teto recusa com o motivo dele (ValueError), antes de
    # qualquer linha do histórico (que não teria o valor de antes ou o novo)
    if valor_antigo is None or not isinstance(valor_em_dolares, float):
        teto_de_gasto.gravar_teto(conexao, periodo, valor_em_dolares, quem)
    # O histórico e o teto numa transação só: a linha do histórico entra primeiro, SEM
    # confirmar; o gravar_teto grava o teto e confirma, levando as duas juntas. Se ele recusar, nada fica gravado
    _preparar(conexao)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conexao.execute(
        "INSERT INTO mudancas_do_teto_da_ia (periodo, valor_antigo_usd, valor_novo_usd, alterado_em, alterado_por) "
        "VALUES (?, ?, ?, ?, ?)", (periodo, valor_antigo, valor_em_dolares, agora, quem.strip()))
    try:
        # Grava pela função do teto (confere o período, o valor e quem; e confirma a transação inteira)
        teto_de_gasto.gravar_teto(conexao, periodo, valor_em_dolares, quem)
    except Exception:
        # Recusado (ou o banco falhou): desfaz a linha do histórico, que ainda não foi confirmada
        conexao.rollback()
        raise
    # A página atualizada, com os avisos
    situacao = situacao_da_pagina(conexao)
    situacao["avisos"] = _avisos_do_ajuste(situacao, periodo)
    situacao["ia_liberada"] = situacao["atingido"] is None
    return situacao


# ---------------- A retomada automática dos envios pausados ----------------

def retomar_envios_pausados(conexao) -> int:
    """Leva de volta para a análise os envios parados pelo teto, enquanto nenhum teto estiver atingido.

    Recebe: a conexão. Devolve: quantos envios voltaram.
    Roda uma de cada vez: se outra retomada estiver em andamento, devolve 0 na hora. Para assim que um teto for
    atingido (antes de cada envio, e quando a própria retomada estoura o teto): os que faltam continuam guardados.
    Um envio que quebra por outro motivo fica anotado no log (só o tipo do erro), e a retomada segue para o próximo.
    """
    # Outra retomada já está rodando: esta não faz nada (a outra cuida dos envios)
    if not trava_da_retomada.acquire(blocking=False):
        return 0
    try:
        retomados = 0
        # Com a IA ainda pausada, nem lista os envios (é o caso comum da volta de 5 em 5 minutos)
        if teto_de_gasto.periodo_atingido(conexao) is not None:
            return retomados
        for envio in envios_pausados_pelo_teto(conexao):
            # Teto atingido de novo: para aqui (os outros envios esperam a próxima vez)
            if teto_de_gasto.periodo_atingido(conexao) is not None:
                break
            try:
                # A mesma retomada do botão "Tentar de novo" (confere a empresa, a etapa e o teto)
                cadastro.tentar_de_novo(conexao, envio["empresa_id"], envio["processamento_id"])
            except teto_de_gasto.TetoDeGastoAtingido:
                # O teto foi atingido no meio: o envio continua guardado, e a retomada para
                break
            except Exception as erro:
                # Outro problema neste envio: anota o tipo (sem dado nenhum) e segue para o próximo
                registro.warning("A retomada automática não conseguiu retomar um envio (%s).", type(erro).__name__)
                continue
            retomados = retomados + 1
        return retomados
    finally:
        # Libera a trava, dando certo ou não
        trava_da_retomada.release()


def retomar_com_conexao_nova(abrir_conexao) -> int:
    """Abre uma conexão, retoma os envios pausados e fecha (usada em segundo plano, fora do pedido da tela).

    Recebe: abrir_conexao — a função que abre a conexão com o banco da aplicação (ex.: auth.conectar).
    Devolve: quantos envios voltaram; 0 se algo falhar (a falha fica no log e nunca derruba o servidor).
    """
    try:
        # Uma conexão só desta retomada (ela roda fora do pedido que a disparou)
        conexao = abrir_conexao()
        try:
            return retomar_envios_pausados(conexao)
        finally:
            # Fecha a conexão, dando certo ou não
            conexao.close()
    except Exception as erro:
        # Sem a retomada agora, a próxima tentativa (em 5 minutos) ou o botão da empresa resolvem
        registro.warning("A retomada automática dos envios falhou (%s).", type(erro).__name__)
        return 0


def _rodar_a_retomada_periodica(abrir_conexao, intervalo_s: float) -> None:
    """O laço da retomada periódica: espera o intervalo e retoma, para sempre (numa linha de execução própria).

    Recebe: a função que abre a conexão; o intervalo em segundos. Devolve: nunca (termina com o servidor).
    É o que faz os envios voltarem sozinhos quando o dia (ou o mês) vira: a cada volta, se nenhum teto estiver
    atingido e houver envio pausado, ele volta para a análise.
    """
    while True:
        # Espera primeiro: na partida do servidor não há pressa
        time.sleep(intervalo_s)
        retomar_com_conexao_nova(abrir_conexao)


def ligar_retomada_periodica(abrir_conexao, intervalo_s: float = INTERVALO_DA_RETOMADA_S) -> bool:
    """Liga, uma vez só, a retomada periódica numa linha de execução de fundo (chamada na partida do servidor).

    Recebe: a função que abre a conexão; o intervalo em segundos (padrão: 5 minutos).
    Devolve: True se ligou agora; False se já estava ligada.
    "Linha de execução de fundo" (thread daemon): um trabalho que corre ao lado do servidor e termina junto com ele.
    """
    # Já ligada neste servidor: não liga outra
    if retomada_periodica["ligada"]:
        return False
    retomada_periodica["ligada"] = True
    # A linha de fundo com o laço da retomada
    linha_de_fundo = threading.Thread(target=_rodar_a_retomada_periodica, args=(abrir_conexao, intervalo_s),
                                      name="retomada-do-teto-da-ia", daemon=True)
    linha_de_fundo.start()
    return True
