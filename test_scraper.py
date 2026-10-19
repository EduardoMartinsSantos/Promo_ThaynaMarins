"""
Teste rápido: valida token ML e mostra promoções capturadas.
Não envia nada para WhatsApp.

Uso:
    python test_scraper.py
"""
import asyncio
from app.scrapers.mercadolivre import MercadoLivreScraper


async def main():
    async with MercadoLivreScraper() as scraper:
        promos = await scraper.fetch_promotions()

    print(f"\nTotal de promocoes capturadas: {len(promos)}\n")
    for p in promos[:10]:
        print(f"- {p.name[:60]}")
        print(f"    De R$ {p.original_price} por R$ {p.promotional_price} "
              f"({p.discount_percent}% off)")
        print(f"    {p.original_url}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
