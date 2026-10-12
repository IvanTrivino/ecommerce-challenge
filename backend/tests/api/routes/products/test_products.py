import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import product_images_public_url
from tests.utils.product import create_random_category, create_random_product
from tests.utils.storage import upload_image
from tests.utils.utils import random_lower_string

URL = f"{settings.API_V1_STR}/products"


def _payload(category_id: uuid.UUID) -> dict[str, object]:
    return {
        "name": "Sneakers",
        "sku": random_lower_string(),
        "category_uuid": str(category_id),
        "price": "59.90",
        "stock": 3,
    }


def test_reads_are_public(client: TestClient, db: Session) -> None:
    product = create_random_product(db)
    listing = client.get(
        f"{URL}/", params={"category_uuid": str(product.category_uuid)}
    )
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    single = client.get(f"{URL}/{product.id}")
    assert single.status_code == 200
    assert single.json()["sku"] == product.sku


def test_read_product_not_found(client: TestClient) -> None:
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/"), ("patch", f"/{uuid.uuid4()}"), ("delete", f"/{uuid.uuid4()}")],
)
def test_writes_require_authentication(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    method: str,
    path: str,
) -> None:
    anonymous = client.request(method, f"{URL}{path}", json={})
    assert anonymous.status_code == 401
    normal = client.request(
        method, f"{URL}{path}", json={}, headers=normal_user_token_headers
    )
    assert normal.status_code == 403


def test_superuser_crud_flow(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    category = create_random_category(db)
    created = client.post(
        f"{URL}/", json=_payload(category.id), headers=superuser_token_headers
    )
    assert created.status_code == 200
    product_id = created.json()["id"]

    assert client.get(f"{URL}/{product_id}").json()["name"] == "Sneakers"  # cached

    updated = client.patch(
        f"{URL}/{product_id}", json={"stock": 10}, headers=superuser_token_headers
    )
    assert updated.status_code == 200
    assert client.get(f"{URL}/{product_id}").json()["stock"] == 10  # invalidated

    deleted = client.delete(f"{URL}/{product_id}", headers=superuser_token_headers)
    assert deleted.status_code == 200
    assert client.get(f"{URL}/{product_id}").status_code == 404


@pytest.mark.usefixtures("images_bucket")
def test_product_image_flow(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    category = create_random_category(db)
    created = client.post(
        f"{URL}/", json=_payload(category.id), headers=superuser_token_headers
    )
    product_id = created.json()["id"]
    assert created.json()["image_url"] is None
    assert client.get(f"{URL}/{product_id}").json()["image_url"] is None  # cached

    key = upload_image()
    patched = client.patch(
        f"{URL}/{product_id}", json={"image_key": key}, headers=superuser_token_headers
    )
    assert patched.status_code == 200
    image_url = client.get(f"{URL}/{product_id}").json()["image_url"]  # invalidated
    assert image_url == f"{product_images_public_url()}/{key}"

    cleared = client.patch(
        f"{URL}/{product_id}", json={"image_key": None}, headers=superuser_token_headers
    )
    assert cleared.status_code == 200
    assert client.get(f"{URL}/{product_id}").json()["image_url"] is None


@pytest.mark.usefixtures("images_bucket")
def test_product_with_a_bad_image_key_is_rejected(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    category = create_random_category(db)
    payload = _payload(category.id) | {"image_key": "nope.png"}

    response = client.post(f"{URL}/", json=payload, headers=superuser_token_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image key"


def test_create_product_validation_and_conflict(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    product = create_random_product(db)
    duplicate = _payload(product.category_uuid) | {"sku": product.sku}
    r = client.post(f"{URL}/", json=duplicate, headers=superuser_token_headers)
    assert r.status_code == 409
    invalid = _payload(product.category_uuid) | {"price": "-1"}
    r = client.post(f"{URL}/", json=invalid, headers=superuser_token_headers)
    assert r.status_code == 422
