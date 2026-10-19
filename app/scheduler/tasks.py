import asyncio
from app.scheduler.celery_app import celery
from app.core.logger import get_logger

logger = get_logger("scheduler.tasks")


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def check_promotions(self):
    try:
        from app.scheduler.worker import run
        run()
    except Exception as exc:
        logger.error(f"Tarefa falhou: {exc}")
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=2, default_retry_delay=120)
def refresh_ml_token(self):
    """Renova proativamente o Access Token do ML antes de expirar."""
    try:
        from app.affiliate.ml_token import token_manager

        async def _run():
            async with __import__("app.database.connection", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
                await token_manager._refresh(db)

        asyncio.run(_run())
        logger.info("[ML Token] Renovação preventiva concluída")
    except Exception as exc:
        logger.error(f"[ML Token] Falha na renovação preventiva: {exc}")
        raise self.retry(exc=exc)
