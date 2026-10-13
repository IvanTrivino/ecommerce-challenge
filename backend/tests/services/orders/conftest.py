from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models import User
from app.repositories import (
    CartItemRepository,
    OrderNotificationRepository,
    OrderRepository,
    ProductRepository,
)
from app.schemas import CartPublic, PlaceOrderRequest
from app.services import (
    CartService,
    CheckoutService,
    MockPaymentsGateway,
    OrderService,
    PaymentsGateway,
)


def cart_service(session: Session) -> CartService:
    return CartService(
        OrderRepository(session),
        CartItemRepository(session),
        ProductRepository(session),
    )


def order_service(
    session: Session,
    gateway: PaymentsGateway | None = None,
    enqueue: Callable[[int], None] | None = None,
) -> OrderService:
    return OrderService(
        OrderRepository(session),
        ProductRepository(session),
        OrderNotificationRepository(session),
        gateway or MockPaymentsGateway(),
        enqueue,
    )


def checkout_service(
    session: Session,
    gateway: PaymentsGateway | None = None,
    enqueue: Callable[[int], None] | None = None,
) -> CheckoutService:
    return CheckoutService(
        OrderRepository(session),
        ProductRepository(session),
        order_service(session, gateway, enqueue),
    )


def place_request(cart: CartPublic, **overrides: object) -> PlaceOrderRequest:
    assert cart.id is not None
    values: dict[str, object] = {
        "order_id": cart.id,
        "expected_total": cart.total_price,
    } | overrides
    return PlaceOrderRequest.model_validate(values)


def load_user(session: Session, user: User) -> User:
    loaded = session.get(User, user.id)
    assert loaded is not None
    return loaded
