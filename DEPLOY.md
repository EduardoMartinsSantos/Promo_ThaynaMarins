# Colocar o Robo-Promo online (grátis, 24/7)

> Tem um Mac que pode ficar ligado? Veja [DEPLOY-MAC.md](DEPLOY-MAC.md).
> É mais simples que este guia e não precisa de conta na Oracle.

Resultado final: o painel fica em `https://SEU-NOME.duckdns.org`, com login,
e o robô roda o tempo todo, mesmo com seu PC desligado.

| Peça | Para que serve | Custo |
|------|----------------|-------|
| Oracle Cloud "Always Free" | Servidor ligado 24h | Grátis (pede cartão só para verificar identidade) |
| DuckDNS | Endereço fácil (`seunome.duckdns.org`) | Grátis |
| Caddy (instalado pelo script) | Cadeado HTTPS automático | Grátis |

No servidor rodam 3 serviços, que reiniciam sozinhos após quedas e reboots:

| Serviço | O que faz |
|---------|-----------|
| `robopromo-bridge` | Mantém o WhatsApp conectado |
| `robopromo-worker` | Robô: busca promoções e envia |
| `robopromo-dashboard` | Painel de configuração (atrás do Caddy) |

Tempo total: cerca de 30 minutos, só na primeira vez.

---

## 1. Crie o servidor na Oracle

1. Crie a conta em https://www.oracle.com/cloud/free/
2. Menu ☰ → **Compute → Instances → Create instance**.
3. **Image and shape → Edit**:
   - Image: **Canonical Ubuntu 22.04** (ou 24.04).
   - Shape: **Ampere → VM.Standard.A1.Flex**, 1 OCPU e 6 GB de memória.
     Se der "Out of capacity", tente de novo mais tarde ou use
     **VM.Standard.E2.1.Micro** (também grátis, mais fraco, mas funciona).
4. **Add SSH keys → Generate a key pair for me → Save private key**.
   Guarde o arquivo `.key` baixado; ele é a sua chave de acesso.
5. **Create**. Quando ficar verde (Running), anote o **Public IP address**.

### Libere as portas do site (80 e 443)

1. Na página da instância, clique no link da **Subnet**.
2. **Security Lists → Default Security List → Add Ingress Rules**:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: `TCP`
   - Destination Port Range: `80,443`
3. **Add Ingress Rules**.

---

## 2. Crie o endereço no DuckDNS

1. Entre em https://www.duckdns.org com sua conta Google ou GitHub.
2. Em **sub domain**, digite um nome (ex.: `meurobo`) e clique **add domain**.
3. No campo **current ip** desse domínio, cole o IP público da Oracle e
   clique **update ip**.

Seu endereço será `meurobo.duckdns.org`.

---

## 3. Envie o projeto (no seu PC, PowerShell)

Na pasta do projeto. Troque `C:\caminho\da\chave.key` e `SEU_IP`:

```powershell
# A chave precisa ser só sua, senão o ssh recusa ("UNPROTECTED PRIVATE KEY FILE")
icacls "C:\caminho\da\chave.key" /inheritance:r /grant:r "$($env:USERNAME):R"

# Empacota o projeto (sem dependências e sem a sessão local do WhatsApp)
tar --exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=whatsapp-bridge/auth_info --exclude=whatsapp-bridge/.env --exclude=whatsapp-bridge/bridge.log --exclude=whatsapp-bridge/qr.png -czf "$env:TEMP\robopromo.tar.gz" .

scp -i "C:\caminho\da\chave.key" "$env:TEMP\robopromo.tar.gz" ubuntu@SEU_IP:/tmp/
```

O pacote leva o seu `.env` (credenciais do ML e da Shopee) e o
`robopromo.db` (histórico anti-repetição).

---

## 4. Instale no servidor

```powershell
ssh -i "C:\caminho\da\chave.key" ubuntu@SEU_IP
```

Já dentro do servidor (troque `meurobo` pelo seu nome):

```bash
sudo mkdir -p /opt/robopromo
sudo tar -xzf /tmp/robopromo.tar.gz -C /opt/robopromo
cd /opt/robopromo
sudo sed -i 's/\r$//' deploy/setup.sh deploy/*.service
sudo bash deploy/setup.sh meurobo.duckdns.org
```

No fim, o script mostra o endereço, o **usuário** e a **senha** do painel.
Anote os três.

---

## 5. Configure pelo painel

1. Abra `https://meurobo.duckdns.org` e entre com o usuário e a senha.
   No primeiro acesso, o cadeado HTTPS pode levar até 1 minuto para ficar pronto.
2. Card **WhatsApp → 1. Conectar número**: escaneie o QR Code com o celular.
3. **2. Grupos de destino → Escolher grupos**: marque os grupos e salve.
4. **3. Testar**: envie a mensagem de teste.

O robô aplica o que você salvar no painel a partir do próximo ciclo. Não
precisa reiniciar nada.

**Depois disso, pare o robô e o painel no seu PC.** Senão as promoções
saem duplicadas.

---

## Manutenção

Ver a senha do painel de novo (no servidor):

```bash
sudo grep DASHBOARD_ /opt/robopromo/.env
```

Ver logs e status:

```bash
systemctl status robopromo-bridge robopromo-worker robopromo-dashboard
journalctl -u robopromo-worker -f      # robô
journalctl -u robopromo-bridge -f      # WhatsApp
```

### Atualizar o código

Repita o passo 3 com o comando `tar` abaixo. Ele não leva o `.env` nem o
banco, para não apagar o que já está configurado no servidor:

```powershell
tar --exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=whatsapp-bridge/auth_info --exclude=whatsapp-bridge/.env --exclude=whatsapp-bridge/bridge.log --exclude=whatsapp-bridge/qr.png --exclude=.env --exclude=robopromo.db -czf "$env:TEMP\robopromo.tar.gz" .
```

Depois, no servidor, rode os mesmos comandos do passo 4. O `setup.sh` pode
ser rodado quantas vezes precisar.

### Token do Mercado Livre

Confira se `ML_REFRESH_TOKEN` está preenchido no `.env` antes de enviar.
Se não estiver, rode `python get_token.py` no seu PC. Sem esse token, o
acesso expira em cerca de 6h e o robô para de capturar promoções.

### Rodar só no seu PC (sem servidor)

```powershell
python -m uvicorn app.dashboard.main:app --port 8000   # painel + WhatsApp
python run_local.py                                     # robô
```

Abra `http://127.0.0.1:8000`. O painel sobe a bridge do WhatsApp sozinho.
