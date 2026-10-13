import logging

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def heartbeat() -> str:
    """Example periodic task scheduled by Celery Beat."""
    logger.info("celery beat heartbeat")
    return "ok"
