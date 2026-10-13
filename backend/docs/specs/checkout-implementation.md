# Implementation Plan: Cart, Checkout and Orders (backend)

This plan is for the engineer or model implementing the backend part of
[`checkout.md`](./checkout.md) (the **spec**). The spec decides *what* to build. This document
decides *how* and *in what order*. If the two disagree, the spec wins: stop and ask rather than
guess.

Requirement IDs (`FR-x`, `NFR-x`, `AC-x`, `Dx`) refer to the spec. The frontend has its own plan
([`frontend/docs/specs/checkout-implementation.md`](../../../frontend/docs/specs/checkout-implementation.md)).
It can start once **Step 6** of this plan is merged and the client is regenerated, because it needs
the new OpenAPI schema. **Appendix B** is the API contract the frontend relies on: the route
function names there are fixed.

**Read the whole spec before starting.** The concurrency rules matter most, and the spec explains
them:

- row locks and their order (D6, D11, FR-2.6, NFR-2)
- idempotent placement (D12)
- the notification outbox (D9, D10, FR-6)

---

## 0. Before you start

### 0.1 Read these files first

| File | Why |
|---|---|
| `backend/docs/specs/product-images-implementation.md` §0.2–0.3 | **Commands and codebase rules. They apply unchanged** (Python 3.14, PEP 695, `mypy --strict`, `ty`, ruff, no `print`, sparse comments, commit format) |
| `backend/docs/specs/product-imports-implementation.md` §0.3–0.4 | More rules: settings read at call time, `save()` commits, the API layer passes an `enqueue` callable into services, operation ids |
| `backend/README.md` | Layering: api → services → repositories → models |
| `app/models/base.py`, `app/models/products/product.py`, `app/models/products/product_import.py` | `Base` (UUID id, soft delete, timestamps) vs `ModelBase` (bare). Partial unique indexes, `CheckConstraint`, relationships |
| `app/models/outbox/outbox_event.py`, `app/repositories/outbox/outbox_repository.py` | The model for `order_notification`: identity PK, status column, `available_at`, `claim_batch()` with `FOR UPDATE SKIP LOCKED` |
| `app/outbox/listeners.py`, `app/outbox/fields.py` | The search listener emits events only when `PRODUCT_SEARCH_FIELDS` change. `stock` isn't one of them, so stock changes emit nothing (spec D6) |
| `app/repositories/base.py` | `_live()`, `get()`, `save()` (**commits**), `delete()` (soft) |
| `app/repositories/products/product_repository.py` | You add `lock_many()` |
| `app/services/products/product_service.py`, `app/services/products/imports/service.py` | Service style, `AppError` subclasses, the injected `Enqueue` callable, `_constraint_name(IntegrityError)` |
| `app/core/cache.py`, `app/services/products/cache.py` | `PRODUCTS` namespace and `invalidate_quietly()` |
| `app/core/exceptions.py`, `app/main.py` | `AppError` → JSON `{"detail": …}`. Operation ids are `<tag>-<route function name>` |
| `app/api/deps/product_imports.py`, `app/api/routes/product_imports/router.py` | Dependency + router style, and the lazy `from app.tasks import …` inside the enqueue function |
| `app/api/routes/users/router.py` | Where the customer's "my orders" routes go |
| `app/core/celery_app.py`, `app/tasks.py`, `tests/test_tasks.py` | Task and beat style, and how tasks are run eagerly in tests (`task.apply(args=[…])`) |
| `app/services/email/email_service.py`, `app/email-templates/*.html` | `render_email_template`, `send_email`, the `generate_*_email` functions |
| `packages/react-email/emails/*.tsx`, `packages/react-email/ui/*.tsx` | **Email templates are written in React Email and exported to HTML with Jinja placeholders.** Don't hand-write HTML |
| `app/alembic/versions/0005_create_product_import_tables.py` | Migration style (explicit `op.create_table`, partial indexes with `postgresql_where`) |
| `tests/conftest.py`, `tests/utils/user.py`, `tests/utils/product.py`, `tests/api/routes/product_imports/test_product_imports.py` | Fixtures, helpers, how the `enqueue` function is monkeypatched in API tests |
| `tests/search/test_worker.py`, `tests/repositories/products/test_product_upsert.py` (`test_concurrently_created_sku_is_updated_not_rejected`) | How the existing tests use threads and separate sessions against the real Postgres |

### 0.2 Running checks

From the repo root:

```bash
docker compose up -d
docker compose exec backend alembic upgrade head             # after Step 1
docker compose exec backend bash scripts/tests-start.sh -x   # tests (extra pytest args are passed through)
docker compose exec backend bash scripts/lint.sh             # mypy (strict), ty, ruff check, ruff format --check
docker compose exec backend ruff format app tests            # auto-format
npx bun run email:export                                     # Step 7: React Email → backend/app/email-templates
bash scripts/generate-client.sh                              # Step 10: refresh frontend/openapi.json + client
```

**At the end of every step, `tests-start.sh` and `lint.sh` must pass.** Tests talk to the real
Postgres. The cache is `FakeRedis` (autouse fixture). Never mock the database.

Mailpit (<http://localhost:8025>) catches every email the dev stack sends. Use it to check
templates by hand in Step 8.

### 0.3 Rules for this codebase

Everything in the images plan §0.3 and the imports plan §0.3 applies. In addition:

- Work on a branch (suggested: `checkout`). One commit per step, in the repo's format:
  `(feat): …`, `(test): …`, `(chore): …`.
- New code lives in an `orders` package at every layer:
  - `app/models/orders/`
  - `app/repositories/orders/`
  - `app/schemas/orders/`
  - `app/services/orders/`
  - `app/api/routes/cart/`, `app/api/routes/orders/`
  - `app/api/deps/orders.py`

  Export public names from each package's `__init__.py` **and** from the top-level
  `app/models/__init__.py`, `app/repositories/__init__.py`, `app/schemas/__init__.py` and
  `app/services/__init__.py`, keeping `__all__` sorted. That's what the existing packages do.
- **Services never import `app.tasks`** (circular import). The API dependency passes an
  `enqueue` callable into the service, as `app/api/deps/product_imports.py` does.
- Money is `Decimal` everywhere. Never `float`. Quantize prices with `Decimal("0.01")` and weights
  with `Decimal("0.001")`.
- Services own transactions in this feature. Repositories **don't** commit, except the inherited
  `save()`, which you won't use for orders. Every service method that writes follows this pattern:

  ```python
  try:
      ...  # locks, checks, writes
      self.session.commit()
  except Exception:
      self.session.rollback()
      raise
  ```

  Side effects that must not happen if the transaction fails run **after** the commit: cache
  invalidation and enqueueing.

### 0.4 Existing behaviour that affects this work

1. **`BaseRepository.save()` commits.** Don't call it inside placement, cancel or cart writes.
   Each of these is one transaction with one commit at the end. Use `session.add()` /
   `session.flush()`.
2. **The session doesn't refresh objects it already holds.** If an `Order` is already in the
   session's identity map, a later `SELECT … FOR UPDATE` returns the **cached** attribute values,
   not the ones in the database. Every locking query in this plan must use
   `.execution_options(populate_existing=True)`. Otherwise the "is it still a Draft?" re-check
   after waiting on a lock reads stale data, and two concurrent placements both see `draft`.
3. **`FOR UPDATE` and outer joins.** Postgres rejects `FOR UPDATE` on the nullable side of an
   outer join, and SQLAlchemy uses `LEFT OUTER JOIN` for `lazy="joined"` unless
   `innerjoin=True`. So:
   - Locking queries use `.with_for_update(of=Order)` (or `of=Product`).
   - Relationships that are always present use `lazy="joined", innerjoin=True`.
4. **`order` is a reserved word.** SQLAlchemy and Alembic quote it automatically, as they do for
   `"user"`. In any raw `sa.text(...)` you must write `"order"` with double quotes.
5. **Product reads are cached for 5 minutes** (`@cached(PRODUCTS, …)` in `ProductService`). After
   any stock change (placement, cancel), call `invalidate_quietly(PRODUCTS)` **after** the commit
   (spec D16). Tests use `FakeRedis`, so you can assert this.
6. **The search outbox listener runs on every flush.** Changing `product.stock` through the ORM
   emits **no** event, because `stock` isn't in `PRODUCT_SEARCH_FIELDS`. Step 5 has a test that
   proves it. Don't add `stock` to that list. Don't write `product` with Core statements:
   product-imports D17 forbids it, and the ORM path is the only one allowed outside
   `upsert_many()`.
7. **The test DB is the dev DB, and teardown order matters.** The session-scoped `db` fixture
   deletes `Product` and `User` at the end. `cart_item` references `product`, and `order`
   references `user`, so the fixture must delete `OrderNotification`, `CartItem` and `Order`
   **first** (Step 1).
8. **`normal_user_token_headers` is shared across a whole module.** Its user is
   `EMAIL_TEST_USER`. A cart built in one test would still be there in the next one. Order tests
   must create a **fresh user per test** (helper in Step 1), and wipe orders around each test
   (fixture in Step 1).
9. **Celery isn't running eagerly in tests.** Calling `.delay()` from an API test would push a
   real message to the broker. Monkeypatch the enqueue function, like the imports tests do
   (`monkeypatch.setattr("app.api.deps.product_imports.enqueue_product_import", …)`). Tasks are
   executed in tests with `task.apply(args=[…])`.
10. **`send_email()` never raises on SMTP failure.** The `emails` library reports errors in the
    returned response. Step 7 adds an opt-in `raise_on_error` flag. Existing callers keep today's
    behaviour.
11. **`render_email_template()` doesn't autoescape.** Product names come from admins and CSV
    imports, so they can contain `<script>`. Step 7 turns autoescaping on (spec FR-6.3, AC-17).
12. **Auth codes:** anonymous → 401 on every protected route. A non-superuser on an admin route →
    403. A customer asking for someone else's order or cart line → **404** (spec NFR-1), never 403.
13. **Operation ids** become client method names (`<tag>-<function>` → `TagService.function`).
    Use the route function names in Appendix B **exactly**. The frontend plan depends on them.

---

## Step 1: Settings, models, migration 0006 and test fixtures

**Spec:** FR-1, FR-7, D1, D2, D3, D13, D17

### 1.1 `app/core/config.py`

Add after the `PRODUCT_IMPORT_*` settings:

```python
# Cart and orders (see backend/docs/specs/checkout.md)
CART_MAX_ITEMS: int = 50
ORDER_CURRENCY: str = "USD"
ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS: int = 120
ORDER_NOTIFICATION_MAX_ATTEMPTS: int = 5
ORDER_NOTIFICATION_BACKOFF_SECONDS: int = 30
```

Add the same keys, commented, to `.env.example` / `.env.prod.example` **if** those files list the
other `PRODUCT_IMPORT_*` settings. Otherwise skip them.

### 1.2 `app/models/orders/order.py` (new)

```python
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.users import User

if TYPE_CHECKING:
    from app.models.orders.cart_item import CartItem


class OrderState(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


PLACED_STATES = (OrderState.IN_PROGRESS, OrderState.COMPLETED, OrderState.CANCELLED)


class Order(Base):
    __tablename__ = "order"
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'in_progress', 'completed', 'cancelled')",
            name="ck_order_state",
        ),
        CheckConstraint(
            "state = 'draft' OR (placed_at IS NOT NULL AND total_price IS NOT NULL "
            "AND total_weight IS NOT NULL)",
            name="ck_order_placed_totals",
        ),
        Index(
            "ux_order_user_draft",
            "user_uuid",
            unique=True,
            postgresql_where=text("state = 'draft' AND NOT is_deleted"),
        ),
        Index("ix_order_state_placed_at", "state", text("placed_at DESC")),
        Index(
            "ix_order_user_placed_at",
            "user_uuid",
            text("placed_at DESC"),
            postgresql_where=text("state <> 'draft'"),
        ),
    )

    user_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)
    state: Mapped[str] = mapped_column(
        String(20), default=OrderState.DRAFT.value, server_default="draft"
    )
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    total_weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), default=None)
    currency: Mapped[str] = mapped_column(String(3))
    payment_reference: Mapped[str | None] = mapped_column(String(100), default=None)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    items: Mapped[list["CartItem"]] = relationship(
        back_populates="order",
        order_by="CartItem.created_at",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def number(self) -> str:
        return self.id.hex[:8].upper()

    @property
    def user_email(self) -> str:
        return self.user.email

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)
```

`currency` has **no Python default**: the service sets it from `settings.ORDER_CURRENCY` when it
creates the Draft (§0.4 of the imports plan: never bind a setting at import time).

### 1.3 `app/models/orders/cart_item.py` (new)

```python
MAX_QUANTITY_PER_ITEM = 99


class CartItem(Base):
    __tablename__ = "cart_item"
    __table_args__ = (
        UniqueConstraint("order_uuid", "product_uuid", name="uq_cart_item_order_product"),
        CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_QUANTITY_PER_ITEM}", name="ck_cart_item_quantity"
        ),
    )

    order_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order.id", ondelete="CASCADE"), index=True
    )
    order: Mapped["Order"] = relationship(back_populates="items")
    product_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), index=True)
    # Not filtered by is_deleted on purpose: a deleted product still shows in old orders
    product: Mapped[Product] = relationship(lazy="joined", innerjoin=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    unit_weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), default=None)
    product_name: Mapped[str | None] = mapped_column(String(255), default=None)
    product_sku: Mapped[str | None] = mapped_column(String(100), default=None)

    # Fixed values once placed, live product values while the order is a Draft
    @property
    def name(self) -> str:
        return self.product_name or self.product.name

    @property
    def sku(self) -> str:
        return self.product_sku or self.product.sku

    @property
    def line_total(self) -> Decimal | None:
        return None if self.unit_price is None else self.unit_price * self.quantity
```

`CartItem` extends `Base`, so it has an `is_deleted` column, but lines are **hard-deleted** when
removed from a Draft (spec FR-1.2). Don't use `BaseRepository.delete()` for them.

### 1.4 `app/models/orders/order_notification.py` (new)

Copy the shape of `OutboxEvent`:

```python
class OrderNotificationKind(StrEnum):
    PLACED = "placed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class OrderNotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class OrderNotification(ModelBase):
    __tablename__ = "order_notification"
    __table_args__ = (
        UniqueConstraint("order_uuid", "kind", name="uq_order_notification_order_kind"),
        CheckConstraint("kind IN ('placed', 'cancelled', 'completed')", name="ck_order_notification_kind"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')", name="ck_order_notification_status"
        ),
        Index(
            "ix_order_notification_pending",
            "available_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_uuid: Mapped[uuid.UUID] = mapped_column(ForeignKey("order.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default=OrderNotificationStatus.PENDING.value,
                                        server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime_utc, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

`available_at` has no default: the repository sets it (Step 2) from the setting at call time.

### 1.5 Package exports

- `app/models/orders/__init__.py` exports `CartItem`, `MAX_QUANTITY_PER_ITEM`, `Order`,
  `OrderNotification`, `OrderNotificationKind`, `OrderNotificationStatus`, `OrderState`,
  `PLACED_STATES`.
- Add them to `app/models/__init__.py`. Import `app.models.orders` **after** `products` and
  `users`, because the models reference both.

### 1.6 Migration `app/alembic/versions/0006_create_order_tables.py`

`revision = "0006"`, `down_revision = "0005"`. Write it by hand in the style of `0005`. Don't
trust autogenerate for partial indexes. Create, in order:

1. `"order"`: all `Base` columns (copy the four from `0005`'s `product_import`), then the columns
   from §1.2. FK `user_uuid → user.id`. Both check constraints. Indexes `ix_order_user_uuid`,
   `ux_order_user_draft` (unique, partial), `ix_order_state_placed_at`,
   `ix_order_user_placed_at` (partial).
2. `cart_item`: `Base` columns plus §1.3. FK `order_uuid → order.id ON DELETE CASCADE`, FK
   `product_uuid → product.id`. `uq_cart_item_order_product`, `ck_cart_item_quantity` (write the
   literal `99` in the migration; migrations must not import app constants), indexes
   `ix_cart_item_order_uuid` and `ix_cart_item_product_uuid`.
3. `order_notification`: §1.4. FK with `ON DELETE CASCADE`, unique, both checks, the partial
   pending index.

`downgrade()` drops everything in reverse order.

Check:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1 && docker compose exec backend alembic upgrade head
docker compose exec backend alembic check     # models and migration agree: "No new upgrade operations detected"
```

`alembic check` must be clean. If it reports differences, fix the **migration** (or the model, if
the model is wrong). Don't ignore them.

### 1.7 Test fixtures

**`tests/conftest.py`:**

- Session teardown of `db`: delete `OrderNotification`, `CartItem` and `Order` **before**
  `OutboxEvent` / `Product` / `User` (§0.4.7).
- New fixture (not autouse):

  ```python
  @pytest.fixture
  def clean_orders() -> Generator[None]:
      def wipe() -> None:
          with Session(engine) as session:
              session.execute(delete(OrderNotification))
              session.execute(delete(CartItem))
              session.execute(delete(Order))
              session.commit()

      wipe()
      yield
      wipe()
  ```

**`tests/utils/order.py` (new):**

```python
def create_customer(client: TestClient, db: Session) -> tuple[User, dict[str, str]]:
    """A fresh non-superuser and their auth headers (carts must not leak between tests)."""

def create_stocked_product(db: Session, *, price: str = "10.00", stock: int = 5,
                           weight: str | None = "0.500") -> Product: ...

def add_to_cart(client, headers, product_id, quantity=1) -> dict: ...  # POST /cart/items, asserts 200

def place(client, headers) -> httpx.Response:
    """GET /cart then POST /cart/place with its id and total_price."""
```

`create_customer` uses `create_random_user` with a known password, then
`user_authentication_headers`. Change `create_random_user` to return the password too, or add a
sibling helper. Don't change its existing callers' behaviour.

### 1.8 Tests: `tests/repositories/orders/test_order_models.py` (new)

- A second Draft for the same user → `IntegrityError` on `ux_order_user_draft`. A second Draft
  after the first is placed → allowed.
- A placed order without totals → `IntegrityError` on `ck_order_placed_totals`.
- `quantity` 0 and 100 → `IntegrityError` on `ck_cart_item_quantity`.
- The same product twice in one order → `IntegrityError` on `uq_cart_item_order_product`.
- `Order.number` is the first 8 hex chars uppercased. `item_count` sums quantities.
- `CartItem.name` / `sku` return live values while the fixed ones are null, and the fixed ones
  after they're set, even if the product is renamed afterwards.

Commit: `(feat): Add order, cart item and order notification models`

---

## Step 2: Repositories

**Spec:** D2, D6, D9, D11, FR-2.6, FR-4

All three repositories take a `Session`, never commit, and own every query for their table.

### 2.1 `app/repositories/orders/order_repository.py`

```python
class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Order)

    def _locked(self) -> Select[tuple[Order]]:
        return (
            self._live()
            .with_for_update(of=Order)
            .execution_options(populate_existing=True)
        )

    def lock(self, order_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> Order | None:
        """Lock one order. With user_id, only if the user owns it."""

    def lock_draft(self, user_id: uuid.UUID) -> Order | None:
        """The user's Draft, locked (FR-2.6). None if there isn't one."""
        # self._locked().where(Order.user_uuid == user_id, Order.state == "draft")

    def get_draft(self, user_id: uuid.UUID) -> Order | None:
        """Unlocked read for GET /cart."""

    def create_draft(self, user_id: uuid.UUID, currency: str) -> Order | None:
        """Insert a Draft inside a SAVEPOINT. Return None if another transaction created one first."""
        try:
            with self.session.begin_nested():
                order = Order(user_uuid=user_id, currency=currency)
                self.session.add(order)
                self.session.flush()
            return order
        except IntegrityError as exc:
            if _constraint_name(exc) != "ux_order_user_draft":
                raise
            return None

    def list_placed_for_user(self, user_id, *, skip, limit) -> Sequence[Order]: ...
    def count_placed_for_user(self, user_id) -> int: ...
    def get_placed_for_user(self, order_id, user_id) -> Order | None: ...

    def list_by_states(self, states: Collection[str], *, skip, limit) -> Sequence[Order]:
        # ORDER BY coalesce(placed_at, updated_at) DESC, id DESC
    def count_by_states(self, states: Collection[str]) -> int: ...
```

Move `_constraint_name()` from `app/services/products/imports/service.py` into a shared helper,
`app/repositories/base.py` → `constraint_name(exc)`. Import it from both places.

**How the Draft race resolves** (spec D2, AC-2): two first adds from the same user both find no
Draft. Both call `create_draft()`. The second `INSERT` **blocks** on the unique index until the
first transaction commits, then fails. The savepoint rolls back only that insert. The service
then calls `lock_draft()` again, which now returns the winner's Draft (Step 4).

### 2.2 `app/repositories/orders/cart_item_repository.py`

Doesn't extend `BaseRepository` (lines are hard-deleted, §1.3):

```python
class CartItemRepository:
    def __init__(self, session: Session) -> None: ...
    def get_in_order(self, order_id: uuid.UUID, item_id: uuid.UUID) -> CartItem | None: ...
    def get_for_product(self, order_id: uuid.UUID, product_id: uuid.UUID) -> CartItem | None: ...
    def add(self, item: CartItem) -> None: ...      # session.add + flush
    def remove(self, item: CartItem) -> None: ...   # session.delete + flush
```

### 2.3 `ProductRepository.lock_many` (existing file)

```python
def lock_many(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Product]:
    """Lock products in id order (no deadlocks between checkouts, spec D6).

    Includes soft-deleted products: callers decide what a deleted product means.
    """
    if not ids:
        return {}
    statement = (
        select(Product)
        .where(Product.id.in_(ids))
        .order_by(Product.id)
        .with_for_update(of=Product)
        .execution_options(populate_existing=True)
    )
    return {p.id: p for p in self.session.scalars(statement)}
```

It uses `select(Product)`, **not** `self._live()`, on purpose (see the docstring).

### 2.4 `app/repositories/orders/order_notification_repository.py`

```python
class OrderNotificationRepository:
    def add(self, order_id: uuid.UUID, kind: OrderNotificationKind, *, now: datetime) -> OrderNotification:
        # available_at = now + ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS (read at call time); flush; return
    def claim(self, notification_id: int) -> OrderNotification | None:
        # SELECT … WHERE id = :id AND status = 'pending' FOR UPDATE SKIP LOCKED, populate_existing
    def mark_sent(self, n: OrderNotification, *, now: datetime) -> None: ...
    def mark_skipped(self, n: OrderNotification) -> None: ...
    def mark_failure(self, n: OrderNotification, error: str, *, now: datetime) -> None:
        # attempts += 1; last_error = error[:2000]
        # attempts >= ORDER_NOTIFICATION_MAX_ATTEMPTS → status = failed
        # else available_at = now + timedelta(seconds=BACKOFF * 2 ** (attempts - 1))
    def due_ids(self, *, now: datetime, limit: int) -> list[int]:
        # status = 'pending' AND available_at <= now ORDER BY available_at, id LIMIT :limit
```

### 2.5 Exports and tests

Export the three repositories from `app/repositories/orders/__init__.py` and
`app/repositories/__init__.py`.

`tests/repositories/orders/test_order_repository.py` (new, `usefixtures("clean_orders")`):

- `create_draft` twice in **separate sessions** (two threads, `threading.Barrier(2)` before the
  insert): one returns an `Order`, the other `None`. Afterwards there is exactly one Draft.
- **`lock_draft` waits and re-checks.**
  1. Session A locks the Draft and sets `state = in_progress` without committing yet.
  2. In a thread, session B calls `lock_draft` and blocks.
  3. A commits.
  4. B returns `None`.

  This proves `populate_existing` and the `WHERE` re-check (§0.4.2).
- `lock(order_id, user_id=other)` → `None`.
- `list_by_states` ordering, filtering, and counts.

`tests/repositories/orders/test_order_notification_repository.py` (new):

- `add` sets `available_at` 120 s later.
- `claim` returns `None` for a row already `sent`, and `None` while another session holds the
  row lock (`SKIP LOCKED`).
- `mark_failure` backoff is 30, 60, 120, 240 s, then `failed` on the 5th attempt.
- `due_ids` ignores future and non-pending rows.

`tests/repositories/products/test_product_repositories.py`: `lock_many` returns soft-deleted
products, and returns `{}` for an empty input.

Commit: `(feat): Add order repositories with row locking`

---

## Step 3: Schemas

**Spec:** FR-2.1, FR-3.1, FR-4.1

`app/schemas/orders/cart.py`:

```python
class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=MAX_QUANTITY_PER_ITEM)

class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_ITEM)

class CartItemPublic(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    sku: str
    image_url: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    available: bool
    available_stock: int

class CartPublic(BaseModel):
    id: uuid.UUID | None
    items: list[CartItemPublic]
    item_count: int
    total_price: Decimal
    total_weight: Decimal
    can_place: bool

class PlaceOrderRequest(BaseModel):
    order_id: uuid.UUID
    expected_total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
```

`CartPublic` and `CartItemPublic` are built by `CartService` (Step 4), not with
`from_attributes`, because they mix live product data with line data.

`app/schemas/orders/order.py`:

```python
OrderStateLiteral = Literal["draft", "in_progress", "completed", "cancelled"]

class OrderItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID = Field(validation_alias="product_uuid")
    name: str
    sku: str
    quantity: int
    unit_price: Decimal | None
    unit_weight: Decimal | None
    line_total: Decimal | None

class OrderSummaryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    state: OrderStateLiteral
    user_id: uuid.UUID = Field(validation_alias="user_uuid")
    user_email: str
    total_price: Decimal | None
    total_weight: Decimal | None
    currency: str
    item_count: int
    payment_reference: str | None
    placed_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime

class OrderPublic(OrderSummaryPublic):
    items: list[OrderItemPublic]

class OrdersPublic(BaseModel):
    data: list[OrderSummaryPublic]
    count: int
```

`number`, `user_email`, `item_count`, `name`, `sku` and `line_total` come from the model
properties added in Step 1. With `validation_alias`, the **serialized** name stays `product_id` /
`user_id`. Check that in a test. If `populate_by_name` turns out to be needed, add it to
`model_config`.

Export everything from `app/schemas/orders/__init__.py` and `app/schemas/__init__.py`.

Tests (`tests/schemas/test_order_schemas.py`, new folder with `__init__.py`): `CartItemAdd`
rejects quantity 0 and 100. `OrderPublic.model_validate(order).model_dump()` has the keys
`product_id` and `user_id`, and money comes out as strings in `model_dump(mode="json")`.

Commit: `(feat): Add cart and order schemas`

---

## Step 4: Cart service and cart API

**Spec:** FR-2, D2, D3, D14, D15, FR-2.6

### 4.1 `app/services/orders/cart_service.py`

```python
class CartService:
    def __init__(self, orders: OrderRepository, items: CartItemRepository,
                 products: ProductRepository) -> None:
        self.orders, self.items, self.products = orders, items, products
        self.session = orders.session

    def get_cart(self, user: User) -> CartPublic:
        return self._to_public(self.orders.get_draft(user.id))

    def add_item(self, user: User, data: CartItemAdd) -> CartPublic: ...
    def update_item(self, user: User, item_id: uuid.UUID, data: CartItemUpdate) -> CartPublic: ...
    def remove_item(self, user: User, item_id: uuid.UUID) -> CartPublic: ...
```

**`add_item`**, in one transaction (try/commit/except-rollback, §0.3):

1. `product = self.products.get(data.product_id)`. `get()` filters soft-deleted products. If
   there's none → `NotFoundError("Product not found")`.
2. `order = self._lock_or_create_draft(user)`:

   ```python
   order = self.orders.lock_draft(user.id)
   if order is None:
       order = self.orders.create_draft(user.id, settings.ORDER_CURRENCY)
   if order is None:                      # lost the race (spec D2)
       order = self.orders.lock_draft(user.id)
   if order is None:                      # cannot happen; fail loudly rather than loop
       raise RuntimeError("Draft vanished")
   ```

   A Draft created by `create_draft()` is locked implicitly: this transaction inserted it, so
   nobody else can see it until the commit.
3. `existing = self.items.get_for_product(order.id, product.id)`.
   `merged = (existing.quantity if existing else 0) + data.quantity`.
4. Checks, in this order. Each one raises **before** any write, and the rollback also discards a
   Draft created in step 2:
   - `merged > MAX_QUANTITY_PER_ITEM` → `ConflictError(f"You can add at most {MAX} of this product")`
   - `merged > product.stock` → `ConflictError(f"Only {product.stock} left in stock")`. With
     stock 0 the message reads "Only 0 left in stock". That's acceptable, the frontend disables
     the button anyway.
   - `existing is None and len(order.items) >= settings.CART_MAX_ITEMS` →
     `ConflictError("Your cart is full")`
5. `existing.quantity = merged`, or `self.items.add(CartItem(order_uuid=order.id, product_uuid=product.id, quantity=data.quantity))`.
6. Touch `order.updated_at` (`order.updated_at = get_datetime_utc()`), so the admin "Drafts" tab
   orders by last activity. Commit.
7. `self.session.refresh(order)` (reloads `items`), then return `self._to_public(order)`.

**`update_item`**:

1. Lock the Draft. If there's none → `NotFoundError("Cart item not found")`.
2. `item = self.items.get_in_order(order.id, item_id)`. If it's missing →
   `NotFoundError("Cart item not found")`. Another user's line is "missing" too (NFR-1).
3. If `data.quantity > item.quantity` and `data.quantity > item.product.stock` → the same 409 as
   in add. Lowering is always allowed (spec FR-2.4).
4. Set the quantity, touch `updated_at`, commit, refresh, return.

**`remove_item`**: lock the Draft, find the line (same 404), `self.items.remove(item)`, touch,
commit, refresh, return. The empty Draft stays.

**`_to_public(order: Order | None) -> CartPublic`**:

```python
if order is None:
    return CartPublic(id=None, items=[], item_count=0, total_price=Decimal("0.00"),
                      total_weight=Decimal("0.000"), can_place=False)
lines = []
for item in order.items:
    p = item.product
    available = not p.is_deleted and p.stock >= item.quantity
    lines.append(CartItemPublic(
        id=item.id, product_id=p.id, name=p.name, sku=p.sku,
        image_url=product_image_url(p.image_key) if p.image_key else None,
        unit_price=p.price, quantity=item.quantity, line_total=p.price * item.quantity,
        available=available, available_stock=0 if p.is_deleted else p.stock,
    ))
ok = [l for l in lines if l.available]
# total_price / total_weight over available lines only, quantized (spec FR-2.1)
```

For `total_weight`, use `item.product.weight or Decimal(0)`. Put the totals arithmetic in a small
module-level function, `cart_totals(pairs: Iterable[tuple[Product, int]]) -> tuple[Decimal, Decimal]`,
in `app/services/orders/pricing.py`. Checkout (Step 5) **must** use the same function, so the
cart total the customer sees and the total checked at placement are computed identically
(spec D5).

### 4.2 Dependencies: `app/api/deps/orders.py` (new)

```python
def get_cart_service(session: SessionDep) -> CartService:
    return CartService(OrderRepository(session), CartItemRepository(session),
                       ProductRepository(session))

CartServiceDep = Annotated[CartService, Depends(get_cart_service)]
```

Export it from `app/api/deps/__init__.py`. Step 5 adds more to this file.

### 4.3 Router: `app/api/routes/cart/router.py` (new)

```python
router = APIRouter(prefix="/cart", tags=["cart"])

@router.get("/", response_model=CartPublic)
def read_cart(service: CartServiceDep, current_user: CurrentUser) -> Any: ...

@router.post("/items", response_model=CartPublic)
def add_cart_item(service: CartServiceDep, current_user: CurrentUser, item_in: CartItemAdd) -> Any: ...

@router.patch("/items/{item_id}", response_model=CartPublic)
def update_cart_item(service: CartServiceDep, current_user: CurrentUser,
                     item_id: uuid.UUID, item_in: CartItemUpdate) -> Any: ...

@router.delete("/items/{item_id}", response_model=CartPublic)
def remove_cart_item(service: CartServiceDep, current_user: CurrentUser, item_id: uuid.UUID) -> Any: ...
```

Add the `__init__.py` re-exporting `router` (copy `app/api/routes/products/__init__.py`), and
register it in `app/api/main.py` after `product_imports`.

### 4.4 Tests

`tests/services/orders/test_cart_service.py` (service level, real DB, `clean_orders`):

- The first add creates a Draft with `currency == settings.ORDER_CURRENCY`. A second add of the
  same product → quantity 2, still one line, one Draft.
- 409 messages for: more than 99, more than stock, cart full (monkeypatch `CART_MAX_ITEMS` to 2).
  After each one, the cart is unchanged, and a **first** add that fails leaves **no** Draft.
- Soft-deleted product → 404.
- `update_item` raising above stock → 409. Lowering below stock while the line is unavailable → OK.
- Another user's `item_id` → 404, for both update and remove.
- `_to_public`:
  - A product soft-deleted after it was added → `available: false`, `available_stock: 0`,
    excluded from the totals, `can_place: false`.
  - Stock lowered below the quantity → `available: false`, `available_stock: <stock>`.
- Weights: a product without weight adds 0. Totals are quantized.
- **Concurrency (AC-2):**
  1. A fresh user, with 10 threads behind a `threading.Barrier(10)`.
  2. Each thread uses its own `Session(engine)` and calls `add_item(product, 1)`.
  3. Expect exactly one Draft, one line, and `quantity == 10`.
- **FR-2.6:**
  1. Session A locks the Draft and moves it to `in_progress` without committing.
  2. A thread calls `add_item` and blocks.
  3. A commits.
  4. The thread's add lands in a **new** Draft, and the placed order still has its original lines.

`tests/api/routes/cart/test_cart.py` (`clean_orders`):

- Every endpoint without a token → 401.
- `GET /cart` with no Draft → `{"id": null, "items": [], …, "can_place": false}`, and no Draft
  row created.
- Add, update and remove round trip through the API, checking the JSON shape (money as strings).
- `quantity: 0` → 422. Unknown product → 404.

Commit: `(feat): Add the cart API`

---

## Step 5: Payments gateway, checkout service and the place endpoint

**Spec:** FR-3, D4–D8, D12, D13, D16

### 5.1 `app/core/exceptions.py`

```python
class PaymentRequiredError(AppError):
    status_code = 402
```

### 5.2 `app/services/orders/payments.py` (new)

```python
class PaymentStatus(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"


@dataclass(frozen=True)
class PaymentResult:
    status: PaymentStatus
    reference: str | None = None


class PaymentGatewayError(Exception):
    """The provider could not be reached or answered with an error."""


class PaymentsGateway(Protocol):
    def charge(self, *, order_id: uuid.UUID, amount: Decimal, currency: str) -> PaymentResult: ...


class MockPaymentsGateway:
    """Stands in for a real provider: every charge is approved (spec D7)."""

    def charge(self, *, order_id: uuid.UUID, amount: Decimal, currency: str) -> PaymentResult:
        logger.info("Mock charge of %s %s for order %s", amount, currency, order_id)
        return PaymentResult(PaymentStatus.APPROVED, f"mock_{order_id.hex[:8].upper()}")
```

### 5.3 `app/services/orders/order_service.py` (new): the diagram's "Order Service"

This class owns **every** state transition. Step 5 adds `place()`. Step 6 adds `cancel()` and
`complete()`.

```python
Enqueue = Callable[[int], None]


class OrderService:
    def __init__(self, orders: OrderRepository, products: ProductRepository,
                 notifications: OrderNotificationRepository, gateway: PaymentsGateway,
                 enqueue: Enqueue | None = None) -> None: ...

    def place(self, order: Order, products: Mapping[uuid.UUID, Product]) -> OrderNotification:
        """Move a locked, validated Draft to in_progress. The caller holds the locks and commits."""
        now = get_datetime_utc()
        for item in order.items:
            product = products[item.product_uuid]
            product.stock -= item.quantity
            item.unit_price = product.price
            item.unit_weight = product.weight
            item.product_name = product.name
            item.product_sku = product.sku
        order.total_price, order.total_weight = cart_totals(
            (products[i.product_uuid], i.quantity) for i in order.items
        )
        result = self._charge(order)
        order.state = OrderState.IN_PROGRESS.value
        order.placed_at = now
        order.payment_reference = result.reference
        return self.notifications.add(order.id, OrderNotificationKind.PLACED, now=now)

    def _charge(self, order: Order) -> PaymentResult:
        assert order.total_price is not None
        try:
            result = self.gateway.charge(order_id=order.id, amount=order.total_price,
                                         currency=order.currency)
        except PaymentGatewayError as exc:
            logger.warning("Payment gateway error for order %s", order.id, exc_info=True)
            raise ServiceUnavailableError("Payment service unavailable") from exc
        if result.status != PaymentStatus.APPROVED:
            raise PaymentRequiredError("Payment declined")
        return result

    def after_commit(self, notification_id: int, *, stock_changed: bool) -> None:
        if stock_changed:
            invalidate_quietly(PRODUCTS)
        self._enqueue_quietly(notification_id)

    def _enqueue_quietly(self, notification_id: int) -> None:
        if self._enqueue is None:
            return
        try:
            self._enqueue(notification_id)
        except Exception:
            # Beat re-enqueues pending notifications (spec D9)
            logger.warning("Could not enqueue order notification %s", notification_id, exc_info=True)
```

The order of operations inside `place()` matters (spec FR-3.2 steps 7 → 8 → 9). The stock is
decremented and the values fixed **before** the charge. If the charge raises, the caller's
rollback undoes all of it.

### 5.4 `app/services/orders/checkout/validators.py` (new)

```python
@dataclass(frozen=True)
class CheckoutContext:
    order: Order
    products: Mapping[uuid.UUID, Product]
    expected_total: Decimal


class CheckoutValidator(Protocol):
    def validate(self, ctx: CheckoutContext) -> None: ...


class CartNotEmpty:
    def validate(self, ctx: CheckoutContext) -> None:
        if not ctx.order.items:
            raise ConflictError("Your cart is empty")


class InventoryAvailable:
    def validate(self, ctx: CheckoutContext) -> None:
        for item in ctx.order.items:
            p = ctx.products[item.product_uuid]
            if p.is_deleted or p.stock < item.quantity:
                raise ConflictError("Some items in your cart are unavailable")


class PriceUnchanged:
    def validate(self, ctx: CheckoutContext) -> None:
        total, _ = cart_totals((ctx.products[i.product_uuid], i.quantity) for i in ctx.order.items)
        if total != ctx.expected_total.quantize(Decimal("0.01")):
            raise ConflictError("Prices changed, please review your cart")


DEFAULT_VALIDATORS: tuple[CheckoutValidator, ...] = (
    CartNotEmpty(), InventoryAvailable(), PriceUnchanged(),
)
```

Every validator only reads, so a 409 leaves everything untouched (spec FR-3.4).

### 5.5 `app/services/orders/checkout/service.py` (new): the diagram's "Checkout Service"

```python
class CheckoutService:
    def __init__(self, orders: OrderRepository, products: ProductRepository,
                 order_service: OrderService,
                 validators: Sequence[CheckoutValidator] = DEFAULT_VALIDATORS) -> None: ...

    def place(self, user: User, data: PlaceOrderRequest) -> Order:
        session = self.orders.session
        try:
            order = self.orders.lock(data.order_id, user_id=user.id)
            if order is None:
                raise NotFoundError("Order not found")
            if order.state != OrderState.DRAFT:
                session.rollback()                      # release the lock; idempotent replay (D12)
                return order
            products = self.products.lock_many({i.product_uuid for i in order.items})
            ctx = CheckoutContext(order, products, data.expected_total)
            for validator in self.validators:
                validator.validate(ctx)
            notification = self.order_service.place(order, products)
            session.commit()
        except Exception:
            session.rollback()
            raise
        logger.info("Order %s placed by %s: %s in %d lines", order.id, user.id,
                    order.total_price, len(order.items))
        self.order_service.after_commit(notification.id, stock_changed=True)
        session.refresh(order)
        return order
```

On the idempotent replay path, `session.rollback()` expires the object. Accessing it afterwards
reloads it, which is fine. Make sure the response is still fully populated: the API test
(AC-5) checks it.

The products are locked **after** the order (spec NFR-2: always order, then products). Because
`lock()` holds the order row, nobody can change its lines between reading `order.items` and
locking the products (FR-2.6).

### 5.6 Dependencies (`app/api/deps/orders.py`)

```python
def enqueue_order_notification(notification_id: int) -> None:
    from app.tasks import send_order_notification

    send_order_notification.delay(notification_id)


def get_payments_gateway() -> PaymentsGateway:
    return MockPaymentsGateway()


PaymentsGatewayDep = Annotated[PaymentsGateway, Depends(get_payments_gateway)]


def get_order_service(session: SessionDep, gateway: PaymentsGatewayDep) -> OrderService:
    return OrderService(OrderRepository(session), ProductRepository(session),
                        OrderNotificationRepository(session), gateway,
                        enqueue_order_notification)


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


def get_checkout_service(session: SessionDep, order_service: OrderServiceDep) -> CheckoutService:
    return CheckoutService(OrderRepository(session), ProductRepository(session), order_service)


CheckoutServiceDep = Annotated[CheckoutService, Depends(get_checkout_service)]
```

`enqueue_order_notification` is looked up at call time inside `get_order_service`, so
`monkeypatch.setattr("app.api.deps.orders.enqueue_order_notification", …)` works (§0.4.9). FastAPI
caches dependencies per request, so the `SessionDep` shared by these services is the **same**
session. Rely on that: `CheckoutService` and `OrderService` must write in one transaction.

### 5.7 Route (`app/api/routes/cart/router.py`)

```python
@router.post("/place", response_model=OrderPublic)
def place_order(service: CheckoutServiceDep, current_user: CurrentUser,
                place_in: PlaceOrderRequest) -> Any:
    return service.place(current_user, place_in)
```

### 5.8 Tests

Fixtures for these tests (in `tests/services/orders/conftest.py` and
`tests/api/routes/cart/conftest.py`):

- `queue`: monkeypatches the enqueue function and records the ids.
- `declining_gateway` / `broken_gateway`: test doubles. In API tests, install them with
  `app.dependency_overrides[get_payments_gateway] = lambda: Double()`, and **clear the override**
  in teardown.

`tests/services/orders/test_checkout_service.py`:

- **AC-4:** for a 2-line cart:
  - stock is decremented
  - each line gets its fixed values
  - totals are correct
  - state is `in_progress`, `placed_at` is set, `payment_reference == f"mock_{order.number}"`
  - there is one `placed` notification with `available_at ≈ now + 120 s`
  - the enqueue was called with its id
  - `PRODUCTS` was invalidated (the `FakeRedis` version key changed)

  Then change the product's price and name: the order's lines and totals don't change.
- **No search events** for a stock change: count `OutboxEvent` rows before and after placement.
  They must be equal (§0.4.6).
- **AC-5:** calling `place` again with the same `order_id` returns the same order, stock is
  decremented once, there is one notification, and enqueue is called once.
- **AC-8:** wrong `expected_total` → 409 "Prices changed…", and nothing changed (stock, state,
  fixed values). With the right total → OK.
- Empty Draft → 409 "Your cart is empty". Unavailable line → 409, nothing changed.
- **AC-9:** declining gateway → `PaymentRequiredError`, everything rolled back, no notification.
  Broken gateway → `ServiceUnavailableError`, same checks.
- An enqueue that raises → the placement still succeeds, and the notification stays `pending`.
- **AC-10:** after placement, `add_item` creates a new Draft.
- **AC-6 (oversell):**
  1. Use a product with stock 1, and two customers who each have it in their cart.
  2. A gateway double blocks inside `charge()` on a `threading.Event`, while holding the product
     lock.
  3. Thread A places and blocks inside `charge()`.
  4. Thread B places and blocks on the product lock. Wait about 0.2 s, then set the event.
  5. Expected: A gets 200 and B gets 409 "Some items in your cart are unavailable". Final stock
     is 0.

  Each thread uses its own `Session(engine)` and builds its own services.
- **AC-7 (deadlocks):** carts {A, B} and {B, A} for two users, placed at the same time behind a
  `Barrier(2)`, 20 iterations (re-stock and rebuild the carts each time). There must be no
  `OperationalError`, and both must succeed.

`tests/api/routes/cart/test_place.py`: the full HTTP round trip (add → `GET /cart` → place → 200
`OrderPublic`), the second place → 200 with the same body, 402 and 503 through
`dependency_overrides`, and another user's `order_id` → 404.

Commit: `(feat): Place orders through the checkout service`

---

## Step 6: Admin transitions and the orders APIs

**Spec:** FR-4, FR-5, D11

### 6.1 `OrderService` additions

```python
def cancel(self, order_id: uuid.UUID) -> Order:
    try:
        order = self.orders.lock(order_id)
        if order is None:
            raise NotFoundError("Order not found")
        if order.state != OrderState.IN_PROGRESS:
            raise ConflictError("Only in-progress orders can be cancelled")
        products = self.products.lock_many({i.product_uuid for i in order.items})
        for item in order.items:
            products[item.product_uuid].stock += item.quantity
        now = get_datetime_utc()
        order.state, order.cancelled_at = OrderState.CANCELLED.value, now
        notification = self.notifications.add(order.id, OrderNotificationKind.CANCELLED, now=now)
        self.session.commit()
    except Exception:
        self.session.rollback()
        raise
    self.after_commit(notification.id, stock_changed=True)
    self.session.refresh(order)
    return order

def complete(self, order_id: uuid.UUID) -> Order:
    # same shape: lock, state check ("Only in-progress orders can be completed"),
    # state/completed_at, notification COMPLETED, commit, after_commit(stock_changed=False)

def get(self, order_id: uuid.UUID) -> Order: ...                        # admin, any state, 404
def list_orders(self, states: Collection[str] | None, *, skip, limit) -> OrdersPublic:
    # states None → PLACED_STATES (Drafts hidden, spec FR-4.3)
def list_for_user(self, user: User, *, skip, limit) -> OrdersPublic: ...
def get_for_user(self, user: User, order_id: uuid.UUID) -> Order: ...   # placed only, else 404
```

Restock also restores stock on soft-deleted products (spec FR-5.1). `lock_many` includes them
(§2.3).

### 6.2 Admin router: `app/api/routes/orders/router.py` (new)

```python
router = APIRouter(prefix="/orders", tags=["orders"],
                   dependencies=[Depends(get_current_active_superuser)])

@router.get("/", response_model=OrdersPublic)
def read_orders(service: OrderServiceDep,
                state: Annotated[list[OrderStateLiteral] | None, Query()] = None,
                skip: Annotated[int, Query(ge=0)] = 0,
                limit: Annotated[int, Query(ge=1, le=100)] = 20) -> Any: ...

@router.get("/{order_id}", response_model=OrderPublic)
def read_order(service: OrderServiceDep, order_id: uuid.UUID) -> Any: ...

@router.post("/{order_id}/cancel", response_model=OrderPublic)
def cancel_order(service: OrderServiceDep, order_id: uuid.UUID) -> Any: ...

@router.post("/{order_id}/complete", response_model=OrderPublic)
def complete_order(service: OrderServiceDep, order_id: uuid.UUID) -> Any: ...
```

Register it in `app/api/main.py`. `read_orders` must return `OrdersPublic` with
`OrderSummaryPublic` items. Build it with `OrderSummaryPublic.model_validate(o)` in the service,
like `ProductService.list_products`.

### 6.3 Customer routes: `app/api/routes/users/router.py`

Add these next to the other `/me` routes, **before** the `/{user_id}` routes (good practice, even
though `/me/orders` has two segments and can't collide):

```python
@router.get("/me/orders", response_model=OrdersPublic)
def read_my_orders(service: OrderServiceDep, current_user: CurrentUser,
                   skip: Annotated[int, Query(ge=0)] = 0,
                   limit: Annotated[int, Query(ge=1, le=100)] = 10) -> Any: ...

@router.get("/me/orders/{order_id}", response_model=OrderPublic)
def read_my_order(service: OrderServiceDep, current_user: CurrentUser, order_id: uuid.UUID) -> Any: ...
```

### 6.4 Tests

`tests/services/orders/test_order_service.py`:

- **AC-11:** cancel restores stock, sets `cancelled_at`, writes a `cancelled` notification,
  enqueues it and invalidates `PRODUCTS`. A second cancel → 409, and the stock was restored once.
- Cancel and complete issued concurrently (two threads, a barrier, separate sessions): exactly
  one succeeds and the other gets 409. Stock is consistent with the winner.
- **AC-12:** complete or cancel on draft, completed or cancelled → 409.
- Complete doesn't touch stock and doesn't invalidate `PRODUCTS`.
- Cancel restocks a product that was soft-deleted after placement.

`tests/api/routes/orders/test_orders_admin.py`:

- **AC-1:** anonymous → 401, customer → 403.
- **AC-14:** the default list excludes Drafts. `?state=draft` lists them, and
  `?state=in_progress&state=cancelled` filters. Pagination `count` is right.
- Detail of a Draft works for the admin (money fields null, live name and SKU).
- Cancel and complete round trips.

`tests/api/routes/users/test_my_orders.py`:

- **AC-13:** only the caller's placed orders, newest first. A Draft id → 404. Another user's
  order → 404.

Commit: `(feat): Let admins cancel and complete orders, and customers list theirs`

---

## Step 7: Email templates and sending

**Spec:** FR-6.3, FR-6.4, AC-17

### 7.1 `app/services/email/email_service.py`

1. Turn on autoescaping for **all** templates: `Template(template_str, autoescape=True)`. Check
   that the existing email tests still pass. The reset link only contains `?token=`, so its output
   doesn't change.
2. Add an opt-in failure mode to `send_email`:

   ```python
   class EmailDeliveryError(Exception):
       pass

   def send_email(*, email_to: str, subject: str = "", html_content: str = "",
                  raise_on_error: bool = False) -> None:
       ...
       response = message.send(to=email_to, smtp=smtp_options)
       logger.info(f"send email result: {response}")
       if raise_on_error and response.status_code != 250:
           raise EmailDeliveryError(f"SMTP {response.status_code}: {response.error}")
   ```

   With the `emails` library, `response.status_code` is `None` when the connection fails, and
   `response.error` holds the exception. Check this against the installed version's
   `emails.backend.response.SMTPResponse` before relying on it.
3. Add the generator:

   ```python
   ORDER_EMAILS = {
       OrderNotificationKind.PLACED: ("order_placed.html", "Order #{number} confirmed"),
       OrderNotificationKind.CANCELLED: ("order_cancelled.html", "Order #{number} cancelled"),
       OrderNotificationKind.COMPLETED: ("order_completed.html", "Order #{number} completed"),
   }

   def generate_order_email(order: Order, kind: OrderNotificationKind) -> EmailData:
       template, subject = ORDER_EMAILS[kind]
       context = {
           "project_name": settings.PROJECT_NAME,
           "number": order.number,
           "placed_at": f"{order.placed_at:%b %d, %Y %H:%M} UTC",
           "items": [
               {"name": i.name, "sku": i.sku, "quantity": i.quantity,
                "unit_price": _money(i.unit_price), "line_total": _money(i.line_total)}
               for i in order.items
           ],
           "total_price": _money(order.total_price),
           "total_weight": f"{order.total_weight:.3f} kg",
           "payment_reference": order.payment_reference or "",
           "link": f"{settings.FRONTEND_HOST}/orders/{order.id}",
       }
       return EmailData(
           html_content=render_email_template(template_name=template, context=context),
           subject=f"{settings.PROJECT_NAME} - {subject.format(number=order.number)}",
       )
   ```

   `_money(Decimal) -> str` formats as `$1,234.50`. Every value is preformatted in Python, so the
   templates contain no logic beyond the loop.

### 7.2 React Email templates (`packages/react-email/emails/`)

Create `order_placed.tsx`, `order_cancelled.tsx` and `order_completed.tsx`. Use the existing
`Layout`, `Heading`, `LinkButton` and `Link` from `../ui`, and the same text styles as
`reset_password.tsx`. Default props are the Jinja placeholders, as in the existing templates.

**The line-item loop.** React can't express a Jinja loop directly. Emit the Jinja tags as **text
inside a table cell**. `Section` renders `<table><tbody><tr><td>{children}</td></tr></tbody></table>`,
and each `Row` is its own `<table>`. Jinja then repeats one complete table per item, which is
valid HTML:

```tsx
<Section>
  {"{% for item in items %}"}
  <Row>
    <Column style={nameCell}>
      {"{{ item.name }}"}
      <br />
      <span style={skuStyle}>{"{{ item.sku }}"}</span>
    </Column>
    <Column style={qtyCell}>×{"{{ item.quantity }}"}</Column>
    <Column style={priceCell}>{"{{ item.unit_price }}"}</Column>
    <Column style={priceCell}>{"{{ item.line_total }}"}</Column>
  </Row>
  {"{% endfor %}"}
</Section>
```

Rules, because React escapes text when rendering:

- No quotes, `<`, `>` or `&` inside a Jinja expression in JSX text. React would turn them into
  entities and Jinja would choke. The expressions above don't need any.
- Run the export and **open the generated HTML**. Check that `{% for item in items %}` and
  `{% endfor %}` appear verbatim inside a `<td>`, around the item `<table>`.

Content:

- **Placed:**
  - heading "Thanks for your order", then "Order #{{ number }} · {{ placed_at }}"
  - the items table with a header row (Item, Qty, Price, Total)
  - the totals block (Total weight, **Total**), and "Payment reference {{ payment_reference }}"
  - a `LinkButton` "View your order" → `{{ link }}`
- **Cancelled:** heading "Your order was cancelled", "Order #{{ number }} ({{ total_price }}) has
  been cancelled.", and a link button.
- **Completed:** heading "Your order is complete", the same structure.

Export with `npx bun run email:export` from the repo root. Commit the `.tsx` files **and** the
generated `.html` files. `git diff` on the three existing HTML files must be empty. If the export
changed them, find out why before you continue.

### 7.3 Tests: `tests/services/email/test_order_emails.py` (new)

- `generate_order_email` for placed:
  - the subject is right
  - the HTML contains the number, every item name and SKU, the formatted prices, the total, the
    weight and the link
  - the item loop rendered once per item (count the occurrences of a unique SKU)
- **AC-17:** a product named `<script>alert(1)</script>` → the HTML contains
  `&lt;script&gt;alert(1)&lt;/script&gt;` and not the raw tag.
- `send_email(..., raise_on_error=True)` with a monkeypatched `emails.message.Message.send`
  returning a response with `status_code=None` → `EmailDeliveryError`. Without the flag, no raise.

Commit: `(feat): Add order email templates`

---

## Step 8: Notification task and beat job

**Spec:** FR-6.1, FR-6.2, D9, D10

### 8.1 `app/services/orders/notifications.py` (new)

```python
class NotificationOutcome(StrEnum):
    SENT = "sent"
    SKIPPED = "skipped"
    RETRY = "retry"
    FAILED = "failed"
    NOT_PENDING = "not_pending"


class OrderNotificationSender:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def send(self, notification_id: int) -> NotificationOutcome:
        with Session(self.engine) as session:
            repo = OrderNotificationRepository(session)
            n = repo.claim(notification_id)            # holds the row lock until commit
            if n is None:
                return NotificationOutcome.NOT_PENDING
            if not settings.emails_enabled:
                logger.info("Emails disabled, skipping order notification %s", n.id)
                repo.mark_skipped(n)
                session.commit()
                return NotificationOutcome.SKIPPED
            order = OrderRepository(session).get(n.order_uuid)
            assert order is not None
            email = generate_order_email(order, OrderNotificationKind(n.kind))
            now = get_datetime_utc()
            try:
                send_email(email_to=order.user.email, subject=email.subject,
                           html_content=email.html_content, raise_on_error=True)
            except (EmailDeliveryError, OSError, smtplib.SMTPException) as exc:
                logger.warning("Order notification %s failed: %s", n.id, exc)
                repo.mark_failure(n, str(exc), now=now)
                session.commit()
                return (NotificationOutcome.FAILED if n.status == OrderNotificationStatus.FAILED
                        else NotificationOutcome.RETRY)
            repo.mark_sent(n, now=now)
            session.commit()
            logger.info("Order notification %s (%s) sent for order %s", n.id, n.kind, order.id)
            return NotificationOutcome.SENT

    def requeue_due(self, enqueue: Callable[[int], None], *, limit: int = 500) -> int:
        with Session(self.engine) as session:
            ids = OrderNotificationRepository(session).due_ids(now=get_datetime_utc(), limit=limit)
        for notification_id in ids:
            enqueue(notification_id)
        return len(ids)
```

`OrderRepository.get()` filters soft-deleted orders. Orders are never soft-deleted in this
feature, so the `assert` holds.

### 8.2 `app/tasks.py`

```python
@celery_app.task
def send_order_notification(notification_id: int) -> str:
    return OrderNotificationSender(engine).send(notification_id).value


@celery_app.task
def requeue_order_notifications() -> int:
    return OrderNotificationSender(engine).requeue_due(send_order_notification.delay)
```

No `bind`, no `max_retries`. Beat is the only retry mechanism (spec FR-6.1).

### 8.3 `app/core/celery_app.py`

```python
"requeue-order-notifications": {
    "task": "app.tasks.requeue_order_notifications",
    "schedule": crontab(minute="*"),
},
```

### 8.4 Tests: `tests/services/orders/test_notifications.py` (new) and `tests/test_tasks.py`

Use `monkeypatch.setattr("app.services.orders.notifications.send_email", fake)` to capture
sends, and monkeypatch `SMTP_HOST` / `EMAILS_FROM_EMAIL` so that `emails_enabled` is true.

- **Happy path:** place an order, then `send_order_notification.apply(args=[id])` → `"sent"`. One
  email to the customer with the right subject. The row is `sent`, with `attempts == 1` and
  `sent_at` set.
- **Idempotent:** running it again → `"not_pending"`, no second email.
- **Concurrent claim:** another session holds the row lock → `"not_pending"` (`SKIP LOCKED`), no
  email.
- **Emails disabled** (`SMTP_HOST=None`) → `"skipped"`.
- **SMTP failure:** a fake that raises `EmailDeliveryError` → `"retry"`, `attempts == 1`,
  `available_at ≈ now + 30 s`. Repeat up to attempt 5 → `"failed"`.
- **AC-16:** a pending row with `available_at` in the past → `requeue_order_notifications.apply()`
  enqueues it. Monkeypatch `send_order_notification.delay` to record the ids. A row in the future
  isn't enqueued.
- **End to end with Mailpit (by hand, not automated):** see Step 10.

Commit: `(feat): Email customers about their orders from a Celery task`

---

## Step 9: Hardening pass

**Spec:** NFR-1–NFR-4

Go through this checklist and fix whatever fails:

- [ ] `grep -rn "with_for_update" app/` → every hit also has `populate_existing=True` (or is
      `SKIP LOCKED` on a row the session hasn't loaded before).
- [ ] Nothing in `app/services/orders/` calls `.save()` or `.commit()` outside the
      try/commit/except-rollback pattern.
- [ ] Every query in `CartService` and in the `OrderService` customer paths filters by
      `user_uuid`.
- [ ] Every lock is taken in the order **order → products (by id)**. No path locks products
      first.
- [ ] No `float` anywhere in `app/services/orders/` or `app/schemas/orders/`
      (`grep -rn "float" app/services/orders app/schemas/orders`).
- [ ] Log lines from NFR-4 are present: placement, cancel and complete at `INFO`, notification
      send and failure.
- [ ] `docker compose exec backend bash scripts/tests-start.sh` → overall coverage doesn't
      drop, and every new module is ≥ 90 %.

Commit (only if something changed): `(fix): Harden checkout locking and logging`

---

## Step 10: Client, docs and final verification

1. Regenerate the OpenAPI schema and client: `bash scripts/generate-client.sh`. Check that
   `frontend/src/client/sdk.gen.ts` contains `CartService`, `OrdersService`, and the new
   `UsersService` methods listed in Appendix B. Commit `frontend/openapi.json` and `src/client/**`
   with this step. The frontend plan starts from here.
2. `backend/README.md`: add a short "Orders" section. Cover the state diagram (copy it from the
   spec), the fact that payments are mocked (`MockPaymentsGateway`), and that order emails go
   through `order_notification` and the `requeue-order-notifications` beat job.
3. Spec header: set **Status** to `Implemented (backend)` and link this plan.
4. **Manual check against the dev stack** (all services up, including `celery-worker` and
   `celery-beat`):
   1. Log in as a customer through the API, add two products, `GET /cart`, and place the order.
   2. Within a few seconds, Mailpit shows "Order #XXXXXXXX confirmed" with both lines.
   3. As the admin, `POST /orders/{id}/cancel`. Mailpit shows the cancel email, and
      `GET /products/{id}` shows the stock back.
   4. Stop `celery-worker`, place another order, and start the worker again 30 s later. The email
      arrives within about 3 minutes (beat requeue, AC-16).
5. Final: `tests-start.sh`, `lint.sh`, `alembic check` all clean.

Commit: `(chore): Document orders and regenerate the client`

---

## Appendix A: Files touched

| File | Change |
|---|---|
| `app/core/config.py` | New `CART_*` / `ORDER_*` settings |
| `app/core/exceptions.py` | `PaymentRequiredError` (402) |
| `app/core/celery_app.py` | Beat entry `requeue-order-notifications` |
| `app/models/orders/{__init__,order,cart_item,order_notification}.py` | New |
| `app/models/__init__.py` | Exports |
| `app/alembic/versions/0006_create_order_tables.py` | New |
| `app/repositories/base.py` | `constraint_name()` helper (moved from the imports service) |
| `app/repositories/orders/{__init__,order_repository,cart_item_repository,order_notification_repository}.py` | New |
| `app/repositories/products/product_repository.py` | `lock_many()` |
| `app/repositories/__init__.py` | Exports |
| `app/schemas/orders/{__init__,cart,order}.py`, `app/schemas/__init__.py` | New / exports |
| `app/services/orders/{__init__,cart_service,order_service,payments,pricing,notifications}.py` | New |
| `app/services/orders/checkout/{__init__,service,validators}.py` | New |
| `app/services/products/imports/service.py` | Use the shared `constraint_name()` |
| `app/services/__init__.py` | Exports |
| `app/services/email/email_service.py` | Autoescape, `raise_on_error`, `EmailDeliveryError`, `generate_order_email` |
| `app/email-templates/order_{placed,cancelled,completed}.html` | Generated |
| `packages/react-email/emails/order_{placed,cancelled,completed}.tsx` | New |
| `app/api/deps/orders.py`, `app/api/deps/__init__.py` | New / exports |
| `app/api/routes/cart/{__init__,router}.py`, `app/api/routes/orders/{__init__,router}.py` | New |
| `app/api/routes/users/router.py` | `/me/orders`, `/me/orders/{order_id}` |
| `app/api/main.py` | Register `cart` and `orders` routers |
| `app/tasks.py` | `send_order_notification`, `requeue_order_notifications` |
| `tests/conftest.py`, `tests/utils/order.py`, `tests/utils/user.py` | Cleanup order, `clean_orders`, helpers |
| `tests/repositories/orders/*`, `tests/schemas/*`, `tests/services/orders/*`, `tests/services/email/*`, `tests/api/routes/{cart,orders}/*`, `tests/api/routes/users/test_my_orders.py`, `tests/test_tasks.py` | New tests |
| `backend/README.md`, `backend/docs/specs/checkout.md` | Docs |
| `frontend/openapi.json`, `frontend/src/client/**` | Regenerated |

## Appendix B: API contract summary (for the frontend)

All paths are under `/api/v1`. Money and weights are **decimal strings** in JSON (`"19.99"`,
`"1.250"`). Errors are `{"detail": "<message>"}`.

| Method & path | Route function → client method | Auth | Body | Success | Errors (`detail`) |
|---|---|---|---|---|---|
| `GET /cart/` | `read_cart` → `CartService.readCart` | user | | 200 `CartPublic` | |
| `POST /cart/items` | `add_cart_item` → `CartService.addCartItem` | user | `{product_id, quantity?}` | 200 `CartPublic` | 404 `Product not found` · 409 `Only N left in stock` / `You can add at most 99 of this product` / `Your cart is full` · 422 |
| `PATCH /cart/items/{item_id}` | `update_cart_item` → `CartService.updateCartItem` | user | `{quantity}` | 200 `CartPublic` | 404 `Cart item not found` · 409 `Only N left in stock` · 422 |
| `DELETE /cart/items/{item_id}` | `remove_cart_item` → `CartService.removeCartItem` | user | | 200 `CartPublic` | 404 `Cart item not found` |
| `POST /cart/place` | `place_order` → `CartService.placeOrder` | user | `{order_id, expected_total}` | 200 `OrderPublic` (also on replay) | 404 `Order not found` · 409 `Your cart is empty` / `Some items in your cart are unavailable` / `Prices changed, please review your cart` · 402 `Payment declined` · 503 `Payment service unavailable` |
| `GET /users/me/orders?skip&limit` | `read_my_orders` → `UsersService.readMyOrders` | user | | 200 `OrdersPublic` | |
| `GET /users/me/orders/{order_id}` | `read_my_order` → `UsersService.readMyOrder` | user | | 200 `OrderPublic` | 404 `Order not found` |
| `GET /orders/?state&skip&limit` | `read_orders` → `OrdersService.readOrders` | admin | | 200 `OrdersPublic` | |
| `GET /orders/{order_id}` | `read_order` → `OrdersService.readOrder` | admin | | 200 `OrderPublic` | 404 |
| `POST /orders/{order_id}/cancel` | `cancel_order` → `OrdersService.cancelOrder` | admin | | 200 `OrderPublic` | 404 · 409 `Only in-progress orders can be cancelled` |
| `POST /orders/{order_id}/complete` | `complete_order` → `OrdersService.completeOrder` | admin | | 200 `OrderPublic` | 404 · 409 `Only in-progress orders can be completed` |

**Schemas:**

- `CartPublic`: `id: uuid | null`, `items: CartItemPublic[]`, `item_count: int`,
  `total_price: decimal`, `total_weight: decimal`, `can_place: bool`
- `CartItemPublic`: `id`, `product_id`, `name`, `sku`, `image_url: string | null`,
  `unit_price`, `quantity`, `line_total`, `available: bool`, `available_stock: int`
- `OrderSummaryPublic`: `id`, `number` (8 uppercase hex chars), `state`
  (`draft | in_progress | completed | cancelled`), `user_id`, `user_email`,
  `total_price | null`, `total_weight | null`, `currency`, `item_count`,
  `payment_reference | null`, `placed_at | null`, `completed_at | null`, `cancelled_at | null`,
  `created_at`
- `OrderPublic`: `OrderSummaryPublic` + `items: OrderItemPublic[]`
- `OrderItemPublic`: `id`, `product_id`, `name`, `sku`, `quantity`, `unit_price | null`,
  `unit_weight | null`, `line_total | null`
- `OrdersPublic`: `{data: OrderSummaryPublic[], count: int}`

The client methods' **exact** generated names depend on `openapi-ts.config.ts`. The ones above
follow the existing pattern (`ProductImportsService.presignProductImport`). Confirm them in
`sdk.gen.ts` after Step 10.
