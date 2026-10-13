from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import CartItem, Order, OrderState, Product, User
from tests.utils.order import create_stocked_product
from tests.utils.user import create_random_user

pytestmark = pytest.mark.usefixtures("clean_orders")


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def user(db: Session) -> User:
    return create_random_user(db)


@pytest.fixture
def product(db: Session) -> Product:
    return create_stocked_product(db)


def make_order(user: User, **kwargs: object) -> Order:
    return Order(user_uuid=user.id, currency="USD", **kwargs)  # type: ignore[arg-type]


def constraint(exc: IntegrityError) -> str:
    return str(exc.orig.diag.constraint_name)  # type: ignore[union-attr]


def test_second_draft_for_the_same_user_is_rejected(
    session: Session, user: User
) -> None:
    session.add(make_order(user))
    session.commit()
    session.add(make_order(user))
    with pytest.raises(IntegrityError) as exc:
        session.commit()
    assert constraint(exc.value) == "ux_order_user_draft"


def test_a_new_draft_is_allowed_after_the_first_is_placed(
    session: Session, user: User
) -> None:
    first = make_order(user)
    session.add(first)
    session.commit()
    first.state = OrderState.IN_PROGRESS.value
    first.placed_at = datetime.now(UTC)
    first.total_price = Decimal("1.00")
    first.total_weight = Decimal("0.000")
    session.add(make_order(user))
    session.commit()
    assert session.query(Order).filter_by(user_uuid=user.id).count() == 2


def test_placed_order_requires_totals(session: Session, user: User) -> None:
    session.add(make_order(user, state=OrderState.IN_PROGRESS.value))
    with pytest.raises(IntegrityError) as exc:
        session.commit()
    assert constraint(exc.value) == "ck_order_placed_totals"


@pytest.mark.parametrize("quantity", [0, 100])
def test_quantity_must_be_between_1_and_99(
    session: Session, user: User, product: Product, quantity: int
) -> None:
    order = make_order(user)
    order.items.append(CartItem(product_uuid=product.id, quantity=quantity))
    session.add(order)
    with pytest.raises(IntegrityError) as exc:
        session.commit()
    assert constraint(exc.value) == "ck_cart_item_quantity"


def test_a_product_appears_once_per_order(
    session: Session, user: User, product: Product
) -> None:
    order = make_order(user)
    order.items.append(CartItem(product_uuid=product.id, quantity=1))
    order.items.append(CartItem(product_uuid=product.id, quantity=2))
    session.add(order)
    with pytest.raises(IntegrityError) as exc:
        session.commit()
    assert constraint(exc.value) == "uq_cart_item_order_product"


def test_number_and_item_count(session: Session, user: User, db: Session) -> None:
    order = make_order(user)
    order.items.append(CartItem(product_uuid=create_stocked_product(db).id, quantity=2))
    order.items.append(CartItem(product_uuid=create_stocked_product(db).id, quantity=3))
    session.add(order)
    session.commit()
    assert order.number == order.id.hex[:8].upper()
    assert len(order.number) == 8
    assert order.item_count == 5


def test_line_names_are_live_until_fixed(
    session: Session, user: User, product: Product
) -> None:
    order = make_order(user)
    item = CartItem(product_uuid=product.id, quantity=1)
    order.items.append(item)
    session.add(order)
    session.commit()
    live_product = session.get(Product, product.id)
    assert live_product is not None
    assert item.name == live_product.name
    assert item.sku == live_product.sku
    assert item.line_total is None

    original_name, original_sku = live_product.name, live_product.sku
    item.product_name, item.product_sku = original_name, original_sku
    item.unit_price = Decimal("10.00")
    live_product.name = "Renamed"
    live_product.sku = "renamed-sku"
    session.commit()
    assert item.name == original_name
    assert item.sku == original_sku
    assert item.line_total == Decimal("10.00")
