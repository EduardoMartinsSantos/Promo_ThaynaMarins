#!/bin/bash
# Setup do servidor para o Robo-Promo (Ubuntu 22.04+).
# Rode como root ou com sudo, a partir da pasta /opt/robopromo
# (depois de extrair o projeto lá).
set -e

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

echo "=== 1/7 Pacotes do sistema ==="
apt-get update
apt-get install -y python3 python3-venv python3-pip curl

echo "=== 2/7 Node.js 20 LTS ==="
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "=== 3/7 Usuário de serviço 'robopromo' ==="
if ! id "robopromo" &>/dev/null; then
  useradd -r -m -d /opt/robopromo -s /bin/bash robopromo
fi

echo "=== 4/7 Ambiente Python (venv) ==="
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo "=== 5/7 Dependências do bridge WhatsApp ==="
cd "$PROJECT_DIR/whatsapp-bridge"
npm install --omit=dev
cd "$PROJECT_DIR"

echo "=== 6/7 Banco de dados ==="
if [ ! -f "$PROJECT_DIR/robopromo.db" ]; then
  "$PROJECT_DIR/.venv/bin/python" init_db.py
fi

echo "=== 7/7 Permissões e serviços systemd ==="
chown -R robopromo:robopromo "$PROJECT_DIR"
cp "$PROJECT_DIR/deploy/robopromo-bridge.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/robopromo-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now robopromo-bridge.service
systemctl enable --now robopromo-worker.service

echo ""
echo "=== Pronto! ==="
echo "Status:  systemctl status robopromo-bridge robopromo-worker"
echo "Logs:    journalctl -u robopromo-bridge -f"
echo "         journalctl -u robopromo-worker -f"
