from datetime import timedelta

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.storage import head_object
from app.models import ProductImport, ProductImportStatus
from app.models.base import get_datetime_utc
from app.repositories import ProductImportRepository
from app.schemas import ProductImportPublic
from tests.utils.imports import make_service, start_import, upload_csv

pytestmark = pytest.mark.usefixtures("imports_bucket")

BODY = b"name,sku,category,price,stock\r\nMug,M-1,Kitchen,1.00,1\r\n"


def exists(key: str) -> bool:
    return head_object(settings.S3_PRODUCT_IMPORTS_BUCKET, key) is not None


def fresh(db: Session, imp: ProductImport) -> ProductImport:
    db.expire_all()
    return db.get_one(ProductImport, imp.id)


def test_sweep_deletes_old_files_except_active_ones(db: Session) -> None:
    service = make_service(db)
    completed = start_import(db, BODY)
    completed.status = ProductImportStatus.COMPLETED
    db.commit()
    active = start_import(db, BODY)
    never_imported = upload_csv(service, BODY)
    now = get_datetime_utc()

    assert service.sweep_files(now=now + timedelta(days=6)) == 0
    assert service.sweep_files(now=now + timedelta(days=8)) == 2

    assert not exists(completed.file_key)
    assert not exists(never_imported)
    assert exists(active.file_key)
    assert fresh(db, completed).file_deleted_at is not None
    assert fresh(db, active).file_deleted_at is None


def test_a_swept_import_cannot_be_retried(db: Session) -> None:
    imp = start_import(db, BODY)
    imp.status = ProductImportStatus.COMPLETED
    db.commit()

    make_service(db).sweep_files(now=get_datetime_utc() + timedelta(days=8))
    imp = fresh(db, imp)
    imp.status = ProductImportStatus.FAILED
    db.commit()

    assert not ProductImportPublic.model_validate(imp).can_retry


def test_sweep_survives_a_failing_page(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_csv(make_service(db), BODY)

    def broken(_bucket: str, _keys: object) -> None:
        raise ClientError(
            {"Error": {"Code": "500", "Message": "boom"}}, "DeleteObjects"
        )

    monkeypatch.setattr("app.services.products.imports.service.delete_objects", broken)

    assert make_service(db).sweep_files(now=get_datetime_utc() + timedelta(days=8)) == 0


def test_reaper_fails_silent_imports(db: Session) -> None:
    imp = start_import(db, BODY)
    imp.status = ProductImportStatus.RUNNING
    imp.heartbeat_at = get_datetime_utc() - timedelta(minutes=11)
    db.commit()

    assert make_service(db).reap_stale(now=get_datetime_utc()) == 1

    reaped = fresh(db, imp)
    assert reaped.status == ProductImportStatus.FAILED
    assert reaped.error_message == "Import was interrupted"
    assert reaped.finished_at is not None
    assert ProductImportPublic.model_validate(reaped).can_retry


def test_reaper_leaves_locked_imports_alone(db: Session) -> None:
    imp = start_import(db, BODY)
    imp.status = ProductImportStatus.RUNNING
    imp.heartbeat_at = get_datetime_utc() - timedelta(minutes=11)
    db.commit()
    with engine.connect() as other:
        assert ProductImportRepository(db).try_lock(other, imp.id)

        reaped = make_service(db).reap_stale(now=get_datetime_utc())

        ProductImportRepository(db).unlock(other, imp.id)
    assert reaped == 0
    assert fresh(db, imp).status == ProductImportStatus.RUNNING


def test_reaper_leaves_fresh_imports_alone(db: Session) -> None:
    imp = start_import(db, BODY)

    assert make_service(db).reap_stale(now=get_datetime_utc()) == 0
    assert fresh(db, imp).status == ProductImportStatus.PENDING


def test_reaper_fails_a_pending_import_that_was_never_picked_up(db: Session) -> None:
    imp = start_import(db, BODY)

    assert (
        make_service(db).reap_stale(now=get_datetime_utc() + timedelta(minutes=11)) == 1
    )
    assert fresh(db, imp).status == ProductImportStatus.FAILED
