#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
if [[ "$EUID" -ne 0 ]]; then echo "Execute: sudo bash deploy/bootstrap_oci.sh" >&2; exit 1; fi
DEPLOY_USER="${SUDO_USER:-ubuntu}"
DEPLOY_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
[[ -n "$DEPLOY_HOME" && -d "$DEPLOY_HOME" ]] || { echo "Usuário de deploy inválido." >&2; exit 1; }
DEPLOY_GROUP="$(id -gn "$DEPLOY_USER")"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip rsync openssl sudo curl
getent group secureops >/dev/null || groupadd --system secureops
id secureops >/dev/null 2>&1 || useradd --system --gid secureops --home-dir /var/lib/secureops-lab --no-create-home --shell /usr/sbin/nologin secureops
usermod --gid secureops secureops
install -d -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" -m 0750 "${DEPLOY_HOME}/secureops-lab-staging"
install -d -o root -g secureops -m 0750 /etc/secureops-lab
install -d -o secureops -g secureops -m 0750 /opt/secureops-lab /var/lib/secureops-lab
if [[ ! -f /etc/secureops-lab/secureops.env ]]; then
  SECRET_KEY="$(openssl rand -hex 32)"
  printf 'APP_ENV=production\nSECRET_KEY=%s\nUSERS_FILE=/var/lib/secureops-lab/users.json\n' "$SECRET_KEY" > /etc/secureops-lab/secureops.env
  unset SECRET_KEY
fi
chown root:secureops /etc/secureops-lab/secureops.env
chmod 0640 /etc/secureops-lab/secureops.env
install -o root -g root -m 0755 deploy/deploy-secureops-lab.sh /usr/local/sbin/deploy-secureops-lab
install -o root -g root -m 0755 deploy/configure-nginx-imc.py /usr/local/sbin/configure-nginx-imc
install -o root -g root -m 0644 deploy/secureops-lab.service /etc/systemd/system/secureops-lab.service
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/deploy-secureops-lab\n' "$DEPLOY_USER" > /etc/sudoers.d/secureops-lab-deploy
chmod 0440 /etc/sudoers.d/secureops-lab-deploy
visudo -cf /etc/sudoers.d/secureops-lab-deploy
systemctl daemon-reload
systemctl enable secureops-lab
echo "Bootstrap concluído. O primeiro deploy será feito pelo GitHub Actions."
