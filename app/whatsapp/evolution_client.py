"""
Cliente para Evolution API (self-hosted WhatsApp).
Documentação: https://doc.evolution-api.com/
Suporta envio para grupos, comunidades e canais.
"""
import aiohttp
import asyncio
from typing import Optional
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("whatsapp.evolution")


class EvolutionAPIClient:
    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL.rstrip("/")
        self.headers = {
            "apikey": settings.EVOLUTION_API_KEY,
            "Content-Type": "application/json",
        }
        self.instance = settings.EVOLUTION_INSTANCE

    async def send_image_with_caption(
        self,
        channel_id: str,
        image_url: str,
        caption: str,
    ) -> bool:
        """Envia imagem + legenda formatada (exatamente como na referência)."""
        payload = {
            "number": channel_id,
            "mediatype": "image",
            "mimetype": "image/jpeg",
            "caption": caption,
            "media": image_url,
        }
        return await self._post(f"/message/sendMedia/{self.instance}", payload)

    async def send_text(self, channel_id: str, text: str) -> bool:
        payload = {
            "number": channel_id,
            "text": text,
        }
        return await self._post(f"/message/sendText/{self.instance}", payload)

    async def _post(self, path: str, payload: dict) -> bool:
        url = self.base_url + path
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                try:
                    async with session.post(
                        url, json=payload, headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        body = await resp.json()
                        if resp.status in (200, 201):
                            logger.info(f"[WA] Mensagem enviada → {path}")
                            return True
                        logger.warning(f"[WA] HTTP {resp.status}: {body}")
                        return False
                except Exception as e:
                    wait = 2 ** attempt
                    logger.error(f"[WA] Tentativa {attempt+1} falhou: {e} — retry {wait}s")
                    await asyncio.sleep(wait)
        return False

    async def check_connection(self) -> bool:
        url = f"{self.base_url}/instance/connectionState/{self.instance}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    state = data.get("instance", {}).get("state", "")
                    connected = state == "open"
                    logger.info(f"[WA] Estado da conexão: {state}")
                    return connected
            except Exception as e:
                logger.error(f"[WA] Falha ao verificar conexão: {e}")
                return False

    async def list_groups(self) -> list[dict]:
        """Helper exclusivo do whatsapp-bridge (Baileys) — lista grupos para achar o ID (@g.us)."""
        url = f"{self.base_url}/groups"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"[WA] /groups HTTP {resp.status}")
                        return []
                    return await resp.json()
            except Exception as e:
                logger.error(f"[WA] Falha ao listar grupos: {e}")
                return []
