import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import emails
from jinja2 import Template

from app.core.config import settings
from app.models import Order, OrderNotificationKind

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    pass


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parents[2] / "email-templates" / template_name
    ).read_text()
    template: Template = Template(template_str, autoescape=True)
    html_content = template.render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
    raise_on_error: bool = False,
) -> None:
    assert settings.emails_enabled, "no provided configuration for email variables"
    assert settings.EMAILS_FROM_EMAIL  # For type checker
    message = emails.message.Message(
        subject=subject,
        html=html_content,
        mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    logger.info(f"send email result: {response}")
    if raise_on_error and response.status_code != 250:
        raise EmailDeliveryError(f"SMTP {response.status_code}: {response.error}")


def generate_test_email(email_to: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Test email"
    html_content = render_email_template(
        template_name="test_email.html",
        context={"project_name": settings.PROJECT_NAME, "email": email_to},
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Password recovery for user {email}"
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(
    email_to: str, username: str, password: str
) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - New account for user {username}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "password": password,
            "email": email_to,
            "link": settings.FRONTEND_HOST,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


ORDER_EMAILS = {
    OrderNotificationKind.PLACED: ("order_placed.html", "Order #{number} confirmed"),
    OrderNotificationKind.CANCELLED: (
        "order_cancelled.html",
        "Order #{number} cancelled",
    ),
    OrderNotificationKind.COMPLETED: (
        "order_completed.html",
        "Order #{number} completed",
    ),
}


def _money(amount: Decimal | None) -> str:
    return f"${amount or Decimal(0):,.2f}"


def generate_order_email(order: Order, kind: OrderNotificationKind) -> EmailData:
    template, subject = ORDER_EMAILS[kind]
    assert order.placed_at is not None
    context = {
        "project_name": settings.PROJECT_NAME,
        "number": order.number,
        "placed_at": f"{order.placed_at:%b %d, %Y %H:%M} UTC",
        "items": [
            {
                "name": item.name,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": _money(item.unit_price),
                "line_total": _money(item.line_total),
            }
            for item in order.items
        ],
        "total_price": _money(order.total_price),
        "total_weight": f"{order.total_weight or Decimal(0):.3f} kg",
        "payment_reference": order.payment_reference or "",
        "link": f"{settings.FRONTEND_HOST}/orders/{order.id}",
    }
    return EmailData(
        html_content=render_email_template(template_name=template, context=context),
        subject=f"{settings.PROJECT_NAME} - {subject.format(number=order.number)}",
    )
