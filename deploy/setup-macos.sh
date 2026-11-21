#!/bin/bash
# Setup do Robo-Promo em um Mac próprio, ligado 24h.
#
#   bash deploy/setup-macos.sh https://SEU-FRONT.vercel.app
#
# O endereço do front (Vercel) é opcional; sem ele, só o painel embutido
# (/admin) consegue usar a API. Rode como seu usuário normal (NÃO com sudo); a senha do Mac será pedida
# quando necessário. Pode ser rodado de novo sem problema (ex.: depois de
# atualizar o código).
#
# Pré-requisitos (instaladores gráficos, "avançar, avançar"):
#   - Python 3.10+  https://www.python.org/downloads/macos/
#   - Node.js LTS   https://nodejs.org
#   - Tailscale     https://tailscale.com/download/mac  (para acessar de fora)
set -e

if [ "$(id -u)" -eq 0 ]; then
  echo "Rode sem sudo: bash deploy/setup-macos.sh"
  exit 1
fi

FRONT_URL="${1%/}"

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
ENV_FILE="$PROJECT_DIR/.env"
RUN_USER="$(id -un)"
LOG_DIR="$PROJECT_DIR/logs"

# O macOS bloqueia serviços em segundo plano de ler Mesa/Documentos/Downloads/iCloud.
case "$PROJECT_DIR" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*|"$HOME/Library/Mobile Documents"*)
    echo "ERRO: mova a pasta do projeto para fora de Mesa/Documentos/Downloads/iCloud."
    echo "      Exemplo: mv \"$PROJECT_DIR\" ~/robopromo  e rode de novo a partir de lá."
    exit 1 ;;
esac

set_env() {
  if grep -q "^$1=" "$ENV_FILE"; then
    sed -i '' "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    echo "$1=$2" >> "$ENV_FILE"
  fi
}
get_env() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

echo "=== 1/6 Conferindo Python e Node ==="
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "ERRO: precisa do Python 3.10 ou mais novo. Instale em https://www.python.org/downloads/macos/"
  exit 1
fi
NODE="$(command -v node || true)"
if [ -z "$NODE" ]; then
  echo "ERRO: Node.js não encontrado. Instale a versão LTS em https://nodejs.org"
  exit 1
fi
echo "Python: $("$PYTHON" --version)  |  Node: $("$NODE" --version)"

echo "=== 2/6 Dependências (Python e bridge WhatsApp) ==="
"$PYTHON" -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
(cd "$PROJECT_DIR/whatsapp-bridge" && npm install --omit=dev)
CERT_FILE="$("$PROJECT_DIR/.venv/bin/python" -c 'import certifi; print(certifi.where())')"

echo "=== 3/6 Configuração (.env) e banco ==="
[ -f "$ENV_FILE" ] || cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
sed -i '' 's/\r$//' "$ENV_FILE"   # .env vindo do Windows (CRLF)
set_env EVOLUTION_API_URL "http://127.0.0.1:8080"
[ -n "$(get_env EVOLUTION_INSTANCE)" ] || set_env EVOLUTION_INSTANCE "robopromo"
case "$(get_env EVOLUTION_API_KEY)" in
  ""|troque-esta-chave) set_env EVOLUTION_API_KEY "$(openssl rand -hex 24)" ;;
esac
rm -f "$PROJECT_DIR/whatsapp-bridge/.env"   # a bridge lê o .env do projeto
[ -n "$(get_env DASHBOARD_USER)" ] || set_env DASHBOARD_USER "admin"
if [ -z "$(get_env DASHBOARD_PASSWORD)" ]; then
  set_env DASHBOARD_PASSWORD "$(openssl rand -base64 12 | tr -d '/+=')"
fi
[ -n "$FRONT_URL" ] && set_env DASHBOARD_ALLOWED_ORIGINS "$FRONT_URL"
chmod 600 "$ENV_FILE"
if [ ! -f "$PROJECT_DIR/robopromo.db" ]; then
  "$PROJECT_DIR/.venv/bin/python" init_db.py
fi
mkdir -p "$LOG_DIR"

echo "=== 4/6 Serviços (iniciam com o Mac, mesmo sem login) ==="
echo "A senha do Mac pode ser pedida agora."
PATH_ENV="$(dirname "$NODE"):/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# write_daemon LABEL WORKDIR EXTRA_ENV_XML ARG...
write_daemon() {
  local label="$1" workdir="$2" extra_env="$3"; shift 3
  local args="" a
  for a in "$@"; do args="$args<string>$a</string>"; done
  local plist="/Library/LaunchDaemons/$label.plist"
  sudo tee "$plist" >/dev/null <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>UserName</key><string>$RUN_USER</string>
  <key>WorkingDirectory</key><string>$workdir</string>
  <key>ProgramArguments</key><array>$args</array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$PATH_ENV</string>
    <key>SSL_CERT_FILE</key><string>$CERT_FILE</string>
    $extra_env
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/$label.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/$label.log</string>
</dict>
</plist>
EOF
  sudo chown root:wheel "$plist"
  sudo chmod 644 "$plist"
  sudo launchctl bootout "system/$label" 2>/dev/null || true
  sudo launchctl bootstrap system "$plist"
}

write_daemon com.robopromo.bridge "$PROJECT_DIR/whatsapp-bridge" "" \
  "$NODE" index.js
write_daemon com.robopromo.worker "$PROJECT_DIR" "" \
  "$PROJECT_DIR/.venv/bin/python" run_local.py
# A bridge já é um serviço próprio: o painel não deve abrir outra cópia.
write_daemon com.robopromo.dashboard "$PROJECT_DIR" \
  "<key>BRIDGE_AUTOSTART</key><string>false</string>" \
  "$PROJECT_DIR/.venv/bin/uvicorn" app.dashboard.main:app --host 127.0.0.1 --port 8000

echo "=== 5/6 Mac sempre acordado ==="
# Nunca dormir; religar sozinho depois de queda de energia (Macs de mesa).
sudo pmset -a sleep 0 disksleep 0
sudo pmset -a autorestart 1 2>/dev/null || true
sudo pmset -a womp 1 2>/dev/null || true

echo "=== 6/6 Endereço público HTTPS (Tailscale Funnel) ==="
# Funnel publica o painel/API na internet (o front da Vercel precisa alcançar
# de qualquer lugar). Protegido pelo login do painel; nada é aberto no roteador.
TS="$(command -v tailscale || true)"
[ -z "$TS" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] \
  && TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
URL=""
if [ -n "$TS" ] && "$TS" funnel --bg 8000; then
  DNS_NAME="$("$TS" status --json 2>/dev/null | "$PROJECT_DIR/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
  [ -n "$DNS_NAME" ] && URL="https://$DNS_NAME"
else
  echo "AVISO: Tailscale não configurado. Instale e entre na sua conta:"
  echo "       https://tailscale.com/download/mac  — depois rode este script de novo."
  echo "       (Se aparecer um link pedindo para ativar HTTPS/Funnel, abra-o e confirme.)"
fi

echo ""
echo "=================================================="
echo " Pronto! Painel neste Mac:  http://127.0.0.1:8000"
[ -n "$URL" ] && echo " Endereço do robô (use no login do front):  $URL"
[ -n "$FRONT_URL" ] && echo " Front autorizado:  $FRONT_URL"
echo " Usuário: $(get_env DASHBOARD_USER)"
echo " Senha:   $(get_env DASHBOARD_PASSWORD)"
echo "=================================================="
echo " Anote a senha. Para ver de novo: grep DASHBOARD_ \"$ENV_FILE\""
echo " Logs:  tail -f \"$LOG_DIR/com.robopromo.worker.log\""
