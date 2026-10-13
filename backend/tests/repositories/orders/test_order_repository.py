import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import Order, OrderState, User
from app.repositories import OrderRepository
from tests.utils.user import create_random_user

pytestmark = pytest.mark.usefixtures("clean_orders")


@pytest.fixture
def user(db: Session) -> User:
    return create_random_user(db)


def place_in_session(order: Order, *, placed_at: datetime | None = None) -> None:
    order.state = OrderState.IN_PROGRESS.value
    order.placed_at = placed_at or datetime.now(UTC)
    order.total_price = Decimal("1.00")
    order.total_weight = Decimal("0.000")


def new_order(
    session: Session,
    user: User,
    state: OrderState = OrderState.DRAFT,
    placed_at: datetime | None = None,
) -> Order:
    order = Order(user_uuid=user.id, currency="USD")
    session.add(order)
    if state != OrderState.DRAFT:
        place_in_session(order, placed_at=placed_at)
        order.state = state.value
    session.commit()
    return order


def test_create_draft_twice_at_the_same_time_creates_one(user: User) -> None:
    barrier = threading.Barrier(2)

    def create() -> Order | None:
        with Session(engine) as session:
            repo = OrderRepository(session)
            barrier.wait(timeout=5)
            order = repo.create_draft(user.id, "USD")
            session.commit()
            return order

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))

    assert sorted(r is None for r in results) == [False, True]
    with Session(engine) as session:
        drafts = session.scalars(select(Order).where(Order.user_uuid == user.id)).all()
        assert len(drafts) == 1


def test_lock_draft_waits_and_rechecks_the_state(user: User) -> None:
    with Session(engine) as a, Session(engine) as b:
        new_order(a, user)
        draft = OrderRepository(a).lock_draft(user.id)
        assert draft is not None
        place_in_session(draft)
        a.flush()

        # B already holds the order in its identity map as a Draft
        assert OrderRepository(b).get_draft(user.id) is not None
        result: list[Order | None] = []
        thread = threading.Thread(
            target=lambda: result.append(OrderRepository(b).lock_draft(user.id))
        )
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive()
        a.commit()
        thread.join(timeout=5)

        assert result == [None]


def test_lock_returns_fresh_values_after_waiting(user: User) -> None:
    with Session(engine) as a, Session(engine) as b:
        order = new_order(a, user)
        a_order = OrderRepository(a).lock(order.id)
        assert a_order is not None
        place_in_session(a_order)
        a.flush()

        b_order = OrderRepository(b).get(order.id)
        assert b_order is not None
        assert b_order.state == OrderState.DRAFT
        result: list[Order | None] = []
        thread = threading.Thread(
            target=lambda: result.append(OrderRepository(b).lock(order.id))
        )
        thread.start()
        time.sleep(0.3)
        a.commit()
        thread.join(timeout=5)

        assert result[0] is b_order
        assert b_order.state == OrderState.IN_PROGRESS


def test_lock_of_another_users_order_returns_none(db: Session, user: User) -> None:
    other = create_random_user(db)
    with Session(engine) as session:
        order = new_order(session, user)
        repo = OrderRepository(session)
        assert repo.lock(order.id, user_id=other.id) is None
        assert repo.lock(order.id, user_id=user.id) is not None


def test_get_draft_never_creates_one(user: User) -> None:
    with Session(engine) as session:
        assert OrderRepository(session).get_draft(user.id) is None
        assert session.scalars(select(Order)).all() == []


def test_user_listing_is_placed_only_newest_first(db: Session, user: User) -> None:
    now = datetime.now(UTC)
    other = create_random_user(db)
    with Session(engine) as session:
        old = new_order(session, user, OrderState.COMPLETED, now - timedelta(days=2))
        new = new_order(session, user, OrderState.IN_PROGRESS, now)
        new_order(session, other, OrderState.IN_PROGRESS, now)
        draft_owner = create_random_user(db)
        new_order(session, draft_owner)

        repo = OrderRepository(session)
        assert [o.id for o in repo.list_placed_for_user(user.id, skip=0, limit=10)] == [
            new.id,
            old.id,
        ]
        assert repo.count_placed_for_user(user.id) == 2
        assert repo.count_placed_for_user(draft_owner.id) == 0
        assert repo.get_placed_for_user(new.id, user.id) is not None
        assert repo.get_placed_for_user(new.id, other.id) is None


def test_get_placed_for_user_ignores_drafts(user: User) -> None:
    with Session(engine) as session:
        draft = new_order(session, user)
        assert OrderRepository(session).get_placed_for_user(draft.id, user.id) is None


def test_list_by_states_filters_orders_and_counts(db: Session, user: User) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        completed = new_order(
            session, user, OrderState.COMPLETED, now - timedelta(hours=2)
        )
        in_progress = new_order(session, user, OrderState.IN_PROGRESS, now)
        cancelled = new_order(
            session, user, OrderState.CANCELLED, now - timedelta(hours=1)
        )
        draft = new_order(session, create_random_user(db))

        repo = OrderRepository(session)
        placed = ["in_progress", "completed", "cancelled"]
        assert [o.id for o in repo.list_by_states(placed, skip=0, limit=10)] == [
            in_progress.id,
            cancelled.id,
            completed.id,
        ]
        assert repo.count_by_states(placed) == 3
        assert [o.id for o in repo.list_by_states(["draft"], skip=0, limit=10)] == [
            draft.id
        ]
        assert [o.id for o in repo.list_by_states(placed, skip=1, limit=1)] == [
            cancelled.id
        ]
        assert repo.count_by_states(["in_progress", "cancelled"]) == 2
