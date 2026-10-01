#!/usr/bin/env bash
# =====================================================================================================================
# dar_permissao_do_detector.sh: dá à chave do Bedrock a permissão do detector de ataques do Bedrock Guardrails (ADR-147)
#
# Para que serve:
#   A aplicação chama o Bedrock com uma chave (AWS_BEARER_TOKEN_BEDROCK). Cada chave pertence a um usuário do IAM e só
#   pode o que as políticas desse usuário permitem. A política padrão das chaves (AmazonBedrockLimitedAccess, v9, de
#   04/08/2026) não traz a permissão do detector de ataques (bedrock:InvokeGuardrailChecks). Este script grava essa
#   permissão, e só ela, no usuário da chave.
#
# Quem roda: a dona da conta, no CloudShell, com a conta principal (root), porque o usuário integra-publicador só
# mexe nos "integra-*".
# Serve para as duas chaves: a do ambiente local e a de produção, quando a IA for ligada no site.
#
# Como usar (no CloudShell, depois de enviar este arquivo por Actions > Upload file):
#   bash dar_permissao_do_detector.sh MantleApiKey-2hfuccuu
#
# O que faz, em ordem, e pergunta antes de gravar:
#   1. mostra as chaves do Bedrock da conta (o usuário, se está ativa, quando foi criada e quando vence);
#   2. mostra as permissões do usuário hoje (pela simulação do IAM, que não chama o Bedrock e não custa nada);
#   3. se faltar a permissão, pergunta e grava a política "integra-detector-de-ataques";
#   4. confere de novo e escreve o resultado numa linha.
#
# Custo: nenhum para gravar. Cada checagem feita depois custa US$ 0,08 por 1.000 unidades de texto (uma unidade tem até
# 1.000 caracteres), pelo preço público de https://aws.amazon.com/bedrock/pricing/ (conferido em 30/09/2026).
#
# Como desfazer: aws iam delete-user-policy --user-name <usuario-da-chave> --policy-name integra-detector-de-ataques
# =====================================================================================================================

# Para no primeiro erro e em variável não definida
set -eu

# O nome da política que fica gravada dentro do usuário da chave (com hífen, pela regra do projeto)
NOME_DA_POLITICA="integra-detector-de-ataques"
# O texto da política: só a permissão do detector. A API não tem recurso na conta, por isso o "*" (documentação do
# InvokeGuardrailChecks, página "Set up permissions")
TEXTO_DA_POLITICA='{"Version":"2012-10-17","Statement":[{"Sid":"DetectorDeAtaquesDoGuardrails","Effect":"Allow","Action":"bedrock:InvokeGuardrailChecks","Resource":"*"}]}'

# O usuário do IAM da chave vem como primeiro argumento (ex.: MantleApiKey-2hfuccuu)
USUARIO_DA_CHAVE="${1:-}"
# Sem o usuário, explica como usar e para sem mudar nada
if [ -z "$USUARIO_DA_CHAVE" ]; then
  echo "Uso: bash dar_permissao_do_detector.sh <usuario-da-chave>   (ex.: MantleApiKey-2hfuccuu)"
  exit 1
fi

# Quem está logado no CloudShell (o endereço completo no IAM, o "ARN")
QUEM_ESTA_LOGADO=$(aws sts get-caller-identity --query Arn --output text)
# Só a conta principal pode mudar o usuário da chave: com outro login, para antes de tentar
if [[ "$QUEM_ESTA_LOGADO" != *":root" ]]; then
  echo "Entre no console com a conta principal (root). Agora está: $QUEM_ESTA_LOGADO. Nada foi gravado."
  exit 1
fi

# O número da conta, para montar o endereço do usuário da chave
NUMERO_DA_CONTA=$(aws sts get-caller-identity --query Account --output text)
# O endereço (ARN) do usuário da chave, que a simulação do IAM pede
ENDERECO_DO_USUARIO="arn:aws:iam::${NUMERO_DA_CONTA}:user/${USUARIO_DA_CHAVE}"


# Mostra as chaves do Bedrock de todos os usuários da conta (a chave é uma "credencial de serviço" do IAM).
listar_as_chaves_do_bedrock() {
  # As colunas: o usuário, se está ativa, quando foi criada e quando vence
  local colunas="ServiceSpecificCredentials[].[UserName,Status,CreateDate,ExpirationDate]"
  # Tenta numa chamada só (a opção --all-users existe nas versões novas do AWS CLI)
  if aws iam list-service-specific-credentials --all-users --service-name bedrock.amazonaws.com \
      --query "$colunas" --output table 2>/dev/null; then
    return 0
  fi
  # Sem a opção, pergunta usuário por usuário
  for usuario in $(aws iam list-users --query "Users[].UserName" --output text); do
    # Mostra as chaves do Bedrock deste usuário (nada, se ele não tem)
    aws iam list-service-specific-credentials --user-name "$usuario" --service-name bedrock.amazonaws.com \
      --query "$colunas" --output text
  done
}


# Mostra as duas permissões que importam: usar a chave (CallWithBearerToken) e chamar o detector.
mostrar_as_permissoes() {
  # A simulação do IAM responde "allowed" (permitido) ou "implicitDeny" (falta), sem chamar o Bedrock
  aws iam simulate-principal-policy --policy-source-arn "$ENDERECO_DO_USUARIO" \
    --action-names bedrock:CallWithBearerToken bedrock:InvokeGuardrailChecks \
    --query "EvaluationResults[].[EvalActionName,EvalDecision]" --output table
}


# Devolve a decisão do IAM só para o detector ("allowed" quando ele já pode ser chamado).
decisao_do_detector() {
  # A mesma simulação, com a resposta numa palavra
  aws iam simulate-principal-policy --policy-source-arn "$ENDERECO_DO_USUARIO" \
    --action-names bedrock:InvokeGuardrailChecks --query "EvaluationResults[0].EvalDecision" --output text
}


echo "== 1. As chaves do Bedrock desta conta (usuário, situação, criada em, vence em) =="
# A conferência antes: o usuário da chave tem de aparecer como "Active"
listar_as_chaves_do_bedrock

echo "== 2. As permissões de $USUARIO_DA_CHAVE hoje =="
# A conferência antes: se a chave pode ser usada e se o detector já está permitido
mostrar_as_permissoes

# Se o detector já está permitido, não há o que gravar
if [ "$(decisao_do_detector)" = "allowed" ]; then
  echo "Resultado: o detector já estava permitido para $USUARIO_DA_CHAVE. Nada foi gravado."
  exit 0
fi

# Pergunta antes de gravar: só com o usuário certo, com a chave ativa, na tabela 1
read -r -p "A tabela 1 mostra $USUARIO_DA_CHAVE como Active? Gravar a permissão do detector? (s/n) " RESPOSTA
# Qualquer resposta diferente de "s" para sem mudar nada
if [ "$RESPOSTA" != "s" ]; then
  echo "Resultado: nada foi gravado."
  exit 0
fi

echo "== 3. Gravando a política $NOME_DA_POLITICA em $USUARIO_DA_CHAVE =="
# Grava a política dentro do usuário da chave (uma política "inline": mora no usuário e sai junto com ele)
aws iam put-user-policy --user-name "$USUARIO_DA_CHAVE" --policy-name "$NOME_DA_POLITICA" \
  --policy-document "$TEXTO_DA_POLITICA"
# Dá alguns segundos para o IAM registrar a mudança antes de conferir
sleep 5

echo "== 4. As permissões depois =="
# A conferência depois: agora as duas linhas têm de dizer "allowed"
mostrar_as_permissoes
# O resultado numa linha, para conferir de relance
echo "Resultado: detector = $(decisao_do_detector)"
