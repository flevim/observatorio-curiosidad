#!/usr/bin/env bash
# Instalación del Observatorio de la Curiosidad en una VM Ubuntu 24.04 (Oracle Cloud, ARM).
# Uso (dentro de la VM, como usuario ubuntu):
#   git clone https://github.com/flevim/observatorio-curiosidad.git && bash observatorio-curiosidad/deploy/servidor/setup.sh
set -euo pipefail

REPO_URL="https://github.com/flevim/observatorio-curiosidad.git"
DIR="$HOME/observatorio-curiosidad"

echo "==> Paquetes del sistema"
sudo apt-get update -y
sudo apt-get install -y git python3 python3-venv python3-pip curl ca-certificates

echo "==> Código"
if [ ! -d "$DIR/.git" ]; then
  git clone "$REPO_URL" "$DIR"
else
  git -C "$DIR" pull --ff-only
fi
cd "$DIR"

echo "==> Entorno de Python y dependencias"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install ./pipeline

echo "==> Configuración (.env)"
if [ ! -f .env ]; then
  cp deploy/servidor/env.ejemplo .env
  echo "Se creó .env. Edita OBSERVATORIO_CONTACT antes de continuar:  nano $DIR/.env"
fi

echo "==> Servicios systemd"
sudo cp deploy/servidor/observatorio-api.service /etc/systemd/system/
sudo cp deploy/servidor/observatorio-diario.service /etc/systemd/system/
sudo cp deploy/servidor/observatorio-diario.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now observatorio-api.service
sudo systemctl enable --now observatorio-diario.timer

echo "==> cloudflared (túnel saliente: no hace falta abrir puertos)"
if ! command -v cloudflared >/dev/null 2>&1; then
  curl -fsSL -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
  sudo apt-get install -y /tmp/cloudflared.deb
fi

cat <<'EOF'

Listo. Próximos pasos:
  1. Edita el contacto:            nano ~/observatorio-curiosidad/.env
  2. Reinicia la API:              sudo systemctl restart observatorio-api
  3. Primera descarga completa (tarda ~2 h; ejecútala dentro de tmux o screen):
        cd ~/observatorio-curiosidad && .venv/bin/python -m observatorio all
  4. Revisa la API:                curl -s http://127.0.0.1:8010/api/health
  5. Túnel público: ver docs/oracle-cloud.md (opción con dominio o rápida).
EOF
