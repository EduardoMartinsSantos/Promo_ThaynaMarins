from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "robopromo",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.scheduler.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    beat_schedule={
        "check-promotions": {
            "task": "app.scheduler.tasks.check_promotions",
            "schedule": settings.SCRAPER_INTERVAL_SECONDS,
        },
        # Renova o token com 1h de antecedência (token dura 6h)
        "refresh-ml-token": {
            "task": "app.scheduler.tasks.refresh_ml_token",
            "schedule": 5 * 60 * 60,  # a cada 5 horas
        },
    },
)
