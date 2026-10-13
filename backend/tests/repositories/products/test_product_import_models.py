import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ProductCategory,
    ProductImport,
    ProductImportError,
    ProductImportStatus,
)
from tests.utils.utils import random_lower_string


def make_import(status: str = ProductImportStatus.PENDING) -> ProductImport:
    return ProductImport(
        file_key=f"imports/{random_lower_string()}.csv",
        filename="products.csv",
        status=status,
        total_bytes=10,
        etag='"abc"',
    )


def test_only_one_active_import(db: Session) -> None:
    db.add(make_import(ProductImportStatus.PENDING))
    db.commit()

    db.add(make_import(ProductImportStatus.RUNNING))
    with pytest.raises(IntegrityError) as exc_info:
        db.commit()
    db.rollback()

    assert exc_info.value.orig is not None
    assert (
        getattr(exc_info.value.orig, "diag").constraint_name
        == "ix_product_import_active"
    )


def test_a_finished_import_does_not_block_a_new_one(db: Session) -> None:
    db.add(make_import(ProductImportStatus.COMPLETED))
    db.add(make_import(ProductImportStatus.FAILED))
    db.add(make_import(ProductImportStatus.PENDING))
    db.commit()


def test_live_category_names_are_unique_ignoring_case(db: Session) -> None:
    name = random_lower_string()
    first = ProductCategory(name=name.capitalize(), code=random_lower_string()[:20])
    db.add(first)
    db.commit()

    db.add(ProductCategory(name=name, code=random_lower_string()[:20]))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    first.is_deleted = True
    db.commit()
    db.add(ProductCategory(name=name, code=random_lower_string()[:20]))
    db.commit()


def test_deleting_an_import_cascades_to_its_errors(db: Session) -> None:
    imp = make_import(ProductImportStatus.COMPLETED)
    db.add(imp)
    db.flush()
    db.add(ProductImportError(import_id=imp.id, line=4, sku="A", message="bad"))
    db.commit()

    db.execute(delete(ProductImport).where(ProductImport.id == imp.id))
    db.commit()

    assert (
        db.scalars(
            select(ProductImportError).where(ProductImportError.import_id == imp.id)
        ).all()
        == []
    )
