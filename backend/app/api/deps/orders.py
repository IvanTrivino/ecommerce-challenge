from typing import Annotated

from fastapi import Depends

from app.api.deps.database import SessionDep
from app.repositories import (
    CartItemRepository,
    OrderNotificationRepository,
    OrderRepository,
    ProductRepository,
)
from app.services import (
    CartService,
    CheckoutService,
    MockPaymentsGateway,
    OrderService,
    PaymentsGateway,
)


def enqueue_order_notification(notification_id: int) -> None:
    from app.tasks import send_order_notification

    send_order_notification.delay(notification_id)


def get_payments_gateway() -> PaymentsGateway:
    return MockPaymentsGateway()


PaymentsGatewayDep = Annotated[PaymentsGateway, Depends(get_payments_gateway)]


def get_cart_service(session: SessionDep) -> CartService:
    return CartService(
        OrderRepository(session),
        CartItemRepository(session),
        ProductRepository(session),
    )


def get_order_service(session: SessionDep, gateway: PaymentsGatewayDep) -> OrderService:
    return OrderService(
        OrderRepository(session),
        ProductRepository(session),
        OrderNotificationRepository(session),
        gateway,
        enqueue_order_notification,
    )


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


def get_checkout_service(
    session: SessionDep, order_service: OrderServiceDep
) -> CheckoutService:
    return CheckoutService(
        OrderRepository(session), ProductRepository(session), order_service
    )


CartServiceDep = Annotated[CartService, Depends(get_cart_service)]
CheckoutServiceDep = Annotated[CheckoutService, Depends(get_checkout_service)]
