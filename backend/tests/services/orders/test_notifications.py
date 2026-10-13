from collections.abc import Generator
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.models import OrderNotification, OrderNotificationStatus, User
from app.models.base import get_datetime_utc
from app.repositories import OrderNotificationRepository
from app.services.email.email_service import EmailDeliveryError
from app.tasks import requeue_order_notifications, send_order_notification
from tests.services.orders.conftest import load_user, placed_order
from tests.utils.order import create_stocked_product
from tests.utils.user import create_random_user

pytestmark = pytest.mark.usefixtures("clean_orders")


class Outbox:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.error: Exception | None = None

    def __call__(
        self,
        *,
        email_to: str,
        subject: str = "",
        html_content: str = "",
        raise_on_error: bool = False,
    ) -> None:
        if self.error:
            raise self.error
        self.sent.append({"to": email_to, "subject": subject, "html": html_content})


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    fake = Outbox()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", "shop@example.com")
    monkeypatch.setattr("app.services.orders.notifications.send_email", fake)
    return fake


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def user(db: Session, session: Session) -> User:
    return load_user(session, create_random_user(db))


@pytest.fixture
def notification(db: Session, session: Session, user: User) -> OrderNotification:
    product = create_stocked_product(db, stock=5)
    order = placed_order(session, user, (product, 2))
    return load(order.id)


def load(order_id: object) -> OrderNotification:
    with Session(engine) as s:
        return s.scalars(
            select(OrderNotification).where(OrderNotification.order_uuid == order_id)
        ).one()


def reload(notification: OrderNotification) -> OrderNotification:
    with Session(engine) as s:
        return s.get_one(OrderNotification, notification.id)


def run(notification: OrderNotification) -> str:
    return send_order_notification.apply(args=[notification.id]).get()


def test_the_email_is_sent_once(
    outbox: Outbox, notification: OrderNotification, user: User
) -> None:
    assert run(notification) == "sent"

    [email] = outbox.sent
    assert email["to"] == user.email
    assert "confirmed" in email["subject"]
    row = reload(notification)
    assert row.status == OrderNotificationStatus.SENT
    assert row.attempts == 1
    assert row.sent_at is not None

    assert run(notification) == "not_pending"
    assert len(outbox.sent) == 1


def test_a_notification_being_sent_elsewhere_is_left_alone(
    outbox: Outbox, notification: OrderNotification
) -> None:
    with Session(engine) as holder:
        assert OrderNotificationRepository(holder).claim(notification.id) is not None

        assert run(notification) == "not_pending"

    assert outbox.sent == []
    assert reload(notification).status == OrderNotificationStatus.PENDING


def test_disabled_emails_are_skipped(
    outbox: Outbox, notification: OrderNotification, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", None)

    assert run(notification) == "skipped"

    assert outbox.sent == []
    assert reload(notification).status == OrderNotificationStatus.SKIPPED


def test_smtp_failures_back_off_then_give_up(
    outbox: Outbox, notification: OrderNotification
) -> None:
    outbox.error = EmailDeliveryError("SMTP None: down")
    delays = []

    for attempt in range(1, 5):
        before = get_datetime_utc()
        assert run(notification) == "retry"
        row = reload(notification)
        assert row.attempts == attempt
        assert row.last_error == "SMTP None: down"
        delays.append(round((row.available_at - before).total_seconds() / 30))
    assert delays == [1, 2, 4, 8]

    assert run(notification) == "failed"
    row = reload(notification)
    assert (row.status, row.attempts) == (OrderNotificationStatus.FAILED, 5)
    assert run(notification) == "not_pending"


def test_network_errors_are_retried_too(
    outbox: Outbox, notification: OrderNotification
) -> None:
    outbox.error = ConnectionRefusedError("refused")

    assert run(notification) == "retry"


@pytest.mark.usefixtures("outbox")
def test_beat_requeues_only_due_pending_rows(
    notification: OrderNotification, monkeypatch: pytest.MonkeyPatch
) -> None:
    queued: list[int] = []
    monkeypatch.setattr(send_order_notification, "delay", queued.append)

    assert requeue_order_notifications.apply().get() == 0
    assert queued == []

    with Session(engine) as s:
        row = s.get_one(OrderNotification, notification.id)
        row.available_at = get_datetime_utc() - timedelta(minutes=1)
        s.commit()

    assert requeue_order_notifications.apply().get() == 1
    assert queued == [notification.id]


def test_a_lost_enqueue_is_recovered_end_to_end(
    outbox: Outbox,
    notification: OrderNotification,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(engine) as s:
        row = s.get_one(OrderNotification, notification.id)
        row.available_at = get_datetime_utc() - timedelta(minutes=1)
        s.commit()
    monkeypatch.setattr(
        send_order_notification,
        "delay",
        lambda notification_id: send_order_notification.apply(args=[notification_id]),
    )

    requeue_order_notifications.apply()

    assert len(outbox.sent) == 1
    assert reload(notification).status == OrderNotificationStatus.SENT
