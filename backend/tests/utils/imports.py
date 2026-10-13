import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ProductImport, User
from app.repositories import ProductImportRepository, UserRepository
from app.schemas import ProductImportCreate, ProductImportUploadRequest
from app.services import ProductImportService
from tests.utils.storage import post_upload

EXAMPLE_CSV = Path(__file__).parents[1] / "fixtures" / "product-import-example.csv"


class Enqueued(list[uuid.UUID]):
    """Records the imports a service queued, in place of Celery."""

    def __call__(self, import_id: uuid.UUID) -> str:
        self.append(import_id)
        return "task-id"


def superuser(db: Session) -> User:
    user = UserRepository(db).get_by_email(settings.FIRST_SUPERUSER)
    assert user
    return user


def make_service(db: Session, enqueued: Enqueued | None = None) -> ProductImportService:
    return ProductImportService(
        ProductImportRepository(db), enqueued if enqueued is not None else Enqueued()
    )


def upload_csv(service: ProductImportService, body: bytes) -> str:
    """Presign and upload `body` the way the browser would. Returns the object key."""
    ticket = service.presign(
        ProductImportUploadRequest(filename="products.csv", size=len(body))
    )
    response = post_upload(ticket, body)
    assert response.status_code == 204, response.text
    return ticket.key


def start_import(
    db: Session,
    body: bytes,
    *,
    filename: str = "products.csv",
    enqueued: Enqueued | None = None,
) -> ProductImport:
    service = make_service(db, enqueued)
    key = upload_csv(service, body)
    imp, created = service.start(
        ProductImportCreate(key=key, filename=filename), superuser(db)
    )
    assert created
    return imp
