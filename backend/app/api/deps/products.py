from typing import Annotated

from fastapi import Depends

from app.api.deps.database import SessionDep
from app.core.search import get_es
from app.repositories import (
    ProductCategoryRepository,
    ProductRepository,
    ProductSearchRepository,
)
from app.services import (
    ProductCategoryService,
    ProductImageService,
    ProductSearchService,
    ProductService,
)


def get_product_image_service(session: SessionDep) -> ProductImageService:
    return ProductImageService(ProductRepository(session))


def get_product_service(session: SessionDep) -> ProductService:
    repo = ProductRepository(session)
    return ProductService(
        repo, ProductCategoryRepository(session), ProductImageService(repo)
    )


def get_product_category_service(session: SessionDep) -> ProductCategoryService:
    return ProductCategoryService(ProductCategoryRepository(session))


def get_product_search_service(session: SessionDep) -> ProductSearchService:
    return ProductSearchService(
        ProductSearchRepository(get_es()), ProductRepository(session)
    )


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
ProductImageServiceDep = Annotated[
    ProductImageService, Depends(get_product_image_service)
]
ProductCategoryServiceDep = Annotated[
    ProductCategoryService, Depends(get_product_category_service)
]
ProductSearchServiceDep = Annotated[
    ProductSearchService, Depends(get_product_search_service)
]
