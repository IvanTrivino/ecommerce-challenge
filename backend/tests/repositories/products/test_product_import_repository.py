import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import ProductImport, ProductImportStatus
from app.models.base import get_datetime_utc
from app.repositories import ProductImportRepository
from app.services.products.imports.rows import RowError
from tests.utils.utils import random_lower_string


@pytest.fixture
def session() -> Generator[Session]:
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def conns() -> Generator[tuple[Connection, Connection]]:
    with engine.connect() as a, engine.connect() as b:
        yield a, b


def make_import(session: Session, **kwargs: object) -> ProductImport:
    values: dict[str, object] = {
        "file_key": f"imports/{uuid.uuid4()}.csv",
        "filename": f"{random_lower_string()}.csv",
        "status": ProductImportStatus.COMPLETED,
        "total_bytes": 10,
        "etag": '"e"',
    } | kwargs
    imp = ProductImport(**values)
    session.add(imp)
    session.commit()
    return imp


def test_stale_finds_silent_active_imports(session: Session) -> None:
    now = get_datetime_utc()
    old = now - timedelta(minutes=11)
    running = make_import(session, status="running", heartbeat_at=old)
    session.commit()
    repo = ProductImportRepository(session)

    assert [i.id for i in repo.stale(now, 10)] == [running.id]
    running.status = "completed"
    session.commit()
    pending = make_import(session, status="pending", created_at=old)
    assert [i.id for i in repo.stale(now, 10)] == [pending.id]


def test_stale_skips_fresh_and_finished_imports(session: Session) -> None:
    now = get_datetime_utc()
    make_import(session, status="completed", heartbeat_at=now - timedelta(hours=1))
    make_import(session, status="failed", heartbeat_at=now - timedelta(hours=1))
    make_import(session, status="running", heartbeat_at=now - timedelta(minutes=2))

    assert ProductImportRepository(session).stale(now, 10) == []


def test_get_active_and_get_by_key(session: Session) -> None:
    repo = ProductImportRepository(session)
    assert repo.get_active() is None
    done = make_import(session)
    active = make_import(session, status="pending")

    assert repo.get_active() is not None
    assert repo.get_active().id == active.id  # type: ignore[union-attr]
    assert repo.get_by_key(done.file_key) is not None
    assert repo.get_by_key("imports/nope.csv") is None
    assert repo.active_file_keys() == {active.file_key}


def test_advisory_lock_is_exclusive(
    session: Session, conns: tuple[Connection, Connection]
) -> None:
    a, b = conns
    repo = ProductImportRepository(session)
    import_id = uuid.uuid4()

    assert repo.try_lock(a, import_id)
    assert not repo.try_lock(b, import_id)
    assert not repo.try_xact_lock(import_id)
    session.rollback()

    repo.unlock(a, import_id)
    assert repo.try_lock(b, import_id)
    repo.unlock(b, import_id)


def test_mark_files_deleted_only_touches_matching_untouched_rows(
    session: Session,
) -> None:
    now = get_datetime_utc()
    earlier = now - timedelta(days=1)
    target = make_import(session)
    already = make_import(session, file_deleted_at=earlier)
    other = make_import(session)

    ProductImportRepository(session).mark_files_deleted(
        [target.file_key, already.file_key], now
    )
    session.commit()
    for imp in (target, already, other):
        session.refresh(imp)

    assert target.file_deleted_at == now
    assert already.file_deleted_at == earlier
    assert other.file_deleted_at is None


def test_errors_are_ordered_and_paged(session: Session) -> None:
    imp = make_import(session)
    repo = ProductImportRepository(session)
    repo.add_errors(
        imp.id,
        [RowError(line, f"S{line}", f"bad {line}") for line in (30, 4, 17, 8)],
    )
    session.commit()

    assert repo.count_errors(imp.id) == 4
    assert [e.line for e in repo.list_errors(imp.id)] == [4, 8, 17, 30]
    assert [e.line for e in repo.list_errors(imp.id, skip=1, limit=2)] == [8, 17]
