from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import UserRepository
from app.schemas import UserCreate
from app.services import UserService

engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


def init_db(session: Session) -> None:
    # Tables are created with Alembic migrations
    service = UserService(UserRepository(session))
    if not service.get_by_email(settings.FIRST_SUPERUSER):
        service.create_user(
            UserCreate(
                email=settings.FIRST_SUPERUSER,
                password=settings.FIRST_SUPERUSER_PASSWORD,
                is_superuser=True,
            )
        )
