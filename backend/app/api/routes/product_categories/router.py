import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import ProductCategoryServiceDep, get_current_active_superuser
from app.schemas import (
    Message,
    ProductCategoriesPublic,
    ProductCategoryCreate,
    ProductCategoryPublic,
    ProductCategoryUpdate,
)

router = APIRouter(prefix="/product-categories", tags=["product-categories"])

SuperuserOnly = [Depends(get_current_active_superuser)]


@router.get("/", response_model=ProductCategoriesPublic)
def read_categories(
    service: ProductCategoryServiceDep, skip: int = 0, limit: int = 100
) -> Any:
    return service.list_categories(skip=skip, limit=limit)


@router.get("/{category_id}", response_model=ProductCategoryPublic)
def read_category(category_id: uuid.UUID, service: ProductCategoryServiceDep) -> Any:
    return service.get_by_id(category_id)


@router.post("/", dependencies=SuperuserOnly, response_model=ProductCategoryPublic)
def create_category(
    service: ProductCategoryServiceDep, category_in: ProductCategoryCreate
) -> Any:
    return service.create_category(category_in)


@router.patch(
    "/{category_id}", dependencies=SuperuserOnly, response_model=ProductCategoryPublic
)
def update_category(
    service: ProductCategoryServiceDep,
    category_id: uuid.UUID,
    category_in: ProductCategoryUpdate,
) -> Any:
    return service.update_category(category_id, category_in)


@router.delete("/{category_id}", dependencies=SuperuserOnly)
def delete_category(
    service: ProductCategoryServiceDep, category_id: uuid.UUID
) -> Message:
    service.delete_category(category_id)
    return Message(message="Product category deleted successfully")
