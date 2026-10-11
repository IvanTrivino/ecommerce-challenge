import uuid

from app.core.cache import cached, invalidates
from app.core.exceptions import ConflictError, NotFoundError
from app.models import Product
from app.repositories import ProductCategoryRepository, ProductRepository
from app.schemas import ProductCreate, ProductPublic, ProductsPublic, ProductUpdate
from app.services.products.cache import PRODUCTS

NULLABLE_FIELDS = {"description", "weight"}


class ProductService:
    def __init__(
        self, repo: ProductRepository, category_repo: ProductCategoryRepository
    ) -> None:
        self.repo = repo
        self.category_repo = category_repo

    @cached(PRODUCTS, ProductPublic)
    def get_by_id(self, product_id: uuid.UUID) -> ProductPublic:
        return ProductPublic.model_validate(self._get(product_id))

    @cached(PRODUCTS, ProductsPublic)
    def list_products(
        self, *, category_id: uuid.UUID | None, skip: int, limit: int
    ) -> ProductsPublic:
        products = self.repo.list_filtered(
            category_id=category_id, skip=skip, limit=limit
        )
        return ProductsPublic(
            data=[ProductPublic.model_validate(p) for p in products],
            count=self.repo.count_filtered(category_id=category_id),
        )

    @invalidates(PRODUCTS)
    def create_product(self, product_in: ProductCreate) -> Product:
        self._ensure_sku_available(product_in.sku)
        self._ensure_category_exists(product_in.category_uuid)
        return self.repo.save(Product(**product_in.model_dump()))

    @invalidates(PRODUCTS)
    def update_product(
        self, product_id: uuid.UUID, product_in: ProductUpdate
    ) -> Product:
        product = self._get(product_id)
        data = {
            field: value
            for field, value in product_in.model_dump(exclude_unset=True).items()
            if value is not None or field in NULLABLE_FIELDS
        }
        if "sku" in data:
            self._ensure_sku_available(data["sku"], product_id)
        if "category_uuid" in data:
            self._ensure_category_exists(data["category_uuid"])
        for field, value in data.items():
            setattr(product, field, value)
        return self.repo.save(product)

    @invalidates(PRODUCTS)
    def delete_product(self, product_id: uuid.UUID) -> None:
        self.repo.delete(self._get(product_id))

    def _get(self, product_id: uuid.UUID) -> Product:
        product = self.repo.get(product_id)
        if not product:
            raise NotFoundError("Product not found")
        return product

    def _ensure_sku_available(
        self, sku: str, product_id: uuid.UUID | None = None
    ) -> None:
        existing = self.repo.get_by_sku(sku)
        if existing and existing.id != product_id:
            raise ConflictError("A product with this SKU already exists")

    def _ensure_category_exists(self, category_id: uuid.UUID) -> None:
        if not self.category_repo.get(category_id):
            raise NotFoundError("Product category not found")
