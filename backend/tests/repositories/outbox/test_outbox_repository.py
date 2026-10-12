import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import OutboxEvent, OutboxStatus, OutboxTopic
from app.models.base import get_datetime_utc
from app.repositories import OutboxRepository
from app.repositories.outbox import backoff


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture(autouse=True)
def _clean(session: Session) -> None:
    session.query(OutboxEvent).delete()
    session.commit()


def _add(session: Session, n: int = 1) -> list[OutboxEvent]:
    ids = [uuid.uuid4() for _ in range(n)]
    OutboxRepository(session).add_many(OutboxTopic.SEARCH_PRODUCT, ids)
    session.flush()
    return list(session.scalars(select(OutboxEvent).order_by(OutboxEvent.id)).all())


def test_backoff_values_and_cap() -> None:
    expected = [2, 4, 8, 16, 32, 64, 128, 256, 300, 300]
    assert [backoff(n).total_seconds() for n in range(1, 11)] == expected


def test_mark_retry_backs_off_then_fails(session: Session) -> None:
    repo = OutboxRepository(session)
    (event,) = _add(session)
    repo.mark_retry(event, "boom", max_attempts=2)
    assert event.status == OutboxStatus.PENDING
    assert event.attempts == 1
    assert event.available_at > get_datetime_utc()
    repo.mark_retry(event, "boom" * 1000, max_attempts=2)
    assert event.status == OutboxStatus.FAILED
    assert event.last_error is not None
    assert len(event.last_error) == 2000


def test_purge_done_and_retry_failed(session: Session) -> None:
    repo = OutboxRepository(session)
    old, recent, failed = _add(session, 3)
    now = get_datetime_utc()
    old.status = recent.status = OutboxStatus.DONE.value
    old.processed_at = now - timedelta(days=10)
    recent.processed_at = now
    failed.status = OutboxStatus.FAILED.value
    failed.attempts = 10
    session.flush()

    assert repo.purge_done(now - timedelta(days=7)) == 1
    stats = repo.stats()
    assert (stats.pending, stats.failed) == (0, 1)
    assert repo.retry_failed() == 1
    session.refresh(failed)
    assert failed.status == OutboxStatus.PENDING
    assert failed.attempts == 0
    stats = repo.stats()
    assert (stats.pending, stats.failed) == (1, 0)
    assert stats.oldest_pending_at is not None


def test_mark_done(session: Session) -> None:
    events = _add(session, 2)
    OutboxRepository(session).mark_done(events)
    assert all(e.status == OutboxStatus.DONE and e.processed_at for e in events)


def test_claim_batch_skip_locked() -> None:
    """AC-12"""
    with Session(engine) as setup:
        _add(setup, 4)
        setup.commit()
    a, b = Session(engine), Session(engine)
    try:
        claimed_a = {e.id for e in OutboxRepository(a).claim_batch(2)}
        claimed_b = {e.id for e in OutboxRepository(b).claim_batch(10)}
        assert len(claimed_a) == 2
        assert len(claimed_b) == 2
        assert claimed_a.isdisjoint(claimed_b)
    finally:
        a.rollback()
        b.rollback()
        a.close()
        b.close()
