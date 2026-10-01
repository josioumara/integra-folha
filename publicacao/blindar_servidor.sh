#!/usr/bin/env bash
# =====================================================================================================================
# blindar_servidor.sh: prepara e protege a máquina nova da AWS (roda UMA vez, logo depois de a pilha ser criada)
#
# Para que serve:
#   A máquina nasce com o Ubuntu "de fábrica". Este script a deixa pronta e fechada, como trocar as fechaduras e
#   instalar o alarme de uma casa nova antes de mudar:
#   1. o fuso de Brasília e as atualizações de segurança automáticas;
#   2. o swap de 2 GB (um pedaço do disco usado como memória extra: a t3.small tem 2 GB, e a primeira subida da
#      aplicação passa disso);
#   3. o usuário "deploy", que publica, com a mesma chave SSH; o SSH só por chave (sem senha) e sem o root;
#   4. o firewall do próprio Ubuntu (ufw): só 22, 80 e 443. E o fail2ban, que bloqueia quem erra o SSH várias vezes;
#   5. o Docker (com o compose), o AWS CLI (para o backup) e o git;
#   6. a pasta /srv/integra-folha, um repositório git que recebe o código pelo "git push" do computador local.
#
# Como usar (do computador local, na primeira entrada, com o usuário "ubuntu" que vem na imagem):
#   scp -i ~/.ssh/integra-folha-ec2 publicacao/blindar_servidor.sh ubuntu@<ip>:/tmp/
#   ssh -i ~/.ssh/integra-folha-ec2 ubuntu@<ip> "sudo bash /tmp/blindar_servidor.sh"
#   Depois, teste num terminal NOVO: ssh -i ~/.ssh/integra-folha-ec2 deploy@<ip>  (antes de fechar o que está aberto)
#
# Pode rodar de novo sem estragar nada: cada passo confere se já foi feito.
# =====================================================================================================================

# Para no primeiro erro, em variável não definida e em erro no meio de um "|"
set -euo pipefail

# O usuário que publica (dono da pasta do site e do Docker)
USUARIO_DE_PUBLICACAO="deploy"
# A pasta do site no servidor
PASTA_DO_SITE="/srv/integra-folha"
# O tamanho do swap
TAMANHO_DO_SWAP="2G"

# Mostra cada etapa com um título, para acompanhar
etapa() {
  # Escreve o título da etapa
  echo ""
  echo "==== $1"
}

# O script precisa do administrador (root), porque mexe no sistema
if [ "$(id -u)" -ne 0 ]; then
  # Avisa e para
  echo "Rode com sudo: sudo bash $0"
  exit 1
fi

etapa "1. Fuso de Brasília e atualizações"
# O relógio do servidor no horário de Brasília (o backup da noite usa esta hora)
timedatectl set-timezone America/Sao_Paulo
# Não fazer perguntas durante a instalação dos pacotes
export DEBIAN_FRONTEND=noninteractive
# Atualiza a lista de pacotes
apt-get update -q
# Instala as atualizações pendentes
apt-get upgrade -y -q
# Instala as atualizações de segurança automáticas, o firewall, o fail2ban e o git
apt-get install -y -q unattended-upgrades ufw fail2ban git ca-certificates curl
# Liga as atualizações de segurança automáticas
dpkg-reconfigure -f noninteractive unattended-upgrades

etapa "2. Swap de $TAMANHO_DO_SWAP"
# Só cria se ainda não existir
if [ ! -f /swapfile ]; then
  # Reserva o espaço no disco
  fallocate -l "$TAMANHO_DO_SWAP" /swapfile
  # Só o administrador lê o arquivo (ele pode ter pedaços da memória)
  chmod 600 /swapfile
  # Formata como swap
  mkswap /swapfile
  # Liga agora
  swapon /swapfile
  # Liga de novo a cada reinício
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi
# Usa o swap só quando a memória apertar de verdade (o padrão, 60, usa cedo demais)
sysctl -w vm.swappiness=10
# Mantém a preferência depois de reiniciar
echo "vm.swappiness=10" > /etc/sysctl.d/99-integra-swap.conf

etapa "3. Usuário $USUARIO_DE_PUBLICACAO e SSH só por chave"
# Cria o usuário, se ainda não existir
if ! id "$USUARIO_DE_PUBLICACAO" >/dev/null 2>&1; then
  # Cria com pasta pessoal e sem senha (a entrada é só pela chave)
  adduser --disabled-password --gecos "" "$USUARIO_DE_PUBLICACAO"
fi
# A pasta das chaves do usuário
mkdir -p "/home/$USUARIO_DE_PUBLICACAO/.ssh"
# Copia a mesma chave pública que o "ubuntu" recebeu da AWS
cp /home/ubuntu/.ssh/authorized_keys "/home/$USUARIO_DE_PUBLICACAO/.ssh/authorized_keys"
# O usuário é dono das próprias chaves
chown -R "$USUARIO_DE_PUBLICACAO:$USUARIO_DE_PUBLICACAO" "/home/$USUARIO_DE_PUBLICACAO/.ssh"
# Só ele lê a pasta e o arquivo das chaves (o SSH recusa se estiver aberto)
chmod 700 "/home/$USUARIO_DE_PUBLICACAO/.ssh"
chmod 600 "/home/$USUARIO_DE_PUBLICACAO/.ssh/authorized_keys"
# Pode usar o sudo sem senha (ele não tem senha; a proteção é a chave SSH, como o "ubuntu" da AWS)
echo "$USUARIO_DE_PUBLICACAO ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$USUARIO_DE_PUBLICACAO"
# O arquivo do sudo precisa ser só de leitura
chmod 440 "/etc/sudoers.d/90-$USUARIO_DE_PUBLICACAO"
# As regras do SSH: sem senha e sem entrar como root
cat > /etc/ssh/sshd_config.d/99-integra.conf <<'REGRAS_DO_SSH'
# Só entra quem tem a chave (sem senha)
PasswordAuthentication no
# Ninguém entra direto como administrador
PermitRootLogin no
# Sem o login por teclado interativo (outra forma de senha)
KbdInteractiveAuthentication no
REGRAS_DO_SSH
# Confere se a configuração do SSH está certa antes de aplicar (se errar, a porta fecharia para todos)
sshd -t
# Aplica as regras novas
systemctl reload ssh

etapa "4. Firewall (ufw) e fail2ban"
# Por padrão, nada entra
ufw default deny incoming
# Por padrão, tudo sai (atualizações, Let's Encrypt, Bedrock, backup)
ufw default allow outgoing
# O SSH
ufw allow 22/tcp
# O http (o Caddy)
ufw allow 80/tcp
# O https (o Caddy)
ufw allow 443/tcp
# O https pelo HTTP/3
ufw allow 443/udp
# Liga o firewall sem perguntar
ufw --force enable
# Liga o fail2ban (o padrão do Ubuntu já protege o SSH)
systemctl enable --now fail2ban

etapa "5. Docker, compose e AWS CLI"
# Instala o Docker só se ainda não estiver instalado
if ! command -v docker >/dev/null 2>&1; then
  # A pasta das chaves dos repositórios de pacotes
  install -m 0755 -d /etc/apt/keyrings
  # Baixa a chave oficial do Docker (garante que o pacote é do Docker mesmo)
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  # Todo mundo pode ler a chave
  chmod a+r /etc/apt/keyrings/docker.asc
  # A versão do Ubuntu (ex.: "noble", o 24.04)
  VERSAO_DO_UBUNTU="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  # Acrescenta o repositório oficial do Docker
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSAO_DO_UBUNTU stable" > /etc/apt/sources.list.d/docker.list
  # Atualiza a lista de pacotes com o repositório novo
  apt-get update -q
  # Instala o Docker e o plugin do compose
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# O usuário de publicação pode usar o Docker sem sudo
usermod -aG docker "$USUARIO_DE_PUBLICACAO"
# Instala o AWS CLI (usado pelo backup, com o papel da máquina), se ainda não existir
if ! command -v aws >/dev/null 2>&1; then
  # O pacote oficial pelo snap
  snap install aws-cli --classic
fi

etapa "6. Pasta do site ($PASTA_DO_SITE)"
# Cria a pasta, se ainda não existir
mkdir -p "$PASTA_DO_SITE"
# O usuário de publicação é o dono
chown "$USUARIO_DE_PUBLICACAO:$USUARIO_DE_PUBLICACAO" "$PASTA_DO_SITE"
# Transforma a pasta num repositório git, que aceita o "git push" e já atualiza os arquivos (updateInstead)
if [ ! -d "$PASTA_DO_SITE/.git" ]; then
  # Cria o repositório como o usuário de publicação
  sudo -u "$USUARIO_DE_PUBLICACAO" git -C "$PASTA_DO_SITE" init -q -b main
  # Aceita o push na branch que está aberta e atualiza a pasta
  sudo -u "$USUARIO_DE_PUBLICACAO" git -C "$PASTA_DO_SITE" config receive.denyCurrentBranch updateInstead
fi

etapa "Pronto"
# Mostra o resumo do que ficou
echo "Swap: $(swapon --show --noheadings | awk '{print $3}')  |  Fuso: $(timedatectl show -p Timezone --value)"
echo "Firewall: $(ufw status | head -1)  |  Docker: $(docker --version)"
echo "Agora teste num terminal NOVO: ssh -i ~/.ssh/integra-folha-ec2 $USUARIO_DE_PUBLICACAO@<ip>"
