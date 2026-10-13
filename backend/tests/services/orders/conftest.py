from sqlalchemy.orm import Session

from app.models import User
from app.repositories import CartItemRepository, OrderRepository, ProductRepository
from app.services import CartService


def cart_service(session: Session) -> CartService:
    return CartService(
        OrderRepository(session),
        CartItemRepository(session),
        ProductRepository(session),
    )


def load_user(session: Session, user: User) -> User:
    loaded = session.get(User, user.id)
    assert loaded is not None
    return loaded
