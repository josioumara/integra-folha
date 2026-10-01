#!/usr/bin/env bash
# =====================================================================================================================
# conferir.sh: as provas de que o site publicado está certo (roda no computador local, pelo Git Bash)
#
# Para que serve:
#   Toda publicação só termina com estas provas. Se alguma falhar, o publicar.sh volta sozinho à versão anterior.
#   1. o endereço abre em https, com certificado válido (o curl recusa certificado inválido);
#   2. uma página sem login volta para o login, e a API sem login responde 401;
#   3. o robots.txt tem "Disallow: /" e as respostas trazem o "X-Robots-Tag: noindex" (ADR-100);
#   4. de fora, as portas 8000 (aplicação) e 5432 (banco) estão fechadas; e a IA é chamada pela Virgínia, onde a
#      retenção zero está gravada;
#   5. a versão no ar é a do commit pedido.
#
# Como usar:
#   bash publicacao/conferir.sh <etiqueta do commit esperada>
#   Devolve 0 se tudo passou e 1 se alguma prova falhou.
# =====================================================================================================================

# Para em variável não definida (os erros das provas são contados, não param o script)
set -u

# O endereço do site
ENDERECO="https://integrafolha.com.br"
# O atalho do SSH para o servidor (em ~/.ssh/config)
SERVIDOR="integra-folha"
# A etiqueta esperada (o código do commit)
ETIQUETA_ESPERADA="${1:?informe a etiqueta esperada (o código do commit)}"
# Quantas provas falharam
PROVAS_QUE_FALHARAM=0

# Registra uma prova: o nome, o valor visto e o valor esperado
provar() {
  # O que a prova confere
  local nome_da_prova="$1"
  # O que foi visto
  local valor_visto="$2"
  # O que era esperado
  local valor_esperado="$3"
  # Compara e mostra o resultado
  if [ "$valor_visto" = "$valor_esperado" ]; then
    echo "  OK    $nome_da_prova ($valor_visto)"
  else
    echo "  FALHA $nome_da_prova: veio '$valor_visto', esperado '$valor_esperado'"
    # Conta a falha
    PROVAS_QUE_FALHARAM=$((PROVAS_QUE_FALHARAM + 1))
  fi
}

echo "Conferindo $ENDERECO (versão esperada $ETIQUETA_ESPERADA)"
# 1. O https com certificado válido: a página de login responde 200 (o curl falha se o certificado for inválido)
provar "https e certificado (login.html)" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$ENDERECO/login.html")" "200"
# O http leva para o https
provar "http leva ao https" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "http://integrafolha.com.br/login.html")" "308"
# 2. Uma página sem login é mandada para o login (o destino do redirecionamento contém "login")
DESTINO_SEM_LOGIN="$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 15 "$ENDERECO/home.html")"
provar "página sem login vai ao login" "$(echo "$DESTINO_SEM_LOGIN" | grep -c login)" "1"
# A API sem login responde 401
provar "API sem login" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$ENDERECO/api/empresa/envios/pagina")" "401"
# 3. O robots.txt fecha o site para os buscadores
provar "robots.txt com Disallow: /" "$(curl -s --max-time 15 "$ENDERECO/robots.txt" | grep -c '^Disallow: /$')" "1"
# O cabeçalho noindex vem nas respostas
provar "X-Robots-Tag noindex" "$(curl -sI --max-time 15 "$ENDERECO/login.html" | grep -ci 'x-robots-tag:.*noindex')" "1"
# 4. As portas internas fechadas por fora (o IP vem do DNS)
IP_DO_SITE="$(nslookup integrafolha.com.br 2>/dev/null | awk '/^Address/ {ip=$2} END {print ip}')"
provar "porta 8000 fechada por fora" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$IP_DO_SITE:8000/" || true)" "000"
provar "porta 5432 fechada por fora" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$IP_DO_SITE:5432/" || true)" "000"
# No servidor, só 22, 80 e 443 escutam para fora (o que escuta só em 127.0.0.1 não conta)
PORTAS_ABERTAS="$(ssh "$SERVIDOR" "sudo ss -tlnH | awk '{print \$4}' | grep -v '^127\.' | grep -v '^\[::1\]' | sed 's/.*://' | sort -un | tr '\n' ' '")"
provar "portas abertas no servidor" "$(echo "$PORTAS_ABERTAS" | xargs)" "22 80 443"
# A IA é chamada pela Virgínia, onde a retenção zero está gravada (ADR-135; ela vale pela região de origem)
provar "IA chamada pela Virgínia (retenção zero)" "$(ssh "$SERVIDOR" "grep -c '^REGIAO_BEDROCK=us-east-1$' /srv/integra-folha/publicacao/.env")" "1"
# 5. A versão no ar: a etiqueta da imagem que a aplicação está rodando
VERSAO_NO_AR="$(ssh "$SERVIDOR" "docker inspect --format '{{.Config.Image}}' integra-folha-aplicacao-1" | sed 's/.*://')"
provar "versão no ar" "$VERSAO_NO_AR" "$ETIQUETA_ESPERADA"

# O resultado final
if [ "$PROVAS_QUE_FALHARAM" -eq 0 ]; then
  echo "Tudo certo."
  exit 0
fi
echo "$PROVAS_QUE_FALHARAM prova(s) falharam."
exit 1
