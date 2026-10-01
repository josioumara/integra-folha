"""Limite de tentativas de login: depois de 5 senhas erradas seguidas, o login fica bloqueado por 15 minutos (ADR-110).

Para que serve: sem limite, alguém pode tentar milhares de senhas seguidas para o mesmo usuário até acertar. Esse
ataque se chama "força bruta" (tentar todas as combinações, como quem testa todas as chaves de um molho numa
fechadura). O bcrypt (services/auth.py) deixa cada tentativa lenta; este arquivo põe um teto no número delas.

Como funciona, em linguagem simples:
1. Cada senha errada soma 1 no contador daquele login (a contagem vale por 15 minutos a partir do primeiro erro).
2. No 5º erro dentro desses 15 minutos, o login fica bloqueado por 15 minutos. Durante o bloqueio, a senha nem é
   conferida: nem a senha certa entra. Se a senha certa entrasse, o bloqueio não serviria para nada, porque quem
   tenta adivinhar continuaria tentando e saberia quando acertou.
3. Um login certo zera o contador.

Por que a conta é feita pelo login DIGITADO, exista ele ou não: se só os usuários de verdade fossem bloqueados, o
aviso de bloqueio revelaria quais logins existem (o ADR-69 proíbe isso). Assim, um login inventado também é bloqueado
depois de 5 tentativas, e a resposta é igual para os dois.

As tentativas ficam numa tabela do banco (tentativas_de_login), e não na memória do servidor: se o servidor
reiniciar, ou se houver mais de uma cópia dele rodando, a contagem continua valendo. A tabela é criada na primeira
vez que é usada, como as outras (funciona no SQLite e no PostgreSQL pela porta services/banco.py).
"""
import math
from datetime import datetime, timedelta, timezone

# Quantas senhas erradas seguidas bloqueiam o login
LIMITE_DE_ERROS_SEGUIDOS = 5
# Por quanto tempo os erros são somados, a partir do primeiro (erro mais antigo que isso não conta mais)
JANELA_DE_CONTAGEM_EM_MINUTOS = 15
# Por quanto tempo o login fica bloqueado depois do último erro permitido
BLOQUEIO_EM_MINUTOS = 15


def _agora() -> datetime:
    """A data e hora de agora, no horário universal (UTC)."""
    return datetime.now(timezone.utc)


def _como_texto(momento: datetime) -> str:
    """O momento em texto, sempre no mesmo formato, para guardar no banco.

    Ex.: 27/09/2026 14:05:09 (UTC) → "2026-09-27T14:05:09+00:00".
    Sempre com os segundos e sem frações: assim, comparar dois textos dá o mesmo resultado que comparar as datas
    (a limpeza de registros vencidos, mais abaixo, compara os textos direto no banco).
    """
    return momento.astimezone(timezone.utc).isoformat(timespec="seconds")


def preparar_tabela(conexao) -> None:
    """Cria a tabela das tentativas de login, se ainda não existir. Uma linha por login com erro recente."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS tentativas_de_login (
               login            TEXT PRIMARY KEY,   -- o login digitado (exista ou não)
               erros_seguidos   INTEGER NOT NULL,   -- quantas senhas erradas desde o primeiro erro da janela
               primeiro_erro_em TEXT NOT NULL,      -- quando a contagem atual começou
               bloqueado_ate    TEXT                -- até quando o login está bloqueado (vazio: não está)
           )"""
    )
    # Confirma a criação (no PostgreSQL, até a criação de tabela precisa ser confirmada)
    conexao.commit()


def minutos_de_bloqueio(conexao, login: str, agora: datetime | None = None) -> int:
    """Quantos minutos faltam para o login poder tentar de novo. 0 quer dizer "não está bloqueado".

    Recebe: conexao; login — o login digitado; agora — informado nos testes (na vida real, o momento atual).
    Devolve: os minutos que faltam, arredondados para cima (faltando 30 segundos, devolve 1).
    Exemplo: bloqueado até 14:20 e agora são 14:08 → 12.
    """
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # "agora" pode ser informado nos testes; na vida real, é o momento atual
    momento = agora or _agora()
    # Procura o registro deste login
    linha = conexao.execute("SELECT bloqueado_ate FROM tentativas_de_login WHERE login = ?", (login,)).fetchone()
    # Sem registro ou sem bloqueio: pode tentar
    if linha is None or linha[0] is None:
        return 0
    # Quanto tempo falta até o fim do bloqueio
    tempo_que_falta = datetime.fromisoformat(linha[0]) - momento
    # O bloqueio já acabou
    if tempo_que_falta.total_seconds() <= 0:
        return 0
    # Arredonda para cima: "tente em 0 minutos" não faria sentido
    return math.ceil(tempo_que_falta.total_seconds() / 60)


def registrar_erro(conexao, login: str, agora: datetime | None = None) -> None:
    """Anota uma senha errada para o login. No 5º erro dentro da janela, bloqueia o login por 15 minutos.

    Recebe: conexao; login — o login digitado (exista ou não); agora — informado nos testes.
    Devolve: nada. Quem quiser saber se bloqueou pergunta a minutos_de_bloqueio.
    """
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # "agora" pode ser informado nos testes; na vida real, é o momento atual
    momento = agora or _agora()
    # Login já bloqueado: o erro não conta de novo e, principalmente, não pode apagar o bloqueio que está valendo
    if minutos_de_bloqueio(conexao, login, momento) > 0:
        return
    # Antes de anotar, apaga os registros que já não servem para nada (a tabela não cresce sem fim)
    _apagar_registros_vencidos(conexao, momento)
    # Quantos erros este login já tem na janela atual (e desde quando)
    erros_seguidos, primeiro_erro_em = _contagem_atual(conexao, login, momento)
    # Soma este erro
    erros_seguidos = erros_seguidos + 1
    # Ainda não chegou ao limite: sem bloqueio
    bloqueado_ate = None
    # Chegou ao limite: bloqueia e zera a contagem (depois do bloqueio, a pessoa tem de novo 5 tentativas)
    if erros_seguidos >= LIMITE_DE_ERROS_SEGUIDOS:
        bloqueado_ate = _como_texto(momento + timedelta(minutes=BLOQUEIO_EM_MINUTOS))
        erros_seguidos = 0
    # Grava (ou atualiza) o registro do login.
    # "ON CONFLICT (login) DO UPDATE": se o login já tem registro, atualiza (igual no SQLite e no PostgreSQL)
    conexao.execute(
        "INSERT INTO tentativas_de_login (login, erros_seguidos, primeiro_erro_em, bloqueado_ate) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (login) DO UPDATE SET erros_seguidos = excluded.erros_seguidos, "
        "primeiro_erro_em = excluded.primeiro_erro_em, bloqueado_ate = excluded.bloqueado_ate",
        (login, erros_seguidos, primeiro_erro_em, bloqueado_ate),
    )
    conexao.commit()


def _contagem_atual(conexao, login: str, momento: datetime) -> tuple[int, str]:
    """Os erros do login na janela atual e quando ela começou. Janela vencida (ou nenhuma) recomeça do zero.

    Devolve: (erros até agora, início da contagem em texto). Ex.: (2, "2026-09-27T14:05:09+00:00").
    """
    # Procura o registro deste login
    linha = conexao.execute("SELECT erros_seguidos, primeiro_erro_em FROM tentativas_de_login WHERE login = ?",
                            (login,)).fetchone()
    # Nenhum erro anotado: a contagem começa agora
    if linha is None:
        return 0, _como_texto(momento)
    erros_seguidos, primeiro_erro_em = linha
    # A contagem começou há mais de 15 minutos: os erros antigos não contam mais, começa de novo agora.
    # Contagem zerada por um bloqueio (0 erros) também recomeça agora
    fim_da_janela = datetime.fromisoformat(primeiro_erro_em) + timedelta(minutes=JANELA_DE_CONTAGEM_EM_MINUTOS)
    if fim_da_janela <= momento or erros_seguidos == 0:
        return 0, _como_texto(momento)
    # Ainda dentro da janela: continua somando
    return erros_seguidos, primeiro_erro_em


def _apagar_registros_vencidos(conexao, momento: datetime) -> None:
    """Apaga os registros com a contagem vencida e sem bloqueio valendo: eles já não mudam nenhuma decisão.

    Por quê: cada login inventado que alguém tenta vira uma linha. Sem a limpeza, quem tentasse milhões de logins
    diferentes faria a tabela crescer sem fim. Com ela, só ficam as linhas dos últimos 15 minutos.
    """
    # A contagem que começou antes disto já venceu
    inicio_da_janela = _como_texto(momento - timedelta(minutes=JANELA_DE_CONTAGEM_EM_MINUTOS))
    # Apaga o que tem a contagem vencida e não está bloqueado (ou tem o bloqueio já acabado)
    conexao.execute(
        "DELETE FROM tentativas_de_login WHERE primeiro_erro_em < ? AND (bloqueado_ate IS NULL OR bloqueado_ate <= ?)",
        (inicio_da_janela, _como_texto(momento)),
    )


def registrar_acerto(conexao, login: str) -> None:
    """Login certo: zera o contador do login (apaga o registro dele)."""
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # Sem registro, a próxima senha errada começa a contar do zero
    conexao.execute("DELETE FROM tentativas_de_login WHERE login = ?", (login,))
    conexao.commit()
