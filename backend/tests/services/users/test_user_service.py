from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User
from app.repositories import UserRepository
from app.schemas import UserCreate, UserUpdate
from app.services import UserService
from tests.utils.utils import random_email, random_lower_string


def _service(db: Session) -> UserService:
    return UserService(UserRepository(db))


def test_create_user(db: Session) -> None:
    email = random_email()
    user = _service(db).create_user(
        UserCreate(email=email, password=random_lower_string())
    )
    assert user.email == email
    assert user.password != ""
    assert user.is_active is True
    assert user.is_superuser is False


def test_authenticate_user(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    service = _service(db)
    user = service.create_user(UserCreate(email=email, password=password))
    authenticated = service.authenticate(email, password)
    assert authenticated
    assert authenticated.id == user.id


def test_not_authenticate_user(db: Session) -> None:
    assert _service(db).authenticate(random_email(), random_lower_string()) is None


def test_update_user(db: Session) -> None:
    service = _service(db)
    user = service.create_user(
        UserCreate(email=random_email(), password=random_lower_string())
    )
    new_password = random_lower_string()
    service.update_user(user.id, UserUpdate(password=new_password, is_superuser=True))
    user_2 = UserRepository(db).get(user.id)
    assert user_2
    assert user_2.is_superuser is True
    verified, _ = verify_password(new_password, user_2.password)
    assert verified


def test_authenticate_user_with_bcrypt_upgrades_to_argon2(db: Session) -> None:
    """A user with a bcrypt password hash gets upgraded to argon2 on login."""
    email = random_email()
    password = random_lower_string()
    bcrypt_hash = BcryptHasher().hash(password)
    assert bcrypt_hash.startswith("$2")

    user = UserRepository(db).save(User(email=email, password=bcrypt_hash))
    assert user.password.startswith("$2")

    authenticated = _service(db).authenticate(email, password)
    assert authenticated
    db.refresh(authenticated)
    assert authenticated.password.startswith("$argon2")

    verified, updated_hash = verify_password(password, authenticated.password)
    assert verified
    assert updated_hash is None


def test_deleted_user_cannot_authenticate(db: Session) -> None:
    service = _service(db)
    email = random_email()
    password = random_lower_string()
    user = service.create_user(UserCreate(email=email, password=password))
    service.delete_user(
        user.id,
        service.create_user(
            UserCreate(email=random_email(), password=random_lower_string())
        ),
    )
    assert service.authenticate(email, password) is None


def test_can_register_again_after_delete(db: Session) -> None:
    service = _service(db)
    email = random_email()
    first = service.create_user(UserCreate(email=email, password=random_lower_string()))
    admin = service.create_user(
        UserCreate(email=random_email(), password=random_lower_string())
    )
    service.delete_user(first.id, admin)
    second = service.create_user(
        UserCreate(email=email, password=random_lower_string())
    )
    assert second.id != first.id
