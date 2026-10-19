"""
Worker principal — orquestra scraping → filtragem → envio.
Executado pelo Celery beat a cada SCRAPER_INTERVAL_SECONDS.
"""
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.database.connection import AsyncSessionLocal
from app.database.models import Product, Promotion, Coupon, SentMessage
from app.scrapers.mercadolivre import MercadoLivreScraper
from app.scrapers.shopee import ShopeeScraper
from app.scrapers.coupon_scraper import get_general_coupon, coupon_for_promotion
from app.core.bot_state import is_bot_enabled, is_source_enabled
from app.scrapers.base import RawPromotion
from app.affiliate.manager import get_affiliate_link
from app.filters.promotion_filter import PromotionFilter
from app.whatsapp.evolution_client import EvolutionAPIClient
from app.whatsapp.formatter import format_promotion_message

logger = get_logger("scheduler.worker")


SCRAPER_CLASSES = (MercadoLivreScraper, ShopeeScraper)


async def run_cycle(dry_run: bool = False):
    async with AsyncSessionLocal() as db:
        if not await is_bot_enabled(db):
            logger.info("Robo desligado — ciclo ignorado.")
            return
        enabled_scrapers = [
            cls for cls in SCRAPER_CLASSES
            if await is_source_enabled(db, cls.source)
        ]

    if not enabled_scrapers:
        logger.info("Nenhuma loja habilitada — ciclo ignorado.")
        return

    logger.info("=== Iniciando ciclo de verificação ===")

    async def _run_scraper(scraper_cls):
        async with scraper_cls() as scraper:
            return await scraper.fetch_promotions()

    batches = await asyncio.gather(
        *[_run_scraper(cls) for cls in enabled_scrapers],
        return_exceptions=True,
    )
    promotions: List[RawPromotion] = []
    for batch, scraper_cls in zip(batches, enabled_scrapers):
        if isinstance(batch, Exception):
            logger.error(f"[{scraper_cls.source}] falha no scraper: {batch}")
            continue
        promotions.extend(batch)

    async with AsyncSessionLocal() as db:
        wa_client = EvolutionAPIClient()
        channels = settings.WHATSAPP_CHANNELS
        general_coupon = await get_general_coupon(db)

        for channel in channels:
            channel_id = channel["id"]
            filt = PromotionFilter(db)

            approved: List[RawPromotion] = []
            for promo in promotions:
                result = await filt.evaluate(promo, channel_id)
                if result.approved:
                    approved.append(promo)

            # Prioriza os maiores descontos e limita o volume por ciclo
            approved.sort(key=lambda p: p.discount_percent, reverse=True)
            approved = approved[: settings.MAX_PROMOTIONS_PER_CYCLE]

            for promo in approved:
                affiliate_url = get_affiliate_link(promo.source, promo.original_url)
                coupon = coupon_for_promotion(general_coupon, promo.promotional_price)
                message = format_promotion_message(promo, affiliate_url, coupon)

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Mensagem que seria enviada para {channel_id}:\n"
                        f"{message}\nImagem: {promo.image_url}\n"
                    )
                    continue

                sent = await wa_client.send_image_with_caption(
                    channel_id=channel_id,
                    image_url=promo.image_url,
                    caption=message,
                )

                if sent:
                    await _persist(db, promo, affiliate_url, channel_id, coupon)
                    await asyncio.sleep(3)  # intervalo entre envios anti-spam

        await db.commit()

    logger.info("=== Ciclo concluído ===")


async def _persist(
    db: AsyncSession,
    promo: RawPromotion,
    affiliate_url: str,
    channel_id: str,
    coupon: str | None,
):
    from sqlalchemy import select
    # Upsert product
    result = await db.execute(
        select(Product).where(Product.external_id == promo.external_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        product = Product(
            external_id=promo.external_id,
            source=promo.source,
            name=promo.name,
            category=promo.category,
            seller=promo.seller,
            rating=promo.rating,
            rating_count=promo.rating_count,
            image_url=promo.image_url,
            original_url=promo.original_url,
        )
        db.add(product)
        await db.flush()

    promotion = Promotion(
        product_id=product.id,
        original_price=promo.original_price,
        promotional_price=promo.promotional_price,
        discount_percent=promo.discount_percent,
        savings_amount=promo.savings,
        affiliate_url=affiliate_url,
    )
    db.add(promotion)
    await db.flush()

    if coupon:
        db.add(Coupon(promotion_id=promotion.id, code=coupon))

    db.add(SentMessage(
        promotion_id=promotion.id,
        channel_id=channel_id,
        price_at_send=promo.promotional_price,
        affiliate_url=affiliate_url,
    ))


# Entry point para Celery task
def run():
    asyncio.run(run_cycle())
