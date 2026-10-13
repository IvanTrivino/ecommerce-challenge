from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.repositories import UserRepository
from tests.utils.utils import random_email


def test_save_and_get(db: Session) -> None:
    repo = UserRepository(db)
    user = repo.save(User(email=random_email(), password="x"))
    fetched = repo.get(user.id)
    assert fetched
    assert fetched.email == user.email
    assert repo.get_by_email(user.email) == user


def test_delete_is_soft(db: Session) -> None:
    repo = UserRepository(db)
    user = repo.save(User(email=random_email(), password="x"))
    repo.delete(user)
    db.expire_all()
    row = db.scalars(select(User).where(User.id == user.id)).one()
    assert row.is_deleted is True
    assert repo.get(user.id) is None


def test_deleted_users_excluded_from_list_and_count(db: Session) -> None:
    repo = UserRepository(db)
    before = repo.count()
    user = repo.save(User(email=random_email(), password="x"))
    assert repo.count() == before + 1
    repo.delete(user)
    assert repo.count() == before
    assert user.id not in {u.id for u in repo.list(skip=0, limit=1000)}


def test_email_can_be_reused_after_delete(db: Session) -> None:
    repo = UserRepository(db)
    email = random_email()
    repo.delete(repo.save(User(email=email, password="x")))
    new_user = repo.save(User(email=email, password="y"))
    assert repo.get_by_email(email) == new_user
