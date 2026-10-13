from decimal import Decimal
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Product, User
from app.repositories import ProductRepository
from tests.utils.product import create_random_category
from tests.utils.user import (
    create_random_user_with_password,
    user_authentication_headers,
)
from tests.utils.utils import random_lower_string


def create_customer(client: TestClient, db: Session) -> tuple[User, dict[str, str]]:
    """A fresh non-superuser and their auth headers (carts must not leak between tests)."""
    user, password = create_random_user_with_password(db)
    headers = user_authentication_headers(
        client=client, email=user.email, password=password
    )
    return user, headers


def create_stocked_product(
    db: Session,
    *,
    price: str = "10.00",
    stock: int = 5,
    weight: str | None = "0.500",
) -> Product:
    category = create_random_category(db)
    return ProductRepository(db).save(
        Product(
            name=random_lower_string(),
            sku=random_lower_string(),
            category_uuid=category.id,
            price=Decimal(price),
            stock=stock,
            weight=Decimal(weight) if weight is not None else None,
        )
    )


def add_to_cart(
    client: TestClient,
    headers: dict[str, str],
    product_id: object,
    quantity: int = 1,
) -> dict[str, Any]:
    response = client.post(
        f"{settings.API_V1_STR}/cart/items",
        headers=headers,
        json={"product_id": str(product_id), "quantity": quantity},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def place(client: TestClient, headers: dict[str, str]) -> httpx.Response:
    """GET /cart then POST /cart/place with its id and total_price."""
    cart = client.get(f"{settings.API_V1_STR}/cart/", headers=headers).json()
    return client.post(
        f"{settings.API_V1_STR}/cart/place",
        headers=headers,
        json={"order_id": cart["id"], "expected_total": cart["total_price"]},
    )
