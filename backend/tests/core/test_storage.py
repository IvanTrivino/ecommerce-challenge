import httpx
import pytest

from app.core.config import settings
from app.core.storage import (
    ObjectChangedError,
    ObjectNotFoundError,
    ensure_product_images_bucket,
    ensure_product_imports_bucket,
    get_s3,
    head_object,
    iter_object_chunks,
    product_images_public_url,
)
from tests.utils.storage import PNG_1PX, internal_url


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


@pytest.mark.usefixtures("imports_bucket")
def test_ensure_product_imports_bucket_is_idempotent() -> None:
    ensure_product_imports_bucket()
    ensure_product_imports_bucket()


def test_imports_bucket_is_private(imports_bucket: str) -> None:
    get_s3().put_object(Bucket=imports_bucket, Key="imports/x.csv", Body=b"a,b\n")
    base = internal_url(f"{settings.S3_ENDPOINT_URL}/{imports_bucket}")

    assert httpx.get(f"{base}/imports/x.csv").status_code == 403
    assert httpx.get(base).status_code == 403


def test_imports_bucket_cors_allows_only_post(imports_bucket: str) -> None:
    rules = get_s3().get_bucket_cors(Bucket=imports_bucket)["CORSRules"]

    assert len(rules) == 1
    assert rules[0]["AllowedMethods"] == ["POST"]
    assert rules[0]["AllowedOrigins"] == [settings.FRONTEND_HOST]


def test_iter_object_chunks_streams_from_an_offset(imports_bucket: str) -> None:
    body = bytes(range(256)) * 800  # ~200 KB
    get_s3().put_object(Bucket=imports_bucket, Key="imports/big.csv", Body=body)
    etag = head_object(imports_bucket, "imports/big.csv").etag  # type: ignore[union-attr]
    assert etag

    def read(start: int) -> bytes:
        return b"".join(
            iter_object_chunks(
                imports_bucket,
                "imports/big.csv",
                start=start,
                etag=etag,
                chunk_size=64 * 1024,
            )
        )

    assert read(0) == body
    assert read(1000) == body[1000:]


def test_iter_object_chunks_fails_when_the_object_changed(imports_bucket: str) -> None:
    s3 = get_s3()
    s3.put_object(Bucket=imports_bucket, Key="imports/a.csv", Body=b"one")
    etag = head_object(imports_bucket, "imports/a.csv").etag  # type: ignore[union-attr]
    assert etag
    s3.put_object(Bucket=imports_bucket, Key="imports/a.csv", Body=b"two")

    with pytest.raises(ObjectChangedError):
        list(iter_object_chunks(imports_bucket, "imports/a.csv", start=0, etag=etag))


def test_iter_object_chunks_fails_for_a_missing_object(imports_bucket: str) -> None:
    with pytest.raises(ObjectNotFoundError):
        list(
            iter_object_chunks(
                imports_bucket, "imports/missing.csv", start=0, etag='"x"'
            )
        )


def test_head_object_returns_a_quoted_etag(imports_bucket: str) -> None:
    get_s3().put_object(Bucket=imports_bucket, Key="imports/e.csv", Body=b"x")

    stored = head_object(imports_bucket, "imports/e.csv")

    assert stored is not None
    assert stored.etag
    assert stored.etag.startswith('"')
