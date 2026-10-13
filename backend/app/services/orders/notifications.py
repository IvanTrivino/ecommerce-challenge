import logging
import smtplib
from collections.abc import Callable
from enum import StrEnum

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import OrderNotificationKind, OrderNotificationStatus
from app.models.base import get_datetime_utc
from app.repositories import OrderNotificationRepository, OrderRepository
from app.services.email.email_service import (
    EmailDeliveryError,
    generate_order_email,
    send_email,
)

logger = logging.getLogger(__name__)


class NotificationOutcome(StrEnum):
    SENT = "sent"
    SKIPPED = "skipped"
    RETRY = "retry"
    FAILED = "failed"
    NOT_PENDING = "not_pending"


class OrderNotificationSender:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def send(self, notification_id: int) -> NotificationOutcome:
        """Send one notification. The row lock is held until the outcome is saved,
        so concurrent copies of the task can't send the same email twice."""
        with Session(self.engine) as session:
            repo = OrderNotificationRepository(session)
            notification = repo.claim(notification_id)
            if notification is None:
                return NotificationOutcome.NOT_PENDING
            if not settings.emails_enabled:
                logger.info(
                    "Emails disabled, skipping order notification %s", notification.id
                )
                repo.mark_skipped(notification)
                session.commit()
                return NotificationOutcome.SKIPPED
            order = OrderRepository(session).get(notification.order_uuid)
            assert order is not None
            email = generate_order_email(
                order, OrderNotificationKind(notification.kind)
            )
            now = get_datetime_utc()
            try:
                send_email(
                    email_to=order.user.email,
                    subject=email.subject,
                    html_content=email.html_content,
                    raise_on_error=True,
                )
            except (EmailDeliveryError, OSError, smtplib.SMTPException) as exc:
                logger.warning("Order notification %s failed: %s", notification.id, exc)
                repo.mark_failure(notification, str(exc), now=now)
                session.commit()
                if notification.status == OrderNotificationStatus.FAILED:
                    return NotificationOutcome.FAILED
                return NotificationOutcome.RETRY
            repo.mark_sent(notification, now=now)
            session.commit()
            logger.info(
                "Order notification %s (%s) sent for order %s",
                notification.id,
                notification.kind,
                order.id,
            )
            return NotificationOutcome.SENT

    def requeue_due(self, enqueue: Callable[[int], object], *, limit: int = 500) -> int:
        with Session(self.engine) as session:
            ids = OrderNotificationRepository(session).due_ids(
                now=get_datetime_utc(), limit=limit
            )
        for notification_id in ids:
            enqueue(notification_id)
        return len(ids)
