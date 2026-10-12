#!/usr/bin/env bash
set -euo pipefail
if [[ "$EUID" -ne 0 ]]; then echo "Execute: sudo bash deploy/bootstrap_oci.sh" >&2; exit 1; fi
DEPLOY_USER="${SUDO_USER:-ubuntu}"
DEPLOY_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
[[ -n "$DEPLOY_HOME" ]] || { echo "Não consegui determinar o usuário de deploy." >&2; exit 1; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv rsync openssl
if ! id secureops >/dev/null 2>&1; then useradd --system --home-dir /opt/secureops-lab --shell /usr/sbin/nologin secureops; fi
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0750 "${DEPLOY_HOME}/secureops-lab-staging"
install -d -o root -g secureops -m 0750 /etc/secureops-lab
install -d -o secureops -g secureops -m 0750 /opt/secureops-lab
install -d -o secureops -g secureops -m 0750 /var/lib/secureops-lab
if [[ ! -f /etc/secureops-lab/secureops.env ]]; then
  SECRET_KEY="$(openssl rand -hex 32)"
  cat > /etc/secureops-lab/secureops.env <<EOF
APP_ENV=production
SECRET_KEY=${SECRET_KEY}
USERS_FILE=/var/lib/secureops-lab/users.json
EOF
  chown root:secureops /etc/secureops-lab/secureops.env
  chmod 0640 /etc/secureops-lab/secureops.env
  echo "Criado /etc/secureops-lab/secureops.env. Confira SECRET_KEY e USERS_FILE antes de liberar o acesso público."
fi
install -o root -g root -m 0755 deploy/deploy-secureops-lab.sh /usr/local/sbin/deploy-secureops-lab
install -o root -g root -m 0644 deploy/secureops-lab.service /etc/systemd/system/secureops-lab.service
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/deploy-secureops-lab\n' "$DEPLOY_USER" > /etc/sudoers.d/secureops-lab-deploy
chmod 0440 /etc/sudoers.d/secureops-lab-deploy
visudo -cf /etc/sudoers.d/secureops-lab-deploy
systemctl daemon-reload
systemctl enable secureops-lab
echo "Base criada. Confira a configuração do arquivo persistente de usuários e o proxy HTTPS do Nginx antes de expor o serviço."
