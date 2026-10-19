"""
Rode este script UMA VEZ para obter o access_token e refresh_token do ML.
Depois disso o sistema renova automaticamente.

Uso:
    python get_token.py
"""
import os
import sys
import webbrowser
import urllib.parse
import urllib.request
import json

# Lê APP_ID e SECRET do .env
def load_env():
    env = {}
    try:
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        print("❌ Arquivo .env não encontrado. Execute na pasta raiz do projeto.")
        sys.exit(1)
    return env

env = load_env()

APP_ID     = env.get("ML_APP_ID", "")
SECRET_KEY = env.get("ML_SECRET_KEY", "")
REDIRECT   = "https://httpbin.org/get"

if not APP_ID or APP_ID == "COLE_APENAS_O_NUMERO_DO_APP":
    print("❌ Preencha ML_APP_ID no .env primeiro.")
    sys.exit(1)

if not SECRET_KEY or SECRET_KEY == "COLE_O_SECRET_KEY_CURTO":
    print("❌ Preencha ML_SECRET_KEY no .env primeiro.")
    sys.exit(1)

# ── Passo 1: abre o navegador para autorizar ──────────────────────────
auth_url = (
    f"https://auth.mercadolivre.com.br/authorization"
    f"?response_type=code"
    f"&client_id={APP_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT, safe='')}"
)

print("\n" + "="*60)
print("PASSO 1 — Autorize o app no navegador")
print("="*60)
print(f"\nAbrindo: {auth_url}\n")
webbrowser.open(auth_url)

print("Após autorizar, o navegador vai abrir uma página como:")
print(f"  {REDIRECT}?code=TG-XXXXXXXXXXXXXXXXXX-XXXXXXXXX\n")

code = input("Cole aqui o valor do 'code' que apareceu na URL: ").strip()
if not code:
    print("❌ Código não informado.")
    sys.exit(1)

# Remove prefixo caso o usuário tenha colado a URL inteira
if "code=" in code:
    code = code.split("code=")[-1].split("&")[0]

print(f"\n✅ Código recebido: {code[:20]}...")

# ── Passo 2: troca o code pelo token ─────────────────────────────────
print("\nTrocando code pelo access_token...")

data = urllib.parse.urlencode({
    "grant_type":    "authorization_code",
    "client_id":     APP_ID,
    "client_secret": SECRET_KEY,
    "code":          code,
    "redirect_uri":  REDIRECT,
}).encode()

req = urllib.request.Request(
    "https://api.mercadolibre.com/oauth/token",
    data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"❌ Erro HTTP {e.code}: {body}")
    sys.exit(1)

access_token  = result.get("access_token", "")
refresh_token = result.get("refresh_token", "")
expires_in    = result.get("expires_in", 21600)

if not access_token:
    print(f"❌ Resposta inesperada: {result}")
    sys.exit(1)

# ── Passo 3: salva no .env ────────────────────────────────────────────
with open(".env", "r") as f:
    content = f.read()

content = content.replace(
    f"ML_ACCESS_TOKEN={env.get('ML_ACCESS_TOKEN', 'PREENCHER_VIA_OAUTH')}",
    f"ML_ACCESS_TOKEN={access_token}"
)

# Adiciona REFRESH_TOKEN se não existir
if "ML_REFRESH_TOKEN=" not in content:
    content += f"\nML_REFRESH_TOKEN={refresh_token}\n"
else:
    import re
    content = re.sub(r"ML_REFRESH_TOKEN=.*", f"ML_REFRESH_TOKEN={refresh_token}", content)

with open(".env", "w") as f:
    f.write(content)

# ── Resultado ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("✅ SUCESSO! Tokens salvos no .env")
print("="*60)
print(f"  access_token  : {access_token[:30]}...")
print(f"  refresh_token : {refresh_token[:20]}...")
print(f"  expira em     : {expires_in // 3600}h")
print("\nPróximo passo:")
print("  cd docker && docker compose up -d --build")
