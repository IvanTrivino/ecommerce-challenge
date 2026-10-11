from typing import Annotated

from fastapi import Depends

from app.api.deps.database import SessionDep
from app.repositories import ProductCategoryRepository, ProductRepository
from app.services import ProductCategoryService, ProductService


def get_product_service(session: SessionDep) -> ProductService:
    return ProductService(
        ProductRepository(session), ProductCategoryRepository(session)
    )


def get_product_category_service(session: SessionDep) -> ProductCategoryService:
    return ProductCategoryService(ProductCategoryRepository(session))


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
ProductCategoryServiceDep = Annotated[
    ProductCategoryService, Depends(get_product_category_service)
]
