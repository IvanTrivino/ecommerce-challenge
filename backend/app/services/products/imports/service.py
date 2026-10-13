import logging
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from itertools import batched

from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.storage import (
    PRODUCT_IMPORTS_PREFIX,
    browser_bucket_url,
    delete_objects,
    head_object,
    iter_objects,
    presign_post,
)
from app.models import ProductImport, ProductImportStatus, User
from app.models.base import get_datetime_utc
from app.repositories import ProductImportRepository
from app.repositories.base import constraint_name
from app.schemas import (
    ProductImportCreate,
    ProductImportErrorPublic,
    ProductImportErrorsPublic,
    ProductImportPublic,
    ProductImportsPublic,
    ProductImportUpload,
    ProductImportUploadRequest,
)

logger = logging.getLogger(__name__)

KEY_PATTERN = re.compile(r"^imports/[0-9a-f-]{36}\.csv$")
CONTENT_TYPE = "text/csv"
ACTIVE_INDEX = "ix_product_import_active"
FILE_KEY_CONSTRAINT = "product_import_file_key_key"

Enqueue = Callable[[uuid.UUID], str]


def _too_large_message() -> str:
    return f"CSV must be {settings.PRODUCT_IMPORT_MAX_BYTES // (1024 * 1024)} MB or smaller"


class ProductImportService:
    def __init__(
        self, repo: ProductImportRepository, enqueue: Enqueue | None = None
    ) -> None:
        self.repo = repo
        self._enqueue = enqueue

    def presign(self, request: ProductImportUploadRequest) -> ProductImportUpload:
        max_bytes = settings.PRODUCT_IMPORT_MAX_BYTES
        if request.size > max_bytes:
            raise BadRequestError(_too_large_message())
        bucket = settings.S3_PRODUCT_IMPORTS_BUCKET
        expires_in = settings.PRODUCT_IMPORT_UPLOAD_EXPIRES_SECONDS
        key = f"{PRODUCT_IMPORTS_PREFIX}{uuid.uuid4()}.csv"
        try:
            fields = presign_post(
                bucket,
                key,
                fields={"Content-Type": CONTENT_TYPE},
                max_bytes=max_bytes,
                expires_in=expires_in,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("Could not presign product import upload", exc_info=True)
            raise ServiceUnavailableError("Import storage unavailable") from exc
        return ProductImportUpload(
            url=browser_bucket_url(bucket),
            fields=fields,
            key=key,
            max_bytes=max_bytes,
            expires_in=expires_in,
        )

    def start(
        self, data: ProductImportCreate, user: User
    ) -> tuple[ProductImport, bool]:
        self._require_enqueue()
        if not KEY_PATTERN.fullmatch(data.key):
            raise BadRequestError("Invalid import file")
        existing = self.repo.get_by_key(data.key)
        if existing:
            return existing, False
        try:
            stored = head_object(settings.S3_PRODUCT_IMPORTS_BUCKET, data.key)
        except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
            logger.error("Could not check import file %s", data.key, exc_info=True)
            raise ServiceUnavailableError("Import storage unavailable") from exc
        if stored is None:
            raise BadRequestError("Import file not found")
        if stored.size > settings.PRODUCT_IMPORT_MAX_BYTES:
            raise BadRequestError(_too_large_message())
        if not stored.etag:
            raise ServiceUnavailableError("Import storage unavailable")
        if self.repo.get_active():
            raise ConflictError("Another import is in progress")

        imp = ProductImport(
            file_key=data.key,
            filename=data.filename.strip(),
            created_by_id=user.id,
            status=ProductImportStatus.PENDING.value,
            total_bytes=stored.size,
            etag=stored.etag,
        )
        self.repo.session.add(imp)
        try:
            self.repo.session.commit()
        except IntegrityError as exc:
            self.repo.session.rollback()
            constraint = constraint_name(exc)
            if constraint == ACTIVE_INDEX:
                raise ConflictError("Another import is in progress") from exc
            if constraint == FILE_KEY_CONSTRAINT:
                existing = self.repo.get_by_key(data.key)
                if existing:
                    return existing, False
            raise
        self._queue(imp)
        return imp, True

    def list_imports(self, *, skip: int, limit: int) -> ProductImportsPublic:
        return ProductImportsPublic(
            data=[
                ProductImportPublic.model_validate(i)
                for i in self.repo.list(skip=skip, limit=limit)
            ],
            count=self.repo.count(),
        )

    def get(self, import_id: uuid.UUID) -> ProductImport:
        imp = self.repo.get(import_id)
        if not imp:
            raise NotFoundError("Import not found")
        return imp

    def list_errors(
        self, import_id: uuid.UUID, *, skip: int, limit: int
    ) -> ProductImportErrorsPublic:
        imp = self.get(import_id)
        count = self.repo.count_errors(import_id)
        return ProductImportErrorsPublic(
            data=[
                ProductImportErrorPublic.model_validate(e)
                for e in self.repo.list_errors(import_id, skip=skip, limit=limit)
            ],
            count=count,
            truncated=imp.error_count > count,
        )

    def retry(self, import_id: uuid.UUID) -> ProductImport:
        self._require_enqueue()
        imp = self.get(import_id)
        if imp.status != ProductImportStatus.FAILED:
            raise ConflictError("Import cannot be retried")
        if imp.file_deleted_at is not None:
            raise ConflictError("Import file no longer available")
        imp.status = ProductImportStatus.PENDING.value
        imp.error_message = None
        imp.finished_at = None
        imp.heartbeat_at = None
        try:
            self.repo.session.commit()
        except IntegrityError as exc:
            self.repo.session.rollback()
            if constraint_name(exc) == ACTIVE_INDEX:
                raise ConflictError("Another import is in progress") from exc
            raise
        self._queue(imp)
        return imp

    def sweep_files(self, *, now: datetime) -> int:
        bucket = settings.S3_PRODUCT_IMPORTS_BUCKET
        cutoff = now - timedelta(days=settings.PRODUCT_IMPORT_RETENTION_DAYS)
        active = self.repo.active_file_keys()
        deleted = 0
        for page in batched(
            iter_objects(bucket, PRODUCT_IMPORTS_PREFIX), 1000, strict=False
        ):
            try:
                old = [
                    obj.key
                    for obj in page
                    if obj.last_modified < cutoff and obj.key not in active
                ]
                if not old:
                    continue
                delete_objects(bucket, old)
                self.repo.mark_files_deleted(old, now)
                self.repo.session.commit()
                deleted += len(old)
            except ClientError, BotoCoreError:
                self.repo.session.rollback()
                logger.warning("Product import sweep failed for a page", exc_info=True)
        logger.info("Deleted %d old product import files", deleted)
        return deleted

    def reap_stale(self, *, now: datetime) -> int:
        stale_ids = [
            i.id for i in self.repo.stale(now, settings.PRODUCT_IMPORT_STALE_MINUTES)
        ]
        self.repo.session.rollback()
        reaped = 0
        for import_id in stale_ids:
            if not self.repo.try_xact_lock(import_id):
                self.repo.session.rollback()
                continue
            imp = self.repo.get(import_id)
            if imp and imp.status in (
                ProductImportStatus.PENDING,
                ProductImportStatus.RUNNING,
            ):
                imp.status = ProductImportStatus.FAILED.value
                imp.error_message = "Import was interrupted"
                imp.finished_at = now
                reaped += 1
                logger.error("Product import %s was interrupted", import_id)
            self.repo.session.commit()
        return reaped

    def _require_enqueue(self) -> Enqueue:
        if self._enqueue is None:
            raise RuntimeError("ProductImportService needs an enqueue callable")
        return self._enqueue

    def _queue(self, imp: ProductImport) -> None:
        try:
            imp.celery_task_id = self._require_enqueue()(imp.id)
        except Exception as exc:
            logger.error("Could not queue product import %s", imp.id, exc_info=True)
            imp.status = ProductImportStatus.FAILED.value
            imp.error_message = "Could not queue the import"
            imp.finished_at = get_datetime_utc()
            self.repo.session.commit()
            raise ServiceUnavailableError("Import queue unavailable") from exc
        self.repo.session.commit()
        self.repo.session.refresh(imp)
