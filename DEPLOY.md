# Deploy — Robo-Promo (24/7, custo mínimo)

Arquitetura atual (sem Docker, sem Postgres/Redis/Celery):

| Processo                | O que faz                                         |
|-------------------------|----------------------------------------------------|
| `whatsapp-bridge` (Node) | Mantém a sessão do WhatsApp (Baileys) e expõe HTTP |
| `run_local.py` (Python)  | Loop: scraping ML → filtro → envia via bridge      |
| `robopromo.db` (SQLite)  | Banco local — guarda histórico/anti-spam            |

Os dois processos rodam como serviços `systemd` (`Restart=always`), então
sobrevivem a reboots e quedas.

---

## 1. Crie o servidor (escolha um)

### Opção A — Oracle Cloud "Always Free" (US$0/mês)
1. Crie conta em https://www.oracle.com/cloud/free/ (pede cartão para
   verificação de identidade, mas não cobra nada nos recursos "Always Free").
2. Menu → **Compute → Instances → Create Instance**.
3. Shape: **Ampere A1 (ARM)** — escolha 1 OCPU / 6 GB RAM (cabe dentro do
   limite gratuito de 4 OCPU / 24 GB).
4. Imagem: **Ubuntu 22.04** (ou 24.04).
5. Adicione/gere uma chave SSH e crie a instância.
6. Anote o IP público. Usuário SSH padrão: `ubuntu`.

> Se aparecer "Out of capacity" no shape Ampere, tente outra região/AD ou
> tente novamente mais tarde — é um problema comum de disponibilidade do
> tier gratuito, não um erro de configuração.

### Opção B — Hetzner CX22 (~€4,5/mês, mais garantido)
1. Crie conta em https://www.hetzner.com/cloud
2. **Add Server** → Ubuntu 22.04 → tipo **CX22** → adicione sua chave SSH
   → criar.
3. Anote o IP público. Usuário SSH padrão: `root`.

---

## 2. Acesse via SSH

```powershell
ssh ubuntu@SEU_IP        # Oracle
# ou
ssh root@SEU_IP          # Hetzner
```

---

## 3. Envie o projeto para o servidor

No seu PC (PowerShell), a partir da pasta do projeto:

```powershell
# Cria um pacote sem node_modules / .venv / banco temporário
tar --exclude='whatsapp-bridge/node_modules' --exclude='.venv' --exclude='__pycache__' -czf robopromo.tar.gz .

scp robopromo.tar.gz ubuntu@SEU_IP:/tmp/
```

No servidor:

```bash
sudo mkdir -p /opt/robopromo
sudo tar -xzf /tmp/robopromo.tar.gz -C /opt/robopromo
cd /opt/robopromo
```

### Envie a sessão do WhatsApp e o banco (preserva o que já está rodando)

Isso evita escanear o QR Code de novo e mantém o histórico anti-spam:

```powershell
scp -r whatsapp-bridge\auth_info ubuntu@SEU_IP:/tmp/auth_info
scp robopromo.db ubuntu@SEU_IP:/tmp/robopromo.db
```

No servidor:

```bash
cp -r /tmp/auth_info /opt/robopromo/whatsapp-bridge/auth_info
cp /tmp/robopromo.db /opt/robopromo/robopromo.db
```

---

## 4. Configure o `.env`

O `.env` enviado já tem suas credenciais. Confira/ajuste:

```bash
cd /opt/robopromo
nano .env
```

- `EVOLUTION_API_URL=http://localhost:8080` (bridge roda no mesmo servidor)
- `WHATSAPP_CHANNELS` — grupo(s) de destino
- `ML_ACCESS_TOKEN` / `ML_REFRESH_TOKEN` — **importante**: rode
  `python get_token.py` localmente antes do deploy (ou no servidor) para
  garantir que `ML_REFRESH_TOKEN` está preenchido. Sem ele, o token expira
  em ~6h e o bot para de capturar promoções.

---

## 5. Rode o setup

```bash
cd /opt/robopromo
chmod +x deploy/setup.sh
sudo ./deploy/setup.sh
```

Isso instala Node 20, Python venv, dependências, cria o usuário de serviço
`robopromo`, e sobe os dois serviços via `systemd` (`enable --now`, ou seja,
já inicia e fica ativo após reboot).

---

## 6. Verifique

```bash
systemctl status robopromo-bridge robopromo-worker

journalctl -u robopromo-bridge -f   # logs do WhatsApp
journalctl -u robopromo-worker -f   # logs do scraper/ciclo
```

Se o bridge perder a sessão (raro, já que `auth_info/` foi copiado), os
logs mostrarão um novo QR Code em `whatsapp-bridge/qr.png` — baixe com
`scp` e escaneie de novo.

---

## Manutenção

```bash
# Reiniciar após alterar .env ou código
sudo systemctl restart robopromo-worker
sudo systemctl restart robopromo-bridge

# Atualizar código (repita o passo 3 e reinicie os serviços)
```
