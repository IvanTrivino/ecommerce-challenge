import logging
import uuid
from collections.abc import Callable, Mapping

from app.core.cache import invalidate_quietly
from app.core.exceptions import (
    PaymentRequiredError,
    ServiceUnavailableError,
)
from app.models import (
    Order,
    OrderNotification,
    OrderNotificationKind,
    OrderState,
    Product,
)
from app.models.base import get_datetime_utc
from app.repositories import (
    OrderNotificationRepository,
    OrderRepository,
    ProductRepository,
)
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
    """Owns every order state transition and the payment call."""

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
        """Move a locked, validated Draft to in_progress.

        The caller holds the locks and commits. If the charge fails, the caller's
        rollback undoes the stock and the fixed values.
        """
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
