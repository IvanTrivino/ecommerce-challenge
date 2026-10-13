import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps.orders import get_payments_gateway
from app.core.config import settings
from app.main import app
from app.models import Order, OrderNotification
from tests.utils.order import (
    add_to_cart,
    create_customer,
    create_stocked_product,
    place,
)
from tests.utils.payments import BrokenGateway, DecliningGateway

pytestmark = pytest.mark.usefixtures("clean_orders")

CART = f"{settings.API_V1_STR}/cart"


def test_add_review_and_place(
    client: TestClient, db: Session, queue: list[int]
) -> None:
    user, headers = create_customer(client, db)
    product = create_stocked_product(db, price="19.99", weight="0.250", stock=5)
    add_to_cart(client, headers, product.id, quantity=2)

    response = place(client, headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "in_progress"
    assert body["user_id"] == str(user.id)
    assert body["user_email"] == user.email
    assert body["total_price"] == "39.98"
    assert body["total_weight"] == "0.500"
    assert body["currency"] == "USD"
    assert body["item_count"] == 2
    assert body["payment_reference"] == f"mock_{body['number']}"
    [line] = body["items"]
    assert line["product_id"] == str(product.id)
    assert line["unit_price"] == "19.99"
    assert line["line_total"] == "39.98"
    assert len(queue) == 1

    cart = client.get(f"{CART}/", headers=headers).json()
    assert cart["id"] is None

    stock = client.get(f"{settings.API_V1_STR}/products/{product.id}").json()["stock"]
    assert stock == 3


def test_placing_again_returns_the_same_order(
    client: TestClient, db: Session, queue: list[int]
) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db)
    cart = add_to_cart(client, headers, product.id)
    body = {"order_id": cart["id"], "expected_total": cart["total_price"]}

    first = client.post(f"{CART}/place", headers=headers, json=body)
    second = client.post(f"{CART}/place", headers=headers, json=body)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(queue) == 1


def test_stale_total_is_a_conflict(client: TestClient, db: Session) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db, price="10.00")
    cart = add_to_cart(client, headers, product.id)

    response = client.post(
        f"{CART}/place",
        headers=headers,
        json={"order_id": cart["id"], "expected_total": "9.00"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Prices changed, please review your cart"}


def test_empty_cart_is_a_conflict(client: TestClient, db: Session) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db)
    cart = add_to_cart(client, headers, product.id)
    client.delete(f"{CART}/items/{cart['items'][0]['id']}", headers=headers)

    response = place(client, headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Your cart is empty"}


@pytest.mark.parametrize(
    ("gateway", "status", "detail"),
    [
        (DecliningGateway, 402, "Payment declined"),
        (BrokenGateway, 503, "Payment service unavailable"),
    ],
)
@pytest.mark.usefixtures("clear_overrides")
def test_payment_failures_leave_the_cart_untouched(
    client: TestClient,
    db: Session,
    queue: list[int],
    gateway: type,
    status: int,
    detail: str,
) -> None:
    _, headers = create_customer(client, db)
    product = create_stocked_product(db)
    cart = add_to_cart(client, headers, product.id)
    app.dependency_overrides[get_payments_gateway] = lambda: gateway()

    response = place(client, headers)

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert client.get(f"{CART}/", headers=headers).json() == cart
    assert queue == []
    assert db.scalars(select(OrderNotification)).all() == []


def test_another_customers_order_is_not_found(client: TestClient, db: Session) -> None:
    _, mine = create_customer(client, db)
    _, theirs = create_customer(client, db)
    product = create_stocked_product(db)
    cart = add_to_cart(client, mine, product.id)

    response = client.post(
        f"{CART}/place",
        headers=theirs,
        json={"order_id": cart["id"], "expected_total": cart["total_price"]},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}
    assert db.scalars(select(Order).where(Order.state == "in_progress")).all() == []


def test_anonymous_cannot_place(client: TestClient) -> None:
    response = client.post(
        f"{CART}/place",
        json={
            "order_id": "3f9a12c0-0000-4000-8000-000000000000",
            "expected_total": "1",
        },
    )
    assert response.status_code == 401
