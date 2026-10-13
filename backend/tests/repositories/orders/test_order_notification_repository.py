from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import (
    Order,
    OrderNotification,
    OrderNotificationKind,
    OrderNotificationStatus,
    OrderState,
)
from app.repositories import OrderNotificationRepository
from tests.utils.user import create_random_user

pytestmark = pytest.mark.usefixtures("clean_orders")


@pytest.fixture
def order(db: Session) -> Order:
    user = create_random_user(db)
    with Session(engine) as session:
        placed = Order(
            user_uuid=user.id,
            currency="USD",
            state=OrderState.IN_PROGRESS.value,
            placed_at=datetime.now(UTC),
            total_price=1,
            total_weight=0,
        )
        session.add(placed)
        session.commit()
        session.refresh(placed)
        session.expunge(placed)
    return placed


@pytest.fixture
def session() -> Session:
    with Session(engine) as s:
        yield s  # type: ignore[misc]


def make(
    session: Session,
    order: Order,
    kind: OrderNotificationKind = OrderNotificationKind.PLACED,
) -> OrderNotification:
    notification = OrderNotificationRepository(session).add(
        order.id, kind, now=datetime.now(UTC)
    )
    session.commit()
    return notification


def test_add_schedules_the_first_requeue_two_minutes_out(
    session: Session, order: Order
) -> None:
    now = datetime.now(UTC)
    notification = OrderNotificationRepository(session).add(
        order.id, OrderNotificationKind.PLACED, now=now
    )
    assert notification.status == OrderNotificationStatus.PENDING
    assert notification.available_at == now + timedelta(seconds=120)


def test_claim_returns_none_for_a_sent_row(session: Session, order: Order) -> None:
    notification = make(session, order)
    repo = OrderNotificationRepository(session)
    claimed = repo.claim(notification.id)
    assert claimed is not None
    repo.mark_sent(claimed, now=datetime.now(UTC))
    session.commit()
    assert repo.claim(notification.id) is None


def test_claim_skips_a_row_locked_by_another_session(
    session: Session, order: Order
) -> None:
    notification = make(session, order)
    with Session(engine) as holder:
        assert OrderNotificationRepository(holder).claim(notification.id) is not None
        assert OrderNotificationRepository(session).claim(notification.id) is None


def test_failures_back_off_and_end_failed(session: Session, order: Order) -> None:
    notification = make(session, order)
    repo = OrderNotificationRepository(session)
    now = datetime.now(UTC)

    delays = []
    for _ in range(4):
        repo.mark_failure(notification, "smtp down", now=now)
        assert notification.status == OrderNotificationStatus.PENDING
        delays.append((notification.available_at - now).total_seconds())
    assert delays == [30, 60, 120, 240]

    repo.mark_failure(notification, "smtp down", now=now)
    assert notification.attempts == 5
    assert notification.status == OrderNotificationStatus.FAILED
    assert notification.last_error == "smtp down"


def test_due_ids_ignores_future_and_non_pending_rows(
    session: Session, order: Order
) -> None:
    repo = OrderNotificationRepository(session)
    now = datetime.now(UTC)
    due = make(session, order, OrderNotificationKind.PLACED)
    future = make(session, order, OrderNotificationKind.COMPLETED)
    sent = make(session, order, OrderNotificationKind.CANCELLED)
    due.available_at = now - timedelta(minutes=1)
    sent.available_at = now - timedelta(minutes=1)
    sent.status = OrderNotificationStatus.SENT.value
    future.available_at = now + timedelta(minutes=1)
    session.commit()

    assert repo.due_ids(now=now, limit=10) == [due.id]
    assert repo.due_ids(now=now, limit=0) == []
