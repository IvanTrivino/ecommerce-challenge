import threading
import time
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import ConflictError, NotFoundError
from app.models import Order, OrderState, Product, User
from app.repositories import OrderRepository, ProductRepository
from app.schemas import CartItemAdd, CartItemUpdate
from tests.services.orders.conftest import cart_service, load_user
from tests.utils.order import create_stocked_product
from tests.utils.user import create_random_user

pytestmark = pytest.mark.usefixtures("clean_orders")


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def user(db: Session, session: Session) -> User:
    return load_user(session, create_random_user(db))


@pytest.fixture
def product(db: Session) -> Product:
    return create_stocked_product(db, price="10.00", stock=5, weight="0.500")


def drafts(user_id: uuid.UUID) -> list[Order]:
    with Session(engine) as s:
        return list(s.scalars(select(Order).where(Order.user_uuid == user_id)).all())


def test_first_add_creates_a_draft_and_the_second_raises_the_quantity(
    session: Session, user: User, product: Product
) -> None:
    service = cart_service(session)

    first = service.add_item(user, CartItemAdd(product_id=product.id))
    second = service.add_item(user, CartItemAdd(product_id=product.id))

    assert first.id == second.id
    assert len(second.items) == 1
    assert second.items[0].quantity == 2
    assert second.item_count == 2
    assert len(drafts(user.id)) == 1
    assert drafts(user.id)[0].currency == settings.ORDER_CURRENCY


def test_get_cart_without_a_draft_is_empty_and_creates_nothing(
    session: Session, user: User
) -> None:
    cart = cart_service(session).get_cart(user)

    assert cart.id is None
    assert cart.items == []
    assert cart.can_place is False
    assert cart.total_price == Decimal("0.00")
    assert drafts(user.id) == []


def test_totals_use_live_prices_and_missing_weight_counts_as_zero(
    db: Session, session: Session, user: User, product: Product
) -> None:
    no_weight = create_stocked_product(db, price="1.25", weight=None)
    service = cart_service(session)
    service.add_item(user, CartItemAdd(product_id=product.id, quantity=3))
    cart = service.add_item(user, CartItemAdd(product_id=no_weight.id, quantity=2))

    assert cart.total_price == Decimal("32.50")
    assert cart.total_weight == Decimal("1.500")
    assert cart.can_place is True
    assert [i.line_total for i in cart.items] == [Decimal("30.00"), Decimal("2.50")]


def test_more_than_the_maximum_per_product_is_rejected(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db, stock=500)
    service = cart_service(session)
    service.add_item(user, CartItemAdd(product_id=product.id, quantity=90))

    with pytest.raises(ConflictError, match="at most 99 of this product"):
        service.add_item(user, CartItemAdd(product_id=product.id, quantity=10))

    assert service.get_cart(user).items[0].quantity == 90


def test_more_than_the_stock_is_rejected_and_the_cart_is_unchanged(
    session: Session, user: User, product: Product
) -> None:
    service = cart_service(session)
    service.add_item(user, CartItemAdd(product_id=product.id, quantity=4))

    with pytest.raises(ConflictError, match="Only 5 left in stock"):
        service.add_item(user, CartItemAdd(product_id=product.id, quantity=2))

    assert service.get_cart(user).items[0].quantity == 4


def test_a_failed_first_add_leaves_no_draft(
    session: Session, user: User, product: Product
) -> None:
    with pytest.raises(ConflictError):
        cart_service(session).add_item(
            user, CartItemAdd(product_id=product.id, quantity=6)
        )

    assert drafts(user.id) == []


def test_cart_is_full(
    db: Session,
    session: Session,
    user: User,
    product: Product,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CART_MAX_ITEMS", 2)
    service = cart_service(session)
    service.add_item(user, CartItemAdd(product_id=product.id))
    service.add_item(user, CartItemAdd(product_id=create_stocked_product(db).id))

    with pytest.raises(ConflictError, match="Your cart is full"):
        service.add_item(user, CartItemAdd(product_id=create_stocked_product(db).id))

    cart = service.add_item(user, CartItemAdd(product_id=product.id))
    assert cart.item_count == 3


def test_a_soft_deleted_product_cannot_be_added(
    db: Session, session: Session, user: User, product: Product
) -> None:
    ProductRepository(db).delete(product)

    with pytest.raises(NotFoundError, match="Product not found"):
        cart_service(session).add_item(user, CartItemAdd(product_id=product.id))
    with pytest.raises(NotFoundError):
        cart_service(session).add_item(user, CartItemAdd(product_id=uuid.uuid4()))


def test_update_sets_the_quantity_and_checks_stock(
    session: Session, user: User, product: Product
) -> None:
    service = cart_service(session)
    line = service.add_item(user, CartItemAdd(product_id=product.id)).items[0]

    cart = service.update_item(user, line.id, CartItemUpdate(quantity=4))
    assert cart.items[0].quantity == 4

    with pytest.raises(ConflictError, match="Only 5 left in stock"):
        service.update_item(user, line.id, CartItemUpdate(quantity=6))


def test_lowering_an_unavailable_line_is_always_allowed(
    db: Session, session: Session, user: User, product: Product
) -> None:
    service = cart_service(session)
    line = service.add_item(user, CartItemAdd(product_id=product.id, quantity=4)).items[
        0
    ]
    product.stock = 2
    ProductRepository(db).save(product)

    cart = service.update_item(user, line.id, CartItemUpdate(quantity=3))
    assert cart.items[0].available is False
    cart = service.update_item(user, line.id, CartItemUpdate(quantity=2))
    assert cart.items[0].available is True
    assert cart.can_place is True


def test_remove_keeps_the_empty_draft_for_the_next_add(
    session: Session, user: User, product: Product
) -> None:
    service = cart_service(session)
    cart = service.add_item(user, CartItemAdd(product_id=product.id))

    emptied = service.remove_item(user, cart.items[0].id)
    assert emptied.items == []
    assert emptied.id == cart.id
    assert emptied.can_place is False

    again = service.add_item(user, CartItemAdd(product_id=product.id))
    assert again.id == cart.id
    assert len(drafts(user.id)) == 1


def test_another_users_line_is_not_found(
    db: Session, session: Session, user: User, product: Product
) -> None:
    other = load_user(session, create_random_user(db))
    service = cart_service(session)
    line = service.add_item(user, CartItemAdd(product_id=product.id)).items[0]
    service.add_item(other, CartItemAdd(product_id=product.id))

    with pytest.raises(NotFoundError, match="Cart item not found"):
        service.update_item(other, line.id, CartItemUpdate(quantity=2))
    with pytest.raises(NotFoundError, match="Cart item not found"):
        service.remove_item(other, line.id)


def test_update_and_remove_without_a_draft_are_not_found(
    session: Session, user: User
) -> None:
    service = cart_service(session)
    with pytest.raises(NotFoundError, match="Cart item not found"):
        service.update_item(user, uuid.uuid4(), CartItemUpdate(quantity=1))
    with pytest.raises(NotFoundError, match="Cart item not found"):
        service.remove_item(user, uuid.uuid4())


def test_a_soft_deleted_product_makes_its_line_unavailable(
    db: Session, session: Session, user: User, product: Product
) -> None:
    other = create_stocked_product(db, price="2.00", weight="1.000")
    service = cart_service(session)
    service.add_item(user, CartItemAdd(product_id=product.id, quantity=2))
    service.add_item(user, CartItemAdd(product_id=other.id))
    ProductRepository(db).delete(product)

    cart = service.get_cart(user)

    gone, kept = cart.items
    assert (gone.available, gone.available_stock) == (False, 0)
    assert kept.available is True
    assert cart.total_price == Decimal("2.00")
    assert cart.total_weight == Decimal("1.000")
    assert cart.item_count == 3
    assert cart.can_place is False


def test_stock_below_the_quantity_makes_the_line_unavailable(
    db: Session, session: Session, user: User, product: Product
) -> None:
    service = cart_service(session)
    service.add_item(user, CartItemAdd(product_id=product.id, quantity=4))
    product.stock = 1
    ProductRepository(db).save(product)

    cart = service.get_cart(user)

    assert cart.items[0].available is False
    assert cart.items[0].available_stock == 1
    assert cart.total_price == Decimal("0.00")
    assert cart.can_place is False


def test_concurrent_first_adds_create_one_draft(db: Session) -> None:
    product = create_stocked_product(db, stock=50)
    user = create_random_user(db)
    user_id = user.id
    barrier = threading.Barrier(10)

    def add() -> None:
        with Session(engine) as s:
            barrier.wait(timeout=5)
            cart_service(s).add_item(
                load_user(s, user), CartItemAdd(product_id=product.id)
            )

    with ThreadPoolExecutor(10) as pool:
        for future in [pool.submit(add) for _ in range(10)]:
            future.result(timeout=20)

    [draft] = drafts(user_id)
    assert len(draft.items) == 1
    assert draft.items[0].quantity == 10


def test_a_cart_write_during_placement_lands_in_a_new_draft(
    db: Session, product: Product
) -> None:
    user = create_random_user(db)
    with Session(engine) as seed:
        cart_service(seed).add_item(
            load_user(seed, user), CartItemAdd(product_id=product.id)
        )

    with Session(engine) as placer:
        order = OrderRepository(placer).lock_draft(user.id)
        assert order is not None
        order.state = OrderState.IN_PROGRESS.value
        order.placed_at = datetime.now(UTC)
        order.total_price = Decimal("10.00")
        order.total_weight = Decimal("0.500")
        placer.flush()

        def add() -> None:
            with Session(engine) as s:
                cart_service(s).add_item(
                    load_user(s, user), CartItemAdd(product_id=product.id)
                )

        thread = threading.Thread(target=add)
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive()
        placer.commit()
        thread.join(timeout=10)

    placed, draft = sorted(drafts(user.id), key=lambda o: o.state != "in_progress")
    assert placed.state == OrderState.IN_PROGRESS
    assert [i.quantity for i in placed.items] == [1]
    assert draft.state == OrderState.DRAFT
    assert [i.quantity for i in draft.items] == [1]
