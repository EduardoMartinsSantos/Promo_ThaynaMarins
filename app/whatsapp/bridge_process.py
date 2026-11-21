"""
Sobe o whatsapp-bridge (Node) a partir do painel, para o usuário não precisar
abrir terminal: o painel inicia a bridge com a mesma porta/API key do .env
(EVOLUTION_API_URL / EVOLUTION_API_KEY), então as duas pontas sempre batem.

Só age quando EVOLUTION_API_URL aponta para esta máquina. Se a bridge já
estiver rodando (ex.: serviço systemd em produção), nada é iniciado.
"""
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("whatsapp.bridge")

BRIDGE_DIR = Path(__file__).resolve().parents[2] / "whatsapp-bridge"
LOG_FILE = BRIDGE_DIR / "bridge.log"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

_process: subprocess.Popen | None = None


def is_local() -> bool:
    return (urlparse(settings.EVOLUTION_API_URL).hostname or "") in LOCAL_HOSTS


def is_starting() -> bool:
    """True enquanto o processo que nós iniciamos está vivo (pode ainda não responder HTTP)."""
    return _process is not None and _process.poll() is None


def start() -> str | None:
    """Inicia a bridge local. Retorna mensagem de erro (para o usuário) ou None se iniciou."""
    global _process
    if is_starting():
        return None
    if not settings.BRIDGE_AUTOSTART:
        return "A bridge do WhatsApp está fora do ar. No servidor: sudo systemctl restart robopromo-bridge"
    if not is_local():
        return "EVOLUTION_API_URL não aponta para esta máquina — inicie a bridge no servidor dela."
    if not settings.EVOLUTION_API_KEY:
        return "Defina a API Key do WhatsApp (Avançado) antes de conectar."
    node = shutil.which("node")
    if not node:
        return "Node.js não encontrado. Instale em https://nodejs.org e reabra o painel."
    if not (BRIDGE_DIR / "node_modules").is_dir():
        return f"Dependências da bridge ausentes. Rode 'npm install' em {BRIDGE_DIR}."

    port = urlparse(settings.EVOLUTION_API_URL).port or 80
    env = {**os.environ, "PORT": str(port), "API_KEY": settings.EVOLUTION_API_KEY}
    log = open(LOG_FILE, "ab")
    try:
        _process = subprocess.Popen(
            [node, "index.js"], cwd=BRIDGE_DIR, env=env,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
    except OSError as e:
        return f"Falha ao iniciar a bridge: {e}"
    finally:
        log.close()  # o processo filho mantém o próprio handle
    logger.info(f"[WA] Bridge iniciada pelo painel (pid={_process.pid}, porta={port})")
    return None


def stop() -> None:
    """Encerra a bridge somente se foi o painel que a iniciou."""
    global _process
    if is_starting():
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
        logger.info("[WA] Bridge encerrada junto com o painel")
    _process = None
