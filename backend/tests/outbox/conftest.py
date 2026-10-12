import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models import OutboxEvent


@pytest.fixture(autouse=True)
def clean_outbox() -> None:
    with Session(engine) as session:
        session.execute(delete(OutboxEvent))
        session.commit()
