from decimal import Decimal
from typing import Optional
from app.scrapers.base import RawPromotion


def _brl(value: Decimal) -> str:
    """Formata um valor decimal como moeda brasileira: 1.234,56."""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_promotion_message(
    promo: RawPromotion,
    affiliate_url: str,
    coupon: Optional[str] = None,
) -> str:
    coupon_line = f"\n🎟 Cupom: *{coupon}*\n" if coupon else ""
    savings = promo.original_price - promo.promotional_price

    return (
        f"🔥 *PROMOÇÃO IMPERDÍVEL* 🔥\n\n"
        f"*{promo.name}*\n\n"
        f"💰 De: ~~R$ {_brl(promo.original_price)}~~\n"
        f"🔥 Por: *R$ {_brl(promo.promotional_price)}*\n"
        f"💵 Economia: *R$ {_brl(savings)}*"
        f"{coupon_line}\n"
        f"📉 Desconto: *{promo.discount_percent:.0f}%*\n\n"
        f"🔗 Link:\n{affiliate_url}\n\n"
        f"⏰ _Promoção sujeita a alteração sem aviso prévio_"
    )
