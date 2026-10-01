"""Sessões lembradas por cookie: apertar F5 não desloga (ADR-40).

Ao entrar, o usuário recebe um "ingresso" (token) sorteado, com validade. O navegador guarda o
ingresso num cookie; o banco guarda só o hash dele, como faz com a senha. A cada página, o ingresso é
conferido: existe, não venceu, não foi cancelado e o usuário continua ativo.

Por que SHA-256 aqui e bcrypt na senha: a senha é escolhida por uma pessoa e pode ser fraca, então
precisa de um hash lento (bcrypt) para atrapalhar quem tenta adivinhar. O ingresso tem 256 bits
sorteados, e nenhuma tentativa em massa o adivinha; um hash rápido (SHA-256) basta.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from models.contratos import Perfil
from services.auth import Usuario

# Nome do cookie no navegador (a sessão do Integra Folha)
NOME_COOKIE = "integra_folha_sessao"
# Por quantas horas o ingresso vale; o cookie, além disso, some ao fechar o navegador. Não há "Lembrar de
# mim": toda sessão vale 8 horas
VALIDADE_HORAS = 8


def _agora() -> datetime:
    """A data e hora de agora, no horário universal (UTC)."""
    return datetime.now(timezone.utc)


def _hash_do_ingresso(ingresso: str) -> str:
    """O hash SHA-256 do ingresso (é só isso que fica guardado no banco)."""
    return hashlib.sha256(ingresso.encode("utf-8")).hexdigest()


def preparar_tabela(conexao) -> None:
    """Cria a tabela de sessões no banco, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS sessoes (
               token_hash TEXT PRIMARY KEY,
               login      TEXT NOT NULL,
               criada_em  TEXT NOT NULL,
               expira_em  TEXT NOT NULL,
               revogada   INTEGER NOT NULL DEFAULT 0
           )"""
    )


def criar_sessao(conexao, login: str, agora: datetime | None = None) -> str:
    """Cria a sessão de quem acabou de entrar e devolve o ingresso (só o hash vai para o banco).

    A sessão vale VALIDADE_HORAS (8 horas) a partir de agora.
    """
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # "agora" pode ser informado nos testes; na vida real, é o momento atual
    momento = agora or _agora()
    # Sorteia o ingresso: 32 bytes = 256 bits aleatórios, em texto seguro para cookie
    ingresso = secrets.token_urlsafe(32)
    # Quando o ingresso vence
    vence_em = momento + timedelta(hours=VALIDADE_HORAS)
    # Grava a sessão com o hash do ingresso, nunca o ingresso em si
    conexao.execute(
        "INSERT INTO sessoes (token_hash, login, criada_em, expira_em) VALUES (?, ?, ?, ?)",
        (_hash_do_ingresso(ingresso), login, momento.isoformat(), vence_em.isoformat()),
    )
    conexao.commit()
    return ingresso


def validar_sessao(conexao, token: str | None, agora: datetime | None = None) -> Usuario | None:
    """Devolve o usuário dono do ingresso, se o ingresso ainda vale; senão, None."""
    # O cookie vem de fora: só aceita texto não vazio, qualquer outra coisa é recusada
    if not isinstance(token, str) or not token:
        return None
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # Procura a sessão pelo hash do ingresso, junto com os dados atuais do usuário
    consulta = conexao.execute(
        """SELECT sessoes.expira_em, sessoes.revogada, usuarios.login, usuarios.perfil,
                  usuarios.empresa_id, usuarios.ativo, usuarios.senha_provisoria
             FROM sessoes JOIN usuarios ON usuarios.login = sessoes.login
            WHERE sessoes.token_hash = ?""",
        (_hash_do_ingresso(token),),
    )
    linha = consulta.fetchone()
    # Ingresso inventado ou de outro sistema
    if linha is None:
        return None
    expira_em, revogada, login, perfil, empresa_id, ativo, senha_provisoria = linha
    # Ingresso cancelado ("Sair", senha redefinida ou usuário desativado)
    if revogada:
        return None
    # Usuário desativado depois do login
    if not ativo:
        return None
    # Ingresso vencido
    momento = agora or _agora()
    if datetime.fromisoformat(expira_em) <= momento:
        return None
    # Tudo certo: devolve quem é (e se a senha ainda é a provisória, que precisa ser trocada, ADR-109)
    return Usuario(login=login, perfil=Perfil(perfil), empresa_id=empresa_id, ativo=True,
                   senha_provisoria=bool(senha_provisoria))


def encerrar_sessao(conexao, token: str | None) -> None:
    """Cancela o ingresso ("Sair"). Depois disso ele não vale mais, mesmo que alguém o tenha copiado."""
    # Sem ingresso, nada a cancelar
    if not token:
        return
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # Marca a sessão como cancelada (não apaga: fica no histórico)
    conexao.execute("UPDATE sessoes SET revogada = 1 WHERE token_hash = ?", (_hash_do_ingresso(token),))
    conexao.commit()


def encerrar_as_outras_sessoes(conexao, login: str, ingresso_que_fica: str | None) -> None:
    """Derruba todas as sessões de alguém, menos a que está em uso agora (a pessoa trocou a própria senha, A-17).

    Por quê: quem troca a senha por desconfiar de roubo precisa expulsar quem copiou o ingresso; a própria pessoa
    continua na tela, sem precisar entrar de novo.
    Exemplo: a pessoa está logada no notebook e alguém copiou o ingresso; ela troca a senha no notebook e a outra
    sessão cai na hora.
    """
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # Cancela as sessões desse login, menos a do ingresso que fica (comparado pelo hash, como está guardado)
    conexao.execute("UPDATE sessoes SET revogada = 1 WHERE login = ? AND token_hash <> ?",
                    (login, _hash_do_ingresso(ingresso_que_fica or "")))
    conexao.commit()


def encerrar_sessoes_do_usuario(conexao, login: str) -> None:
    """Derruba todas as sessões de alguém (senha redefinida pelo banco ou usuário desativado)."""
    # Garante que a tabela existe
    preparar_tabela(conexao)
    # Cancela todas as sessões desse login
    conexao.execute("UPDATE sessoes SET revogada = 1 WHERE login = ?", (login,))
    conexao.commit()
