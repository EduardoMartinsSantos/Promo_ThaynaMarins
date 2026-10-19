from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional
import random
import asyncio
import aiohttp
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("scraper.base")


@dataclass
class RawPromotion:
    """Estrutura genérica — funciona para ML, Shopee, Amazon, etc."""
    source: str
    external_id: str
    name: str
    original_price: Decimal
    promotional_price: Decimal
    discount_percent: Decimal
    image_url: str
    original_url: str
    category: str = ""
    seller: str = ""
    rating: Optional[Decimal] = None
    rating_count: int = 0
    coupons: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def savings(self) -> Decimal:
        return self.original_price - self.promotional_price


class BaseScraper(ABC):
    source: str = "unknown"

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT),
            headers={"User-Agent": random.choice(settings.USER_AGENTS)},
        )
        return self

    async def __aexit__(self, *_):
        if self._session:
            await self._session.close()

    async def _get(self, url: str, **kwargs) -> dict:
        """GET com retry e back-off exponencial."""
        for attempt in range(3):
            try:
                async with self._session.get(url, **kwargs) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"[{self.source}] GET {url} falhou ({e}) — retry em {wait}s")
                await asyncio.sleep(wait)
        raise RuntimeError(f"[{self.source}] Falha após 3 tentativas: {url}")

    @abstractmethod
    async def fetch_promotions(self) -> List[RawPromotion]:
        """Retorna lista de promoções brutas."""
        ...
