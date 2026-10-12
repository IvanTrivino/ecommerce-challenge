import httpx
import pytest

from app.core.config import settings
from app.core.storage import (
    ensure_product_images_bucket,
    get_s3,
    head_object,
    product_images_public_url,
)
from tests.utils.storage import PNG_1PX


@pytest.mark.usefixtures("images_bucket")
def test_ensure_product_images_bucket_is_idempotent() -> None:
    ensure_product_images_bucket()
    ensure_product_images_bucket()


def test_public_read_is_limited_to_the_products_prefix(images_bucket: str) -> None:
    s3 = get_s3()
    s3.put_object(Bucket=images_bucket, Key="products/x.png", Body=PNG_1PX)
    s3.put_object(Bucket=images_bucket, Key="private/x.txt", Body=b"secret")
    base = product_images_public_url()

    assert httpx.get(f"{base}/products/x.png").status_code == 200
    assert httpx.get(f"{base}/private/x.txt").status_code == 403
    assert httpx.get(base).status_code == 403


def test_bucket_cors_allows_the_frontend_origin(images_bucket: str) -> None:
    rules = get_s3().get_bucket_cors(Bucket=images_bucket)["CORSRules"]

    assert rules[0]["AllowedOrigins"] == [settings.FRONTEND_HOST]


def test_public_url_uses_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "S3_PRODUCT_IMAGES_PUBLIC_URL", "https://cdn.example.com/"
    )

    assert product_images_public_url() == "https://cdn.example.com"


def test_public_url_falls_back_to_the_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "S3_PRODUCT_IMAGES_PUBLIC_URL", None)
    monkeypatch.setattr(settings, "S3_PRODUCT_IMAGES_BUCKET", "imgs")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://internal:9000")
    monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT_URL", "http://public:9000")
    assert product_images_public_url() == "http://public:9000/imgs"

    monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT_URL", None)
    assert product_images_public_url() == "http://internal:9000/imgs"


def test_public_url_uses_the_aws_form_without_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "S3_PRODUCT_IMAGES_PUBLIC_URL", None)
    monkeypatch.setattr(settings, "S3_PRODUCT_IMAGES_BUCKET", "imgs")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None)
    monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT_URL", None)
    monkeypatch.setattr(settings, "S3_REGION", "eu-west-1")

    assert product_images_public_url() == "https://imgs.s3.eu-west-1.amazonaws.com"


def test_head_object_returns_none_for_a_missing_key(images_bucket: str) -> None:
    assert head_object(images_bucket, "products/missing.png") is None
