import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import emails
import pytest

from app.core.config import settings
from app.models import CartItem, Order, OrderNotificationKind, Product, User
from app.services.email.email_service import (
    EmailDeliveryError,
    generate_order_email,
    send_email,
)


def make_order(*names: str) -> Order:
    user = User(id=uuid.uuid4(), email="buyer@example.com", password="x")
    order = Order(
        id=uuid.uuid4(),
        user_uuid=user.id,
        user=user,
        currency="USD",
        state="in_progress",
        total_price=Decimal("1234.50"),
        total_weight=Decimal("2.500"),
        payment_reference="mock_ABCDEF12",
        placed_at=datetime(2026, 10, 12, 9, 30, tzinfo=UTC),
    )
    for index, name in enumerate(names):
        product = Product(
            id=uuid.uuid4(), name=name, sku=f"SKU-{index}", price=Decimal(1)
        )
        order.items.append(
            CartItem(
                id=uuid.uuid4(),
                product_uuid=product.id,
                product=product,
                quantity=index + 1,
                unit_price=Decimal("1000.00"),
                unit_weight=Decimal("0.500"),
                product_name=name,
                product_sku=f"SKU-{index}",
            )
        )
    return order


def test_placed_email_has_the_order_details() -> None:
    order = make_order("Mug", "Teapot")

    email = generate_order_email(order, OrderNotificationKind.PLACED)

    assert email.subject == f"{settings.PROJECT_NAME} - Order #{order.number} confirmed"
    html = email.html_content
    for expected in [
        order.number,
        "Oct 12, 2026 09:30 UTC",
        "Mug",
        "Teapot",
        "SKU-0",
        "SKU-1",
        "$1,000.00",
        "$2,000.00",
        "$1,234.50",
        "2.500 kg",
        "mock_ABCDEF12",
        f"{settings.FRONTEND_HOST}/orders/{order.id}",
    ]:
        assert expected in html
    assert html.count("SKU-0") == 1
    assert html.count("SKU-1") == 1
    assert "{%" not in html
    assert "{{" not in html


def test_the_item_loop_runs_once_per_item() -> None:
    html = generate_order_email(
        make_order("A", "B", "C"), OrderNotificationKind.PLACED
    ).html_content

    assert [html.count(f"SKU-{i}") for i in range(3)] == [1, 1, 1]
    assert html.count("×") == 3


@pytest.mark.parametrize(
    ("kind", "word"),
    [
        (OrderNotificationKind.CANCELLED, "cancelled"),
        (OrderNotificationKind.COMPLETED, "completed"),
    ],
)
def test_other_emails_have_number_total_and_link(
    kind: OrderNotificationKind, word: str
) -> None:
    order = make_order("Mug")

    email = generate_order_email(order, kind)

    assert email.subject == f"{settings.PROJECT_NAME} - Order #{order.number} {word}"
    assert order.number in email.html_content
    assert "$1,234.50" in email.html_content
    assert f"{settings.FRONTEND_HOST}/orders/{order.id}" in email.html_content


def test_product_names_are_escaped() -> None:
    html = generate_order_email(
        make_order("<script>alert(1)</script>"), OrderNotificationKind.PLACED
    ).html_content

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", "shop@example.com")


@pytest.mark.usefixtures("smtp")
def test_send_email_raises_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = SimpleNamespace(status_code=None, error=ConnectionRefusedError("down"))
    monkeypatch.setattr(emails.message.Message, "send", lambda *a, **k: failed)

    send_email(email_to="a@example.com", subject="s", html_content="<p>x</p>")
    with pytest.raises(EmailDeliveryError, match="down"):
        send_email(
            email_to="a@example.com",
            subject="s",
            html_content="<p>x</p>",
            raise_on_error=True,
        )


@pytest.mark.usefixtures("smtp")
def test_send_email_accepts_a_250(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = SimpleNamespace(status_code=250, error=None)
    monkeypatch.setattr(emails.message.Message, "send", lambda *a, **k: ok)

    send_email(
        email_to="a@example.com", subject="s", html_content="x", raise_on_error=True
    )
