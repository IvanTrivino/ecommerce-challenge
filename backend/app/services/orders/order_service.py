import logging
import uuid
from collections.abc import Callable, Collection, Mapping

from app.core.cache import invalidate_quietly
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PaymentRequiredError,
    ServiceUnavailableError,
)
from app.models import (
    PLACED_STATES,
    Order,
    OrderNotification,
    OrderNotificationKind,
    OrderState,
    Product,
    User,
)
from app.models.base import get_datetime_utc
from app.repositories import (
    OrderNotificationRepository,
    OrderRepository,
    ProductRepository,
)
from app.schemas import OrdersPublic, OrderSummaryPublic
from app.services.orders.payments import (
    PaymentGatewayError,
    PaymentResult,
    PaymentsGateway,
    PaymentStatus,
)
from app.services.orders.pricing import cart_totals
from app.services.products.cache import PRODUCTS

logger = logging.getLogger(__name__)

Enqueue = Callable[[int], None]


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        products: ProductRepository,
        notifications: OrderNotificationRepository,
        gateway: PaymentsGateway,
        enqueue: Enqueue | None = None,
    ) -> None:
        self.orders = orders
        self.products = products
        self.notifications = notifications
        self.gateway = gateway
        self.session = orders.session
        self._enqueue = enqueue

    def place(
        self, order: Order, products: Mapping[uuid.UUID, Product]
    ) -> OrderNotification:
        now = get_datetime_utc()
        for item in order.items:
            product = products[item.product_uuid]
            product.stock -= item.quantity
            item.unit_price = product.price
            item.unit_weight = product.weight
            item.product_name = product.name
            item.product_sku = product.sku
        order.total_price, order.total_weight = cart_totals(
            (products[item.product_uuid], item.quantity) for item in order.items
        )
        result = self._charge(order)
        order.state = OrderState.IN_PROGRESS.value
        order.placed_at = now
        order.payment_reference = result.reference
        return self.notifications.add(order.id, OrderNotificationKind.PLACED, now=now)

    def cancel(self, order_id: uuid.UUID) -> Order:
        try:
            order = self._lock_in_progress(
                order_id, "Only in-progress orders can be cancelled"
            )
            products = self.products.lock_many({i.product_uuid for i in order.items})
            for item in order.items:
                products[item.product_uuid].stock += item.quantity
            now = get_datetime_utc()
            order.state = OrderState.CANCELLED.value
            order.cancelled_at = now
            notification = self.notifications.add(
                order.id, OrderNotificationKind.CANCELLED, now=now
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(
            "Order %s cancelled: %s in %d lines",
            order.id,
            order.total_price,
            len(order.items),
        )
        self.after_commit(notification.id, stock_changed=True)
        self.session.refresh(order)
        return order

    def complete(self, order_id: uuid.UUID) -> Order:
        try:
            order = self._lock_in_progress(
                order_id, "Only in-progress orders can be completed"
            )
            now = get_datetime_utc()
            order.state = OrderState.COMPLETED.value
            order.completed_at = now
            notification = self.notifications.add(
                order.id, OrderNotificationKind.COMPLETED, now=now
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(
            "Order %s completed: %s in %d lines",
            order.id,
            order.total_price,
            len(order.items),
        )
        self.after_commit(notification.id, stock_changed=False)
        self.session.refresh(order)
        return order

    def get(self, order_id: uuid.UUID) -> Order:
        order = self.orders.get(order_id)
        if order is None:
            raise NotFoundError("Order not found")
        return order

    def list_orders(
        self, states: Collection[str] | None, *, skip: int, limit: int
    ) -> OrdersPublic:
        wanted = states or [state.value for state in PLACED_STATES]
        orders = self.orders.list_by_states(wanted, skip=skip, limit=limit)
        return OrdersPublic(
            data=[OrderSummaryPublic.model_validate(o) for o in orders],
            count=self.orders.count_by_states(wanted),
        )

    def list_for_user(self, user: User, *, skip: int, limit: int) -> OrdersPublic:
        orders = self.orders.list_placed_for_user(user.id, skip=skip, limit=limit)
        return OrdersPublic(
            data=[OrderSummaryPublic.model_validate(o) for o in orders],
            count=self.orders.count_placed_for_user(user.id),
        )

    def get_for_user(self, user: User, order_id: uuid.UUID) -> Order:
        order = self.orders.get_placed_for_user(order_id, user.id)
        if order is None:
            raise NotFoundError("Order not found")
        return order

    def _lock_in_progress(self, order_id: uuid.UUID, message: str) -> Order:
        order = self.orders.lock(order_id)
        if order is None:
            raise NotFoundError("Order not found")
        if order.state != OrderState.IN_PROGRESS:
            raise ConflictError(message)
        return order

    def _charge(self, order: Order) -> PaymentResult:
        assert order.total_price is not None
        try:
            result = self.gateway.charge(
                order_id=order.id, amount=order.total_price, currency=order.currency
            )
        except PaymentGatewayError as exc:
            logger.warning(
                "Payment gateway error for order %s", order.id, exc_info=True
            )
            raise ServiceUnavailableError("Payment service unavailable") from exc
        if result.status != PaymentStatus.APPROVED:
            raise PaymentRequiredError("Payment declined")
        return result

    def after_commit(self, notification_id: int, *, stock_changed: bool) -> None:
        if stock_changed:
            invalidate_quietly(PRODUCTS)
        self._enqueue_quietly(notification_id)

    def _enqueue_quietly(self, notification_id: int) -> None:
        if self._enqueue is None:
            return
        try:
            self._enqueue(notification_id)
        except Exception:
            # Beat re-enqueues pending notifications
            logger.warning(
                "Could not enqueue order notification %s",
                notification_id,
                exc_info=True,
            )
