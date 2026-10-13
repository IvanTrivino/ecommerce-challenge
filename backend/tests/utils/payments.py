import threading
import uuid
from decimal import Decimal

from app.services.orders.payments import (
    MockPaymentsGateway,
    PaymentGatewayError,
    PaymentResult,
    PaymentStatus,
)


class DecliningGateway:
    def charge(
        self, *, order_id: uuid.UUID, amount: Decimal, currency: str
    ) -> PaymentResult:
        return PaymentResult(PaymentStatus.DECLINED)


class BrokenGateway:
    def charge(
        self, *, order_id: uuid.UUID, amount: Decimal, currency: str
    ) -> PaymentResult:
        raise PaymentGatewayError("provider unreachable")


class BlockingGateway(MockPaymentsGateway):
    """Approves after `release` is set, while the caller still holds its locks."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def charge(
        self, *, order_id: uuid.UUID, amount: Decimal, currency: str
    ) -> PaymentResult:
        self.entered.set()
        assert self.release.wait(timeout=10)
        return super().charge(order_id=order_id, amount=amount, currency=currency)
