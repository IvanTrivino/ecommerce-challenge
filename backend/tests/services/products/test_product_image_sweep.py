from datetime import UTC, datetime, timedelta

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.core.storage import head_object
from app.repositories import ProductRepository
from app.services import ProductImageService
from app.services.products import product_image_service
from app.tasks import sweep_product_images
from tests.utils.product import create_random_product
from tests.utils.storage import upload_image

pytestmark = pytest.mark.usefixtures("images_bucket")


def _service(db: Session) -> ProductImageService:
    return ProductImageService(ProductRepository(db))


def _product_with_image(db: Session, key: str, *, deleted: bool = False) -> None:
    product = create_random_product(db)
    product.image_key = key
    repo = ProductRepository(db)
    repo.save(product)
    if deleted:
        repo.delete(product)


def _exists(bucket: str, key: str) -> bool:
    return head_object(bucket, key) is not None


def test_sweep_deletes_only_old_unreferenced_images(
    db: Session, images_bucket: str
) -> None:
    """AC-8"""
    referenced, soft_deleted, orphan_a, orphan_b = (upload_image() for _ in range(4))
    _product_with_image(db, referenced)
    _product_with_image(db, soft_deleted, deleted=True)

    deleted = _service(db).sweep_orphans(now=datetime.now(UTC) + timedelta(hours=25))

    assert deleted == 2
    assert _exists(images_bucket, referenced)
    assert _exists(images_bucket, soft_deleted)
    assert not _exists(images_bucket, orphan_a)
    assert not _exists(images_bucket, orphan_b)


def test_sweep_keeps_recent_orphans(db: Session, images_bucket: str) -> None:
    recent = upload_image()

    deleted = _service(db).sweep_orphans(now=datetime.now(UTC))

    assert deleted == 0
    assert _exists(images_bucket, recent)


def test_sweep_survives_a_failing_page(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_image()

    def fail(*_args: object) -> None:
        raise ClientError(
            {"Error": {"Code": "500", "Message": "boom"}}, "DeleteObjects"
        )

    monkeypatch.setattr(product_image_service, "delete_objects", fail)

    assert _service(db).sweep_orphans(now=datetime.now(UTC) + timedelta(hours=25)) == 0


def test_sweep_task_returns_the_deleted_count() -> None:
    assert isinstance(sweep_product_images(), int)
