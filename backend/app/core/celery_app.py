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
    "sweep-product-images-daily": {
        "task": "app.tasks.sweep_product_images",
        "schedule": crontab(hour=3, minute=30),
    },
    "sweep-product-import-files-daily": {
        "task": "app.tasks.sweep_product_import_files",
        "schedule": crontab(hour=3, minute=45),
    },
    "reap-stale-product-imports": {
        "task": "app.tasks.reap_stale_product_imports",
        "schedule": crontab(minute="*/5"),
    },
    "requeue-order-notifications": {
        "task": "app.tasks.requeue_order_notifications",
        "schedule": crontab(minute="*"),
    },
}
