import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.search import get_es
from app.models import OutboxEvent, OutboxStatus
from app.models.base import get_datetime_utc
from app.search import worker as worker_module
from app.search.products_index import alias, ensure_index
from app.search.worker import Worker
from tests.utils.product import create_random_product


@pytest.fixture(autouse=True)
def heartbeat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "heartbeat"
    monkeypatch.setattr(worker_module, "HEARTBEAT_PATH", path)
    return path


def test_iteration_touches_heartbeat(heartbeat: Path) -> None:
    ensure_index(get_es())
    Worker(get_es()).run_iteration()
    assert heartbeat.exists()


def test_purge_removes_old_done_but_not_failed(db: Session) -> None:
    ensure_index(get_es())
    old = get_datetime_utc() - timedelta(days=30)
    db.add_all(
        [
            OutboxEvent(
                topic="search.product",
                aggregate_id=uuid.uuid4(),
                status=status,
                processed_at=old,
            )
            for status in (OutboxStatus.DONE.value, OutboxStatus.FAILED.value)
        ]
    )
    db.commit()
    worker = Worker(get_es())
    worker._last_purge = get_datetime_utc() - timedelta(hours=1)
    worker.run_iteration()
    db.expire_all()
    remaining = db.scalars(
        select(OutboxEvent).where(OutboxEvent.processed_at == old)
    ).all()
    assert [e.status for e in remaining] == [OutboxStatus.FAILED]


def test_sigterm_finishes_and_stops(db: Session) -> None:
    ensure_index(get_es())
    product = create_random_product(db)
    worker = Worker(get_es())
    thread = threading.Thread(target=worker.run)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        db.expire_all()
        if all(e.status == OutboxStatus.DONE for e in db.scalars(select(OutboxEvent))):
            break
        time.sleep(0.1)
    worker.request_stop()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert get_es().exists(index=alias(), id=str(product.id))


def test_loop_survives_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    worker = Worker(get_es())

    def flaky(*_: object) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            worker.request_stop()
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "process_once", flaky)
    monkeypatch.setattr(worker_module.settings, "SEARCH_OUTBOX_POLL_SECONDS", 0.01)
    worker.run()
    assert calls == 2
