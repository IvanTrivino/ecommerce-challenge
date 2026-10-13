import threading
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.core.exceptions import ConflictError, NotFoundError
from app.models import (
    Order,
    OrderNotification,
    OrderNotificationKind,
    OrderState,
    Product,
    User,
)
from app.repositories import ProductRepository
from app.schemas import CartItemAdd
from tests.services.orders.conftest import (
    cart_service,
    load_user,
    order_service,
    placed_order,
)
from tests.utils.cache import FakeRedis
from tests.utils.order import create_stocked_product
from tests.utils.user import create_random_user

pytestmark = pytest.mark.usefixtures("clean_orders")

VERSION_KEY = "cache:product:version"


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def user(db: Session, session: Session) -> User:
    return load_user(session, create_random_user(db))


def stock_of(product: Product) -> int:
    with Session(engine) as s:
        loaded = s.get(Product, product.id)
        assert loaded is not None
        return loaded.stock


def notifications(order: Order) -> list[OrderNotification]:
    with Session(engine) as s:
        return list(
            s.scalars(
                select(OrderNotification)
                .where(OrderNotification.order_uuid == order.id)
                .order_by(OrderNotification.id)
            )
        )


def test_cancel_restocks_and_queues_the_email(
    db: Session, session: Session, user: User, fake_cache: FakeRedis
) -> None:
    product = create_stocked_product(db, stock=5)
    order = placed_order(session, user, (product, 2))
    assert stock_of(product) == 3
    queue: list[int] = []
    fake_cache.data[VERSION_KEY] = "before"

    cancelled = order_service(session, enqueue=queue.append).cancel(order.id)

    assert cancelled.state == OrderState.CANCELLED
    assert cancelled.cancelled_at is not None
    assert cancelled.payment_reference == order.payment_reference
    assert stock_of(product) == 5
    [_, notification] = notifications(order)
    assert notification.kind == OrderNotificationKind.CANCELLED
    assert queue == [notification.id]
    assert fake_cache.data[VERSION_KEY] != "before"


def test_a_second_cancel_conflicts_and_restocks_once(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db, stock=5)
    order = placed_order(session, user, (product, 2))
    service = order_service(session)
    service.cancel(order.id)

    with pytest.raises(ConflictError, match="Only in-progress orders can be cancelled"):
        service.cancel(order.id)

    assert stock_of(product) == 5
    assert len(notifications(order)) == 2


def test_cancel_restocks_a_product_deleted_after_placement(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db, stock=5)
    order = placed_order(session, user, (product, 2))
    ProductRepository(db).delete(db.get_one(Product, product.id))

    order_service(session).cancel(order.id)

    assert stock_of(product) == 5


def test_complete_leaves_stock_and_cache_alone(
    db: Session, session: Session, user: User, fake_cache: FakeRedis
) -> None:
    product = create_stocked_product(db, stock=5)
    order = placed_order(session, user, (product, 2))
    queue: list[int] = []
    fake_cache.data[VERSION_KEY] = "before"

    completed = order_service(session, enqueue=queue.append).complete(order.id)

    assert completed.state == OrderState.COMPLETED
    assert completed.completed_at is not None
    assert stock_of(product) == 3
    assert fake_cache.data[VERSION_KEY] == "before"
    [_, notification] = notifications(order)
    assert notification.kind == OrderNotificationKind.COMPLETED
    assert queue == [notification.id]


@pytest.mark.parametrize("action", ["cancel", "complete"])
@pytest.mark.parametrize("final", ["completed", "cancelled"])
def test_final_orders_cannot_change_again(
    db: Session, session: Session, user: User, action: str, final: str
) -> None:
    product = create_stocked_product(db)
    order = placed_order(session, user, (product, 1))
    service = order_service(session)
    getattr(service, "complete" if final == "completed" else "cancel")(order.id)

    with pytest.raises(ConflictError):
        getattr(service, action)(order.id)


@pytest.mark.parametrize("action", ["cancel", "complete"])
def test_a_draft_cannot_be_cancelled_or_completed(
    db: Session, session: Session, user: User, action: str
) -> None:
    product = create_stocked_product(db)
    cart = cart_service(session).add_item(user, CartItemAdd(product_id=product.id))
    assert cart.id is not None

    with pytest.raises(ConflictError):
        getattr(order_service(session), action)(cart.id)


def test_unknown_orders_are_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        order_service(session).cancel(uuid.uuid4())
    with pytest.raises(NotFoundError):
        order_service(session).complete(uuid.uuid4())
    with pytest.raises(NotFoundError):
        order_service(session).get(uuid.uuid4())


@pytest.mark.parametrize("pair", [("cancel", "cancel"), ("cancel", "complete")])
def test_concurrent_transitions_have_one_winner(
    db: Session, session: Session, user: User, pair: tuple[str, str]
) -> None:
    product = create_stocked_product(db, stock=5)
    order = placed_order(session, user, (product, 2))
    barrier = threading.Barrier(2)

    def run(action: str) -> str:
        with Session(engine) as s:
            service = order_service(s)
            barrier.wait(timeout=5)
            try:
                getattr(service, action)(order.id)
            except ConflictError:
                return "conflict"
            return "ok"

    with ThreadPoolExecutor(2) as pool:
        results = [f.result(timeout=15) for f in [pool.submit(run, a) for a in pair]]

    assert sorted(results) == ["conflict", "ok"]
    winner = pair[results.index("ok")]
    assert stock_of(product) == (5 if winner == "cancel" else 3)
    assert len(notifications(order)) == 2


def test_listing_hides_drafts_by_default(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db, stock=5)
    placed = placed_order(session, user, (product, 1))
    other = load_user(session, create_random_user(db))
    cart_service(session).add_item(other, CartItemAdd(product_id=product.id))
    service = order_service(session)

    default = service.list_orders(None, skip=0, limit=10)
    drafts = service.list_orders(["draft"], skip=0, limit=10)

    assert [o.id for o in default.data] == [placed.id]
    assert default.count == 1
    assert [o.user_email for o in drafts.data] == [other.email]


def test_customers_only_see_their_placed_orders(
    db: Session, session: Session, user: User
) -> None:
    product = create_stocked_product(db, stock=5)
    mine = placed_order(session, user, (product, 1))
    other = load_user(session, create_random_user(db))
    theirs = placed_order(session, other, (product, 1))
    cart_service(session).add_item(user, CartItemAdd(product_id=product.id))
    service = order_service(session)

    listed = service.list_for_user(user, skip=0, limit=10)

    assert [o.id for o in listed.data] == [mine.id]
    assert listed.count == 1
    assert service.get_for_user(user, mine.id).id == mine.id
    with pytest.raises(NotFoundError):
        service.get_for_user(user, theirs.id)
    draft = cart_service(session).get_cart(user)
    assert draft.id is not None
    with pytest.raises(NotFoundError):
        service.get_for_user(user, draft.id)
