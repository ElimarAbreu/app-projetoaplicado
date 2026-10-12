#!/usr/bin/env bash
set -euo pipefail
DEPLOY_USER="${SUDO_USER:-ubuntu}"
DEPLOY_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
STAGING="${DEPLOY_HOME}/secureops-lab-staging"
APP_DIR="/opt/secureops-lab"
[[ -f "${STAGING}/app.py" ]] || { echo "Não encontrei ${STAGING}/app.py" >&2; exit 1; }
install -d -o secureops -g secureops -m 0750 "$APP_DIR"
rsync -a --delete --exclude='.env' --exclude='.venv/' --exclude='__pycache__/' --exclude='.pytest_cache/' "${STAGING}/" "${APP_DIR}/"
chown -R secureops:secureops "$APP_DIR"
chmod 0750 "$APP_DIR"
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then sudo -u secureops python3 -m venv "${APP_DIR}/.venv"; fi
sudo -u secureops "${APP_DIR}/.venv/bin/pip" install --disable-pip-version-check --upgrade pip
sudo -u secureops "${APP_DIR}/.venv/bin/pip" install --disable-pip-version-check -r "${APP_DIR}/requirements.txt"
[[ -f /etc/secureops-lab/secureops.env ]] || { echo "Configure /etc/secureops-lab/secureops.env antes do deploy." >&2; exit 1; }
systemctl restart secureops-lab
systemctl --no-pager --full status secureops-lab
