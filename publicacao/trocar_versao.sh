#!/usr/bin/env bash
# =====================================================================================================================
# trocar_versao.sh: põe no ar uma versão (etiqueta de imagem) já carregada no servidor (roda no servidor)
#
# Para que serve:
#   Serve para as duas direções: publicar uma versão nova e voltar à anterior. A etiqueta é o código do commit.
#   1. anota a versão que está no ar (o ponto de volta) em ~/versoes.log;
#   2. troca a IMAGEM_TAG no publicacao/.env e sobe a aplicação com a imagem nova (o banco e o Caddy continuam);
#   3. guarda só as 3 imagens mais novas da aplicação, para o disco não encher (as outras são apagadas).
#
# Como usar (no servidor, como deploy, na pasta /srv/integra-folha):
#   bash publicacao/trocar_versao.sh <etiqueta>          # põe a etiqueta no ar
#   bash publicacao/trocar_versao.sh --anterior          # volta à versão que estava antes da última troca
# =====================================================================================================================

# Para no primeiro erro, em variável não definida e em erro no meio de um "|"
set -euo pipefail

# A pasta do site no servidor
PASTA_DO_SITE="/srv/integra-folha"
# O registro das trocas de versão (fora do repositório, para o git push não mexer)
REGISTRO_DAS_VERSOES="$HOME/versoes.log"
# O nome da imagem da aplicação
NOME_DA_IMAGEM="integra-folha/web"

# Entra na pasta do site
cd "$PASTA_DO_SITE"
# O comando do compose de produção, montado uma vez
COMPOSE=(docker compose --env-file publicacao/.env -f docker-compose.yml -f publicacao/compose.prod.yml)
# A versão que está no ar agora (a linha IMAGEM_TAG do .env)
VERSAO_ATUAL="$(grep '^IMAGEM_TAG=' publicacao/.env | cut -d= -f2-)"

# Decide a versão que vai ao ar
if [ "${1:-}" = "--anterior" ]; then
  # A versão anterior é a "de" da última troca registrada
  VERSAO_NOVA="$(tail -1 "$REGISTRO_DAS_VERSOES" | awk '{print $3}')"
else
  # A etiqueta informada
  VERSAO_NOVA="${1:?informe a etiqueta ou --anterior}"
fi

# A imagem precisa estar carregada no servidor
if ! docker image inspect "$NOME_DA_IMAGEM:$VERSAO_NOVA" >/dev/null 2>&1; then
  # Avisa e para
  echo "A imagem $NOME_DA_IMAGEM:$VERSAO_NOVA não está no servidor."
  exit 1
fi

# 1. Anota a troca: data, "de" versão atual, "para" versão nova
echo "$(date '+%F_%T') de ${VERSAO_ATUAL:-nenhuma} para $VERSAO_NOVA" >> "$REGISTRO_DAS_VERSOES"
# 2. Troca a etiqueta no .env
sed -i "s/^IMAGEM_TAG=.*/IMAGEM_TAG=$VERSAO_NOVA/" publicacao/.env
# Confere a configuração sem mostrar os segredos (SEMPRE com --quiet)
"${COMPOSE[@]}" config --quiet
# Sobe tudo: só a aplicação é recriada, porque só a imagem dela mudou
"${COMPOSE[@]}" up -d
# 3. Lista as imagens da aplicação, da mais nova para a mais velha, e apaga da quarta em diante
docker image ls "$NOME_DA_IMAGEM" --format '{{.Tag}}' | tail -n +4 | while read -r etiqueta_antiga; do
  # Nunca apaga a que acabou de ir ao ar nem a anterior
  if [ "$etiqueta_antiga" != "$VERSAO_NOVA" ] && [ "$etiqueta_antiga" != "$VERSAO_ATUAL" ]; then
    # Apaga a imagem velha
    docker image rm "$NOME_DA_IMAGEM:$etiqueta_antiga" >/dev/null
  fi
done
# Mostra o que ficou no ar
echo "No ar: $VERSAO_NOVA (antes: ${VERSAO_ATUAL:-nenhuma})"
