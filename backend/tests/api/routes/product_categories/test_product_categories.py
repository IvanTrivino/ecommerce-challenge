import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from tests.utils.product import create_random_category
from tests.utils.utils import random_lower_string

URL = f"{settings.API_V1_STR}/product-categories"


def test_reads_are_public(client: TestClient, db: Session) -> None:
    category = create_random_category(db)
    listing = client.get(f"{URL}/")
    assert listing.status_code == 200
    assert category.id.hex in {c["id"].replace("-", "") for c in listing.json()["data"]}
    assert client.get(f"{URL}/{category.id}").json()["code"] == category.code
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404


def test_writes_require_superuser(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    body = {"name": "Shoes", "code": random_lower_string()[:20]}
    assert client.post(f"{URL}/", json=body).status_code == 401
    r = client.post(f"{URL}/", json=body, headers=normal_user_token_headers)
    assert r.status_code == 403


def test_superuser_crud_flow(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    name = random_lower_string()
    body = {"name": name, "code": random_lower_string()[:20]}
    created = client.post(f"{URL}/", json=body, headers=superuser_token_headers)
    assert created.status_code == 200
    category_id = created.json()["id"]

    assert client.get(f"{URL}/{category_id}").json()["name"] == name  # cached
    boots = random_lower_string()
    updated = client.patch(
        f"{URL}/{category_id}", json={"name": boots}, headers=superuser_token_headers
    )
    assert updated.status_code == 200
    assert client.get(f"{URL}/{category_id}").json()["name"] == boots  # invalidated

    deleted = client.delete(f"{URL}/{category_id}", headers=superuser_token_headers)
    assert deleted.status_code == 200
    assert client.get(f"{URL}/{category_id}").status_code == 404
