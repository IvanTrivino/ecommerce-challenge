import pytest
from sqlalchemy.orm import Session

from app.core.search import get_es
from app.models import OutboxTopic
from app.repositories import OutboxRepository
from app.search.__main__ import main
from app.search.products_index import alias, ensure_index
from tests.search.conftest import refresh
from tests.utils.product import create_random_product


def exists(product_id: object) -> bool:
    refresh()
    return bool(get_es().exists(index=alias(), id=str(product_id)))


def test_enqueue_invalid_uuid() -> None:
    assert main(["enqueue", "not-a-uuid"]) == 2


def test_process_exit_code_on_retry(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.search import indexer

    create_random_product(db)

    def boom(*_: object, **__: object) -> None:
        raise indexer.elasticsearch.ConnectionError("down")

    monkeypatch.setattr(indexer.helpers, "streaming_bulk", boom)
    assert main(["process", "--once"]) == 1


def test_reindex_swaps_alias(db: Session) -> None:
    es = get_es()
    old = ensure_index(es)
    products = [create_random_product(db) for _ in range(2)]
    assert main(["reindex"]) == 0
    indices = list(es.indices.get_alias(name=alias()))
    assert len(indices) == 1
    assert indices[0] != old
    assert not es.indices.exists(index=old)
    assert all(exists(p.id) for p in products)


def test_status(capsys: pytest.CaptureFixture[str], db: Session) -> None:
    ensure_index(get_es())
    OutboxRepository(db).add_many(
        OutboxTopic.SEARCH_PRODUCT, [create_random_product(db).id]
    )
    db.commit()
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "pending:" in out
    assert "failed:" in out
