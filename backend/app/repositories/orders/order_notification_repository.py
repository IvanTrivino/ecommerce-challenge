import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    OrderNotification,
    OrderNotificationKind,
    OrderNotificationStatus,
)


class OrderNotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self, order_id: uuid.UUID, kind: OrderNotificationKind, *, now: datetime
    ) -> OrderNotification:
        notification = OrderNotification(
            order_uuid=order_id,
            kind=kind.value,
            available_at=now
            + timedelta(seconds=settings.ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS),
        )
        self.session.add(notification)
        self.session.flush()
        return notification

    def claim(self, notification_id: int) -> OrderNotification | None:
        """Lock a pending notification. None if it is done or another worker has it."""
        statement = (
            select(OrderNotification)
            .where(
                OrderNotification.id == notification_id,
                OrderNotification.status == OrderNotificationStatus.PENDING.value,
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(statement).first()

    def mark_sent(self, notification: OrderNotification, *, now: datetime) -> None:
        notification.attempts += 1
        notification.status = OrderNotificationStatus.SENT.value
        notification.sent_at = now

    def mark_skipped(self, notification: OrderNotification) -> None:
        notification.status = OrderNotificationStatus.SKIPPED.value

    def mark_failure(
        self, notification: OrderNotification, error: str, *, now: datetime
    ) -> None:
        notification.attempts += 1
        notification.last_error = error[:2000]
        if notification.attempts >= settings.ORDER_NOTIFICATION_MAX_ATTEMPTS:
            notification.status = OrderNotificationStatus.FAILED.value
        else:
            backoff = settings.ORDER_NOTIFICATION_BACKOFF_SECONDS * 2 ** (
                notification.attempts - 1
            )
            notification.available_at = now + timedelta(seconds=backoff)

    def due_ids(self, *, now: datetime, limit: int) -> list[int]:
        statement = (
            select(OrderNotification.id)
            .where(
                OrderNotification.status == OrderNotificationStatus.PENDING.value,
                OrderNotification.available_at <= now,
            )
            .order_by(OrderNotification.available_at, OrderNotification.id)
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())
