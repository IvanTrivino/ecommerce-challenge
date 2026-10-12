import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.storage import product_image_url


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=1, max_length=100)
    description: str | None = None
    category_uuid: uuid.UUID
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    stock: int = Field(default=0, ge=0)
    weight: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    image_key: str | None = Field(default=None, max_length=512)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    category_uuid: uuid.UUID | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    weight: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    image_key: str | None = Field(default=None, max_length=512)


class ProductPublic(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_url(self) -> str | None:
        return product_image_url(self.image_key) if self.image_key else None


class ProductsPublic(BaseModel):
    data: list[ProductPublic]
    count: int
