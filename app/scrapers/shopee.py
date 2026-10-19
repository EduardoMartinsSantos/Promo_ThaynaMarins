"""
Scraper para a Shopee — usa a Shopee Affiliate Open API (GraphQL).

Documentação oficial (exige login de afiliado aprovado):
https://affiliate.shopee.com.br/open_api/home

Autenticação: assinatura SHA256 simples (não HMAC) sobre a concatenação
`app_id + timestamp + payload + secret`, enviada no header Authorization:
  Authorization: SHA256 Credential={app_id}, Timestamp={ts}, Signature={sig}

A query `productOfferV2` não expõe um campo "originalPrice" — apenas
`priceMin`/`priceMax` (faixa de preço atual entre variações) e
`priceDiscountRate` (percentual de desconto já calculado pela Shopee).
O preço "original" é derivado a partir desses dois campos.

Sem categorias numéricas (productCatId) confirmadas publicamente, a busca
é feita por palavra-chave (`keyword`), replicando os mesmos nichos gerais
já monitorados no Mercado Livre.
"""
import asyncio
import hashlib
import json
import time
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.scrapers.base import BaseScraper, RawPromotion

logger = get_logger("scraper.shopee")

SHOPEE_GRAPHQL_URL = "https://open-api.affiliate.shopee.com.br/graphql"

# Nichos gerais — mesmas categorias já monitoradas no mercadolivre.py,
# adaptadas para busca por palavra-chave (Shopee não expõe category id
# na API de afiliados sem documentação logada).
MONITORED_KEYWORDS = [
    "celular",              # Celulares e Telefones
    "notebook",             # Informática
    "eletronicos",          # Eletrônicos, Áudio e Vídeo
    "casa e decoracao",     # Casa, Móveis e Decoração
    "beleza",               # Beleza e Cuidado Pessoal
    "brinquedos",           # Brinquedos e Hobbies
    "roupas",               # Calçados, Roupas e Bolsas
    "calcados",             # Calçados, Roupas e Bolsas
    "livros",               # Livros, Revistas e Comics
    "fones de ouvido",      # Música, Filmes e Seriados
    "pet shop",             # Pet Shop
    "ferramentas",          # Indústria e Comércio
    "suplementos",          # Alimentos e Bebidas
    "eletrodomesticos",     # Eletrodomésticos
    "instrumentos musicais",# Instrumentos Musicais
    "relogio",              # Joias e Relógios
    "camera",               # Câmeras e Acessórios
    "games",                # Games
    "fitness",              # Esportes e Fitness
]

OFFER_LIMIT = 20
SORT_TYPE_COMMISSION_DESC = 5

_FIELDS = (
    "itemId productName priceMin priceMax priceDiscountRate imageUrl "
    "productLink offerLink shopName ratingStar sales commissionRate "
    "periodEndTime"
)


class ShopeeScraper(BaseScraper):
    source = "shopee"

    def _sign(self, payload: str) -> dict:
        timestamp = int(time.time())
        sign_factor = f"{settings.SHOPEE_APP_ID}{timestamp}{payload}{settings.SHOPEE_SECRET_KEY}"
        signature = hashlib.sha256(sign_factor.encode()).hexdigest()
        return {
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={settings.SHOPEE_APP_ID}, "
                f"Timestamp={timestamp}, Signature={signature}"
            ),
        }

    async def _query_offers(self, keyword: str) -> List[dict]:
        """POST à API GraphQL com retry e back-off exponencial (mesmo padrão de BaseScraper._get)."""
        query = (
            "query { productOfferV2("
            f'keyword:"{keyword}",sortType:{SORT_TYPE_COMMISSION_DESC},'
            f"limit:{OFFER_LIMIT},page:1"
            f") {{ nodes {{ {_FIELDS} }} }} }}"
        )
        payload = json.dumps({"query": query})

        for attempt in range(3):
            try:
                headers = self._sign(payload)
                async with self._session.post(SHOPEE_GRAPHQL_URL, data=payload, headers=headers) as resp:
                    body = await resp.json()
                    if resp.status == 200 and "data" in body:
                        return body["data"]["productOfferV2"]["nodes"]
                    raise RuntimeError(body.get("errors", body))
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"[shopee] query '{keyword}' falhou ({e}) — retry em {wait}s")
                await asyncio.sleep(wait)
        raise RuntimeError(f"[shopee] Falha após 3 tentativas: keyword='{keyword}'")

    async def fetch_promotions(self) -> List[RawPromotion]:
        sem = asyncio.Semaphore(settings.SCRAPER_CONCURRENCY)
        tasks = [self._fetch_keyword(kw, sem) for kw in MONITORED_KEYWORDS]
        batches = await asyncio.gather(*tasks, return_exceptions=True)

        seen_ids: set[str] = set()
        results: List[RawPromotion] = []
        for batch, kw in zip(batches, MONITORED_KEYWORDS):
            if isinstance(batch, Exception):
                logger.error(f"[shopee] keyword '{kw}': {batch}")
                continue
            for promo in batch:
                if promo.external_id not in seen_ids:
                    seen_ids.add(promo.external_id)
                    results.append(promo)

        logger.info(f"[shopee] {len(results)} promoções capturadas no total")
        return results

    async def _fetch_keyword(self, keyword: str, sem: asyncio.Semaphore) -> List[RawPromotion]:
        async with sem:
            nodes = await self._query_offers(keyword)
        promos = []
        for node in nodes:
            promo = self._build_promotion(node, keyword)
            if promo:
                promos.append(promo)
        return promos

    @staticmethod
    def _parse_discount_percent(raw) -> Optional[Decimal]:
        if raw in (None, ""):
            return None
        try:
            value = Decimal(str(raw).strip().rstrip("%"))
        except InvalidOperation:
            return None
        if value <= 0:
            return None
        # A API retorna o percentual já como número "cheio" (ex.: 35 = 35%),
        # mas alguns retornos vêm como fração (0.35) — normaliza para 0-100.
        if value <= 1:
            value *= 100
        return value

    def _build_promotion(self, node: dict, keyword: str) -> Optional[RawPromotion]:
        item_id = node.get("itemId")
        price_min = node.get("priceMin")
        if not item_id or not price_min:
            return None

        discount = self._parse_discount_percent(node.get("priceDiscountRate"))
        if not discount:
            return None

        try:
            promotional = Decimal(str(price_min))
        except InvalidOperation:
            return None

        discount = discount.quantize(Decimal("0.01"))
        original = (promotional / (1 - discount / 100)).quantize(Decimal("0.01"))
        if original <= promotional:
            return None

        offer_link = node.get("offerLink") or node.get("productLink") or ""
        if not offer_link:
            return None

        rating = node.get("ratingStar")
        return RawPromotion(
            source=self.source,
            external_id=str(item_id),
            name=node.get("productName", ""),
            original_price=original,
            promotional_price=promotional,
            discount_percent=discount,
            image_url=node.get("imageUrl", ""),
            original_url=offer_link,
            category=keyword,
            seller=node.get("shopName", ""),
            rating=Decimal(str(rating)) if rating else None,
            rating_count=0,
            coupons=[],
            extra={
                "sales": node.get("sales"),
                "commission_rate": node.get("commissionRate"),
                "period_end_time": node.get("periodEndTime"),
            },
        )
