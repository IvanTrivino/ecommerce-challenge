import uuid
from typing import Any

from fastapi import APIRouter

from app.api.deps import CartServiceDep, CheckoutServiceDep, CurrentUser
from app.schemas import (
    CartItemAdd,
    CartItemUpdate,
    CartPublic,
    OrderPublic,
    PlaceOrderRequest,
)

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("/", response_model=CartPublic)
def read_cart(service: CartServiceDep, current_user: CurrentUser) -> Any:
    return service.get_cart(current_user)


@router.post("/items", response_model=CartPublic)
def add_cart_item(
    service: CartServiceDep, current_user: CurrentUser, item_in: CartItemAdd
) -> Any:
    return service.add_item(current_user, item_in)


@router.patch("/items/{item_id}", response_model=CartPublic)
def update_cart_item(
    service: CartServiceDep,
    current_user: CurrentUser,
    item_id: uuid.UUID,
    item_in: CartItemUpdate,
) -> Any:
    return service.update_item(current_user, item_id, item_in)


@router.delete("/items/{item_id}", response_model=CartPublic)
def remove_cart_item(
    service: CartServiceDep, current_user: CurrentUser, item_id: uuid.UUID
) -> Any:
    return service.remove_item(current_user, item_id)


@router.post("/place", response_model=OrderPublic)
def place_order(
    service: CheckoutServiceDep, current_user: CurrentUser, place_in: PlaceOrderRequest
) -> Any:
    return service.place(current_user, place_in)
