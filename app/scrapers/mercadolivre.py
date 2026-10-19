"""
Scraper para o Mercado Livre — usa a API oficial.

IMPORTANTE — restrições da API (validadas em 2026):
- `/sites/MLB/search` está bloqueado (403) para a maioria dos apps.
- `/items/{id}` só funciona para itens do PRÓPRIO vendedor (403 access_denied
  para itens de terceiros).
- `/highlights/MLB/category/{id}` funciona e retorna catalog_product_ids.
- `/products/{id}` funciona e retorna nome + imagens do catálogo.
- `/products/{id}/items` funciona e retorna os itens vendáveis com
  price/original_price/seller_id — esta é a fonte de preços.

Fluxo:
  highlights(categoria) -> catalog_product_ids
    -> products/{id}            (nome, imagem, domain_id)
    -> products/{id}/items       (item_id, price, original_price)
    -> RawPromotion

Link do produto é construído como:
  https://produto.mercadolivre.com.br/MLB-{item_id_numero}
(formato reconhecido pelo ML; o redirect de "verificação" só ocorre
para requests automatizados sem sessão de navegador — não afeta
cliques de usuários reais vindos do WhatsApp).
"""
import asyncio
from decimal import Decimal
from typing import List, Optional
from app.core.config import settings
from app.core.logger import get_logger
from app.scrapers.base import BaseScraper, RawPromotion
from app.affiliate.ml_token import get_ml_token

logger = get_logger("scraper.mercadolivre")

ML_API = "https://api.mercadolibre.com"

# Categorias monitoradas — validadas em 2026 via /categories/{id}
# (nomes corretos confirmados; lista expandida de 5 para 18 categorias
# para aumentar o volume de promoções capturadas por ciclo)
MONITORED_CATEGORIES = [
    "MLB1051",   # Celulares e Telefones
    "MLB1648",   # Informática
    "MLB1000",   # Eletrônicos, Áudio e Vídeo
    "MLB1574",   # Casa, Móveis e Decoração
    "MLB1246",   # Beleza e Cuidado Pessoal
    "MLB1132",   # Brinquedos e Hobbies
    "MLB1430",   # Calçados, Roupas e Bolsas
    "MLB1196",   # Livros, Revistas e Comics
    "MLB1168",   # Música, Filmes e Seriados
    "MLB1071",   # Pet Shop
    "MLB1499",   # Indústria e Comércio
    "MLB1403",   # Alimentos e Bebidas
    "MLB5726",   # Eletrodomésticos
    "MLB1182",   # Instrumentos Musicais
    "MLB3937",   # Joias e Relógios
    "MLB1039",   # Câmeras e Acessórios
    "MLB1144",   # Games
    "MLB1276",   # Esportes e Fitness
]

# A API limita o /highlights a ~20 itens por categoria, independente do limit.
HIGHLIGHTS_LIMIT = 20


class MercadoLivreScraper(BaseScraper):
    source = "mercadolivre"

    async def _get_token_header(self) -> dict:
        token = await get_ml_token()
        return {"Authorization": f"Bearer {token}"}

    async def fetch_promotions(self) -> List[RawPromotion]:
        results: List[RawPromotion] = []
        # Semáforo global: limita o total de chamadas simultâneas a
        # /products/{id} e /products/{id}/items entre todas as categorias.
        sem = asyncio.Semaphore(settings.SCRAPER_CONCURRENCY)
        tasks = [self._fetch_category(cat, sem) for cat in MONITORED_CATEGORIES]
        batches = await asyncio.gather(*tasks, return_exceptions=True)
        for batch, cat in zip(batches, MONITORED_CATEGORIES):
            if isinstance(batch, Exception):
                logger.error(f"[ML] categoria {cat}: {batch}")
                continue
            results.extend(batch)
        logger.info(f"[ML] {len(results)} promoções capturadas no total")
        return results

    async def _fetch_category(self, category_id: str, sem: asyncio.Semaphore) -> List[RawPromotion]:
        headers = await self._get_token_header()
        url = f"{ML_API}/highlights/MLB/category/{category_id}?limit={HIGHLIGHTS_LIMIT}"
        data = await self._get(url, headers=headers)

        product_ids = [
            item["id"] for item in data.get("content", [])
            if item.get("type") == "PRODUCT"
        ]
        if not product_ids:
            return []

        tasks = [self._fetch_product(pid, sem) for pid in product_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        promos = []
        for r in results:
            if isinstance(r, RawPromotion):
                promos.append(r)
            elif isinstance(r, Exception):
                logger.debug(f"[ML] erro ao processar produto: {r}")
        return promos

    async def _fetch_product(self, product_id: str, sem: asyncio.Semaphore) -> Optional[RawPromotion]:
        async with sem:
            headers = await self._get_token_header()
            try:
                product = await self._get(f"{ML_API}/products/{product_id}", headers=headers)
                items_data = await self._get(f"{ML_API}/products/{product_id}/items", headers=headers)
            except Exception as e:
                logger.debug(f"[ML] produto {product_id}: {e}")
                return None

            best_item = self._pick_best_item(items_data.get("results", []))
            if not best_item:
                return None

            return self._build_promotion(product, best_item)

    @staticmethod
    def _pick_best_item(items: list) -> Optional[dict]:
        """Escolhe o item com maior desconto absoluto entre os vendáveis."""
        candidates = []
        for item in items:
            original = item.get("original_price")
            current = item.get("price")
            if original and current and original > current:
                candidates.append((original - current, item))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _build_promotion(self, product: dict, item: dict) -> Optional[RawPromotion]:
        original = item.get("original_price")
        current = item.get("price")
        if not original or not current or original <= current:
            return None

        original_d = Decimal(str(original))
        current_d = Decimal(str(current))
        discount = ((original_d - current_d) / original_d * 100).quantize(Decimal("0.01"))

        item_id = item["item_id"]  # ex: MLB4587377807
        permalink = f"https://produto.mercadolivre.com.br/{item_id[:3]}-{item_id[3:]}"

        pictures = product.get("pictures") or []
        image_url = pictures[0]["url"] if pictures else ""

        return RawPromotion(
            source=self.source,
            external_id=item_id,
            name=product.get("name", ""),
            original_price=original_d,
            promotional_price=current_d,
            discount_percent=discount,
            image_url=image_url,
            original_url=permalink,
            category=item.get("category_id") or product.get("domain_id", ""),
            seller=str(item.get("seller_id", "")),
            rating=None,
            rating_count=0,
            coupons=[],
        )
