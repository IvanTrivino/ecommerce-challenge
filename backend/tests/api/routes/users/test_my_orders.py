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

MINE = f"{settings.API_V1_STR}/users/me/orders"


def test_anonymous_is_unauthorized(client: TestClient) -> None:
    assert client.get(MINE).status_code == 401
    assert client.get(f"{MINE}/{uuid.uuid4()}").status_code == 401


def test_lists_only_my_placed_orders_newest_first(
    client: TestClient, db: Session
) -> None:
    _, headers = create_customer(client, db)
    _, other_headers = create_customer(client, db)
    ids = []
    for _ in range(2):
        add_to_cart(client, headers, create_stocked_product(db).id)
        ids.append(place(client, headers).json()["id"])
    add_to_cart(client, other_headers, create_stocked_product(db).id)
    place(client, other_headers)
    draft = add_to_cart(client, headers, create_stocked_product(db).id)

    listed = client.get(MINE, headers=headers).json()

    assert [o["id"] for o in listed["data"]] == ids[::-1]
    assert listed["count"] == 2
    assert draft["id"] not in {o["id"] for o in listed["data"]}
    assert (
        client.get(f"{MINE}?limit=1&skip=1", headers=headers).json()["data"][0]["id"]
        == ids[0]
    )


def test_detail_of_my_order_includes_the_lines(client: TestClient, db: Session) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db)
    add_to_cart(client, headers, product.id, quantity=2)
    order = place(client, headers).json()

    response = client.get(f"{MINE}/{order['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json() == order


def test_drafts_and_other_customers_orders_are_not_found(
    client: TestClient, db: Session
) -> None:
    _, headers = create_customer(client, db)
    _, other_headers = create_customer(client, db)
    draft = add_to_cart(client, headers, create_stocked_product(db).id)
    add_to_cart(client, other_headers, create_stocked_product(db).id)
    theirs = place(client, other_headers).json()

    assert client.get(f"{MINE}/{draft['id']}", headers=headers).status_code == 404
    response = client.get(f"{MINE}/{theirs['id']}", headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}
