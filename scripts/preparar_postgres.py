"""Prepara o PostgreSQL para o projeto: cria o usuário da aplicação e os bancos (ADR-67; docs/banco_de_dados.md).

Usa o superusuário só para esta preparação (POSTGRES_ADMIN_URL no .env) e cria:
- o usuário "integra_folha_app", dono dos bancos, sem poder de superusuário: é ele que a aplicação usa. Se a
  senha dele vazar, ela não dá poder sobre o servidor inteiro (princípio do menor privilégio);
- o banco "integra_folha", o da aplicação;
- o banco "integra_folha_testes", onde os testes automáticos rodam contra o PostgreSQL (nunca no da aplicação).

A senha do usuário da aplicação é gerada aqui e gravada SÓ no .env, em POSTGRES_URL e POSTGRES_URL_TESTES; nunca é
mostrada. Rodar de novo não refaz nada que já exista.

Para rodar: python scripts/preparar_postgres.py   (antes: POSTGRES_ADMIN_URL no .env)
"""
import secrets
import string
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from services import config  # noqa: E402

# O arquivo de configuração e os nomes criados
CAMINHO_DO_ENV = RAIZ / ".env"
USUARIO_DA_APLICACAO = "integra_folha_app"
BANCO_DA_APLICACAO = "integra_folha"
BANCO_DE_TESTES = "integra_folha_testes"


def gerar_senha(tamanho: int = 28) -> str:
    """Uma senha forte só com letras e números (não precisa de escape dentro da URL de conexão)."""
    alfabeto = string.ascii_letters + string.digits
    letras = []
    for _posicao in range(tamanho):
        letras.append(secrets.choice(alfabeto))
    return "".join(letras)


def ler_env() -> str:
    """O conteúdo do .env (vazio se ainda não existir)."""
    if not CAMINHO_DO_ENV.exists():
        return ""
    return CAMINHO_DO_ENV.read_text(encoding="utf-8")


def acrescentar_ao_env(linhas: list[str]) -> None:
    """Acrescenta linhas ao fim do .env, sem mexer no que já está lá."""
    conteudo = ler_env()
    if conteudo and not conteudo.endswith("\n"):
        conteudo += "\n"
    conteudo += "\n".join(linhas) + "\n"
    CAMINHO_DO_ENV.write_text(conteudo, encoding="utf-8")


def criar_usuario(conexao, senha: str) -> bool:
    """Cria o usuário da aplicação (sem superusuário). Devolve True se criou; False se já existia."""
    existe = conexao.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (USUARIO_DA_APLICACAO,)).fetchone()
    if existe:
        return False
    conexao.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEROLE").format(
        sql.Identifier(USUARIO_DA_APLICACAO), sql.Literal(senha)))
    return True


def criar_banco(conexao, nome: str) -> bool:
    """Cria o banco com o usuário da aplicação como dono. Devolve True se criou; False se já existia."""
    existe = conexao.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nome,)).fetchone()
    if existe:
        return False
    conexao.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
        sql.Identifier(nome), sql.Identifier(USUARIO_DA_APLICACAO)))
    return True


def main() -> list[str]:
    """Cria o que falta e devolve, em frases, o que foi feito."""
    if not config.POSTGRES_ADMIN_URL:
        sys.exit("Falta POSTGRES_ADMIN_URL no .env (a conexão do superusuário, usada só para esta preparação).")
    feito = []
    senha_nova = None
    # CREATE DATABASE não pode rodar dentro de uma transação: conexão em modo autocommit
    with psycopg.connect(config.POSTGRES_ADMIN_URL, autocommit=True) as conexao:
        # A senha só é gerada se o usuário ainda não existe (senão, a do .env continua valendo)
        if "POSTGRES_URL=" not in ler_env():
            senha_nova = gerar_senha()
        if senha_nova and criar_usuario(conexao, senha_nova):
            feito.append(f"usuário {USUARIO_DA_APLICACAO} criado")
        for nome in (BANCO_DA_APLICACAO, BANCO_DE_TESTES):
            if criar_banco(conexao, nome):
                feito.append(f"banco {nome} criado")
    if senha_nova:
        acrescentar_ao_env([
            f"POSTGRES_URL=postgresql://{USUARIO_DA_APLICACAO}:{senha_nova}@localhost:5432/{BANCO_DA_APLICACAO}",
            f"POSTGRES_URL_TESTES=postgresql://{USUARIO_DA_APLICACAO}:{senha_nova}@localhost:5432/{BANCO_DE_TESTES}"])
        feito.append("POSTGRES_URL e POSTGRES_URL_TESTES gravadas no .env (a senha não é mostrada)")
    if not feito:
        feito.append("nada a fazer: usuário e bancos já existiam")
    for frase in feito:
        print(f"preparar_postgres: {frase}")
    return feito


if __name__ == "__main__":
    main()
