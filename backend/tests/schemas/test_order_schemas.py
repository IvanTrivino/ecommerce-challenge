import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import CartItem, Order, Product, User
from app.schemas import CartItemAdd, CartItemUpdate, OrderPublic, PlaceOrderRequest

ID = uuid.UUID("3f9a12c0-0000-4000-8000-000000000000")


@pytest.mark.parametrize("quantity", [0, 100])
def test_quantities_out_of_range_are_rejected(quantity: int) -> None:
    with pytest.raises(ValidationError):
        CartItemAdd(product_id=ID, quantity=quantity)
    with pytest.raises(ValidationError):
        CartItemUpdate(quantity=quantity)


@pytest.mark.parametrize("total", [Decimal("-1"), Decimal("1.001")])
def test_expected_total_must_be_a_non_negative_amount_in_cents(total: Decimal) -> None:
    with pytest.raises(ValidationError):
        PlaceOrderRequest(order_id=ID, expected_total=total)


def test_order_public_serializes_aliases_and_money_as_strings() -> None:
    user = User(id=uuid.uuid4(), email="a@example.com", password="x")
    product = Product(
        id=uuid.uuid4(), name="Mug", sku="MUG", price=Decimal("2.50"), stock=1
    )
    order = Order(
        id=uuid.uuid4(),
        user_uuid=user.id,
        user=user,
        currency="USD",
        state="in_progress",
        total_price=Decimal("5.00"),
        total_weight=Decimal("1.000"),
        placed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    order.items.append(
        CartItem(
            id=uuid.uuid4(),
            product_uuid=product.id,
            product=product,
            quantity=2,
            unit_price=Decimal("2.50"),
            unit_weight=Decimal("0.500"),
            product_name="Mug",
            product_sku="MUG",
        )
    )

    data = OrderPublic.model_validate(order).model_dump(mode="json")

    assert data["user_id"] == str(user.id)
    assert data["user_email"] == "a@example.com"
    assert data["number"] == order.number
    assert data["item_count"] == 2
    assert data["total_price"] == "5.00"
    assert data["items"][0]["product_id"] == str(product.id)
    assert data["items"][0]["line_total"] == "5.00"
    assert "product_uuid" not in data["items"][0]
    assert "user_uuid" not in data
