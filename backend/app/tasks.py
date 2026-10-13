import logging
import uuid
from datetime import UTC, datetime

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.db import engine
from app.repositories import ProductImportRepository, ProductRepository
from app.services import ProductImageService, ProductImportService
from app.services.products.imports.runner import (
    ImportOutcome,
    ProductImportRunner,
    TransientImportError,
)

logger = logging.getLogger(__name__)

IMPORT_MAX_RETRIES = 3


@celery_app.task
def heartbeat() -> str:
    logger.info("celery beat heartbeat")
    return "ok"


@celery_app.task
def sweep_product_images() -> int:
    with Session(engine) as session:
        service = ProductImageService(ProductRepository(session))
        return service.sweep_orphans(now=datetime.now(UTC))


@celery_app.task(
    bind=True,
    max_retries=IMPORT_MAX_RETRIES,
    soft_time_limit=30 * 60,
    time_limit=35 * 60,
)
def run_product_import(self: Task, import_id: str) -> str:  # type: ignore[type-arg]
    runner = ProductImportRunner(engine)
    uid = uuid.UUID(import_id)
    try:
        return runner.run(uid).value
    except TransientImportError as exc:
        if self.request.retries >= IMPORT_MAX_RETRIES:
            runner.fail(uid, "Import failed unexpectedly")
            raise
        # Resumes from the checkpoint
        raise self.retry(exc=exc, countdown=10 * 2**self.request.retries)
    except SoftTimeLimitExceeded:
        runner.fail(uid, "Import timed out")
        return ImportOutcome.FAILED.value
    except Exception:
        logger.exception("Product import %s crashed", import_id)
        runner.fail(uid, "Import failed unexpectedly")
        raise


@celery_app.task
def sweep_product_import_files() -> int:
    with Session(engine) as session:
        service = ProductImportService(ProductImportRepository(session))
        return service.sweep_files(now=datetime.now(UTC))


@celery_app.task
def reap_stale_product_imports() -> int:
    with Session(engine) as session:
        service = ProductImportService(ProductImportRepository(session))
        return service.reap_stale(now=datetime.now(UTC))
