import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrderStateLiteral = Literal["draft", "in_progress", "completed", "cancelled"]


class OrderItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID = Field(validation_alias="product_uuid")
    name: str
    sku: str
    quantity: int
    unit_price: Decimal | None
    unit_weight: Decimal | None
    line_total: Decimal | None


class OrderSummaryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    state: OrderStateLiteral
    user_id: uuid.UUID = Field(validation_alias="user_uuid")
    user_email: str
    total_price: Decimal | None
    total_weight: Decimal | None
    currency: str
    item_count: int
    payment_reference: str | None
    placed_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class OrderPublic(OrderSummaryPublic):
    items: list[OrderItemPublic]


class OrdersPublic(BaseModel):
    data: list[OrderSummaryPublic]
    count: int
