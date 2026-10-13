import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.models import ProductImport
from app.services.products.imports.runner import (
    ImportOutcome,
    ProductImportRunner,
    TransientImportError,
)
from app.tasks import IMPORT_MAX_RETRIES, run_product_import


def make_pending_import(db: Session) -> ProductImport:
    imp = ProductImport(
        file_key="imports/00000000-0000-0000-0000-000000000000.csv",
        filename="a.csv",
        status="pending",
        total_bytes=10,
        etag='"e"',
    )
    db.add(imp)
    db.commit()
    return imp


def test_a_transient_error_is_retried_then_fails_the_import(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    imp = make_pending_import(db)
    calls = 0

    def broken(self: ProductImportRunner, _import_id: object) -> ImportOutcome:
        nonlocal calls
        calls += 1
        raise TransientImportError("storage down")

    monkeypatch.setattr(ProductImportRunner, "run", broken)

    run_product_import.apply(args=[str(imp.id)])

    assert calls == IMPORT_MAX_RETRIES + 1
    db.refresh(imp)
    assert imp.status == "failed"
    assert imp.error_message == "Import failed unexpectedly"


def test_the_soft_time_limit_fails_the_import(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    imp = make_pending_import(db)

    def slow(self: ProductImportRunner, _import_id: object) -> ImportOutcome:
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(ProductImportRunner, "run", slow)

    result = run_product_import.apply(args=[str(imp.id)])

    assert result.get() == "failed"
    db.refresh(imp)
    assert (imp.status, imp.error_message) == ("failed", "Import timed out")


def test_an_unexpected_error_fails_the_import(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    imp = make_pending_import(db)

    def crash(self: ProductImportRunner, _import_id: object) -> ImportOutcome:
        raise RuntimeError("bug")

    monkeypatch.setattr(ProductImportRunner, "run", crash)

    run_product_import.apply(args=[str(imp.id)])

    db.refresh(imp)
    assert (imp.status, imp.error_message) == ("failed", "Import failed unexpectedly")
