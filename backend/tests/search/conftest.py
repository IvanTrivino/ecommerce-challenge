from collections.abc import Generator
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.search import get_es
from app.search.products_index import alias
from tests.outbox.conftest import clean_outbox  # noqa: F401  (autouse fixture)


@pytest.fixture(autouse=True)
def es_alias(monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    name = f"test_products_{uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "ELASTICSEARCH_PRODUCTS_ALIAS", name)
    yield name
    es = get_es()
    for index in es.indices.get(index=f"{name}_*", ignore_unavailable=True):
        es.indices.delete(index=index, ignore_unavailable=True)


def refresh() -> None:
    get_es().indices.refresh(index=alias())
