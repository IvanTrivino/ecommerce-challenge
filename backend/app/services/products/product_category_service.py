import uuid

from app.core.cache import cached, invalidates
from app.core.exceptions import ConflictError, NotFoundError
from app.models import ProductCategory
from app.repositories import ProductCategoryRepository
from app.schemas import (
    ProductCategoriesPublic,
    ProductCategoryCreate,
    ProductCategoryPublic,
    ProductCategoryUpdate,
)
from app.services.products.cache import PRODUCT_CATEGORIES


class ProductCategoryService:
    def __init__(self, repo: ProductCategoryRepository) -> None:
        self.repo = repo

    # Queries
    @cached(PRODUCT_CATEGORIES, ProductCategoryPublic)
    def get_by_id(self, category_id: uuid.UUID) -> ProductCategoryPublic:
        return ProductCategoryPublic.model_validate(self._get(category_id))

    @cached(PRODUCT_CATEGORIES, ProductCategoriesPublic)
    def list_categories(self, *, skip: int, limit: int) -> ProductCategoriesPublic:
        categories = self.repo.list(skip=skip, limit=limit)
        return ProductCategoriesPublic(
            data=[ProductCategoryPublic.model_validate(c) for c in categories],
            count=self.repo.count(),
        )

    # Commands
    @invalidates(PRODUCT_CATEGORIES)
    def create_category(self, category_in: ProductCategoryCreate) -> ProductCategory:
        self._ensure_code_available(category_in.code)
        return self.repo.save(ProductCategory(**category_in.model_dump()))

    @invalidates(PRODUCT_CATEGORIES)
    def update_category(
        self, category_id: uuid.UUID, category_in: ProductCategoryUpdate
    ) -> ProductCategory:
        category = self._get(category_id)
        data = category_in.model_dump(exclude_unset=True, exclude_none=True)
        if "code" in data:
            self._ensure_code_available(data["code"], category_id)
        for field, value in data.items():
            setattr(category, field, value)
        return self.repo.save(category)

    @invalidates(PRODUCT_CATEGORIES)
    def delete_category(self, category_id: uuid.UUID) -> None:
        category = self._get(category_id)
        if self.repo.has_products(category_id):
            raise ConflictError("Cannot delete a category that still has products")
        self.repo.delete(category)

    # Helpers
    def _get(self, category_id: uuid.UUID) -> ProductCategory:
        category = self.repo.get(category_id)
        if not category:
            raise NotFoundError("Product category not found")
        return category

    def _ensure_code_available(
        self, code: str, category_id: uuid.UUID | None = None
    ) -> None:
        existing = self.repo.get_by_code(code)
        if existing and existing.id != category_id:
            raise ConflictError("A category with this code already exists")
