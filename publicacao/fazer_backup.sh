#!/usr/bin/env bash
# =====================================================================================================================
# fazer_backup.sh: a cópia de segurança do site, mandada para o bucket privado do S3 (roda no servidor)
#
# Para que serve:
#   Se a máquina quebrar ou uma versão nova estragar os dados, o backup é o ponto de volta. Ele guarda duas coisas:
#   1. o banco inteiro (pg_dump: um arquivo com todos os comandos para recriar as tabelas e os dados);
#   2. o volume "storage" da aplicação (os índices do RAG e os arquivos enviados pelas empresas). O modelo de
#      embeddings fica de fora: ele é baixado de novo sozinho.
#   Os dois vão para s3://integra-folha-backup-<conta>/backup/<data e hora>/. A máquina grava pelo papel dela (sem
#   chave nenhuma guardada) e NÃO consegue apagar nada lá: um invasor não apagaria o backup. O bucket apaga sozinho
#   o que passa de 30 dias.
#
# Como usar (no servidor, como o usuário deploy, na pasta /srv/integra-folha):
#   bash publicacao/fazer_backup.sh                 # um backup agora (o publicar.sh chama antes de trocar a versão)
#   bash publicacao/fazer_backup.sh --agendar       # agenda o backup de toda noite, às 3h (roda uma vez só)
# =====================================================================================================================

# Para no primeiro erro, em variável não definida e em erro no meio de um "|"
set -euo pipefail

# A pasta do site no servidor
PASTA_DO_SITE="/srv/integra-folha"
# O nome do projeto no Docker (dá o nome dos volumes)
NOME_DO_PROJETO="integra-folha"
# Uma pasta temporária para montar os arquivos antes de mandar
PASTA_TEMPORARIA="$(mktemp -d)"
# Apaga a pasta temporária no fim, mesmo se der erro
trap 'rm -rf "$PASTA_TEMPORARIA"' EXIT

# Com --agendar: grava a tarefa da noite no agendador (cron) do usuário e para
if [ "${1:-}" = "--agendar" ]; then
  # A linha do cron: todo dia às 3h, guardando o registro de cada rodada
  LINHA_DO_AGENDADOR="0 3 * * * bash $PASTA_DO_SITE/publicacao/fazer_backup.sh >> $HOME/backup.log 2>&1"
  # Junta a linha às tarefas que já existem, sem repetir
  { crontab -l 2>/dev/null | grep -v "fazer_backup.sh" || true; echo "$LINHA_DO_AGENDADOR"; } | crontab -
  # Mostra o que ficou agendado
  echo "Agendado: $LINHA_DO_AGENDADOR"
  exit 0
fi

# O número da conta, lido pelo papel da máquina (o nome do bucket leva esse número)
NUMERO_DA_CONTA="$(aws sts get-caller-identity --query Account --output text)"
# O bucket do backup
BUCKET_DO_BACKUP="integra-folha-backup-$NUMERO_DA_CONTA"
# A pasta desta rodada no bucket: a data e a hora (ex.: 2026-09-30_0300)
PASTA_DA_RODADA="backup/$(date +%Y-%m-%d_%H%M)"

# Entra na pasta do site (o docker compose precisa dela)
cd "$PASTA_DO_SITE"
# O comando do compose de produção, montado uma vez
COMPOSE=(docker compose --env-file publicacao/.env -f docker-compose.yml -f publicacao/compose.prod.yml)

# 1. O banco: o pg_dump roda dentro do contêiner do banco e sai comprimido
echo "$(date '+%F %T') banco..."
"${COMPOSE[@]}" exec -T banco pg_dump -U postgres --clean --if-exists integra_folha | gzip > "$PASTA_TEMPORARIA/banco.sql.gz"

# 2. O storage: um contêiner descartável lê o volume e empacota, sem o modelo de embeddings
echo "$(date '+%F %T') storage..."
docker run --rm -v "${NOME_DO_PROJETO}_arquivos_da_aplicacao:/dados:ro" -v "$PASTA_TEMPORARIA:/saida" alpine \
  tar czf /saida/storage.tar.gz --exclude=./modelos -C /dados .

# 3. Manda os dois para o bucket (conexão segura; o bucket recusa texto aberto)
echo "$(date '+%F %T') enviando para s3://$BUCKET_DO_BACKUP/$PASTA_DA_RODADA/ ..."
aws s3 cp "$PASTA_TEMPORARIA/banco.sql.gz" "s3://$BUCKET_DO_BACKUP/$PASTA_DA_RODADA/banco.sql.gz" --only-show-errors
aws s3 cp "$PASTA_TEMPORARIA/storage.tar.gz" "s3://$BUCKET_DO_BACKUP/$PASTA_DA_RODADA/storage.tar.gz" --only-show-errors

# Mostra o tamanho do que foi mandado
echo "$(date '+%F %T') pronto: banco $(du -h "$PASTA_TEMPORARIA/banco.sql.gz" | cut -f1), storage $(du -h "$PASTA_TEMPORARIA/storage.tar.gz" | cut -f1)"
