import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.db import engine
from app.repositories import ProductRepository
from app.services import ProductImageService

logger = logging.getLogger(__name__)


@celery_app.task
def heartbeat() -> str:
    """Example periodic task scheduled by Celery Beat."""
    logger.info("celery beat heartbeat")
    return "ok"


@celery_app.task
def sweep_product_images() -> int:
    with Session(engine) as session:
        service = ProductImageService(ProductRepository(session))
        return service.sweep_orphans(now=datetime.now(UTC))
