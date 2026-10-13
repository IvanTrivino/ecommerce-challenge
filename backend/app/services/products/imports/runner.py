import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from itertools import batched

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.core.cache import invalidate_quietly
from app.core.config import settings
from app.core.storage import ObjectChangedError, ObjectNotFoundError, iter_object_chunks
from app.models import (
    ACTIVE_IMPORT_STATUSES,
    ProductCategory,
    ProductImport,
    ProductImportStatus,
)
from app.models.base import get_datetime_utc
from app.repositories import (
    ProductCategoryRepository,
    ProductImportRepository,
    ProductRepository,
    ProductUpsert,
)
from app.services.products.cache import PRODUCT_CATEGORIES, PRODUCTS
from app.services.products.imports.csv_records import (
    CsvRecord,
    UnterminatedRecordError,
    iter_records,
)
from app.services.products.imports.rows import (
    BLANK,
    HeaderError,
    ImportRow,
    RowError,
    category_code,
    parse_header,
    parse_row,
)

logger = logging.getLogger(__name__)

_ACTIVE = tuple(status.value for status in ACTIVE_IMPORT_STATUSES)


class ImportOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TransientImportError(Exception):
    pass


class _FileFailure(Exception):
    pass


@dataclass
class _Categories:
    ids: dict[str, uuid.UUID]
    codes: set[str]


class ProductImportRunner:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def run(self, import_id: uuid.UUID) -> ImportOutcome:
        with self.engine.connect() as lock_conn, Session(self.engine) as helper:
            lock_repo = ProductImportRepository(helper)
            if not lock_repo.try_lock(lock_conn, import_id):
                logger.info("Product import %s is owned by another worker", import_id)
                lock_conn.rollback()
                return ImportOutcome.SKIPPED
            lock_conn.commit()
            try:
                return self._run_locked(import_id)
            finally:
                try:
                    lock_repo.unlock(lock_conn, import_id)
                    lock_conn.commit()
                except Exception:
                    logger.warning("Could not release the import lock", exc_info=True)
                    lock_conn.invalidate()

    def fail(self, import_id: uuid.UUID, message: str) -> None:
        with Session(self.engine) as session:
            imp = session.get(ProductImport, import_id)
            if imp is None or imp.status not in _ACTIVE:
                return
            now = get_datetime_utc()
            imp.status = ProductImportStatus.FAILED.value
            imp.error_message = message
            imp.finished_at = now
            imp.heartbeat_at = now
            session.commit()
        logger.error("Product import %s failed: %s", import_id, message)

    def _run_locked(self, import_id: uuid.UUID) -> ImportOutcome:
        with Session(self.engine, expire_on_commit=False) as session:
            imp = session.get(ProductImport, import_id)
            if imp is None or imp.status not in _ACTIVE:
                return ImportOutcome.SKIPPED
            now = get_datetime_utc()
            imp.status = ProductImportStatus.RUNNING.value
            imp.started_at = imp.started_at or now
            imp.heartbeat_at = now
            session.commit()
            logger.info(
                "Product import %s started at byte %d of %d",
                imp.id,
                imp.bytes_processed,
                imp.total_bytes,
            )
            try:
                self._process(session, imp)
            except (
                _FileFailure,
                HeaderError,
                UnterminatedRecordError,
                ObjectNotFoundError,
                ObjectChangedError,
            ) as exc:
                session.rollback()
                self.fail(import_id, self._file_message(exc))
                return ImportOutcome.FAILED
            except (
                ClientError,
                BotoCoreError,
                OperationalError,
                InterfaceError,
            ) as exc:
                session.rollback()
                raise TransientImportError(str(exc)) from exc
            return ImportOutcome.COMPLETED

    @staticmethod
    def _file_message(exc: Exception) -> str:
        if isinstance(exc, ObjectNotFoundError):
            return "Import file not found"
        if isinstance(exc, ObjectChangedError):
            return "Import file changed after upload"
        return str(exc)

    def _process(self, session: Session, imp: ProductImport) -> None:
        if imp.columns is not None and imp.bytes_processed >= imp.total_bytes:
            self._complete(session, imp)
            return
        chunks = iter_object_chunks(
            settings.S3_PRODUCT_IMPORTS_BUCKET,
            imp.file_key,
            start=imp.bytes_processed,
            etag=imp.etag,
        )
        records = iter_records(
            chunks,
            start_offset=imp.bytes_processed,
            start_line=imp.next_line,
            max_record_bytes=settings.PRODUCT_IMPORT_MAX_RECORD_BYTES,
        )
        if imp.columns is None:
            header = next(records, None)
            if header is None:
                raise _FileFailure("File is not a UTF-8 CSV")
            imp.columns = parse_header(header.fields)
            imp.bytes_processed = header.end_offset
            imp.next_line = header.next_line
            imp.heartbeat_at = get_datetime_utc()
            session.commit()

        categories = self._load_categories(session)
        for batch in batched(records, settings.PRODUCT_IMPORT_BATCH_SIZE):
            try:
                self._apply_batch(session, imp, batch, categories)
            except IntegrityError:
                session.rollback()
                categories = self._load_categories(session)
                self._apply_batch(session, imp, batch, categories)
        self._complete(session, imp)

    @staticmethod
    def _load_categories(session: Session) -> _Categories:
        ids, codes = ProductCategoryRepository(session).live_names_and_codes()
        return _Categories(ids, codes)

    def _apply_batch(
        self,
        session: Session,
        imp: ProductImport,
        batch: tuple[CsvRecord, ...],
        categories: _Categories,
    ) -> None:
        assert imp.columns is not None
        rows: list[ImportRow] = []
        errors: list[RowError] = []
        blanks = 0
        for record in batch:
            parsed = parse_row(record, imp.columns)
            if parsed is BLANK:
                blanks += 1
            elif isinstance(parsed, RowError):
                errors.append(parsed)
            elif isinstance(parsed, ImportRow):
                rows.append(parsed)
        for error in errors:
            logger.info(
                "Import %s line %d (%s) skipped: %s",
                imp.id,
                error.line,
                error.sku,
                error.message,
            )

        created_categories = self._create_categories(session, rows, categories)

        columns = {
            field
            for field, column in (
                ("description", "description"),
                ("weight", "weight_kg"),
            )
            if column in imp.columns
        }
        created = updated = unchanged = 0
        repo = ProductRepository(session)
        for round_rows in self._rounds(rows):
            result = repo.upsert_many(
                [
                    ProductUpsert(
                        sku=row.sku,
                        name=row.name,
                        category_uuid=categories.ids[row.category.casefold()],
                        price=row.price,
                        stock=row.stock,
                        description=row.description,
                        weight=row.weight,
                    )
                    for row in round_rows
                ],
                columns=columns,
            )
            created += result.created
            updated += result.updated
            unchanged += result.unchanged

        stored = min(imp.error_count, settings.PRODUCT_IMPORT_MAX_STORED_ERRORS)
        room = settings.PRODUCT_IMPORT_MAX_STORED_ERRORS - stored
        ProductImportRepository(session).add_errors(imp.id, errors[:room])

        imp.created_count += created
        imp.updated_count += updated
        imp.unchanged_count += unchanged
        imp.error_count += len(errors)
        imp.blank_count += blanks
        imp.categories_created += created_categories
        imp.bytes_processed = batch[-1].end_offset
        imp.next_line = batch[-1].next_line
        imp.heartbeat_at = get_datetime_utc()
        session.commit()
        invalidate_quietly(
            PRODUCTS, *([PRODUCT_CATEGORIES] if created_categories else [])
        )

    @staticmethod
    def _create_categories(
        session: Session, rows: list[ImportRow], categories: _Categories
    ) -> int:
        new: dict[str, ProductCategory] = {}
        for row in rows:
            key = row.category.casefold()
            if key in categories.ids or key in new:
                continue
            new[key] = ProductCategory(
                name=row.category, code=_unique_code(row.category, categories.codes)
            )
        if not new:
            return 0
        session.add_all(new.values())
        session.flush()
        categories.ids.update({key: category.id for key, category in new.items()})
        return len(new)

    @staticmethod
    def _rounds(rows: list[ImportRow]) -> list[list[ImportRow]]:
        rounds: list[list[ImportRow]] = []
        seen: Counter[str] = Counter()
        for row in rows:
            index = seen[row.sku]
            seen[row.sku] += 1
            if index == len(rounds):
                rounds.append([])
            rounds[index].append(row)
        return rounds

    def _complete(self, session: Session, imp: ProductImport) -> None:
        now: datetime = get_datetime_utc()
        imp.status = ProductImportStatus.COMPLETED.value
        imp.bytes_processed = imp.total_bytes
        imp.finished_at = now
        imp.heartbeat_at = now
        session.commit()
        invalidate_quietly(PRODUCTS, PRODUCT_CATEGORIES)
        logger.info(
            "Product import %s completed: %d created, %d updated, %d unchanged, "
            "%d errors, %d blank, %d categories created",
            imp.id,
            imp.created_count,
            imp.updated_count,
            imp.unchanged_count,
            imp.error_count,
            imp.blank_count,
            imp.categories_created,
        )


def _unique_code(name: str, codes: set[str]) -> str:
    base = category_code(name)
    code = base
    suffix = 2
    while code in codes:
        code = f"{base}_{suffix}"
        suffix += 1
    codes.add(code)
    return code
