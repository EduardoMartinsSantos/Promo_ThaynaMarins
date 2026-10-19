"""
Renovação automática do Access Token do Mercado Livre.
O token expira em 6 horas; este módulo o renova automaticamente
usando o refresh_token e persiste os novos valores no banco.
"""
import asyncio
from datetime import datetime, timedelta
import aiohttp
from sqlalchemy import select
from app.core.config import settings
from app.core.logger import get_logger
from app.database.connection import AsyncSessionLocal
from app.database.models import Configuration

logger = get_logger("affiliate.ml_token")

ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

# Renova com 30 minutos de antecedência
RENEW_BEFORE_SECONDS = 30 * 60


class MLTokenManager:
    """
    Mantém o access_token sempre válido.
    Os tokens são persistidos na tabela `configurations` para
    sobreviver a reinicializações de container.

    Um lock + cache em memória evita que chamadas concorrentes
    (várias categorias em paralelo) disparem múltiplas renovações
    e gravações simultâneas no banco.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cached_token: str | None = None
        self._cached_expires_at: datetime | None = None

    async def get_valid_token(self) -> str:
        """Retorna um token válido, renovando se necessário."""
        async with self._lock:
            if self._cached_token and self._cached_expires_at:
                if datetime.utcnow() < self._cached_expires_at - timedelta(seconds=RENEW_BEFORE_SECONDS):
                    return self._cached_token

            async with AsyncSessionLocal() as db:
                expires_at = await self._get_config(db, "ml_token_expires_at")
                token = await self._get_config(db, "ml_access_token")

                if token and expires_at:
                    expires_dt = datetime.fromisoformat(expires_at)
                    if datetime.utcnow() < expires_dt - timedelta(seconds=RENEW_BEFORE_SECONDS):
                        self._cached_token = token
                        self._cached_expires_at = expires_dt
                        return token  # ainda válido

                refresh_token = await self._get_config(db, "ml_refresh_token")

                if token and not refresh_token:
                    # Primeira execução: token veio do .env e ainda não há
                    # refresh_token configurado. Usa esse token assumindo
                    # que foi gerado recentemente (válido por ~6h) e registra
                    # a expiração para não cair aqui de novo a cada chamada.
                    expires_at_dt = datetime.utcnow() + timedelta(hours=6)
                    await self._set_config(db, "ml_access_token", token)
                    await self._set_config(db, "ml_token_expires_at", expires_at_dt.isoformat())
                    await db.commit()
                    logger.warning(
                        "[ML Token] Usando access_token do .env sem refresh_token "
                        "configurado. Configure ML_REFRESH_TOKEN para renovação automática."
                    )
                    self._cached_token = token
                    self._cached_expires_at = expires_at_dt
                    return token

                logger.info("[ML Token] Renovando access token...")
                new_token = await self._refresh(db)
                self._cached_token = new_token
                self._cached_expires_at = datetime.utcnow() + timedelta(hours=6)
                return new_token

    async def _refresh(self, db) -> str:
        refresh_token = await self._get_config(db, "ml_refresh_token")
        if not refresh_token:
            raise RuntimeError(
                "ml_refresh_token não encontrado no banco. "
                "Execute o fluxo OAuth inicial e salve o refresh_token."
            )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                ML_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.ML_APP_ID,
                    "client_secret": settings.ML_SECRET_KEY,
                    "refresh_token": refresh_token,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Falha ao renovar token ML: {resp.status} — {body}")
                data = await resp.json()

        new_access = data["access_token"]
        new_refresh = data.get("refresh_token", refresh_token)
        expires_in = data.get("expires_in", 21600)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        await self._set_config(db, "ml_access_token", new_access)
        await self._set_config(db, "ml_refresh_token", new_refresh)
        await self._set_config(db, "ml_token_expires_at", expires_at)
        await db.commit()

        logger.info(f"[ML Token] Renovado com sucesso. Expira em {expires_in}s ({expires_at})")
        return new_access

    @staticmethod
    async def _get_config(db, key: str) -> str | None:
        row = (
            await db.execute(select(Configuration).where(Configuration.key == key))
        ).scalar_one_or_none()
        if row:
            v = row.value
            return v if isinstance(v, str) else str(v)
        # fallback para .env (primeira execução)
        if key == "ml_access_token":
            return settings.ML_ACCESS_TOKEN or None
        if key == "ml_refresh_token":
            return settings.ML_REFRESH_TOKEN or None
        return None

    @staticmethod
    async def _set_config(db, key: str, value: str):
        row = (
            await db.execute(select(Configuration).where(Configuration.key == key))
        ).scalar_one_or_none()
        if row:
            row.value = value
        else:
            db.add(Configuration(key=key, value=value))


# Instância singleton
token_manager = MLTokenManager()


async def get_ml_token() -> str:
    """Atalho para uso nos scrapers."""
    return await token_manager.get_valid_token()
