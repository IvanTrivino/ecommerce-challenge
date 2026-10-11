import uuid
from collections.abc import Sequence

from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.security import get_password_hash, verify_password
from app.models import User
from app.repositories import UserRepository
from app.schemas import (
    UpdatePassword,
    UserCreate,
    UserRegister,
    UserUpdate,
    UserUpdateMe,
)

# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    # Queries
    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.repo.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.repo.get_by_email(email)

    def list_users(self, *, skip: int, limit: int) -> tuple[Sequence[User], int]:
        return self.repo.list(skip=skip, limit=limit), self.repo.count()

    # Commands
    def create_user(self, user_in: UserCreate) -> User:
        if self.repo.get_by_email(user_in.email):
            raise BadRequestError(
                "The user with this email already exists in the system"
            )
        user = User(
            **user_in.model_dump(exclude={"password"}),
            password=get_password_hash(user_in.password),
        )
        return self.repo.save(user)

    def register(self, user_in: UserRegister) -> User:
        return self.create_user(UserCreate.model_validate(user_in.model_dump()))

    def update_user(self, user_id: uuid.UUID, user_in: UserUpdate) -> User:
        user = self.repo.get(user_id)
        if not user:
            raise NotFoundError("The user with this id does not exist in the system")
        self._ensure_email_available(user_in.email, user_id)
        return self._apply_update(user, user_in)

    def update_me(self, user: User, user_in: UserUpdateMe) -> User:
        self._ensure_email_available(user_in.email, user.id)
        return self._apply_update(user, user_in)

    def reset_password(self, user: User, new_password: str) -> User:
        return self._apply_update(user, UserUpdate(password=new_password))

    def update_password(self, user: User, body: UpdatePassword) -> None:
        verified, _ = verify_password(body.current_password, user.password)
        if not verified:
            raise BadRequestError("Incorrect password")
        if body.current_password == body.new_password:
            raise BadRequestError("New password cannot be the same as the current one")
        user.password = get_password_hash(body.new_password)
        self.repo.save(user)

    def delete_me(self, user: User) -> None:
        if user.is_superuser:
            raise ForbiddenError("Super users are not allowed to delete themselves")
        self.repo.delete(user)

    def delete_user(self, user_id: uuid.UUID, current_user: User) -> None:
        user = self.repo.get(user_id)
        if not user:
            raise NotFoundError("User not found")
        if user == current_user:
            raise ForbiddenError("Super users are not allowed to delete themselves")
        self.repo.delete(user)

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.repo.get_by_email(email)
        if not user:
            # Run the verification anyway so response time doesn't reveal
            # whether the email exists.
            verify_password(password, DUMMY_HASH)
            return None
        verified, updated_hash = verify_password(password, user.password)
        if not verified:
            return None
        if updated_hash:
            user.password = updated_hash
            self.repo.save(user)
        return user

    # Helpers
    def _ensure_email_available(self, email: str | None, user_id: uuid.UUID) -> None:
        if not email:
            return
        existing = self.repo.get_by_email(email)
        if existing and existing.id != user_id:
            raise ConflictError("User with this email already exists")

    def _apply_update(self, user: User, user_in: UserUpdate | UserUpdateMe) -> User:
        data = user_in.model_dump(exclude_unset=True)
        password = data.pop("password", None)
        for field, value in data.items():
            setattr(user, field, value)
        if password is not None:
            user.password = get_password_hash(password)
        return self.repo.save(user)
