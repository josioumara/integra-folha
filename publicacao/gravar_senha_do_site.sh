#!/usr/bin/env bash
# gravar_senha_do_site.sh: grava a senha dos logins do site (SENHA_DA_BASE_VIVA) no .env de produção.
# Quem roda é quem administra, no servidor: a senha é digitada escondida e vai direto para o arquivo, sem passar
# por mensagens nem pelo Git.
# Para no primeiro erro e em variável não definida
set -eu
# O .env de produção (só o usuário deploy lê: chmod 600)
ARQUIVO_DO_ENV="/srv/integra-folha/publicacao/.env"
# Pede a senha sem mostrar na tela
read -rsp "Senha nova dos logins do site: " SENHA_DIGITADA; echo
# Pede de novo, para evitar erro de digitação
read -rsp "Repita a senha: " SENHA_REPETIDA; echo
# As duas precisam ser iguais
if [ "$SENHA_DIGITADA" != "$SENHA_REPETIDA" ]; then echo "As senhas não conferem. Nada foi gravado."; exit 1; fi
# Pelo menos 12 caracteres, porque o site é público
if [ "${#SENHA_DIGITADA}" -lt 12 ]; then echo "Use pelo menos 12 caracteres. Nada foi gravado."; exit 1; fi
# Tira a linha antiga, se existir (o sed -i mantém a permissão 600)
sed -i '/^SENHA_DA_BASE_VIVA=/d' "$ARQUIVO_DO_ENV"
# Grava a linha nova no fim do arquivo
printf 'SENHA_DA_BASE_VIVA=%s\n' "$SENHA_DIGITADA" >> "$ARQUIVO_DO_ENV"
# Confirma sem mostrar o valor
echo "Senha gravada no .env do servidor ($(stat -c %a "$ARQUIVO_DO_ENV"))."
