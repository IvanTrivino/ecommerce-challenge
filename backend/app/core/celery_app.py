from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
    # Don't lose tasks if a worker dies mid-execution
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# Celery Beat schedule. Run exactly ONE beat instance.
celery_app.conf.beat_schedule = {
    "heartbeat-every-minute": {
        "task": "app.tasks.heartbeat",
        "schedule": crontab(minute="*"),
    },
}
