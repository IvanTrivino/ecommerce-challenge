import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.core.exceptions import ConflictError
from app.models import Order, Product
from app.services.orders.pricing import PRICE_QUANTUM, cart_totals


@dataclass(frozen=True)
class CheckoutContext:
    order: Order
    products: Mapping[uuid.UUID, Product]
    expected_total: Decimal


class CheckoutValidator(Protocol):
    def validate(self, ctx: CheckoutContext) -> None: ...


class CartNotEmpty:
    def validate(self, ctx: CheckoutContext) -> None:
        if not ctx.order.items:
            raise ConflictError("Your cart is empty")


class InventoryAvailable:
    def validate(self, ctx: CheckoutContext) -> None:
        for item in ctx.order.items:
            product = ctx.products[item.product_uuid]
            if product.is_deleted or product.stock < item.quantity:
                raise ConflictError("Some items in your cart are unavailable")


class PriceUnchanged:
    def validate(self, ctx: CheckoutContext) -> None:
        total, _ = cart_totals(
            (ctx.products[item.product_uuid], item.quantity) for item in ctx.order.items
        )
        if total != ctx.expected_total.quantize(PRICE_QUANTUM):
            raise ConflictError("Prices changed, please review your cart")


DEFAULT_VALIDATORS: tuple[CheckoutValidator, ...] = (
    CartNotEmpty(),
    InventoryAvailable(),
    PriceUnchanged(),
)
