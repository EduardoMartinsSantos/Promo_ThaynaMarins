from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Robo-Promo"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/robopromo"

    # Redis (Celery broker + cache)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Mercado Livre
    ML_APP_ID: str = ""
    ML_SECRET_KEY: str = ""
    ML_ACCESS_TOKEN: str = ""
    ML_REFRESH_TOKEN: str = ""
    ML_AFFILIATE_ID: str = ""         # seu publisher_id
    ML_AFFILIATE_TAG: str = ""        # tag de rastreio customizada

    # Shopee Affiliate Open API (GraphQL) — https://affiliate.shopee.com.br/open_api/home
    SHOPEE_APP_ID: str = ""
    SHOPEE_SECRET_KEY: str = ""

    # Filtros padrão
    MIN_DISCOUNT_PERCENT: float = 30.0
    MIN_SAVINGS_BRL: float = 50.0
    MIN_RATING: float = 3.5
    REQUIRE_COUPON: bool = False       # True = só posta se tiver cupom

    # Anti-spam (horas antes de poder repostar o mesmo produto)
    REPOST_COOLDOWN_HOURS: int = 24
    # Repostar se o preço baixou mais que X%
    SIGNIFICANT_PRICE_DROP_PCT: float = 10.0

    # WhatsApp / Evolution API
    EVOLUTION_API_URL: str = ""
    EVOLUTION_API_KEY: str = ""
    EVOLUTION_INSTANCE: str = ""

    # Canais de destino  [ {"id": "120363...", "type": "group"} ]
    WHATSAPP_CHANNELS: List[dict] = []

    # Scraper
    SCRAPER_INTERVAL_SECONDS: int = 300   # 5 minutos
    SCRAPER_CONCURRENCY: int = 10

    # Limite de mensagens enviadas por canal a cada ciclo (prioriza maior desconto)
    MAX_PROMOTIONS_PER_CYCLE: int = 15
    REQUEST_TIMEOUT: int = 15
    USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
