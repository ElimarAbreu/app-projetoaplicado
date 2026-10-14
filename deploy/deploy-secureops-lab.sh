#!/usr/bin/env bash
set -Eeuo pipefail
DEPLOY_USER="${SUDO_USER:-ubuntu}"
DEPLOY_HOME="$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)"
[[ -n "${DEPLOY_HOME}" ]] || { echo "Usuário de deploy não encontrado." >&2; exit 1; }
STAGING="${DEPLOY_HOME}/secureops-lab-staging"; APP_DIR=/opt/secureops-lab; DATA_DIR=/var/lib/secureops-lab
[[ -f "${STAGING}/app.py" && -f "${STAGING}/requirements.txt" ]] || { echo "Código incompleto no staging." >&2; exit 1; }
[[ -f /etc/secureops-lab/secureops.env && -f /etc/systemd/system/secureops-lab.service ]] || { echo "Execute o bootstrap inicial primeiro." >&2; exit 1; }
# Scripts privilegiados são instalados pelo bootstrap, não pelo staging gravável.
install -d -o secureops -g secureops -m 0750 "${APP_DIR}" "${DATA_DIR}"
rsync -a --delete --exclude='/.env' --exclude='/.venv/' --exclude='/instance/' --exclude='/__pycache__/' --exclude='/.pytest_cache/' --exclude='/users.json' --exclude='/*.lock' "${STAGING}/" "${APP_DIR}/"
chown -R secureops:secureops "${APP_DIR}"; chmod 0750 "${APP_DIR}"
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then runuser -u secureops -- python3 -m venv "${APP_DIR}/.venv"; fi
runuser -u secureops -- "${APP_DIR}/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
runuser -u secureops -- "${APP_DIR}/.venv/bin/python" -m pip install --disable-pip-version-check -r "${APP_DIR}/requirements.txt"
systemctl daemon-reload; systemctl restart secureops-lab
healthy=0
for attempt in $(seq 1 20); do if curl --silent --fail --max-time 2 http://127.0.0.1:8000/login >/dev/null 2>&1; then healthy=1; break; fi; sleep 2; done
if [[ "$healthy" != 1 ]]; then echo "Aplicação não respondeu em 127.0.0.1:8000; Nginx não será alterado." >&2; systemctl --no-pager --full status secureops-lab || true; journalctl -u secureops-lab -n 80 --no-pager || true; exit 1; fi
/usr/local/sbin/configure-nginx-imc
systemctl --no-pager --full status secureops-lab
