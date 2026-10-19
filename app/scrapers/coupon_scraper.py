"""
Cupons de desconto.

A API oficial do Mercado Livre não expõe cupons por produto para apps
afiliados:
- `/items/{id}/promotions` retorna 404 (endpoint não existe para este app).
- `/products/{id}` e `/products/{id}/items` não trazem campos de cupom
  (deal_ids sempre vazio).
- A página HTML do produto redireciona para verificação anti-bot em
  requests automatizados, impedindo o parse.

Captura automática por produto não é viável. Em vez disso, este módulo
gerencia um "cupom geral" configurável (tabela `configurations`, chave
`general_coupon`), aplicado às promoções enviadas quando o valor mínimo
de compra é atingido. É configurável via dashboard:
  PUT /api/config/general_coupon
  { "value": { "code": "CUPOM10", "min_purchase": 100, "active": true } }
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.database.models import Configuration

logger = get_logger("scraper.coupon")

CONFIG_KEY = "general_coupon"


async def get_general_coupon(db: AsyncSession) -> Optional[dict]:
    """Lê o cupom geral configurado, se houver e estiver ativo."""
    row = (
        await db.execute(select(Configuration).where(Configuration.key == CONFIG_KEY))
    ).scalar_one_or_none()
    if not row or not row.value:
        return None

    cfg = row.value
    if not cfg.get("active", True) or not cfg.get("code"):
        return None
    return cfg


def coupon_for_promotion(general_coupon: Optional[dict], promo_price: Decimal) -> Optional[str]:
    """Retorna o código do cupom geral se a promoção atingir o valor mínimo."""
    if not general_coupon:
        return None

    min_purchase = Decimal(str(general_coupon.get("min_purchase", 0)))
    if promo_price < min_purchase:
        return None

    return str(general_coupon["code"]).upper()
