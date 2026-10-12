import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

URL = f"{settings.API_V1_STR}/products/images/presign"
BODY = {"content_type": "image/png", "size": 1000}


def test_presign_requires_authentication(client: TestClient) -> None:
    assert client.post(URL, json=BODY).status_code == 401


def test_presign_forbidden_for_normal_users(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.post(URL, headers=normal_user_token_headers, json=BODY)

    assert response.status_code == 403


@pytest.mark.usefixtures("images_bucket")
def test_presign_returns_an_upload_ticket(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.post(URL, headers=superuser_token_headers, json=BODY)

    assert response.status_code == 200
    ticket = response.json()
    assert set(ticket) == {
        "url",
        "fields",
        "key",
        "image_url",
        "max_bytes",
        "expires_in",
    }
    assert ticket["key"].startswith("products/")


@pytest.mark.parametrize(
    "body",
    [
        {"content_type": "image/svg+xml", "size": 1000},
        {"content_type": "image/png", "size": 0},
    ],
)
def test_presign_validates_the_request(
    client: TestClient, superuser_token_headers: dict[str, str], body: dict[str, object]
) -> None:
    response = client.post(URL, headers=superuser_token_headers, json=body)

    assert response.status_code == 422


def test_presign_rejects_files_over_the_limit(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    body = {"content_type": "image/png", "size": 6 * 1024 * 1024}

    response = client.post(URL, headers=superuser_token_headers, json=body)

    assert response.status_code == 400
    assert response.json()["detail"] == "Image must be 5 MB or smaller"
