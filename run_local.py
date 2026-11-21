"""
Executa o robô localmente, sem Celery/Redis/Docker.
Roda o ciclo de verificação em loop, no intervalo configurado em
SCRAPER_INTERVAL_SECONDS (.env).

Uso:
    python run_local.py            # loop contínuo (24h)
    python run_local.py --once     # executa um único ciclo e sai
"""
import asyncio
import sys
from app.core.config import settings, reload_settings
from app.core.logger import get_logger
from app.scheduler.worker import run_cycle

logger = get_logger("run_local")


async def main():
    once = "--once" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if once:
        await run_cycle(dry_run=dry_run)
        return

    logger.info(
        f"Iniciando loop contínuo — verificando a cada "
        f"{settings.SCRAPER_INTERVAL_SECONDS}s. Ctrl+C para parar."
    )
    while True:
        try:
            # Aplica grupos/filtros/credenciais salvos pelo painel desde o último ciclo.
            reload_settings()
            await run_cycle(dry_run=dry_run)
        except Exception:
            logger.exception("Erro no ciclo — continuando no próximo intervalo")

        await asyncio.sleep(settings.SCRAPER_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuário.")
