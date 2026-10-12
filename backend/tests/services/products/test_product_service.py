import uuid
from decimal import Decimal

import pytest
from botocore.exceptions import EndpointConnectionError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.storage import delete_objects, get_s3, product_images_public_url
from app.repositories import ProductCategoryRepository, ProductRepository
from app.schemas import ProductCreate, ProductPublic, ProductUpdate
from app.services import ProductService
from app.services.products import product_image_service
from tests.utils.product import create_random_category, create_random_product
from tests.utils.storage import JPEG_HEADER, PNG_1PX, upload_image
from tests.utils.utils import random_lower_string


def _service(db: Session) -> ProductService:
    return ProductService(ProductRepository(db), ProductCategoryRepository(db))


def _product_in(category_uuid: uuid.UUID, sku: str | None = None) -> ProductCreate:
    return ProductCreate(
        name=random_lower_string(),
        sku=sku or random_lower_string(),
        category_uuid=category_uuid,
        price=Decimal("10.50"),
    )


def test_create_product(db: Session) -> None:
    category = create_random_category(db)
    product = _service(db).create_product(_product_in(category.id))
    assert product.stock == 0
    assert product.category_uuid == category.id


def test_create_product_duplicate_sku(db: Session) -> None:
    existing = create_random_product(db)
    with pytest.raises(ConflictError):
        _service(db).create_product(_product_in(existing.category_uuid, existing.sku))


def test_create_product_unknown_category(db: Session) -> None:
    with pytest.raises(NotFoundError):
        _service(db).create_product(_product_in(uuid.uuid4()))


def test_get_by_id_not_found(db: Session) -> None:
    with pytest.raises(NotFoundError):
        _service(db).get_by_id(uuid.uuid4())


def test_list_products_filters_by_category(db: Session) -> None:
    category = create_random_category(db)
    product = create_random_product(db, category)
    result = _service(db).list_products(category_id=category.id, skip=0, limit=10)
    assert result.count == 1
    assert result.data[0].id == product.id


def test_update_product(db: Session) -> None:
    product = create_random_product(db)
    new_category = create_random_category(db)
    updated = _service(db).update_product(
        product.id,
        ProductUpdate(name="new", price=Decimal("1.00"), category_uuid=new_category.id),
    )
    assert updated.name == "new"
    assert updated.price == Decimal("1.00")
    assert updated.category_uuid == new_category.id


def test_update_ignores_null_for_required_fields_but_clears_nullable(
    db: Session,
) -> None:
    product = create_random_product(db)
    product.description = "to be cleared"
    updated = _service(db).update_product(
        product.id, ProductUpdate(name=None, description=None)
    )
    assert updated.name == product.name
    assert updated.description is None


def test_update_product_keeping_own_sku_is_allowed(db: Session) -> None:
    product = create_random_product(db)
    updated = _service(db).update_product(product.id, ProductUpdate(sku=product.sku))
    assert updated.sku == product.sku


def test_update_product_duplicate_sku(db: Session) -> None:
    first, second = create_random_product(db), create_random_product(db)
    with pytest.raises(ConflictError):
        _service(db).update_product(second.id, ProductUpdate(sku=first.sku))


def test_update_product_unknown_category(db: Session) -> None:
    product = create_random_product(db)
    with pytest.raises(NotFoundError):
        _service(db).update_product(
            product.id, ProductUpdate(category_uuid=uuid.uuid4())
        )


def test_delete_product(db: Session) -> None:
    product = create_random_product(db)
    service = _service(db)
    service.delete_product(product.id)
    with pytest.raises(NotFoundError):
        service.get_by_id(product.id)


def test_write_invalidates_cached_reads(db: Session) -> None:
    product = create_random_product(db)
    service = _service(db)
    assert service.get_by_id(product.id).name == product.name  # fills the cache
    service.update_product(product.id, ProductUpdate(name="renamed"))
    assert service.get_by_id(product.id).name == "renamed"


def _png_key() -> str:
    return f"products/{uuid.uuid4()}.png"


@pytest.mark.usefixtures("images_bucket")
def test_create_product_with_uploaded_image(db: Session) -> None:
    key = upload_image()
    category = create_random_category(db)
    product = _service(db).create_product(
        _product_in(category.id).model_copy(update={"image_key": key})
    )
    assert product.image_key == key
    assert ProductPublic.model_validate(product).image_url == (
        f"{product_images_public_url()}/{key}"
    )


def _create_with_key(db: Session, key: str) -> None:
    category = create_random_category(db)
    with pytest.raises(BadRequestError) as exc:
        _service(db).create_product(
            _product_in(category.id).model_copy(update={"image_key": key})
        )
    raise exc.value


@pytest.mark.usefixtures("images_bucket")
@pytest.mark.parametrize(
    ("key", "detail"),
    [
        ("nope.png", "Invalid image key"),
        (f"products/{uuid.uuid4()}.png", "Image upload not found"),
    ],
)
def test_create_product_rejects_bad_keys(db: Session, key: str, detail: str) -> None:
    with pytest.raises(BadRequestError, match=detail):
        _create_with_key(db, key)


@pytest.mark.usefixtures("images_bucket")
def test_create_product_rejects_wrong_signature(db: Session) -> None:
    key = upload_image(JPEG_HEADER, "image/png")
    with pytest.raises(BadRequestError, match="File is not a valid image"):
        _create_with_key(db, key)


def test_create_product_rejects_type_mismatch(db: Session, images_bucket: str) -> None:
    key = _png_key()
    get_s3().put_object(
        Bucket=images_bucket, Key=key, Body=PNG_1PX, ContentType="image/jpeg"
    )
    with pytest.raises(BadRequestError, match="Image type does not match"):
        _create_with_key(db, key)


@pytest.mark.usefixtures("images_bucket")
def test_create_product_rejects_oversized_image(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = upload_image()
    monkeypatch.setattr(settings, "PRODUCT_IMAGE_MAX_BYTES", len(PNG_1PX) - 1)
    with pytest.raises(BadRequestError, match="MB or smaller"):
        _create_with_key(db, key)


@pytest.mark.usefixtures("images_bucket")
def test_failed_image_check_creates_nothing(db: Session) -> None:
    category = create_random_category(db)
    product_in = _product_in(category.id).model_copy(update={"image_key": _png_key()})
    with pytest.raises(BadRequestError):
        _service(db).create_product(product_in)
    assert ProductRepository(db).get_by_sku(product_in.sku) is None


@pytest.mark.usefixtures("images_bucket")
def test_update_sets_replaces_and_clears_the_image(db: Session) -> None:
    product = create_random_product(db)
    service = _service(db)
    key = upload_image()

    assert (
        service.update_product(product.id, ProductUpdate(image_key=key)).image_key
        == key
    )
    assert service.update_product(product.id, ProductUpdate(stock=1)).image_key == key
    assert (
        service.update_product(product.id, ProductUpdate(image_key=None)).image_key
        is None
    )


def test_update_with_the_same_key_skips_the_storage_check(
    db: Session, images_bucket: str
) -> None:
    product = create_random_product(db)
    service = _service(db)
    key = upload_image()
    service.update_product(product.id, ProductUpdate(image_key=key))
    delete_objects(images_bucket, [key])

    updated = service.update_product(product.id, ProductUpdate(image_key=key, stock=2))

    assert updated.image_key == key


@pytest.mark.usefixtures("images_bucket")
def test_storage_down_is_service_unavailable(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object) -> None:
        raise EndpointConnectionError(endpoint_url="x")

    monkeypatch.setattr(product_image_service, "head_object", fail)
    with pytest.raises(ServiceUnavailableError):
        _service(db).create_product(
            _product_in(create_random_category(db).id).model_copy(
                update={"image_key": _png_key()}
            )
        )
