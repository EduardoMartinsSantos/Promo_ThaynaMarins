#!/bin/bash
# Setup do servidor para o Robo-Promo (Ubuntu 22.04+).
# Rode como root ou com sudo, a partir da pasta /opt/robopromo
# (depois de extrair o projeto lá), passando o seu endereço DuckDNS:
#
#   sudo ./deploy/setup.sh meurobo.duckdns.org
#
# Pode ser rodado de novo sem problema (ex.: depois de atualizar o código).
set -e

DOMAIN="$1"
FRONT_URL="${2%/}"   # opcional: front na Vercel (https://SEU-FRONT.vercel.app)
if [ -z "$DOMAIN" ]; then
  echo "Uso: sudo ./deploy/setup.sh SEU-ENDERECO.duckdns.org [https://SEU-FRONT.vercel.app]"
  exit 1
fi

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
ENV_FILE="$PROJECT_DIR/.env"

# Define KEY=VALUE no .env (substitui se existir, adiciona se não).
set_env() {
  if grep -q "^$1=" "$ENV_FILE"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    echo "$1=$2" >> "$ENV_FILE"
  fi
}
get_env() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

echo "=== 1/8 Pacotes do sistema ==="
apt-get update
apt-get install -y python3 python3-venv python3-pip curl gnupg debian-keyring debian-archive-keyring apt-transport-https

echo "=== 2/8 Node.js 20 LTS ==="
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "=== 3/8 Caddy (HTTPS automático) ==="
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

echo "=== 4/8 Usuário de serviço 'robopromo' ==="
if ! id "robopromo" &>/dev/null; then
  useradd -r -m -d /opt/robopromo -s /bin/bash robopromo
fi

echo "=== 5/8 Ambiente Python (venv) e bridge WhatsApp ==="
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
cd "$PROJECT_DIR/whatsapp-bridge"
npm install --omit=dev
cd "$PROJECT_DIR"

echo "=== 6/8 Configuração (.env) e banco ==="
[ -f "$ENV_FILE" ] || cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
sed -i 's/\r$//' "$ENV_FILE"   # .env vindo do Windows (CRLF)
# Bridge e painel na mesma máquina; uma chave só, gerada se ainda for a de exemplo.
set_env EVOLUTION_API_URL "http://127.0.0.1:8080"
[ -n "$(get_env EVOLUTION_INSTANCE)" ] || set_env EVOLUTION_INSTANCE "robopromo"
case "$(get_env EVOLUTION_API_KEY)" in
  ""|troque-esta-chave) set_env EVOLUTION_API_KEY "$(openssl rand -hex 24)" ;;
esac
# .env próprio da bridge não é usado no servidor (ela lê o .env do projeto).
rm -f "$PROJECT_DIR/whatsapp-bridge/.env"
# Login do painel: gera senha na primeira vez.
[ -n "$(get_env DASHBOARD_USER)" ] || set_env DASHBOARD_USER "admin"
if [ -z "$(get_env DASHBOARD_PASSWORD)" ]; then
  set_env DASHBOARD_PASSWORD "$(openssl rand -base64 12 | tr -d '/+=')"
fi
[ -n "$FRONT_URL" ] && set_env DASHBOARD_ALLOWED_ORIGINS "$FRONT_URL"
chmod 600 "$ENV_FILE"
if [ ! -f "$PROJECT_DIR/robopromo.db" ]; then
  "$PROJECT_DIR/.venv/bin/python" init_db.py
fi

echo "=== 7/8 Firewall (portas 80/443) ==="
# Imagens Ubuntu da Oracle bloqueiam tudo além do SSH via iptables.
for port in 80 443; do
  iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
    || iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
done
if command -v netfilter-persistent >/dev/null 2>&1; then
  netfilter-persistent save
fi

echo "=== 8/8 Serviços (bridge, robô, painel, Caddy) ==="
chown -R robopromo:robopromo "$PROJECT_DIR"
cp "$PROJECT_DIR/deploy/robopromo-bridge.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/robopromo-worker.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/robopromo-dashboard.service" /etc/systemd/system/
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
	reverse_proxy 127.0.0.1:8000
}
EOF
systemctl daemon-reload
for svc in robopromo-bridge robopromo-worker robopromo-dashboard; do
  systemctl enable "$svc.service"
  systemctl restart "$svc.service"
done
systemctl reload caddy || systemctl restart caddy

echo ""
echo "=================================================="
echo " Pronto! Abra no navegador:  https://$DOMAIN"
echo " Usuário: $(get_env DASHBOARD_USER)"
echo " Senha:   $(get_env DASHBOARD_PASSWORD)"
echo "=================================================="
echo " Anote a senha. Para ver de novo: sudo grep DASHBOARD_ $ENV_FILE"
echo " Status:  systemctl status robopromo-bridge robopromo-worker robopromo-dashboard"
echo " Logs:    journalctl -u robopromo-worker -f"
