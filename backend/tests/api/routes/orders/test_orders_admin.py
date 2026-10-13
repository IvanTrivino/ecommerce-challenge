import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from tests.utils.order import (
    add_to_cart,
    create_customer,
    create_stocked_product,
    place,
)

pytestmark = [pytest.mark.usefixtures("clean_orders"), pytest.mark.usefixtures("queue")]

ORDERS = f"{settings.API_V1_STR}/orders"


def place_order(
    client: TestClient, db: Session, *, stock: int = 5, quantity: int = 2
) -> dict:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db, stock=stock)
    add_to_cart(client, headers, product.id, quantity=quantity)
    response = place(client, headers)
    assert response.status_code == 200, response.text
    return {**response.json(), "product_id": str(product.id), "headers": headers}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", f"{ORDERS}/"),
        ("get", f"{ORDERS}/{uuid.uuid4()}"),
        ("post", f"{ORDERS}/{uuid.uuid4()}/cancel"),
        ("post", f"{ORDERS}/{uuid.uuid4()}/complete"),
    ],
)
def test_anonymous_is_unauthorized_and_customers_are_forbidden(
    client: TestClient, db: Session, method: str, path: str
) -> None:
    _, headers = create_customer(client, db)

    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers=headers).status_code == 403


def test_default_list_hides_drafts_and_state_filters_work(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    in_progress = place_order(client, db)
    cancelled = place_order(client, db)
    client.post(f"{ORDERS}/{cancelled['id']}/cancel", headers=superuser_token_headers)
    _, draft_headers = create_customer(client, db)
    add_to_cart(client, draft_headers, create_stocked_product(db).id)

    default = client.get(f"{ORDERS}/", headers=superuser_token_headers).json()
    only_draft = client.get(
        f"{ORDERS}/?state=draft", headers=superuser_token_headers
    ).json()
    two = client.get(
        f"{ORDERS}/?state=in_progress&state=cancelled&limit=1",
        headers=superuser_token_headers,
    ).json()

    assert {o["id"] for o in default["data"]} == {in_progress["id"], cancelled["id"]}
    assert default["count"] == 2
    assert [o["state"] for o in only_draft["data"]] == ["draft"]
    assert two["count"] == 2
    assert len(two["data"]) == 1
    assert "items" not in default["data"][0]


def test_draft_detail_shows_live_values_and_no_money(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db)
    cart = add_to_cart(client, headers, product.id)

    response = client.get(f"{ORDERS}/{cart['id']}", headers=superuser_token_headers)

    body = response.json()
    assert response.status_code == 200
    assert body["state"] == "draft"
    assert body["total_price"] is None
    assert body["items"][0]["name"] == product.name
    assert body["items"][0]["sku"] == product.sku
    assert body["items"][0]["unit_price"] is None


def test_cancel_restores_stock_and_a_second_cancel_conflicts(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    order = place_order(client, db, stock=5, quantity=2)
    url = f"{settings.API_V1_STR}/products/{order['product_id']}"
    assert client.get(url).json()["stock"] == 3

    cancelled = client.post(
        f"{ORDERS}/{order['id']}/cancel", headers=superuser_token_headers
    )
    again = client.post(
        f"{ORDERS}/{order['id']}/cancel", headers=superuser_token_headers
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["cancelled_at"] is not None
    assert again.status_code == 409
    assert again.json() == {"detail": "Only in-progress orders can be cancelled"}
    assert client.get(url).json()["stock"] == 5


def test_complete_and_then_neither_action_is_allowed(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    order = place_order(client, db)

    completed = client.post(
        f"{ORDERS}/{order['id']}/complete", headers=superuser_token_headers
    )
    cancel = client.post(
        f"{ORDERS}/{order['id']}/cancel", headers=superuser_token_headers
    )
    complete = client.post(
        f"{ORDERS}/{order['id']}/complete", headers=superuser_token_headers
    )

    assert completed.json()["state"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert cancel.status_code == 409
    assert complete.status_code == 409
    assert complete.json() == {"detail": "Only in-progress orders can be completed"}


def test_unknown_order_is_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    for method, suffix in [("get", ""), ("post", "/cancel"), ("post", "/complete")]:
        response = client.request(
            method, f"{ORDERS}/{uuid.uuid4()}{suffix}", headers=superuser_token_headers
        )
        assert response.status_code == 404
