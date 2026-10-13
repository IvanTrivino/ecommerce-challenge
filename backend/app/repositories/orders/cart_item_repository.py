import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CartItem


class CartItemRepository:
    """Lines are hard-deleted from a Draft, so this doesn't extend BaseRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_in_order(self, order_id: uuid.UUID, item_id: uuid.UUID) -> CartItem | None:
        statement = select(CartItem).where(
            CartItem.order_uuid == order_id, CartItem.id == item_id
        )
        return self.session.scalars(statement).first()

    def get_for_product(
        self, order_id: uuid.UUID, product_id: uuid.UUID
    ) -> CartItem | None:
        statement = select(CartItem).where(
            CartItem.order_uuid == order_id, CartItem.product_uuid == product_id
        )
        return self.session.scalars(statement).first()

    def add(self, item: CartItem) -> None:
        self.session.add(item)
        self.session.flush()

    def remove(self, item: CartItem) -> None:
        self.session.delete(item)
        self.session.flush()
