"""A receita do Docker Compose (aplicação + PostgreSQL) e o script da primeira subida do banco (ADR-67).

O Docker não está instalado em toda máquina, então as provas conferem a receita lida como texto: o que sobe, em
que ordem, com quais senhas (sempre do .env, nunca escritas no arquivo). O script que cria o usuário da aplicação
roda de verdade contra o PostgreSQL local quando ele existe (com nomes temporários, apagados no fim).
"""
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest
import yaml
from dotenv import dotenv_values

# Pasta raiz do projeto
RAIZ = Path(__file__).resolve().parent.parent
# O script que o PostgreSQL do contêiner roda na primeira subida
SCRIPT_DO_BANCO = RAIZ / "docker" / "postgres" / "criar_usuario_da_aplicacao.sh"
# Onde o bash e o psql costumam estar no Windows (no Linux, vêm do PATH)
LUGARES_DO_BASH = (r"C:\Program Files\Git\bin\bash.exe", "/bin/bash")
PASTA_DO_PSQL_NO_WINDOWS = r"C:\Program Files\PostgreSQL\18\bin"


@pytest.fixture(scope="module")
def receita() -> dict:
    """O docker-compose.yml lido como dicionário."""
    return yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))


def test_sobem_o_banco_e_a_aplicacao_e_a_aplicacao_espera_o_banco(receita):
    """Dois serviços; a aplicação só sobe depois que o teste de saúde do banco passa."""
    assert set(receita["services"]) == {"banco", "aplicacao"}
    assert receita["services"]["aplicacao"]["depends_on"]["banco"]["condition"] == "service_healthy"
    # O teste de saúde usa a rede (127.0.0.1): o servidor provisório da primeira preparação não atende por ela
    assert "-h 127.0.0.1" in receita["services"]["banco"]["healthcheck"]["test"][1]


def test_a_aplicacao_usa_o_postgres_com_o_usuario_sem_superpoderes(receita):
    """A aplicação entra no banco com o usuário da aplicação, nunca com o administrador."""
    ambiente = receita["services"]["aplicacao"]["environment"]
    assert ambiente["BANCO"] == "postgres"
    assert ambiente["POSTGRES_URL"].startswith("postgresql://integra_folha_app:")
    assert "@banco:5432/integra_folha" in ambiente["POSTGRES_URL"]


def test_nenhuma_senha_fica_escrita_na_receita(receita):
    """Toda senha e chave vem do .env, por variável ${...}."""
    ambientes = [receita["services"]["banco"]["environment"], receita["services"]["aplicacao"]["environment"]]
    for ambiente in ambientes:
        for nome, valor in ambiente.items():
            if "SENHA" in nome or "PASSWORD" in nome or "API_KEY" in nome:
                assert str(valor).startswith("${"), nome
    # A senha da aplicação dentro do endereço de conexão também é variável
    assert "${SENHA_POSTGRES_APLICACAO}" in receita["services"]["aplicacao"]["environment"]["POSTGRES_URL"]


def test_dados_em_volumes_e_banco_fechado_para_a_rede(receita):
    """Os dados sobrevivem ao desligar; a porta do banco só abre na própria máquina."""
    assert set(receita["volumes"]) == {"dados_do_banco", "arquivos_da_aplicacao"}
    for porta in receita["services"]["banco"]["ports"]:
        assert porta.startswith("127.0.0.1:")
    # O script da primeira subida existe e é montado na pasta que a imagem oficial executa
    montagens = " ".join(receita["services"]["banco"]["volumes"])
    assert "/docker-entrypoint-initdb.d/criar_usuario_da_aplicacao.sh" in montagens
    assert SCRIPT_DO_BANCO.exists()


def test_script_do_banco_tem_final_de_linha_do_linux():
    """O contêiner roda Linux: um "\\r" do Windows no script faria o sh falhar."""
    assert b"\r" not in SCRIPT_DO_BANCO.read_bytes()


def _achar_bash() -> str | None:
    """O caminho do bash (o do Git, no Windows), ou None se não houver."""
    for lugar in LUGARES_DO_BASH:
        if Path(lugar).exists():
            return lugar
    return None


# A conexão do administrador do PostgreSQL local (vazia: a prova do script é pulada)
URL_DO_ADMINISTRADOR = dotenv_values(RAIZ / ".env").get("POSTGRES_ADMIN_URL", "")
precisa_do_postgres_e_do_bash = pytest.mark.skipif(
    not URL_DO_ADMINISTRADOR or _achar_bash() is None, reason="sem POSTGRES_ADMIN_URL no .env ou sem bash")


def _ambiente_do_script(senha: str | None) -> dict:
    """As variáveis que o PostgreSQL do contêiner daria ao script, apontando para o servidor local."""
    endereco = urlparse(URL_DO_ADMINISTRADOR)
    ambiente = dict(os.environ, PGHOST=endereco.hostname, PGPORT=str(endereco.port or 5432),
                    PGPASSWORD=endereco.password, POSTGRES_USER=endereco.username,
                    USUARIO_DA_APLICACAO="teste_compose_app", BANCO_DA_APLICACAO="teste_compose_banco")
    # O psql do PostgreSQL instalado no Windows não fica no PATH do bash
    ambiente["PATH"] = PASTA_DO_PSQL_NO_WINDOWS + os.pathsep + ambiente["PATH"]
    # Sem a variável da senha, o script precisa recusar
    ambiente.pop("SENHA_POSTGRES_APLICACAO", None)
    if senha is not None:
        ambiente["SENHA_POSTGRES_APLICACAO"] = senha
    return ambiente


@precisa_do_postgres_e_do_bash
def test_script_cria_usuario_sem_superpoderes_dono_do_banco():
    """Roda o script de verdade: o usuário entra com a senha, não é administrador e é dono do banco."""
    # Uma aspa na senha prova que ela é escapada, e não colada solta no comando
    senha = "Teste" + secrets.token_hex(8) + "'aspa"
    try:
        resultado = subprocess.run([_achar_bash(), str(SCRIPT_DO_BANCO)], env=_ambiente_do_script(senha),
                                   capture_output=True, text=True)
        assert resultado.returncode == 0, resultado.stderr
        endereco = urlparse(URL_DO_ADMINISTRADOR)
        with psycopg.connect(host=endereco.hostname, port=endereco.port or 5432, user="teste_compose_app",
                             password=senha, dbname="teste_compose_banco") as conexao:
            poderes = conexao.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user").fetchone()
            dono = conexao.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()").fetchone()[0]
        assert poderes == (False, False, False)
        assert dono == "teste_compose_app"
    finally:
        # Apaga o banco e o usuário temporários, mesmo se a prova falhar
        with psycopg.connect(URL_DO_ADMINISTRADOR, autocommit=True) as administrador:
            administrador.execute("DROP DATABASE IF EXISTS teste_compose_banco")
            administrador.execute("DROP ROLE IF EXISTS teste_compose_app")


@precisa_do_postgres_e_do_bash
def test_script_sem_senha_recusa_e_nao_cria_nada():
    """Sem SENHA_POSTGRES_APLICACAO, o script para com erro antes de criar qualquer coisa."""
    resultado = subprocess.run([_achar_bash(), str(SCRIPT_DO_BANCO)], env=_ambiente_do_script(None),
                               capture_output=True, text=True)
    assert resultado.returncode == 1
    assert "falta SENHA_POSTGRES_APLICACAO" in resultado.stderr
    with psycopg.connect(URL_DO_ADMINISTRADOR) as administrador:
        existe = administrador.execute("SELECT 1 FROM pg_roles WHERE rolname = 'teste_compose_app'").fetchone()
    assert existe is None

