/**
 * Mini-bridge HTTP para WhatsApp usando Baileys.
 *
 * Implementa o mesmo subconjunto da API da Evolution API que o
 * `app/whatsapp/evolution_client.py` consome, para que o robô não
 * precise de Docker/Postgres rodando localmente:
 *
 *   POST /message/sendMedia/:instance   { number, media, caption, ... }
 *   POST /message/sendText/:instance    { number, text }
 *   GET  /instance/connectionState/:instance
 *   GET  /groups                        (helper: lista grupos para achar o ID)
 *
 * Autenticação: header `apikey` (mesmo valor de EVOLUTION_API_KEY no .env).
 *
 * Na primeira execução, escaneie o QR Code exibido no terminal usando
 * WhatsApp > Aparelhos conectados > Conectar um aparelho. A sessão fica
 * salva em ./auth_info e é reaproveitada nas próximas execuções.
 */
const path = require("path");
// .env próprio (opcional) e o .env do projeto — o primeiro valor encontrado vence.
require("dotenv").config({
  quiet: true,
  path: [path.join(__dirname, ".env"), path.join(__dirname, "..", ".env")],
});
const fs = require("fs");
const express = require("express");
const qrcodeTerminal = require("qrcode-terminal");
const qrcode = require("qrcode");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");

const PORT = process.env.PORT || 8080;
// Só escuta na própria máquina: painel e robô acessam via localhost; nada exposto na internet.
const HOST = process.env.HOST || "127.0.0.1";
// Mesma chave que o painel/robô usam (EVOLUTION_API_KEY do .env do projeto).
const API_KEY = process.env.API_KEY || process.env.EVOLUTION_API_KEY || "troque-esta-chave";
const AUTH_DIR = path.join(__dirname, "auth_info");

let sock = null;
let connectionState = "close";
// QR Code atual em data URL (PNG base64) — exposto em GET /instance/qr para o painel.
let currentQr = null;

// Apaga a sessão salva e abre um socket novo, que vai emitir um QR Code novo.
// Com logout=true, avisa o WhatsApp antes (remove o aparelho da lista do celular).
async function resetSession({ logout = false } = {}) {
  const old = sock;
  const wasOpen = connectionState === "open";
  sock = null;
  currentQr = null;
  connectionState = "close";
  if (old) {
    // Remove listeners antes do logout para o evento "close" não disparar outro reset.
    old.ev.removeAllListeners();
    if (logout && wasOpen) {
      try { await old.logout(); } catch (_) { /* segue para o reset */ }
    }
    try { old.end(undefined); } catch (_) { /* socket já fechado */ }
  }
  fs.rmSync(AUTH_DIR, { recursive: true, force: true });
  await startSock();
}

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      qrcode.toDataURL(qr, { width: 300 }, (err, url) => {
        if (!err) currentQr = url;
      });
      const qrPath = path.join(__dirname, "qr.png");
      qrcode.toFile(qrPath, qr, { width: 300 }, (err) => {
        if (err) {
          console.error("[WA] Erro ao gerar QR Code em PNG:", err.message);
        } else {
          console.log(`\n=== QR Code salvo em ${qrPath} — escaneie no WhatsApp > Aparelhos conectados ===\n`);
        }
      });
      qrcodeTerminal.generate(qr, { small: true });
    }

    if (connection === "close") {
      connectionState = "close";
      const statusCode =
        lastDisconnect?.error instanceof Boom
          ? lastDisconnect.error.output?.statusCode
          : undefined;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log(`[WA] Conexão fechada (status=${statusCode}). Reconectar: ${shouldReconnect}`);
      if (shouldReconnect) {
        startSock();
      } else {
        console.log("[WA] Sessão deslogada. Gerando novo QR Code...");
        resetSession().catch((err) => console.error("[WA] Erro ao reiniciar sessão:", err.message));
      }
    } else if (connection === "open") {
      connectionState = "open";
      currentQr = null;
      console.log("[WA] Conectado com sucesso!");
    } else if (connection === "connecting") {
      connectionState = "connecting";
    }
  });
}

startSock();

const app = express();
app.use(express.json({ limit: "5mb" }));

app.use((req, res, next) => {
  if (req.headers["apikey"] !== API_KEY) {
    return res.status(401).json({ error: "apikey inválida" });
  }
  next();
});

app.get("/instance/connectionState/:instance", (req, res) => {
  res.json({ instance: { instanceName: req.params.instance, state: connectionState } });
});

// Estado + QR Code atual (data URL) para o painel exibir a tela de pareamento.
app.get("/instance/qr", (req, res) => {
  res.json({ state: connectionState, qr: connectionState === "open" ? null : currentQr });
});

// Desconecta o número atual e gera um QR Code novo (para trocar de número).
app.post("/instance/logout", async (req, res) => {
  try {
    await resetSession({ logout: true });
    res.json({ status: "logged_out" });
  } catch (err) {
    console.error("[WA] Erro ao desconectar:", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.post("/message/sendMedia/:instance", async (req, res) => {
  if (!sock || connectionState !== "open") {
    return res.status(503).json({ error: "WhatsApp não conectado" });
  }
  const { number, media, caption } = req.body;
  try {
    await sock.sendMessage(number, { image: { url: media }, caption: caption || "" });
    res.json({ status: "sent" });
  } catch (err) {
    console.error("[WA] Erro ao enviar mídia:", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.post("/message/sendText/:instance", async (req, res) => {
  if (!sock || connectionState !== "open") {
    return res.status(503).json({ error: "WhatsApp não conectado" });
  }
  const { number, text } = req.body;
  try {
    await sock.sendMessage(number, { text: text || "" });
    res.json({ status: "sent" });
  } catch (err) {
    console.error("[WA] Erro ao enviar texto:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// Helper: lista os grupos do WhatsApp conectado, para descobrir o ID (xxxx@g.us)
app.get("/groups", async (req, res) => {
  if (!sock || connectionState !== "open") {
    return res.status(503).json({ error: "WhatsApp não conectado" });
  }
  try {
    const groups = await sock.groupFetchAllParticipating();
    const list = Object.values(groups).map((g) => ({ id: g.id, subject: g.subject }));
    res.json(list);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, HOST, () => {
  console.log(`[WA] Bridge HTTP rodando em http://${HOST}:${PORT}`);
});
