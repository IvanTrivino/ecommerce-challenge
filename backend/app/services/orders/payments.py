import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger(__name__)


class PaymentStatus(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"


@dataclass(frozen=True)
class PaymentResult:
    status: PaymentStatus
    reference: str | None = None


class PaymentGatewayError(Exception):
    pass


class PaymentsGateway(Protocol):
    def charge(
        self, *, order_id: uuid.UUID, amount: Decimal, currency: str
    ) -> PaymentResult: ...


class MockPaymentsGateway:
    def charge(
        self, *, order_id: uuid.UUID, amount: Decimal, currency: str
    ) -> PaymentResult:
        logger.info("Mock charge of %s %s for order %s", amount, currency, order_id)
        return PaymentResult(PaymentStatus.APPROVED, f"mock_{order_id.hex[:8].upper()}")
