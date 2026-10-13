import uuid
from typing import Annotated

from fastapi import Depends

from app.api.deps.database import SessionDep
from app.repositories import ProductImportRepository
from app.services import ProductImportService


def enqueue_product_import(import_id: uuid.UUID) -> str:
    from app.tasks import run_product_import

    return str(run_product_import.delay(str(import_id)).id)


def get_product_import_service(session: SessionDep) -> ProductImportService:
    return ProductImportService(
        ProductImportRepository(session), enqueue_product_import
    )


ProductImportServiceDep = Annotated[
    ProductImportService, Depends(get_product_import_service)
]
