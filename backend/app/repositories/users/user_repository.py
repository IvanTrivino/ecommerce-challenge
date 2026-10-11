from sqlalchemy.orm import Session

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """User-specific queries. Generic CRUD comes from `BaseRepository`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalars(self._live().where(User.email == email)).first()
