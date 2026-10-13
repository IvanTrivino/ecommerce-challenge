from typing import Annotated

from fastapi import Depends

from app.api.deps.database import SessionDep
from app.repositories import CartItemRepository, OrderRepository, ProductRepository
from app.services import CartService


def get_cart_service(session: SessionDep) -> CartService:
    return CartService(
        OrderRepository(session),
        CartItemRepository(session),
        ProductRepository(session),
    )


CartServiceDep = Annotated[CartService, Depends(get_cart_service)]
