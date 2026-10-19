"""
Gerenciador de links de afiliado.
Extensível: adicione novos providers implementando AffiliateProvider.
"""
from abc import ABC, abstractmethod
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("affiliate")


class AffiliateProvider(ABC):
    source: str = ""

    @abstractmethod
    def build_link(self, original_url: str) -> str: ...


class MercadoLivreAffiliate(AffiliateProvider):
    source = "mercadolivre"

    def build_link(self, original_url: str) -> str:
        """
        Formato oficial ML Afiliados:
        https://www.mercadolivre.com.br/...?matt_tool=<TOOL_ID>&matt_word=&matt_source=<SOURCE>

        Ou via link curto:
        https://mercadolivre.com/sec/XXXXXXX  (gerado pela API de afiliados)

        Aqui usamos o método de query string (sem necessidade de API call extra).
        """
        sep = "&" if "?" in original_url else "?"
        return (
            f"{original_url}{sep}"
            f"matt_tool={settings.ML_AFFILIATE_ID}"
            f"&matt_word={settings.ML_AFFILIATE_TAG}"
            f"&matt_source=robopromo"
        )


class AmazonAffiliate(AffiliateProvider):
    source = "amazon"

    def build_link(self, original_url: str) -> str:
        sep = "&" if "?" in original_url else "?"
        return f"{original_url}{sep}tag={settings.ML_AFFILIATE_ID}"


class ShopeeAffiliate(AffiliateProvider):
    source = "shopee"

    def build_link(self, original_url: str) -> str:
        """
        A Shopee Affiliate Open API já retorna o `offerLink` pronto
        (rastreado para o SHOPEE_APP_ID configurado) — ao contrário do ML,
        não há query string pra montar aqui. O ShopeeScraper já grava o
        offerLink em `original_url`, então só repassamos.
        """
        return original_url


# Registro central de providers — adicione novos aqui
_PROVIDERS: dict[str, AffiliateProvider] = {
    "mercadolivre": MercadoLivreAffiliate(),
    "amazon": AmazonAffiliate(),
    "shopee": ShopeeAffiliate(),
}


def get_affiliate_link(source: str, original_url: str) -> str:
    provider = _PROVIDERS.get(source)
    if not provider:
        logger.warning(f"Nenhum provider de afiliado para source='{source}', retornando URL original")
        return original_url
    link = provider.build_link(original_url)
    logger.debug(f"[{source}] afiliado gerado: {link}")
    return link
