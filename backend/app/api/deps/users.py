from typing import Annotated

from fastapi import Depends

from app.api.deps.database import SessionDep
from app.repositories import UserRepository
from app.services import UserService


def get_user_service(session: SessionDep) -> UserService:
    return UserService(UserRepository(session))


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
