from typing import get_args

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import get_s3, product_image_url, product_images_public_url
from app.repositories import ProductRepository
from app.schemas import ProductImageContentType, ProductImageUploadRequest
from app.services.products.product_image_service import (
    CACHE_CONTROL,
    IMAGE_TYPES,
    KEY_PATTERN,
    ProductImageService,
)
from tests.utils.storage import PNG_1PX, post_upload

pytestmark = pytest.mark.usefixtures("images_bucket")


def _request(content_type: str, size: int = 100) -> ProductImageUploadRequest:
    return ProductImageUploadRequest.model_validate(
        {"content_type": content_type, "size": size}
    )


@pytest.fixture
def service(db: Session) -> ProductImageService:
    return ProductImageService(ProductRepository(db))


def test_image_types_match_the_schema() -> None:
    assert set(IMAGE_TYPES) == set(get_args(ProductImageContentType))


@pytest.mark.parametrize(
    ("content_type", "extension"),
    [("image/jpeg", "jpg"), ("image/png", "png"), ("image/webp", "webp")],
)
def test_presign_generates_a_key_per_type(
    service: ProductImageService,
    content_type: str,
    extension: str,
) -> None:
    ticket = service.presign(_request(content_type))

    assert KEY_PATTERN.fullmatch(ticket.key)
    assert ticket.key.endswith(f".{extension}")
    assert ticket.fields["Content-Type"] == content_type


def test_presign_returns_the_public_urls(service: ProductImageService) -> None:
    ticket = service.presign(_request("image/png"))

    assert ticket.url == product_images_public_url()
    assert (
        ticket.image_url
        == product_image_url(ticket.key)
        == f"{ticket.url}/{ticket.key}"
    )
    assert ticket.fields["key"] == ticket.key
    assert ticket.max_bytes == settings.PRODUCT_IMAGE_MAX_BYTES
    assert ticket.expires_in == settings.PRODUCT_IMAGE_UPLOAD_EXPIRES_SECONDS


def test_ticket_accepts_a_valid_upload(service: ProductImageService) -> None:
    ticket = service.presign(_request("image/png"))

    assert post_upload(ticket, PNG_1PX).status_code == 204


def test_ticket_rejects_oversized_uploads(
    service: ProductImageService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PRODUCT_IMAGE_MAX_BYTES", 10)
    ticket = service.presign(_request("image/png", size=10))

    response = post_upload(ticket, PNG_1PX)

    assert response.status_code == 400
    assert "EntityTooLarge" in response.text


def test_ticket_rejects_a_different_content_type(service: ProductImageService) -> None:
    ticket = service.presign(_request("image/png"))
    ticket.fields["Content-Type"] = "image/jpeg"

    assert post_upload(ticket, PNG_1PX).status_code == 400


def test_ticket_rejects_a_different_key(service: ProductImageService) -> None:
    ticket = service.presign(_request("image/png"))
    ticket.fields["key"] = "products/other.png"

    assert post_upload(ticket, PNG_1PX).status_code == 400


def test_uploaded_object_keeps_content_type_and_cache_control(
    service: ProductImageService, images_bucket: str
) -> None:
    ticket = service.presign(_request("image/png"))
    post_upload(ticket, PNG_1PX)

    head = get_s3().head_object(Bucket=images_bucket, Key=ticket.key)

    assert head["ContentType"] == "image/png"
    assert head["CacheControl"] == CACHE_CONTROL
