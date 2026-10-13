import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    CurrentUser,
    OrderServiceDep,
    UserServiceDep,
    get_current_active_superuser,
)
from app.core.config import settings
from app.schemas import (
    Message,
    OrderPublic,
    OrdersPublic,
    UpdatePassword,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)
from app.services.email.email_service import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
)
def read_users(service: UserServiceDep, skip: int = 0, limit: int = 100) -> Any:
    users, count = service.list_users(skip=skip, limit=limit)
    return UsersPublic(
        data=[UserPublic.model_validate(user) for user in users], count=count
    )


@router.post(
    "/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic
)
def create_user(*, service: UserServiceDep, user_in: UserCreate) -> Any:
    user = service.create_user(user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *, service: UserServiceDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    return service.update_me(current_user, user_in)


@router.patch("/me/password", response_model=Message)
def update_password_me(
    *, service: UserServiceDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    service.update_password(current_user, body)
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    return current_user


@router.get("/me/orders", response_model=OrdersPublic)
def read_my_orders(
    service: OrderServiceDep,
    current_user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> Any:
    return service.list_for_user(current_user, skip=skip, limit=limit)


@router.get("/me/orders/{order_id}", response_model=OrderPublic)
def read_my_order(
    service: OrderServiceDep, current_user: CurrentUser, order_id: uuid.UUID
) -> Any:
    return service.get_for_user(current_user, order_id)


@router.delete("/me", response_model=Message)
def delete_user_me(service: UserServiceDep, current_user: CurrentUser) -> Any:
    service.delete_me(current_user)
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(service: UserServiceDep, user_in: UserRegister) -> Any:
    return service.register(user_in)


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID, service: UserServiceDep, current_user: CurrentUser
) -> Any:
    user = service.get_by_id(user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
def update_user(
    *,
    service: UserServiceDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    return service.update_user(user_id, user_in)


@router.delete("/{user_id}", dependencies=[Depends(get_current_active_superuser)])
def delete_user(
    service: UserServiceDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Message:
    service.delete_user(user_id, current_user)
    return Message(message="User deleted successfully")
