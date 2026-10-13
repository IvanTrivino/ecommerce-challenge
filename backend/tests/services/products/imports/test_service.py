import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError
from app.models import ProductImportStatus
from app.models.base import get_datetime_utc
from app.schemas import ProductImportCreate, ProductImportUploadRequest
from app.services.products.imports.service import KEY_PATTERN
from tests.utils.imports import (
    EXAMPLE_CSV,
    Enqueued,
    make_service,
    superuser,
    upload_csv,
)
from tests.utils.storage import post_upload

pytestmark = pytest.mark.usefixtures("imports_bucket")

BODY = b"name,sku,category,price,stock\r\nMug,M-1,Kitchen,1.00,1\r\n"


def test_presign_returns_a_pinned_ticket(db: Session) -> None:
    ticket = make_service(db).presign(
        ProductImportUploadRequest(filename="Products.CSV", size=100)
    )

    assert KEY_PATTERN.fullmatch(ticket.key)
    assert ticket.fields["Content-Type"] == "text/csv"
    assert ticket.max_bytes == settings.PRODUCT_IMPORT_MAX_BYTES
    assert ticket.expires_in == settings.PRODUCT_IMPORT_UPLOAD_EXPIRES_SECONDS
    assert post_upload(ticket, EXAMPLE_CSV.read_bytes()).status_code == 204


def test_presign_rejects_oversize_files(db: Session) -> None:
    request = ProductImportUploadRequest(
        filename="a.csv", size=settings.PRODUCT_IMPORT_MAX_BYTES + 1
    )

    with pytest.raises(BadRequestError, match="CSV must be 10 MB or smaller"):
        make_service(db).presign(request)


def test_storage_rejects_uploads_over_the_policy(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "PRODUCT_IMPORT_MAX_BYTES", 10)
    ticket = make_service(db).presign(
        ProductImportUploadRequest(filename="a.csv", size=5)
    )

    assert post_upload(ticket, b"x" * 50).status_code == 400


def test_start_queues_a_pending_import(db: Session) -> None:
    enqueued = Enqueued()
    service = make_service(db, enqueued)
    key = upload_csv(service, BODY)

    imp, created = service.start(
        ProductImportCreate(key=key, filename=" products.csv "), superuser(db)
    )

    assert created
    assert imp.status == ProductImportStatus.PENDING
    assert imp.filename == "products.csv"
    assert imp.total_bytes == len(BODY)
    assert imp.etag.startswith('"')
    assert imp.celery_task_id == "task-id"
    assert imp.created_by_email == settings.FIRST_SUPERUSER
    assert list(enqueued) == [imp.id]


def test_start_twice_with_the_same_key_runs_once(db: Session) -> None:
    enqueued = Enqueued()
    service = make_service(db, enqueued)
    key = upload_csv(service, BODY)
    data = ProductImportCreate(key=key, filename="a.csv")

    first, created_first = service.start(data, superuser(db))
    second, created_second = service.start(data, superuser(db))

    assert (created_first, created_second) == (True, False)
    assert second.id == first.id
    assert len(enqueued) == 1


@pytest.mark.parametrize(
    "key", ["imports/x.csv", "other/" + str(uuid.uuid4()) + ".csv"]
)
def test_start_rejects_invalid_keys(db: Session, key: str) -> None:
    with pytest.raises(BadRequestError, match="Invalid import file"):
        make_service(db).start(
            ProductImportCreate(key=key, filename="a.csv"), superuser(db)
        )


def test_start_rejects_a_missing_object(db: Session) -> None:
    key = f"imports/{uuid.uuid4()}.csv"

    with pytest.raises(BadRequestError, match="Import file not found"):
        make_service(db).start(
            ProductImportCreate(key=key, filename="a.csv"), superuser(db)
        )


def test_start_rejects_an_oversize_object(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = make_service(db)
    key = upload_csv(service, BODY)
    monkeypatch.setattr(settings, "PRODUCT_IMPORT_MAX_BYTES", 5)

    with pytest.raises(BadRequestError, match="CSV must be 0 MB or smaller"):
        service.start(ProductImportCreate(key=key, filename="a.csv"), superuser(db))


def test_start_is_refused_while_another_import_is_active(db: Session) -> None:
    service = make_service(db)
    first, second = upload_csv(service, BODY), upload_csv(service, BODY)
    service.start(ProductImportCreate(key=first, filename="a.csv"), superuser(db))

    with pytest.raises(ConflictError, match="Another import is in progress"):
        service.start(ProductImportCreate(key=second, filename="b.csv"), superuser(db))


def test_a_failing_queue_marks_the_import_failed(db: Session) -> None:
    def broken(_import_id: uuid.UUID) -> str:
        raise ConnectionError("broker down")

    service = make_service(db)
    service._enqueue = broken
    key = upload_csv(service, BODY)

    with pytest.raises(Exception, match="Import queue unavailable"):
        service.start(ProductImportCreate(key=key, filename="a.csv"), superuser(db))

    imp = service.repo.get_by_key(key)
    assert imp
    assert imp.status == ProductImportStatus.FAILED
    assert imp.error_message == "Could not queue the import"
    retry_key = upload_csv(service, BODY)
    service._enqueue = Enqueued()
    service.start(ProductImportCreate(key=retry_key, filename="b.csv"), superuser(db))


def test_retry_a_failed_import(db: Session) -> None:
    enqueued = Enqueued()
    service = make_service(db, enqueued)
    key = upload_csv(service, BODY)
    imp, _ = service.start(
        ProductImportCreate(key=key, filename="a.csv"), superuser(db)
    )
    imp.status = ProductImportStatus.FAILED
    imp.error_message = "boom"
    imp.finished_at = get_datetime_utc()
    db.commit()

    retried = service.retry(imp.id)

    assert retried.status == ProductImportStatus.PENDING
    assert retried.error_message is None
    assert retried.finished_at is None
    assert list(enqueued) == [imp.id, imp.id]


def test_retry_rejects_other_states(db: Session) -> None:
    service = make_service(db)
    key = upload_csv(service, BODY)
    imp, _ = service.start(
        ProductImportCreate(key=key, filename="a.csv"), superuser(db)
    )

    with pytest.raises(ConflictError, match="Import cannot be retried"):
        service.retry(imp.id)
    imp.status = ProductImportStatus.COMPLETED
    db.commit()
    with pytest.raises(ConflictError, match="Import cannot be retried"):
        service.retry(imp.id)


def test_retry_rejects_a_swept_file(db: Session) -> None:
    service = make_service(db)
    key = upload_csv(service, BODY)
    imp, _ = service.start(
        ProductImportCreate(key=key, filename="a.csv"), superuser(db)
    )
    imp.status = ProductImportStatus.FAILED
    imp.file_deleted_at = get_datetime_utc()
    db.commit()

    with pytest.raises(ConflictError, match="Import file no longer available"):
        service.retry(imp.id)


def test_retry_is_refused_while_another_import_is_active(db: Session) -> None:
    service = make_service(db)
    first = service.start(
        ProductImportCreate(key=upload_csv(service, BODY), filename="a.csv"),
        superuser(db),
    )[0]
    first.status = ProductImportStatus.FAILED
    db.commit()
    service.start(
        ProductImportCreate(key=upload_csv(service, BODY), filename="b.csv"),
        superuser(db),
    )

    with pytest.raises(ConflictError, match="Another import is in progress"):
        service.retry(first.id)


def test_list_errors_reports_truncation(db: Session) -> None:
    service = make_service(db)
    imp, _ = service.start(
        ProductImportCreate(key=upload_csv(service, BODY), filename="a.csv"),
        superuser(db),
    )
    imp.error_count = 5
    service.repo.add_errors(imp.id, [])
    db.commit()

    result = service.list_errors(imp.id, skip=0, limit=10)

    assert (result.count, result.truncated) == (0, True)
