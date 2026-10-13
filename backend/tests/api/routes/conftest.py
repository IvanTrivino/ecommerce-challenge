from collections.abc import Generator

import pytest

from app.api.deps.orders import get_payments_gateway
from app.main import app


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Replace the Celery enqueue and record the notification ids."""
    ids: list[int] = []
    monkeypatch.setattr("app.api.deps.orders.enqueue_order_notification", ids.append)
    return ids


@pytest.fixture
def clear_overrides() -> Generator[None]:
    yield
    app.dependency_overrides.pop(get_payments_gateway, None)
