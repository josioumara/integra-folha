#!/bin/sh
# Prepara o PostgreSQL do docker-compose na PRIMEIRA subida (ADR-67; docs/banco_de_dados.md).
#
# A imagem oficial do PostgreSQL roda sozinha os scripts da pasta /docker-entrypoint-initdb.d/, uma única vez,
# quando o disco do banco ainda está vazio. Este script faz o mesmo que o scripts/preparar_postgres.py faz na
# máquina local:
# - cria o usuário da aplicação, SEM poderes de administrador (princípio do menor privilégio);
# - cria o banco da aplicação, com esse usuário como dono.
# As tabelas NÃO são criadas aqui: a própria aplicação cria cada tabela na primeira vez que a usa.
#
# A senha vem da variável SENHA_POSTGRES_APLICACAO (definida no .env e repassada pelo docker-compose.yml);
# nunca fica escrita neste arquivo. Os nomes podem ser trocados por variáveis (usado só no teste deste script).

# Para no primeiro erro, em vez de seguir com o banco pela metade
set -e

# O nome do usuário e do banco da aplicação (os mesmos da máquina local)
USUARIO_DA_APLICACAO="${USUARIO_DA_APLICACAO:-integra_folha_app}"
BANCO_DA_APLICACAO="${BANCO_DA_APLICACAO:-integra_folha}"

# Sem senha, não cria nada: um usuário sem senha seria uma porta aberta
if [ -z "$SENHA_POSTGRES_APLICACAO" ]; then
    echo "criar_usuario_da_aplicacao: falta SENHA_POSTGRES_APLICACAO no .env" >&2
    exit 1
fi

# psql é o terminal de comandos do PostgreSQL. Entra como o administrador da imagem (POSTGRES_USER) e passa os
# nomes e a senha como variáveis do psql; :"nome" vira um nome entre aspas e :'senha' vira um texto entre
# aspas, com o escape certo (a senha nunca é colada solta no comando)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${POSTGRES_DB:-postgres}" \
    -v usuario="$USUARIO_DA_APLICACAO" -v banco="$BANCO_DA_APLICACAO" -v senha="$SENHA_POSTGRES_APLICACAO" <<'COMANDOS'
CREATE ROLE :"usuario" LOGIN PASSWORD :'senha' NOSUPERUSER NOCREATEROLE NOCREATEDB;
CREATE DATABASE :"banco" OWNER :"usuario" ENCODING 'UTF8';
COMANDOS

echo "criar_usuario_da_aplicacao: usuário $USUARIO_DA_APLICACAO e banco $BANCO_DA_APLICACAO criados"
