"""
Liga/desliga geral do robô — mesmo padrão de app/scrapers/coupon_scraper.py
(valor guardado na tabela `configurations`, lido a cada ciclo do worker).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Configuration

CONFIG_KEY = "bot_enabled"
SOURCE_KEY_PREFIX = "source_enabled_"


async def is_bot_enabled(db: AsyncSession) -> bool:
    row = (await db.execute(
        select(Configuration).where(Configuration.key == CONFIG_KEY)
    )).scalar_one_or_none()
    if row is None:
        return True  # padrão: ligado, se nunca configurado
    return bool(row.value)


async def set_bot_enabled(db: AsyncSession, enabled: bool) -> None:
    row = (await db.execute(
        select(Configuration).where(Configuration.key == CONFIG_KEY)
    )).scalar_one_or_none()
    if row:
        row.value = enabled
    else:
        db.add(Configuration(key=CONFIG_KEY, value=enabled, description="Liga/desliga geral do robô"))
    await db.commit()


async def is_source_enabled(db: AsyncSession, source: str) -> bool:
    row = (await db.execute(
        select(Configuration).where(Configuration.key == f"{SOURCE_KEY_PREFIX}{source}")
    )).scalar_one_or_none()
    if row is None:
        return True  # padrão: ligado, se nunca configurado
    return bool(row.value)


async def set_source_enabled(db: AsyncSession, source: str, enabled: bool) -> None:
    key = f"{SOURCE_KEY_PREFIX}{source}"
    row = (await db.execute(
        select(Configuration).where(Configuration.key == key)
    )).scalar_one_or_none()
    if row:
        row.value = enabled
    else:
        db.add(Configuration(key=key, value=enabled, description=f"Liga/desliga loja {source}"))
    await db.commit()
