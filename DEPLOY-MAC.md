# Rodar o Robo-Promo num Mac próprio (grátis, 24/7)

O Mac fica ligado em casa rodando o robô, o WhatsApp e a API do painel. A
tela (front) fica na **Vercel**, e de lá você liga e desliga o robô de
qualquer lugar. Depois de ligado, ele continua rodando até alguém desligar.

| Peça | Onde roda | Custo |
|------|-----------|-------|
| Front (tela) | Vercel | Grátis |
| Robô + WhatsApp + API | Mac, 24h | Grátis |
| Endereço HTTPS público do Mac | Tailscale Funnel | Grátis (nada aberto no roteador) |

A Vercel não consegue rodar o robô: as funções dela duram segundos e não
mantêm a conexão do WhatsApp aberta. Por isso o robô fica no Mac.

Vantagem sobre servidor na nuvem: a internet de casa usa IP residencial, e o
WhatsApp desconfia menos dele. Isso reduz o risco de banimento do número.

Tempo total: cerca de 20 minutos, só na primeira vez.

---

## 1. Instale os programas no Mac

Baixe e instale os três ("Continuar, Continuar, Instalar"):

1. **Python** (versão 3.12 ou mais nova): https://www.python.org/downloads/macos/
2. **Node.js** (botão "LTS"): https://nodejs.org
3. **Tailscale**: https://tailscale.com/download/mac. Abra o app e entre com
   sua conta Google, Microsoft ou Apple.

Só o Mac precisa do Tailscale. Quem usa o front na Vercel não precisa
instalar nada.

---

## 2. Publique o front na Vercel

1. Envie o projeto para o GitHub (sem o `.env`, que já está no `.gitignore`).
2. Em https://vercel.com, entre com o GitHub → **Add New → Project** → escolha
   o repositório.
3. Em **Root Directory**, clique **Edit** e escolha `app/dashboard/static`.
   Framework Preset: **Other**. Não precisa de build.
4. **Deploy**. Anote o endereço gerado, ex.: `https://robo-promo.vercel.app`.

---

## 3. Leve o projeto para o Mac

No PC com Windows, na pasta do projeto (PowerShell):

```powershell
tar --exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=logs --exclude=whatsapp-bridge/auth_info --exclude=whatsapp-bridge/.env --exclude=whatsapp-bridge/bridge.log --exclude=whatsapp-bridge/qr.png -czf "$env:USERPROFILE\Downloads\robopromo.tar.gz" .
```

Isso cria o `robopromo.tar.gz` na pasta **Downloads** do PC (fora do OneDrive, para o `.env` não subir para a nuvem). Ele leva o `.env`
(suas credenciais) e o banco (histórico anti-repetição). Copie o arquivo
para a pasta **Downloads** do Mac por pendrive ou Google Drive.

> O `.env` tem senhas: apague o arquivo do pendrive ou do Drive depois de copiar.

---

## 4. Instale no Mac

Abra o **Terminal** (Cmd+Espaço, digite "Terminal") e cole, trocando pelo
endereço da Vercel do passo 2:

```bash
mkdir -p ~/robopromo
tar -xzf ~/Downloads/robopromo.tar.gz -C ~/robopromo
cd ~/robopromo
bash deploy/setup-macos.sh https://robo-promo.vercel.app
```

- A senha do Mac será pedida. Ao digitar, nada aparece na tela; isso é normal.
- Se aparecer um link do Tailscale pedindo para **ativar HTTPS** ou
  **Funnel**, abra o link, confirme e espere o script continuar.
- Só esse endereço da Vercel pode usar o robô. Se ele mudar, rode o script
  de novo com o endereço novo.
- **Não** coloque a pasta em Mesa, Documentos, Downloads ou iCloud. O macOS
  bloqueia serviços em segundo plano nessas pastas. Por isso usamos `~/robopromo`.

No fim, o script mostra o **endereço do robô** (`https://NOME-DO-MAC.xxxx.ts.net`),
o **usuário** e a **senha**. Anote os três.

O script também deixa o Mac **sem dormir** e religando sozinho após falta de
energia. Robô, WhatsApp e painel iniciam sozinhos quando o Mac liga, mesmo
sem ninguém fazer login.

---

## 5. Use pelo front

1. Abra o endereço da Vercel (no celular ou em qualquer PC).
2. Na tela de login, informe o **endereço do robô**, o **usuário** e a
   **senha**. O navegador lembra; para trocar, use **Sair**.
3. Card **WhatsApp → 1. Conectar número**: escaneie o QR Code.
4. **2. Grupos de destino**: marque os grupos e salve.
5. **3. Testar**: envie a mensagem de teste.
6. Card **Robô**: ligue. Ele roda a cada ciclo até alguém desligar ali,
   mesmo com o front fechado.

No próprio Mac, o painel também abre em `http://127.0.0.1:8000`.

**Depois disso, pare o robô e o painel no PC com Windows.** Senão as
promoções saem duplicadas.

---

## Cuidados com o Mac

- **MacBook**: com a tampa fechada ele dorme mesmo com o ajuste do script.
  Deixe a tampa aberta e na tomada. Para dormir nunca, nem de tampa
  fechada: `sudo pmset -a disablesleep 1`.
- Atualizações do macOS reiniciam o Mac. Os serviços voltam sozinhos.
- Se a internet ou a energia cair, o robô volta quando elas voltarem.

---

## Manutenção

Ver a senha do painel de novo:

```bash
grep DASHBOARD_ ~/robopromo/.env
```

Ver logs:

```bash
tail -f ~/robopromo/logs/com.robopromo.worker.log      # robô
tail -f ~/robopromo/logs/com.robopromo.bridge.log      # WhatsApp
tail -f ~/robopromo/logs/com.robopromo.dashboard.log   # painel
```

Reiniciar um serviço:

```bash
sudo launchctl kickstart -k system/com.robopromo.worker
```

### Atualizar o código

No Windows, gere o pacote **sem** o `.env` e o banco, para não apagar o que
já está configurado no Mac:

```powershell
tar --exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=logs --exclude=whatsapp-bridge/auth_info --exclude=whatsapp-bridge/.env --exclude=whatsapp-bridge/bridge.log --exclude=whatsapp-bridge/qr.png --exclude=.env --exclude=robopromo.db -czf "$env:USERPROFILE\Downloads\robopromo.tar.gz" .
```

No Mac:

```bash
tar -xzf ~/Downloads/robopromo.tar.gz -C ~/robopromo
cd ~/robopromo && bash deploy/setup-macos.sh
```

### Desinstalar os serviços

```bash
for s in bridge worker dashboard; do
  sudo launchctl bootout system/com.robopromo.$s
  sudo rm /Library/LaunchDaemons/com.robopromo.$s.plist
done
```
