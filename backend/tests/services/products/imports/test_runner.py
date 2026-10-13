import csv
import io
import uuid
from collections.abc import Callable, Generator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.storage import get_s3
from app.models import (
    OutboxEvent,
    OutboxTopic,
    Product,
    ProductCategory,
    ProductImport,
    ProductImportError,
)
from app.repositories import ProductImportRepository, ProductRepository
from app.schemas import ProductImportPublic
from app.services.products.cache import PRODUCTS
from app.services.products.imports.runner import (
    ImportOutcome,
    ProductImportRunner,
    TransientImportError,
    _Categories,
)
from tests.utils.cache import FakeRedis
from tests.utils.imports import EXAMPLE_CSV, Enqueued, make_service, start_import
from tests.utils.utils import random_lower_string

pytestmark = pytest.mark.usefixtures("imports_bucket")

_EXAMPLE_ROWS = list(
    csv.DictReader(io.StringIO(EXAMPLE_CSV.read_text(encoding="utf-8"), newline=""))
)
EXAMPLE_SKUS = {r["sku"].strip() for r in _EXAMPLE_ROWS}
EXAMPLE_CATEGORIES = {
    r["category"].strip().lower() for r in _EXAMPLE_ROWS if r["category"].strip()
}
EXAMPLE_ERROR_LINES = [4, 7, 16, 25, 41, 52]
PRICE_ERROR = "price: must be a number like 12.50"


def _wipe_example(db: Session) -> None:
    db.rollback()
    db.execute(delete(OutboxEvent))
    categories = select(ProductCategory.id).where(
        func.lower(ProductCategory.name).in_(EXAMPLE_CATEGORIES)
    )
    db.execute(
        delete(Product).where(
            Product.sku.in_(EXAMPLE_SKUS) | Product.category_uuid.in_(categories)
        )
    )
    db.execute(
        delete(ProductCategory).where(
            func.lower(ProductCategory.name).in_(EXAMPLE_CATEGORIES)
        )
    )
    db.commit()


@pytest.fixture(autouse=True)
def clean_example(db: Session) -> Generator[None]:
    _wipe_example(db)
    yield
    _wipe_example(db)


def run(imp: ProductImport) -> ProductImport:
    ProductImportRunner(engine).run(imp.id)
    return reload(imp.id)


def reload(import_id: uuid.UUID) -> ProductImport:
    with Session(engine, expire_on_commit=False) as session:
        imp = session.get(ProductImport, import_id)
        assert imp
        return imp


def import_example(db: Session) -> ProductImport:
    return run(start_import(db, EXAMPLE_CSV.read_bytes(), filename="example.csv"))


def counters(imp: ProductImport) -> tuple[int, ...]:
    return (
        imp.created_count,
        imp.updated_count,
        imp.unchanged_count,
        imp.error_count,
        imp.blank_count,
        imp.categories_created,
    )


def stored_errors(db: Session, imp: ProductImport) -> list[ProductImportError]:
    return list(ProductImportRepository(db).list_errors(imp.id, limit=500))


def product(db: Session, sku: str) -> Product:
    db.expire_all()
    return db.scalars(
        select(Product).where(Product.sku == sku, ~Product.is_deleted)
    ).one()


def count_events(db: Session, topic: OutboxTopic) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.topic == topic.value)
        )
        or 0
    )


def snapshot(db: Session) -> dict[str, tuple[Any, ...]]:
    db.expire_all()
    rows = db.execute(
        select(
            Product.sku,
            Product.name,
            Product.price,
            Product.stock,
            Product.description,
            Product.weight,
            ProductCategory.name,
        )
        .join(ProductCategory, Product.category_uuid == ProductCategory.id)
        .where(Product.sku.in_(EXAMPLE_SKUS), ~Product.is_deleted)
    ).all()
    return {r[0]: tuple(r) for r in rows}


def test_example_file(db: Session) -> None:
    imp = import_example(db)

    assert imp.status == "completed"
    assert counters(imp) == (86, 3, 0, 6, 2, 17)
    assert imp.bytes_processed == imp.total_bytes == EXAMPLE_CSV.stat().st_size
    assert imp.started_at and imp.finished_at
    assert imp.error_message is None

    errors = stored_errors(db, imp)
    assert [e.line for e in errors] == EXAMPLE_ERROR_LINES
    messages = {e.line: e.message for e in errors}
    assert messages[4] == PRICE_ERROR
    assert messages[7] == PRICE_ERROR
    assert messages[16] == "stock: must be a whole number ≥ 0"
    assert messages[25] == "name: required"
    assert messages[41] == "name: required"
    assert messages[52] == (
        "category: required; weight_kg: must be a number > 0 with up to 3 decimals"
    )

    assert product(db, "RS-001").price == Decimal("94.99")
    speaker = product(db, "BS-021")
    assert (speaker.price, speaker.stock) == (Decimal("59.99"), 110)
    assert product(db, "QI-001").name == 'Quote "Inside" Name'
    description = product(db, "WB-033").description
    assert description and "—" in description and "™" in description
    assert product(db, "SQL-001").name == "Robert'); DROP TABLE products;--"
    food = db.scalars(
        select(ProductCategory).where(ProductCategory.name == "Food & Beverage")
    ).one()
    assert food.code == "FOOD_BEVERAGE"
    assert len(snapshot(db)) == 86

    # 86 creates, plus the 3 updates that change the description (RS-001 once, BS-021 twice)
    assert count_events(db, OutboxTopic.SEARCH_PRODUCT) == 89
    assert count_events(db, OutboxTopic.SEARCH_PRODUCT_CATEGORY) == 17


def test_importing_the_example_again(db: Session) -> None:
    first = import_example(db)
    before = snapshot(db)
    db.execute(delete(OutboxEvent))
    db.commit()

    second = import_example(db)

    assert first.status == second.status == "completed"
    assert counters(second) == (0, 4, 85, 6, 2, 0)
    assert snapshot(db) == before
    assert [e.line for e in stored_errors(db, second)] == EXAMPLE_ERROR_LINES
    # RS-001 (line 36) and BS-021 (lines 56 and 89) change the description, line 11 doesn't
    assert count_events(db, OutboxTopic.SEARCH_PRODUCT) == 4


@pytest.mark.parametrize("batch_size", [1, 10, 1000])
def test_results_do_not_depend_on_the_batch_size(
    db: Session, monkeypatch: pytest.MonkeyPatch, batch_size: int
) -> None:
    monkeypatch.setattr(settings, "PRODUCT_IMPORT_BATCH_SIZE", batch_size)

    imp = import_example(db)

    assert counters(imp) == (86, 3, 0, 6, 2, 17)
    assert product(db, "BS-021").stock == 110
    assert product(db, "RS-001").price == Decimal("94.99")


def test_resuming_after_a_crash(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    original = ProductRepository.upsert_many
    calls = 0

    def flaky(self: ProductRepository, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OperationalError("INSERT", {}, Exception("connection lost"))
        return original(self, *args, **kwargs)

    imp = start_import(db, EXAMPLE_CSV.read_bytes())
    with monkeypatch.context() as patch:
        patch.setattr(ProductRepository, "upsert_many", flaky)
        with pytest.raises(TransientImportError):
            ProductImportRunner(engine).run(imp.id)

    partial = reload(imp.id)
    assert partial.status == "running"
    assert 0 < partial.bytes_processed < partial.total_bytes

    resumed = run(imp)

    assert resumed.status == "completed"
    assert counters(resumed) == (86, 3, 0, 6, 2, 17)
    lines = [e.line for e in stored_errors(db, resumed)]
    assert lines == EXAMPLE_ERROR_LINES
    assert len(snapshot(db)) == 86


def test_a_locked_import_is_skipped(db: Session) -> None:
    imp = start_import(db, EXAMPLE_CSV.read_bytes())
    with engine.connect() as other:
        assert ProductImportRepository(db).try_lock(other, imp.id)

        outcome = ProductImportRunner(engine).run(imp.id)

        ProductImportRepository(db).unlock(other, imp.id)
    assert outcome == ImportOutcome.SKIPPED
    assert reload(imp.id).status == "pending"


def test_finished_imports_are_not_run_again(db: Session) -> None:
    imp = import_example(db)

    assert ProductImportRunner(engine).run(imp.id) == ImportOutcome.SKIPPED
    assert counters(reload(imp.id)) == counters(imp)


def test_missing_required_column_fails_without_writing(db: Session) -> None:
    imp = run(start_import(db, b"name,sku,category,stock\r\nMug,M-1,Kitchen,1\r\n"))

    assert imp.status == "failed"
    assert imp.error_message == "Missing columns: price"
    assert imp.finished_at is not None
    assert counters(imp) == (0, 0, 0, 0, 0, 0)


def test_empty_header_fails(db: Session) -> None:
    imp = run(start_import(db, b"\n"))

    assert imp.status == "failed"
    assert imp.error_message == "File is not a UTF-8 CSV"


def test_unterminated_quote_fails_and_keeps_earlier_batches(db: Session) -> None:
    prefix = random_lower_string()
    lines = ["name,sku,category,price,stock"]
    for line in range(2, 41):
        sku = f"{prefix}-{line}"
        lines.append(
            f'"oops,{sku},C,1.00,1' if line == 25 else f"P{line},{sku},C,1.00,1"
        )
    category = random_lower_string()
    body = "\r\n".join(lines).replace(",C,", f",{category},").encode()

    imp = run(start_import(db, body))

    assert imp.status == "failed"
    assert imp.error_message == "Line 25: unterminated quoted field"
    skus = set(
        db.scalars(select(Product.sku).where(Product.sku.like(f"{prefix}-%"))).all()
    )
    assert skus == {f"{prefix}-{line}" for line in range(2, 22)}
    assert imp.bytes_processed < imp.total_bytes


def test_a_changed_file_fails(db: Session) -> None:
    imp = start_import(db, EXAMPLE_CSV.read_bytes())
    get_s3().put_object(
        Bucket=settings.S3_PRODUCT_IMPORTS_BUCKET, Key=imp.file_key, Body=b"other"
    )

    done = run(imp)

    assert done.status == "failed"
    assert done.error_message == "Import file changed after upload"


def test_a_deleted_file_fails(db: Session) -> None:
    imp = start_import(db, EXAMPLE_CSV.read_bytes())
    get_s3().delete_object(Bucket=settings.S3_PRODUCT_IMPORTS_BUCKET, Key=imp.file_key)

    done = run(imp)

    assert done.status == "failed"
    assert done.error_message == "Import file not found"


def test_only_the_first_errors_are_stored(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "PRODUCT_IMPORT_MAX_STORED_ERRORS", 3)
    monkeypatch.setattr(settings, "PRODUCT_IMPORT_BATCH_SIZE", 2)
    body = "name,sku,category,price,stock\r\n" + "\r\n".join(
        f"P{i},E-{i},C,bad,1" for i in range(5)
    )

    imp = run(start_import(db, body.encode()))

    assert imp.status == "completed"
    assert imp.error_count == 5
    assert [e.line for e in stored_errors(db, imp)] == [2, 3, 4]
    errors = make_service(db, Enqueued()).list_errors(imp.id, skip=0, limit=10)
    assert (errors.count, errors.truncated) == (3, True)


def test_a_category_created_concurrently_is_reused(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = f"Clash {random_lower_string()}"
    db.add(ProductCategory(name=name, code=random_lower_string()[:20].upper()))
    db.commit()
    sku = random_lower_string()
    body = f"name,sku,category,price,stock\r\nMug,{sku},{name.upper()},1.00,1"
    load = ProductImportRunner._load_categories
    loads = 0

    def stale_first(session: Session) -> _Categories:
        nonlocal loads
        loads += 1
        return _Categories({}, set()) if loads == 1 else load(session)

    monkeypatch.setattr(
        ProductImportRunner, "_load_categories", staticmethod(stale_first)
    )

    imp = run(start_import(db, body.encode()))

    assert imp.status == "completed"
    assert (imp.created_count, imp.categories_created) == (1, 0)
    assert loads == 2
    matching = db.scalars(
        select(ProductCategory).where(func.lower(ProductCategory.name) == name.lower())
    ).all()
    assert len(matching) == 1


def test_category_codes_that_are_taken_get_a_suffix(db: Session) -> None:
    db.add(ProductCategory(name=f"Other {random_lower_string()}", code="HOME_OFFICE"))
    db.commit()
    body = b"name,sku,category,price,stock\r\nDesk,D-1,Home & Office,1.00,1"
    try:
        imp = run(start_import(db, body))

        assert imp.categories_created == 1
        code = db.scalars(
            select(ProductCategory.code).where(ProductCategory.name == "Home & Office")
        ).one()
        assert code == "HOME_OFFICE_2"
    finally:
        db.execute(delete(Product).where(Product.sku == "D-1"))
        db.execute(delete(ProductCategory).where(ProductCategory.code == "HOME_OFFICE"))
        db.execute(
            delete(ProductCategory).where(ProductCategory.code == "HOME_OFFICE_2")
        )
        db.commit()


def test_product_caches_are_invalidated(db: Session, fake_cache: FakeRedis) -> None:
    PRODUCTS.invalidate()
    before = fake_cache.data[PRODUCTS._version_key]

    import_example(db)

    assert fake_cache.data[PRODUCTS._version_key] != before


def test_progress_never_decreases_and_reaches_100_on_completion(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, int]] = []
    original: Callable[..., Any] = ProductRepository.upsert_many

    def spy(self: ProductRepository, *args: Any, **kwargs: Any) -> Any:
        with Session(engine) as other:
            current = other.scalars(select(ProductImport)).one()
            public = ProductImportPublic.model_validate(current)
            seen.append((public.status, public.progress))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ProductRepository, "upsert_many", spy)

    imp = import_example(db)

    progress = [p for _, p in seen]
    assert progress == sorted(progress)
    assert all(p < 100 for p in progress)
    assert len(progress) >= 10
    assert reload(imp.id).status == "completed"
