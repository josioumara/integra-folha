#!/usr/bin/env bash
# =====================================================================================================================
# definir_senhas_da_demo.sh: define as senhas dos dois usuários da demo no servidor (roda no servidor)
#
# Para que serve:
#   Os dois logins da demo (empresa.aurora e especialista.banco) precisam de senha no servidor. Quem administra
#   escolhe, e a senha não pode passar por mensagens nem pelo Git. Este script pergunta cada senha na tela (sem
#   mostrar o que é digitado), confere o tamanho e grava no publicacao/.env, que só o dono do servidor lê.
#   Na próxima subida da aplicação, o preparar_servidor.py cria (ou recria) os usuários com estas senhas.
#
# Como usar (no PowerShell do computador local, um comando só):
#   ssh -t integra-folha "bash /srv/integra-folha/publicacao/definir_senhas_da_demo.sh"
# =====================================================================================================================

# Para no primeiro erro e em variável não definida
set -eu

# O arquivo de configuração do servidor
ARQUIVO_DE_CONFIGURACAO="/srv/integra-folha/publicacao/.env"

# Pergunta uma senha duas vezes, sem mostrar, até vir certa; grava na variável do .env
perguntar_e_gravar() {
  # O login, só para mostrar na pergunta
  local login_da_demo="$1"
  # A variável do .env que guarda a senha
  local variavel_da_senha="$2"
  # Repete até a senha ser válida
  while true; do
    # Pede a senha sem mostrar o que é digitado (-s)
    read -r -s -p "Senha para $login_da_demo (8 a 72 caracteres): " senha_digitada
    echo ""
    # Pede de novo, para conferir
    read -r -s -p "Repita a senha: " senha_repetida
    echo ""
    # As duas precisam ser iguais
    if [ "$senha_digitada" != "$senha_repetida" ]; then
      echo "As duas não são iguais. Tente de novo."
      continue
    fi
    # O tamanho mínimo e o máximo da aplicação (services/auth.py)
    if [ "${#senha_digitada}" -lt 8 ] || [ "${#senha_digitada}" -gt 72 ]; then
      echo "A senha precisa ter de 8 a 72 caracteres. Tente de novo."
      continue
    fi
    # Espaço, aspas, "#", "|", "&" e "\" atrapalham o arquivo .env ou o comando que grava
    case "$senha_digitada" in
      *[[:space:]]* | *\"* | *\'* | *\#* | *\|* | *\\* | *\&*)
        echo "Use sem espaço, aspas, #, |, & ou \\. Tente de novo."
        continue
        ;;
    esac
    # Tudo certo: sai da repetição
    break
  done
  # Grava a senha na linha da variável (o "|" separa as partes do comando, por isso ele é proibido na senha)
  sed -i "s|^${variavel_da_senha}=.*|${variavel_da_senha}=${senha_digitada}|" "$ARQUIVO_DE_CONFIGURACAO"
  # Confirma sem mostrar a senha
  echo "Gravada a senha de $login_da_demo."
}

# O login da empresa da demo
perguntar_e_gravar "empresa.aurora" "SENHA_USUARIO_EMPRESA"
# O login do especialista do banco
perguntar_e_gravar "especialista.banco" "SENHA_USUARIO_BANCO"
# Garante que só o dono lê o arquivo
chmod 600 "$ARQUIVO_DE_CONFIGURACAO"
echo "Pronto. As senhas valem a partir da próxima subida do site."
