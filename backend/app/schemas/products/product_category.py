import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)


class ProductCategoryCreate(ProductCategoryBase):
    pass


class ProductCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=50)


class ProductCategoryPublic(ProductCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class ProductCategoriesPublic(BaseModel):
    data: list[ProductCategoryPublic]
    count: int
