"""
Cria as tabelas no banco configurado em DATABASE_URL.
Funciona com SQLite (local) e PostgreSQL (produção).

Uso:
    python init_db.py
"""
import asyncio
from app.database.connection import engine
from app.database.models import Base, Configuration
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal

DEFAULT_CONFIG = {
    "min_discount_percent": 30,
    "min_savings_brl": 50,
    "min_rating": 3.5,
    "require_coupon": False,
    "repost_cooldown_hours": 24,
    "price_drop_threshold": 10,
}


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] Tabelas criadas.")

    async with AsyncSessionLocal() as db:
        for key, value in DEFAULT_CONFIG.items():
            row = (await db.execute(
                select(Configuration).where(Configuration.key == key)
            )).scalar_one_or_none()
            if not row:
                db.add(Configuration(key=key, value=value))
        await db.commit()
    print("[OK] Configuracoes padrao inseridas.")


if __name__ == "__main__":
    asyncio.run(main())
