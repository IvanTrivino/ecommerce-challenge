import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PLACED_STATES, Order, OrderState
from app.repositories.base import BaseRepository, constraint_name

DRAFT_INDEX = "ux_order_user_draft"


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Order)

    def _locked(self) -> Select[tuple[Order]]:
        return (
            self._live()
            .with_for_update(of=Order)
            .execution_options(populate_existing=True)
        )

    def lock(
        self, order_id: uuid.UUID, *, user_id: uuid.UUID | None = None
    ) -> Order | None:
        """Lock one order. With user_id, only if the user owns it."""
        statement = self._locked().where(Order.id == order_id)
        if user_id is not None:
            statement = statement.where(Order.user_uuid == user_id)
        return self.session.scalars(statement).first()

    def lock_draft(self, user_id: uuid.UUID) -> Order | None:
        """The user's Draft, locked. None if there isn't one."""
        statement = self._locked().where(
            Order.user_uuid == user_id, Order.state == OrderState.DRAFT.value
        )
        return self.session.scalars(statement).first()

    def get_draft(self, user_id: uuid.UUID) -> Order | None:
        statement = self._live().where(
            Order.user_uuid == user_id, Order.state == OrderState.DRAFT.value
        )
        return self.session.scalars(statement).first()

    def create_draft(self, user_id: uuid.UUID, currency: str) -> Order | None:
        """Insert a Draft inside a SAVEPOINT.

        Returns None if another transaction created the user's Draft first.
        """
        try:
            with self.session.begin_nested():
                order = Order(user_uuid=user_id, currency=currency)
                self.session.add(order)
                self.session.flush()
            return order
        except IntegrityError as exc:
            if constraint_name(exc) != DRAFT_INDEX:
                raise
            return None

    def _placed_for_user(self, user_id: uuid.UUID) -> Select[tuple[Order]]:
        return self._live().where(
            Order.user_uuid == user_id,
            Order.state.in_([s.value for s in PLACED_STATES]),
        )

    def list_placed_for_user(
        self, user_id: uuid.UUID, *, skip: int = 0, limit: int = 10
    ) -> Sequence[Order]:
        statement = (
            self._placed_for_user(user_id)
            .order_by(Order.placed_at.desc(), Order.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def count_placed_for_user(self, user_id: uuid.UUID) -> int:
        statement = select(func.count()).select_from(
            self._placed_for_user(user_id).subquery()
        )
        return self.session.scalar(statement) or 0

    def get_placed_for_user(
        self, order_id: uuid.UUID, user_id: uuid.UUID
    ) -> Order | None:
        statement = self._placed_for_user(user_id).where(Order.id == order_id)
        return self.session.scalars(statement).first()

    def _in_states(self, states: Collection[str]) -> Select[tuple[Order]]:
        return self._live().where(Order.state.in_(states))

    def list_by_states(
        self, states: Collection[str], *, skip: int = 0, limit: int = 20
    ) -> Sequence[Order]:
        statement = (
            self._in_states(states)
            .order_by(
                func.coalesce(Order.placed_at, Order.updated_at).desc(),
                Order.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def count_by_states(self, states: Collection[str]) -> int:
        statement = select(func.count()).select_from(self._in_states(states).subquery())
        return self.session.scalar(statement) or 0
