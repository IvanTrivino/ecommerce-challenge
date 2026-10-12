import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Delete, Update, delete, func, select, update
from sqlalchemy.orm import Session

from app.models import OutboxEvent, OutboxStatus, OutboxTopic
from app.models.base import get_datetime_utc


@dataclass
class OutboxStats:
    pending: int
    failed: int
    oldest_pending_at: datetime | None


def backoff(attempts: int) -> timedelta:
    return min(timedelta(seconds=2 * 2 ** (attempts - 1)), timedelta(minutes=5))


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_many(self, topic: OutboxTopic, aggregate_ids: Iterable[uuid.UUID]) -> None:
        self.session.add_all(
            OutboxEvent(topic=topic.value, aggregate_id=aggregate_id)
            for aggregate_id in aggregate_ids
        )

    def claim_batch(self, limit: int) -> list[OutboxEvent]:
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == OutboxStatus.PENDING.value,
                OutboxEvent.available_at <= func.now(),
            )
            .order_by(OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(statement).all())

    def mark_done(self, events: Sequence[OutboxEvent]) -> None:
        now = get_datetime_utc()
        for event in events:
            event.status = OutboxStatus.DONE.value
            event.processed_at = now

    def mark_retry(self, event: OutboxEvent, error: str, *, max_attempts: int) -> None:
        event.attempts += 1
        event.last_error = error[:2000]
        if event.attempts >= max_attempts:
            event.status = OutboxStatus.FAILED.value
        else:
            event.available_at = get_datetime_utc() + backoff(event.attempts)

    def purge_done(self, older_than: datetime) -> int:
        statement = delete(OutboxEvent).where(
            OutboxEvent.status == OutboxStatus.DONE.value,
            OutboxEvent.processed_at < older_than,
        )
        return self._rowcount(statement)

    def retry_failed(self) -> int:
        statement = (
            update(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.FAILED.value)
            .values(
                status=OutboxStatus.PENDING.value,
                attempts=0,
                available_at=func.now(),
                last_error=None,
            )
        )
        return self._rowcount(statement)

    def _rowcount(self, statement: Delete | Update) -> int:
        result = cast("CursorResult[Any]", self.session.execute(statement))
        return result.rowcount

    def stats(self) -> OutboxStats:
        pending = OutboxEvent.status == OutboxStatus.PENDING.value
        row = self.session.execute(
            select(
                func.count().filter(pending),
                func.count().filter(OutboxEvent.status == OutboxStatus.FAILED.value),
                func.min(OutboxEvent.created_at).filter(pending),
            )
        ).one()
        return OutboxStats(pending=row[0], failed=row[1], oldest_pending_at=row[2])
