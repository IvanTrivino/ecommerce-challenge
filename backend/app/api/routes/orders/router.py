import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import OrderServiceDep, get_current_active_superuser
from app.schemas import OrderPublic, OrdersPublic, OrderStateLiteral

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    dependencies=[Depends(get_current_active_superuser)],
)


@router.get("/", response_model=OrdersPublic)
def read_orders(
    service: OrderServiceDep,
    state: Annotated[list[OrderStateLiteral] | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Any:
    return service.list_orders(state, skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderPublic)
def read_order(service: OrderServiceDep, order_id: uuid.UUID) -> Any:
    return service.get(order_id)


@router.post("/{order_id}/cancel", response_model=OrderPublic)
def cancel_order(service: OrderServiceDep, order_id: uuid.UUID) -> Any:
    return service.cancel(order_id)


@router.post("/{order_id}/complete", response_model=OrderPublic)
def complete_order(service: OrderServiceDep, order_id: uuid.UUID) -> Any:
    return service.complete(order_id)
