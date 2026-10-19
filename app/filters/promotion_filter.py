"""
Filtro inteligente de promoções.
Todas as regras são configuráveis via tabela `configurations` ou .env.
"""
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import SentMessage, Promotion, Product
from app.scrapers.base import RawPromotion

logger = get_logger("filter")


@dataclass
class FilterResult:
    approved: bool
    reason: str


class PromotionFilter:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(self, promo: RawPromotion, channel_id: str) -> FilterResult:
        checks = [
            self._check_discount(promo),
            self._check_savings(promo),
            self._check_rating(promo),
            await self._check_already_sent(promo, channel_id),
        ]
        for result in checks:
            if not result.approved:
                logger.info(
                    f"[FILTRO] REJEITADO '{promo.name[:50]}' | motivo: {result.reason}"
                )
                return result

        logger.info(f"[FILTRO] APROVADO '{promo.name[:50]}'")
        return FilterResult(approved=True, reason="ok")

    def _check_discount(self, promo: RawPromotion) -> FilterResult:
        min_pct = Decimal(str(settings.MIN_DISCOUNT_PERCENT))
        if promo.discount_percent < min_pct:
            return FilterResult(
                False,
                f"desconto {promo.discount_percent}% < mínimo {min_pct}%"
            )
        if settings.REQUIRE_COUPON and not promo.coupons:
            return FilterResult(False, "cupom obrigatório não encontrado")
        return FilterResult(True, "ok")

    def _check_savings(self, promo: RawPromotion) -> FilterResult:
        min_savings = Decimal(str(settings.MIN_SAVINGS_BRL))
        if promo.savings < min_savings:
            return FilterResult(
                False,
                f"economia R${promo.savings:.2f} < mínimo R${min_savings:.2f}"
            )
        return FilterResult(True, "ok")

    def _check_rating(self, promo: RawPromotion) -> FilterResult:
        if promo.rating and promo.rating > 0:
            min_rating = Decimal(str(settings.MIN_RATING))
            if promo.rating < min_rating:
                return FilterResult(
                    False,
                    f"nota {promo.rating} < mínimo {min_rating}"
                )
        return FilterResult(True, "ok")

    async def _check_already_sent(self, promo: RawPromotion, channel_id: str) -> FilterResult:
        """
        Bloqueia repostagem se:
        - Enviado para o mesmo canal nas últimas REPOST_COOLDOWN_HOURS, E
        - O preço não caiu mais que SIGNIFICANT_PRICE_DROP_PCT
        """
        cooldown = timedelta(hours=settings.REPOST_COOLDOWN_HOURS)
        since = datetime.utcnow() - cooldown

        stmt = (
            select(SentMessage, Promotion)
            .join(Promotion, SentMessage.promotion_id == Promotion.id)
            .join(Product, Promotion.product_id == Product.id)
            .where(
                and_(
                    Product.external_id == promo.external_id,
                    SentMessage.channel_id == channel_id,
                    SentMessage.sent_at >= since,
                )
            )
            .order_by(SentMessage.sent_at.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).first()
        if not row:
            return FilterResult(True, "ok")

        _, last_promo = row
        last_price = last_promo.promotional_price
        drop_threshold = Decimal(str(settings.SIGNIFICANT_PRICE_DROP_PCT)) / 100
        price_dropped_enough = (
            (last_price - promo.promotional_price) / last_price
        ) >= drop_threshold

        if price_dropped_enough:
            return FilterResult(True, "preço caiu significativamente, repostagem permitida")

        return FilterResult(
            False,
            f"já enviado em {cooldown} horas sem queda significativa de preço"
        )
