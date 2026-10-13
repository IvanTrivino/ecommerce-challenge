from collections.abc import Iterable
from decimal import Decimal

from app.models import Product

PRICE_QUANTUM = Decimal("0.01")
WEIGHT_QUANTUM = Decimal("0.001")


def cart_totals(pairs: Iterable[tuple[Product, int]]) -> tuple[Decimal, Decimal]:
    price = Decimal(0)
    weight = Decimal(0)
    for product, quantity in pairs:
        price += product.price * quantity
        weight += (product.weight or Decimal(0)) * quantity
    return price.quantize(PRICE_QUANTUM), weight.quantize(WEIGHT_QUANTUM)
