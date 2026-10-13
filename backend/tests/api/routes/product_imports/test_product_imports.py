import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.imports import EXAMPLE_CSV
from tests.utils.storage import post_upload

URL = f"{settings.API_V1_STR}/product-imports"
ID = uuid.uuid4()

ENDPOINTS = [
    ("post", f"{URL}/presign", {"filename": "a.csv", "size": 10}),
    ("post", f"{URL}/", {"key": "imports/x.csv", "filename": "a.csv"}),
    ("get", f"{URL}/", None),
    ("get", f"{URL}/{ID}", None),
    ("get", f"{URL}/{ID}/errors", None),
    ("post", f"{URL}/{ID}/retry", None),
]


@pytest.fixture(autouse=True)
def queue(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    queued: list[uuid.UUID] = []

    def enqueue(import_id: uuid.UUID) -> str:
        queued.append(import_id)
        return "task-id"

    monkeypatch.setattr("app.api.deps.product_imports.enqueue_product_import", enqueue)
    return queued


@pytest.mark.parametrize(("method", "url", "body"), ENDPOINTS)
def test_anonymous_requests_are_rejected(
    client: TestClient, method: str, url: str, body: dict[str, object] | None
) -> None:
    assert client.request(method, url, json=body).status_code == 401


@pytest.mark.parametrize(("method", "url", "body"), ENDPOINTS)
def test_normal_users_are_forbidden(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    method: str,
    url: str,
    body: dict[str, object] | None,
) -> None:
    response = client.request(method, url, json=body, headers=normal_user_token_headers)

    assert response.status_code == 403


def test_presign_validates_the_request(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    bad_name = client.post(
        f"{URL}/presign",
        json={"filename": "report.xlsx", "size": 10},
        headers=superuser_token_headers,
    )
    too_big = client.post(
        f"{URL}/presign",
        json={"filename": "a.csv", "size": 11 * 1024 * 1024},
        headers=superuser_token_headers,
    )
    empty = client.post(
        f"{URL}/presign",
        json={"filename": "a.csv", "size": 0},
        headers=superuser_token_headers,
    )

    assert bad_name.status_code == 422
    assert empty.status_code == 422
    assert too_big.status_code == 400
    assert too_big.json()["detail"] == "CSV must be 10 MB or smaller"


@pytest.mark.usefixtures("imports_bucket")
def test_full_flow(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    queue: list[uuid.UUID],
) -> None:
    body = EXAMPLE_CSV.read_bytes()
    presign = client.post(
        f"{URL}/presign",
        json={"filename": "example.csv", "size": len(body)},
        headers=superuser_token_headers,
    )
    assert presign.status_code == 200
    ticket = presign.json()
    assert set(ticket) == {"url", "fields", "key", "max_bytes", "expires_in"}
    assert ticket["url"].endswith(f"/{settings.S3_PRODUCT_IMPORTS_BUCKET}")

    class Ticket:
        url = ticket["url"]
        fields = ticket["fields"]

    assert post_upload(Ticket, body).status_code == 204  # type: ignore[arg-type]

    start = client.post(
        f"{URL}/",
        json={"key": ticket["key"], "filename": "example.csv"},
        headers=superuser_token_headers,
    )
    assert start.status_code == 202
    created = start.json()
    assert created["status"] == "pending"
    assert created["progress"] == 0
    assert created["total_bytes"] == len(body)
    assert created["created_by_email"] == settings.FIRST_SUPERUSER
    assert created["can_retry"] is False
    assert queue == [uuid.UUID(created["id"])]

    again = client.post(
        f"{URL}/",
        json={"key": ticket["key"], "filename": "example.csv"},
        headers=superuser_token_headers,
    )
    assert again.status_code == 200
    assert again.json()["id"] == created["id"]
    assert len(queue) == 1

    listing = client.get(f"{URL}/", headers=superuser_token_headers).json()
    assert listing["count"] == 1
    assert listing["data"][0]["id"] == created["id"]
    detail = client.get(f"{URL}/{created['id']}", headers=superuser_token_headers)
    assert detail.status_code == 200
    errors = client.get(
        f"{URL}/{created['id']}/errors", headers=superuser_token_headers
    )
    assert errors.json() == {"data": [], "count": 0, "truncated": False}

    retry = client.post(f"{URL}/{created['id']}/retry", headers=superuser_token_headers)
    assert retry.status_code == 409
    assert retry.json()["detail"] == "Import cannot be retried"


def test_unknown_import_is_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    for suffix in ("", "/errors"):
        response = client.get(f"{URL}/{ID}{suffix}", headers=superuser_token_headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Import not found"


def test_start_with_an_invalid_key(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{URL}/",
        json={"key": "imports/../x.csv", "filename": "a.csv"},
        headers=superuser_token_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid import file"
