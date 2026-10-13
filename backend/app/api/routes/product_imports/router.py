import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import (
    CurrentUser,
    ProductImportServiceDep,
    get_current_active_superuser,
)
from app.schemas import (
    ProductImportCreate,
    ProductImportErrorsPublic,
    ProductImportPublic,
    ProductImportsPublic,
    ProductImportUpload,
    ProductImportUploadRequest,
)

router = APIRouter(
    prefix="/product-imports",
    tags=["product-imports"],
    dependencies=[Depends(get_current_active_superuser)],
)


@router.post("/presign", response_model=ProductImportUpload)
def presign_product_import(
    service: ProductImportServiceDep, upload_in: ProductImportUploadRequest
) -> Any:
    return service.presign(upload_in)


@router.post("/", status_code=202, response_model=ProductImportPublic)
def start_product_import(
    service: ProductImportServiceDep,
    current_user: CurrentUser,
    import_in: ProductImportCreate,
    response: Response,
) -> Any:
    imp, created = service.start(import_in, current_user)
    if not created:
        response.status_code = 200
    return imp


@router.get("/", response_model=ProductImportsPublic)
def read_product_imports(
    service: ProductImportServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Any:
    return service.list_imports(skip=skip, limit=limit)


@router.get("/{import_id}", response_model=ProductImportPublic)
def read_product_import(service: ProductImportServiceDep, import_id: uuid.UUID) -> Any:
    return service.get(import_id)


@router.get("/{import_id}/errors", response_model=ProductImportErrorsPublic)
def read_product_import_errors(
    service: ProductImportServiceDep,
    import_id: uuid.UUID,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Any:
    return service.list_errors(import_id, skip=skip, limit=limit)


@router.post("/{import_id}/retry", status_code=202, response_model=ProductImportPublic)
def retry_product_import(service: ProductImportServiceDep, import_id: uuid.UUID) -> Any:
    return service.retry(import_id)
