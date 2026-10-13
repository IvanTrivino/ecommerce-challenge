import uuid
from decimal import Decimal

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import product_image_url
from app.models import MAX_QUANTITY_PER_ITEM, CartItem, Order, User
from app.models.base import get_datetime_utc
from app.repositories import CartItemRepository, OrderRepository, ProductRepository
from app.schemas import CartItemAdd, CartItemPublic, CartItemUpdate, CartPublic
from app.services.orders.pricing import PRICE_QUANTUM, WEIGHT_QUANTUM, cart_totals

ITEM_NOT_FOUND = "Cart item not found"


class CartService:
    def __init__(
        self,
        orders: OrderRepository,
        items: CartItemRepository,
        products: ProductRepository,
    ) -> None:
        self.orders = orders
        self.items = items
        self.products = products
        self.session = orders.session

    def get_cart(self, user: User) -> CartPublic:
        return self._to_public(self.orders.get_draft(user.id))

    def add_item(self, user: User, data: CartItemAdd) -> CartPublic:
        try:
            product = self.products.get(data.product_id)
            if product is None:
                raise NotFoundError("Product not found")
            order = self._lock_or_create_draft(user)
            existing = self.items.get_for_product(order.id, product.id)
            merged = (existing.quantity if existing else 0) + data.quantity
            if merged > MAX_QUANTITY_PER_ITEM:
                raise ConflictError(
                    f"You can add at most {MAX_QUANTITY_PER_ITEM} of this product"
                )
            if merged > product.stock:
                raise ConflictError(f"Only {product.stock} left in stock")
            if existing is None and len(order.items) >= settings.CART_MAX_ITEMS:
                raise ConflictError("Your cart is full")
            if existing is not None:
                existing.quantity = merged
            else:
                self.items.add(
                    CartItem(
                        order_uuid=order.id,
                        product_uuid=product.id,
                        quantity=data.quantity,
                    )
                )
            order.updated_at = get_datetime_utc()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(order)
        return self._to_public(order)

    def update_item(
        self, user: User, item_id: uuid.UUID, data: CartItemUpdate
    ) -> CartPublic:
        try:
            order, item = self._lock_item(user, item_id)
            if data.quantity > item.quantity and data.quantity > item.product.stock:
                raise ConflictError(f"Only {item.product.stock} left in stock")
            item.quantity = data.quantity
            order.updated_at = get_datetime_utc()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(order)
        return self._to_public(order)

    def remove_item(self, user: User, item_id: uuid.UUID) -> CartPublic:
        try:
            order, item = self._lock_item(user, item_id)
            self.items.remove(item)
            order.updated_at = get_datetime_utc()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(order)
        return self._to_public(order)

    def _lock_or_create_draft(self, user: User) -> Order:
        order = self.orders.lock_draft(user.id)
        if order is None:
            order = self.orders.create_draft(user.id, settings.ORDER_CURRENCY)
        if order is None:
            # Lost the race for the user's single Draft: lock the winner's
            order = self.orders.lock_draft(user.id)
        if order is None:
            raise RuntimeError("Draft vanished")
        return order

    def _lock_item(self, user: User, item_id: uuid.UUID) -> tuple[Order, CartItem]:
        order = self.orders.lock_draft(user.id)
        if order is None:
            raise NotFoundError(ITEM_NOT_FOUND)
        item = self.items.get_in_order(order.id, item_id)
        if item is None:
            raise NotFoundError(ITEM_NOT_FOUND)
        return order, item

    def _to_public(self, order: Order | None) -> CartPublic:
        if order is None:
            return CartPublic(
                id=None,
                items=[],
                item_count=0,
                total_price=Decimal(0).quantize(PRICE_QUANTUM),
                total_weight=Decimal(0).quantize(WEIGHT_QUANTUM),
                can_place=False,
            )
        lines: list[CartItemPublic] = []
        available_pairs = []
        for item in order.items:
            product = item.product
            available = not product.is_deleted and product.stock >= item.quantity
            if available:
                available_pairs.append((product, item.quantity))
            lines.append(
                CartItemPublic(
                    id=item.id,
                    product_id=product.id,
                    name=product.name,
                    sku=product.sku,
                    image_url=(
                        product_image_url(product.image_key)
                        if product.image_key
                        else None
                    ),
                    unit_price=product.price,
                    quantity=item.quantity,
                    line_total=product.price * item.quantity,
                    available=available,
                    available_stock=0 if product.is_deleted else product.stock,
                )
            )
        total_price, total_weight = cart_totals(available_pairs)
        return CartPublic(
            id=order.id,
            items=lines,
            item_count=order.item_count,
            total_price=total_price,
            total_weight=total_weight,
            can_place=bool(lines) and all(line.available for line in lines),
        )
