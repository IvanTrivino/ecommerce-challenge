from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import settings
from app.core.db import engine, init_db
from app.core.storage import (
    delete_objects,
    ensure_product_images_bucket,
    ensure_product_imports_bucket,
    get_s3,
    iter_objects,
)
from app.main import app
from app.models import (
    CartItem,
    Order,
    OrderNotification,
    OutboxEvent,
    Product,
    ProductCategory,
    ProductImport,
    ProductImportError,
    User,
)
from tests.utils.cache import FakeRedis
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    with Session(engine) as session:
        init_db(session)
        yield session
        session.execute(delete(OrderNotification))
        session.execute(delete(CartItem))
        session.execute(delete(Order))
        session.execute(delete(OutboxEvent))
        session.execute(delete(ProductImportError))
        session.execute(delete(ProductImport))
        session.execute(delete(Product))
        session.execute(delete(ProductCategory))
        session.execute(delete(User))
        session.commit()


@pytest.fixture(autouse=True)
def clean_imports() -> Generator[None]:
    """Only one import can be active at a time: never leak one between tests."""

    def wipe() -> None:
        with Session(engine) as session:
            session.execute(delete(ProductImportError))
            session.execute(delete(ProductImport))
            session.commit()

    wipe()
    yield
    wipe()


@pytest.fixture
def clean_orders() -> Generator[None]:
    def wipe() -> None:
        with Session(engine) as session:
            session.execute(delete(OrderNotification))
            session.execute(delete(CartItem))
            session.execute(delete(Order))
            session.commit()

    wipe()
    yield
    wipe()


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    """Isolate every test from the real Redis cache."""
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_cache", lambda: fake)
    return fake


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )


@pytest.fixture
def images_bucket(monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    name = f"test-product-images-{uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "S3_PRODUCT_IMAGES_BUCKET", name)
    # Tests run in the backend container: upload through the internal endpoint
    monkeypatch.setattr(
        settings, "S3_PRODUCT_IMAGES_PUBLIC_URL", f"{settings.S3_ENDPOINT_URL}/{name}"
    )
    ensure_product_images_bucket()
    yield name
    keys = [o.key for o in iter_objects(name, "")]
    if keys:
        delete_objects(name, keys)
    get_s3().delete_bucket(Bucket=name)


@pytest.fixture
def imports_bucket(monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    name = f"test-product-imports-{uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "S3_PRODUCT_IMPORTS_BUCKET", name)
    ensure_product_imports_bucket()
    yield name
    keys = [o.key for o in iter_objects(name, "")]
    if keys:
        delete_objects(name, keys)
    get_s3().delete_bucket(Bucket=name)
