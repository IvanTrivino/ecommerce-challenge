import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Order
from tests.utils.order import add_to_cart, create_customer, create_stocked_product

pytestmark = pytest.mark.usefixtures("clean_orders")

CART = f"{settings.API_V1_STR}/cart"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", f"{CART}/"),
        ("post", f"{CART}/items"),
        ("patch", f"{CART}/items/{uuid.uuid4()}"),
        ("delete", f"{CART}/items/{uuid.uuid4()}"),
    ],
)
def test_anonymous_requests_are_unauthorized(
    client: TestClient, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 401


def test_empty_cart_does_not_create_a_draft(client: TestClient, db: Session) -> None:
    user, headers = create_customer(client, db)

    response = client.get(f"{CART}/", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": None,
        "items": [],
        "item_count": 0,
        "total_price": "0.00",
        "total_weight": "0.000",
        "can_place": False,
    }
    assert db.scalars(select(Order).where(Order.user_uuid == user.id)).all() == []


def test_add_update_and_remove_round_trip(client: TestClient, db: Session) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db, price="19.99", weight="0.250")

    cart = add_to_cart(client, headers, product.id, quantity=2)

    assert cart["item_count"] == 2
    assert cart["total_price"] == "39.98"
    assert cart["total_weight"] == "0.500"
    assert cart["can_place"] is True
    [line] = cart["items"]
    assert line["product_id"] == str(product.id)
    assert line["name"] == product.name
    assert line["sku"] == product.sku
    assert line["image_url"] is None
    assert line["unit_price"] == "19.99"
    assert line["line_total"] == "39.98"
    assert line["available"] is True
    assert line["available_stock"] == 5

    updated = client.patch(
        f"{CART}/items/{line['id']}", headers=headers, json={"quantity": 3}
    )
    assert updated.status_code == 200
    assert updated.json()["total_price"] == "59.97"

    read = client.get(f"{CART}/", headers=headers)
    assert read.json() == updated.json()

    removed = client.delete(f"{CART}/items/{line['id']}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["items"] == []
    assert removed.json()["id"] == cart["id"]


@pytest.mark.parametrize("quantity", [0, 100])
def test_invalid_quantity_is_unprocessable(
    client: TestClient, db: Session, quantity: int
) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db)

    response = client.post(
        f"{CART}/items",
        headers=headers,
        json={"product_id": str(product.id), "quantity": quantity},
    )

    assert response.status_code == 422


def test_unknown_product_is_not_found(client: TestClient, db: Session) -> None:
    _, headers = create_customer(client, db)

    response = client.post(
        f"{CART}/items", headers=headers, json={"product_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


def test_over_stock_is_a_conflict(client: TestClient, db: Session) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db, stock=2)

    response = client.post(
        f"{CART}/items",
        headers=headers,
        json={"product_id": str(product.id), "quantity": 3},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only 2 left in stock"}


def test_a_line_of_another_customer_is_not_found(
    client: TestClient, db: Session
) -> None:
    _, mine = create_customer(client, db)
    _, theirs = create_customer(client, db)
    product = create_stocked_product(db)
    line = add_to_cart(client, mine, product.id)["items"][0]
    add_to_cart(client, theirs, product.id)

    patch = client.patch(
        f"{CART}/items/{line['id']}", headers=theirs, json={"quantity": 2}
    )
    delete = client.delete(f"{CART}/items/{line['id']}", headers=theirs)

    assert patch.status_code == 404
    assert delete.status_code == 404
    assert patch.json() == {"detail": "Cart item not found"}
