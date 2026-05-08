#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-robo}"
APP_DIR="${APP_DIR:-/opt/robo-simulados}"
SERVICE_NAME="${SERVICE_NAME:-robo-simulados}"

echo "[1/7] Instalando dependências do sistema..."
apt-get update
apt-get install -y \
  ca-certificates curl git unzip \
  python3 python3-venv python3-pip \
  libnss3 libatk-bridge2.0-0 libxkbcommon0 libgtk-3-0 \
  libgbm1 libasound2 libxshmfence1 libdrm2 libxcomposite1 \
  libxdamage1 libxfixes3 libxrandr2 libxext6 libx11-6 libxcb1 libx11-xcb1

echo "[2/7] Garantindo usuário do serviço..."
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "${APP_USER}"
fi

echo "[3/7] Preparando diretório..."
mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/logs"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ ! -f "${APP_DIR}/scraper.py" ]]; then
  echo "ERRO: scraper.py não encontrado em ${APP_DIR}."
  echo "Suba o projeto para ${APP_DIR} antes de continuar."
  exit 1
fi

echo "[4/7] Criando ambiente virtual..."
if [[ ! -d "${APP_DIR}/.venv" ]]; then
  sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
fi

echo "[5/7] Instalando dependências Python..."
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m playwright install chromium

echo "[6/7] Configurando .env.server..."
if [[ ! -f "${APP_DIR}/.env.server" ]]; then
  if [[ -f "${APP_DIR}/deploy/.env.server.example" ]]; then
    cp "${APP_DIR}/deploy/.env.server.example" "${APP_DIR}/.env.server"
  else
    cat > "${APP_DIR}/.env.server" <<'EOF'
ROBO_EMAIL=seu_email_aqui
ROBO_SENHA=sua_senha_aqui
ROBO_HEADLESS=1
EOF
  fi
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env.server"
  chmod 600 "${APP_DIR}/.env.server"
  echo "Arquivo ${APP_DIR}/.env.server criado. Edite com suas credenciais antes de iniciar o serviço."
fi

echo "[7/7] Instalando service do systemd..."
TMP_SERVICE="$(mktemp)"
sed \
  -e "s|^User=.*|User=${APP_USER}|" \
  -e "s|^Group=.*|Group=${APP_USER}|" \
  -e "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
  -e "s|^EnvironmentFile=.*|EnvironmentFile=-${APP_DIR}/.env.server|" \
  -e "s|^ExecStart=.*|ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/scraper.py|" \
  -e "s|^StandardOutput=.*|StandardOutput=append:${APP_DIR}/logs/robo-simulados.out.log|" \
  -e "s|^StandardError=.*|StandardError=append:${APP_DIR}/logs/robo-simulados.err.log|" \
  "${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service" > "${TMP_SERVICE}"

install -m 644 "${TMP_SERVICE}" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "${TMP_SERVICE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo
echo "Setup concluído."
echo "Próximos comandos:"
echo "  nano ${APP_DIR}/.env.server"
echo "  systemctl start ${SERVICE_NAME}.service"
echo "  systemctl status ${SERVICE_NAME}.service"
echo "  journalctl -u ${SERVICE_NAME}.service -f"
