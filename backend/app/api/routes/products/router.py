import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    ProductSearchServiceDep,
    ProductServiceDep,
    get_current_active_superuser,
)
from app.schemas import (
    Message,
    ProductCreate,
    ProductPublic,
    ProductsPublic,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])

SuperuserOnly = [Depends(get_current_active_superuser)]


@router.get("/", response_model=ProductsPublic)
def read_products(
    service: ProductServiceDep,
    category_uuid: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    return service.list_products(category_id=category_uuid, skip=skip, limit=limit)


@router.get("/search", response_model=ProductsPublic)
def search_products(
    service: ProductSearchServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    skip: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Any:
    return service.search(q, skip=skip, limit=limit)


@router.get("/{product_id}", response_model=ProductPublic)
def read_product(product_id: uuid.UUID, service: ProductServiceDep) -> Any:
    return service.get_by_id(product_id)


@router.post("/", dependencies=SuperuserOnly, response_model=ProductPublic)
def create_product(service: ProductServiceDep, product_in: ProductCreate) -> Any:
    return service.create_product(product_in)


@router.patch("/{product_id}", dependencies=SuperuserOnly, response_model=ProductPublic)
def update_product(
    service: ProductServiceDep, product_id: uuid.UUID, product_in: ProductUpdate
) -> Any:
    return service.update_product(product_id, product_in)


@router.delete("/{product_id}", dependencies=SuperuserOnly)
def delete_product(service: ProductServiceDep, product_id: uuid.UUID) -> Message:
    service.delete_product(product_id)
    return Message(message="Product deleted successfully")
