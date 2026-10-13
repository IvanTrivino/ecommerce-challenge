import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import MAX_QUANTITY_PER_ITEM


class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=MAX_QUANTITY_PER_ITEM)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_ITEM)


class CartItemPublic(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    sku: str
    image_url: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    available: bool
    available_stock: int


class CartPublic(BaseModel):
    id: uuid.UUID | None
    items: list[CartItemPublic]
    item_count: int
    total_price: Decimal
    total_weight: Decimal
    can_place: bool


class PlaceOrderRequest(BaseModel):
    order_id: uuid.UUID
    expected_total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
