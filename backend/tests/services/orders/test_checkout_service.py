import threading
import time
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PaymentRequiredError,
    ServiceUnavailableError,
)
from app.models import (
    Order,
    OrderNotification,
    OrderNotificationStatus,
    OrderState,
    OutboxEvent,
    Product,
    User,
)
from app.repositories import ProductRepository
from app.schemas import CartItemAdd, CartPublic
from tests.services.orders.conftest import (
    cart_service,
    checkout_service,
    load_user,
    place_request,
)
from tests.utils.cache import FakeRedis
from tests.utils.order import create_stocked_product
from tests.utils.payments import BlockingGateway, BrokenGateway, DecliningGateway
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
def queue() -> list[int]:
    return []


def stock_of(product: Product) -> int:
    with Session(engine) as s:
        loaded = s.get(Product, product.id)
        assert loaded is not None
        return loaded.stock


def count(model: type) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


def fill_cart(
    session: Session, user: User, *pairs: tuple[Product, int]
) -> tuple[Order, Decimal]:
    service = cart_service(session)
    cart = None
    for product, quantity in pairs:
        cart = service.add_item(
            user, CartItemAdd(product_id=product.id, quantity=quantity)
        )
    assert cart is not None and cart.id is not None
    return session.get_one(Order, cart.id), cart.total_price


def test_placing_fixes_values_decrements_stock_and_queues_the_email(
    db: Session,
    session: Session,
    user: User,
    queue: list[int],
    fake_cache: FakeRedis,
) -> None:
    a = create_stocked_product(db, price="10.00", stock=5, weight="0.500")
    a_name, a_sku = a.name, a.sku
    b = create_stocked_product(db, price="2.50", stock=3, weight=None)
    fill_cart(session, user, (a, 2), (b, 1))
    cart = cart_service(session).get_cart(user)
    fake_cache.data["cache:product:version"] = "before"

    order = checkout_service(session, enqueue=queue.append).place(
        user, place_request(cart)
    )

    assert order.state == OrderState.IN_PROGRESS
    assert order.total_price == Decimal("22.50")
    assert order.total_weight == Decimal("1.000")
    assert order.payment_reference == f"mock_{order.number}"
    assert order.placed_at is not None
    by_sku = {i.product_sku: i for i in order.items}
    assert by_sku[a_sku].unit_price == Decimal("10.00")
    assert by_sku[a_sku].unit_weight == Decimal("0.500")
    assert by_sku[a_sku].product_name == a_name
    assert by_sku[b.sku].unit_weight is None
    assert (stock_of(a), stock_of(b)) == (3, 2)

    with Session(engine) as s:
        [notification] = s.scalars(select(OrderNotification)).all()
        assert notification.kind == "placed"
        assert notification.status == OrderNotificationStatus.PENDING
        assert queue == [notification.id]
        delay = (notification.available_at - order.placed_at).total_seconds()
        assert 119 <= delay <= 121
    assert fake_cache.data["cache:product:version"] != "before"

    # Later product edits don't touch the placed order
    a_live = db.get_one(Product, a.id)
    db.refresh(a_live)
    a_live.price = Decimal("99.00")
    a_live.name = "Renamed"
    ProductRepository(db).save(a_live)
    session.refresh(order)
    assert order.total_price == Decimal("22.50")
    placed_a = next(i for i in order.items if i.product_sku == a_sku)
    assert placed_a.unit_price == Decimal("10.00")
    assert placed_a.name == a_name


def test_stock_changes_emit_no_search_events(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db)
    fill_cart(session, user, (product, 1))
    before = count(OutboxEvent)
    cart = cart_service(session).get_cart(user)

    checkout_service(session).place(user, place_request(cart))

    assert count(OutboxEvent) == before


def test_placing_twice_is_idempotent(
    db: Session, session: Session, user: User, queue: list[int]
) -> None:
    product = create_stocked_product(db, stock=5)
    fill_cart(session, user, (product, 2))
    cart = cart_service(session).get_cart(user)
    service = checkout_service(session, enqueue=queue.append)

    first = service.place(user, place_request(cart))
    second = service.place(user, place_request(cart))

    assert second.id == first.id
    assert second.state == OrderState.IN_PROGRESS
    assert second.total_price == first.total_price
    assert [i.id for i in second.items] == [i.id for i in first.items]
    assert stock_of(product) == 3
    assert count(OrderNotification) == 1
    assert len(queue) == 1


def test_a_changed_price_is_rejected_without_changes(
    db: Session, session: Session, user: User, queue: list[int]
) -> None:
    product = create_stocked_product(db, price="10.00", stock=5)
    order, total = fill_cart(session, user, (product, 2))
    cart = cart_service(session).get_cart(user)
    live = db.get_one(Product, product.id)
    live.price = Decimal("12.00")
    ProductRepository(db).save(live)
    service = checkout_service(session, enqueue=queue.append)

    with pytest.raises(ConflictError, match="Prices changed"):
        service.place(user, place_request(cart))

    session.refresh(order)
    assert order.state == OrderState.DRAFT
    assert order.items[0].unit_price is None
    assert stock_of(product) == 5
    assert count(OrderNotification) == 0

    fresh = cart_service(session).get_cart(user)
    assert fresh.total_price == Decimal("24.00")
    placed = service.place(user, place_request(fresh))
    assert placed.total_price == Decimal("24.00")


def test_an_empty_draft_cannot_be_placed(session: Session, user: User) -> None:
    product_cart = cart_service(session)
    # An emptied Draft stays: add then remove a line
    with Session(engine) as s:
        product = create_stocked_product(s)
    cart = product_cart.add_item(user, CartItemAdd(product_id=product.id))
    cart = product_cart.remove_item(user, cart.items[0].id)

    with pytest.raises(ConflictError, match="Your cart is empty"):
        checkout_service(session).place(user, place_request(cart))


def test_an_unavailable_line_blocks_the_order(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db, stock=5)
    order, _ = fill_cart(session, user, (product, 4))
    cart = cart_service(session).get_cart(user)
    live = db.get_one(Product, product.id)
    live.stock = 3
    ProductRepository(db).save(live)

    with pytest.raises(ConflictError, match="Some items in your cart are unavailable"):
        checkout_service(session).place(user, place_request(cart))

    session.refresh(order)
    assert order.state == OrderState.DRAFT
    assert stock_of(product) == 3


def test_a_soft_deleted_product_blocks_the_order(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db)
    fill_cart(session, user, (product, 1))
    cart = cart_service(session).get_cart(user)
    ProductRepository(db).delete(db.get_one(Product, product.id))

    with pytest.raises(ConflictError, match="unavailable"):
        checkout_service(session).place(user, place_request(cart))


def test_someone_elses_order_is_not_found(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db)
    fill_cart(session, user, (product, 1))
    cart = cart_service(session).get_cart(user)
    other = load_user(session, create_random_user(db))

    with pytest.raises(NotFoundError, match="Order not found"):
        checkout_service(session).place(other, place_request(cart))
    with pytest.raises(NotFoundError):
        checkout_service(session).place(
            user, place_request(cart, order_id=uuid.uuid4())
        )


@pytest.mark.parametrize(
    ("gateway", "error"),
    [
        (DecliningGateway(), PaymentRequiredError),
        (BrokenGateway(), ServiceUnavailableError),
    ],
)
def test_a_failed_charge_rolls_everything_back(
    db: Session,
    session: Session,
    user: User,
    queue: list[int],
    gateway: DecliningGateway | BrokenGateway,
    error: type[Exception],
) -> None:
    product = create_stocked_product(db, stock=5)
    order, _ = fill_cart(session, user, (product, 2))
    cart = cart_service(session).get_cart(user)

    with pytest.raises(error):
        checkout_service(session, gateway, queue.append).place(
            user, place_request(cart)
        )

    session.refresh(order)
    assert order.state == OrderState.DRAFT
    assert order.total_price is None
    assert order.items[0].unit_price is None
    assert stock_of(product) == 5
    assert count(OrderNotification) == 0
    assert queue == []


def test_a_failing_enqueue_does_not_fail_the_placement(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db)
    fill_cart(session, user, (product, 1))
    cart = cart_service(session).get_cart(user)

    def broken(_: int) -> None:
        raise ConnectionError("broker down")

    order = checkout_service(session, enqueue=broken).place(user, place_request(cart))

    assert order.state == OrderState.IN_PROGRESS
    with Session(engine) as s:
        [notification] = s.scalars(select(OrderNotification)).all()
        assert notification.status == OrderNotificationStatus.PENDING


def test_the_next_add_after_placement_starts_a_new_draft(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db)
    placed, _ = fill_cart(session, user, (product, 1))
    cart = cart_service(session).get_cart(user)
    checkout_service(session).place(user, place_request(cart))

    new_cart = cart_service(session).add_item(user, CartItemAdd(product_id=product.id))

    assert new_cart.id != placed.id
    assert len(new_cart.items) == 1


def test_two_customers_cannot_oversell_the_last_unit(db: Session) -> None:
    product = create_stocked_product(db, stock=1)
    users = [create_random_user(db) for _ in range(2)]
    carts = []
    for u in users:
        with Session(engine) as s:
            loaded = load_user(s, u)
            cart_service(s).add_item(loaded, CartItemAdd(product_id=product.id))
            carts.append(cart_service(s).get_cart(loaded))
    gateway = BlockingGateway()
    results: dict[int, object] = {}

    def run(index: int, charge_gateway: BlockingGateway) -> None:
        with Session(engine) as s:
            try:
                results[index] = (
                    checkout_service(s, charge_gateway)
                    .place(load_user(s, users[index]), place_request(carts[index]))
                    .id
                )
            except ConflictError as exc:
                results[index] = exc

    first = threading.Thread(target=run, args=(0, gateway))
    first.start()
    assert gateway.entered.wait(timeout=5)
    second = threading.Thread(target=run, args=(1, BlockingGateway()))
    second.start()
    time.sleep(0.3)
    assert second.is_alive()
    gateway.release.set()
    first.join(timeout=10)
    second.join(timeout=10)

    assert isinstance(results[0], uuid.UUID)
    assert isinstance(results[1], ConflictError)
    assert results[1].detail == "Some items in your cart are unavailable"
    assert stock_of(product) == 0


def place_after(barrier: threading.Barrier, user: User, cart: CartPublic) -> uuid.UUID:
    with Session(engine) as s:
        barrier.wait(timeout=5)
        return checkout_service(s).place(load_user(s, user), place_request(cart)).id


def test_carts_sharing_products_in_opposite_orders_do_not_deadlock(
    db: Session,
) -> None:
    a = create_stocked_product(db, stock=100)
    b = create_stocked_product(db, stock=100)
    users = [create_random_user(db) for _ in range(2)]
    orders = [(a, b), (b, a)]

    for _ in range(20):
        carts = []
        for u, (first, second) in zip(users, orders, strict=True):
            with Session(engine) as s:
                loaded = load_user(s, u)
                service = cart_service(s)
                service.add_item(loaded, CartItemAdd(product_id=first.id))
                carts.append(
                    service.add_item(loaded, CartItemAdd(product_id=second.id))
                )
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(place_after, barrier, users[i], carts[i]) for i in range(2)
            ]
            assert all(f.result(timeout=20) for f in futures)
