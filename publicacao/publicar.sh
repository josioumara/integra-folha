#!/usr/bin/env bash
# =====================================================================================================================
# publicar.sh: publica uma versão do Integra Folha no servidor da AWS (roda no computador local, pelo Git Bash)
#
# Para que serve:
#   Leva um commit da main até o site no ar, com volta automática se a conferência falhar:
#   1. confere que o commit existe e está na main (a versão sai sempre da main, com a bateria verde);
#   2. manda o código para o servidor pelo "git push" (o commit, com o compose, o Caddyfile e os scripts);
#   3. constrói a imagem a partir do COMMIT (git archive), e não da pasta de trabalho: o que vai ao ar é exatamente
#      o que está no Git. A etiqueta da imagem é o código do commit. Por padrão, a construção é NO SERVIDOR (ADR-134:
#      o Docker Desktop não cabe na memória do computador local); com --local, ela é feita no computador e a imagem
#      vai comprimida pelo SSH;
#   4. no servidor: faz o backup (o ponto de volta, se a versão nova mexer no banco) e troca a versão;
#   5. roda as provas (conferir.sh). Se alguma falhar, volta sozinho à versão anterior e avisa.
#
# Como usar (com a versão aprovada para publicar e o atalho "integra-folha" no ~/.ssh/config):
#   bash publicacao/publicar.sh <commit>            # constrói no servidor (ex.: bash publicacao/publicar.sh b32b61c)
#   bash publicacao/publicar.sh <commit> --local    # constrói no computador (precisa do Docker Desktop ligado)
# =====================================================================================================================

# Para no primeiro erro, em variável não definida e em erro no meio de um "|"
set -euo pipefail

# O atalho do SSH para o servidor (em ~/.ssh/config, com o usuário deploy)
SERVIDOR="integra-folha"
# O nome da imagem da aplicação
NOME_DA_IMAGEM="integra-folha/web"
# A pasta do site no servidor
PASTA_NO_SERVIDOR="/srv/integra-folha"
# O commit pedido
COMMIT_PEDIDO="${1:?informe o commit (ex.: b32b61c)}"
# Onde construir a imagem: no servidor (o padrão) ou no computador (com --local)
ONDE_CONSTRUIR="servidor"
# Com --local, constrói no computador
if [ "${2:-}" = "--local" ]; then
  ONDE_CONSTRUIR="local"
fi
# O endereço do site, para esperar a aplicação responder
ENDERECO="https://integrafolha.com.br"

# Vai para a raiz do repositório (a pasta acima desta)
cd "$(dirname "$0")/.."

# 1. O commit precisa existir e estar na main
ETIQUETA="$(git rev-parse --short=12 "$COMMIT_PEDIDO^{commit}")"
# Confere que o commit faz parte da main
if ! git merge-base --is-ancestor "$ETIQUETA" main; then
  # Avisa e para
  echo "O commit $ETIQUETA não está na main. Só a main vai ao ar."
  exit 1
fi
echo "Versão: $ETIQUETA ($(git log -1 --format=%s "$ETIQUETA"))"

# O servidor precisa já ter o .env de produção (na primeira vez, ele é preparado à mão, a partir do .env.exemplo)
if ! ssh "$SERVIDOR" "test -f $PASTA_NO_SERVIDOR/publicacao/.env"; then
  # Avisa e para
  echo "O servidor ainda não tem o publicacao/.env. Prepare-o antes, a partir do publicacao/.env.exemplo."
  exit 1
fi

# 2. Manda o código (o commit, com o compose, o Caddyfile e os scripts) para a main do servidor
echo "Mandando o código ..."
git push -q prod "$ETIQUETA:refs/heads/main"

# 3. Constrói a imagem a partir do commit (o Dockerfile está na raiz do repositório)
if [ "$ONDE_CONSTRUIR" = "servidor" ]; then
  # No servidor: o git archive lê o commit que acabou de chegar pelo push
  echo "Construindo a imagem $NOME_DA_IMAGEM:$ETIQUETA no servidor ..."
  ssh "$SERVIDOR" "cd $PASTA_NO_SERVIDOR && git archive --format=tar $ETIQUETA | docker build -q -t $NOME_DA_IMAGEM:$ETIQUETA -"
else
  # No computador: constrói aqui
  echo "Construindo a imagem $NOME_DA_IMAGEM:$ETIQUETA no computador ..."
  git archive --format=tar "$ETIQUETA" | docker build -q -t "$NOME_DA_IMAGEM:$ETIQUETA" -
  # E manda para o servidor, comprimida, e carrega lá
  echo "Mandando a imagem para o servidor ..."
  docker save "$NOME_DA_IMAGEM:$ETIQUETA" | gzip | ssh "$SERVIDOR" "gunzip | docker load -q"
fi

# 4. No servidor: backup, se o banco já estiver no ar (na primeira publicação ainda não está)
if ssh "$SERVIDOR" "docker ps --format '{{.Names}}' | grep -q integra-folha-banco-1"; then
  # O backup antes da troca
  echo "Backup antes da troca ..."
  ssh "$SERVIDOR" "bash $PASTA_NO_SERVIDOR/publicacao/fazer_backup.sh"
fi
# Troca a versão
ssh "$SERVIDOR" "bash $PASTA_NO_SERVIDOR/publicacao/trocar_versao.sh $ETIQUETA"

# 5. As provas: antes, espera a página de login responder pelo https (até 3 minutos)
echo "Esperando a aplicação subir ..."
for tentativa in $(seq 1 36); do
  # O código da resposta da página de login
  CODIGO_DO_LOGIN="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$ENDERECO/login.html" || true)"
  # Respondeu: pode conferir
  if [ "$CODIGO_DO_LOGIN" = "200" ]; then
    break
  fi
  # Ainda não: espera 5 segundos
  sleep 5
done
if bash publicacao/conferir.sh "$ETIQUETA"; then
  # Deu tudo certo
  echo "Publicado: $ETIQUETA. Anote a versão no docs/hospedagem.md (seção 6)."
  exit 0
fi

# Alguma prova falhou: volta sozinho à versão anterior e avisa
echo "A conferência falhou. Voltando à versão anterior ..."
ssh "$SERVIDOR" "bash $PASTA_NO_SERVIDOR/publicacao/trocar_versao.sh --anterior"
echo "Voltou à versão anterior. Veja o que falhou acima."
exit 1
