import logging
from collections.abc import Sequence

from app.core.exceptions import NotFoundError
from app.models import Order, OrderState, User
from app.repositories import OrderRepository, ProductRepository
from app.schemas import PlaceOrderRequest
from app.services.orders.checkout.validators import (
    DEFAULT_VALIDATORS,
    CheckoutContext,
    CheckoutValidator,
)
from app.services.orders.order_service import OrderService

logger = logging.getLogger(__name__)


class CheckoutService:
    def __init__(
        self,
        orders: OrderRepository,
        products: ProductRepository,
        order_service: OrderService,
        validators: Sequence[CheckoutValidator] = DEFAULT_VALIDATORS,
    ) -> None:
        self.orders = orders
        self.products = products
        self.order_service = order_service
        self.validators = validators

    def place(self, user: User, data: PlaceOrderRequest) -> Order:
        session = self.orders.session
        try:
            order = self.orders.lock(data.order_id, user_id=user.id)
            if order is None:
                raise NotFoundError("Order not found")
            if order.state != OrderState.DRAFT:
                # Already placed: release the lock and answer with it as is
                session.rollback()
                return order
            products = self.products.lock_many({i.product_uuid for i in order.items})
            ctx = CheckoutContext(order, products, data.expected_total)
            for validator in self.validators:
                validator.validate(ctx)
            notification = self.order_service.place(order, products)
            session.commit()
        except Exception:
            session.rollback()
            raise
        logger.info(
            "Order %s placed by %s: %s in %d lines",
            order.id,
            user.id,
            order.total_price,
            len(order.items),
        )
        self.order_service.after_commit(notification.id, stock_changed=True)
        session.refresh(order)
        return order
