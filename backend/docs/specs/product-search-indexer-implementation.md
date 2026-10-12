# Implementation Plan: Product Search Indexer

This plan is for the engineer or model implementing
[`product-search-indexer.md`](./product-search-indexer.md) (the **spec**). The spec decides
*what* to build. This document decides *how* and *in what order*. If the two disagree, the
spec wins: stop and ask rather than guess.

Requirement IDs (`FR-x`, `AC-x`) refer to the spec.

---

## 0. Before you start

### 0.1 Read these files first

| File | Why |
|---|---|
| `backend/README.md` | Layering rules: api → services → repositories → models |
| `backend/app/models/base.py` | The shared columns. You will refactor this in Step 1 |
| `backend/app/repositories/base.py` | `BaseRepository`, `_live()`, `save()` (which **commits**), `delete()` (soft delete) |
| `backend/app/repositories/products/*.py` | The style to follow for new repository methods |
| `backend/app/services/products/*.py` | How writes reach the DB (they go through `repo.save` / `repo.delete`) |
| `backend/app/core/search.py` | `get_es()`, the cached ES client. Reuse it |
| `backend/app/core/db.py` | `engine`. Worker sessions use `Session(engine)` |
| `backend/app/core/config.py` | Where new settings go |
| `backend/app/alembic/versions/0002_create_product_tables.py` | Migration style (hand-written, `upgrade()`/`downgrade()`) |
| `backend/tests/conftest.py`, `backend/tests/utils/product.py` | Fixtures and the `create_random_*` helpers |
| `compose.dev.yml`, `compose.prod.yml` | The `celery-worker` service is the template for `search-indexer` |

### 0.2 Running checks

Everything runs inside the dev stack. From the repo root:

```bash
docker compose up -d                                         # stack incl. db + elasticsearch
docker compose exec backend alembic upgrade head             # after Step 1
docker compose exec backend bash scripts/tests-start.sh -x   # tests (pass extra pytest args)
docker compose exec backend bash scripts/lint.sh             # mypy (strict), ty, ruff check, ruff format --check
docker compose exec backend ruff format app tests            # auto-format
```

**At the end of every step, both `tests-start.sh` and `lint.sh` must pass.** Don't move on with
red checks.

### 0.3 Rules for this codebase

- Python 3.14 with PEP 695 generics (`class Foo[T]:`, `def f[T]() -> ...`). Match the existing style.
- `mypy --strict` and `ty` must pass. Type every function signature. Don't use bare `# type: ignore`. If an
  ignore is unavoidable, use the specific code (`# type: ignore[code]`) and add a comment explaining why.
- **Ruff forbids `print` in `app/` (rule `T201`).** CLI output must use `sys.stdout.write(...)`.
  Diagnostics go through `logging`.
- Match the surrounding comment density, which is sparse. Docstrings are only for non-obvious behaviour.
- Repositories own all SQL. Services and the indexer don't build queries inline.
- Don't change existing endpoints, services or schemas. The outbox is wired in at the session level.
- One commit per step, in the repo's format: `(feat): ...`, `(chore): ...`, `(test): ...`.

### 0.4 Existing behaviour that affects this work

1. `BaseRepository.save()` and `.delete()` call `session.commit()`. The outbox row must therefore be
   added **during the flush** (Step 2). Adding it after `save()` would be a separate transaction.
2. `ProductCategoryService.delete_category` refuses to delete a category that still has live
   products. To test FR-4.2 / AC-6, soft-delete the category **through the repository**
   (`ProductCategoryRepository(db).delete(category)`), not through the service or API.
3. Columns are declared on `Base(DeclarativeBase)` itself, so every mapped subclass inherits
   them, including a UUID `id`. `OutboxEvent` needs a `BIGINT` id and no soft delete, which is why
   Step 1 refactors the base.
4. `tests/conftest.py` has a session-scoped `db` fixture that deletes `Product`, `ProductCategory`
   and `User` at teardown. Product tests leave outbox rows behind, so tests that count outbox
   rows must start from an empty table (fixture in Step 4).
5. `get_es()` is `lru_cache`d. Read `settings.ELASTICSEARCH_PRODUCTS_ALIAS` **at call time**, never
   at import time, so tests can monkeypatch it.

---

## Step 1: Settings, model base refactor, `OutboxEvent`, migration 0003

**Spec:** §5, §6

### 1.1 `app/core/config.py`

Add these settings next to `ELASTICSEARCH_API_KEY`:

```python
ELASTICSEARCH_PRODUCTS_ALIAS: str = "products"
SEARCH_OUTBOX_POLL_SECONDS: float = 2
SEARCH_OUTBOX_BATCH_SIZE: int = 500
SEARCH_OUTBOX_MAX_ATTEMPTS: int = 10
SEARCH_OUTBOX_RETENTION_DAYS: int = 7
```

### 1.2 `app/models/base.py`

Split the base into two classes:

```python
class ModelBase(DeclarativeBase):
    """Declarative base that only holds the metadata. Extend `Base` for domain models."""


class Base(ModelBase):
    """Abstract base for domain models, with the columns every domain table shares."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = ...          # unchanged
    is_deleted: Mapped[bool] = ...       # unchanged
    created_at: Mapped[datetime] = ...   # unchanged
    updated_at: Mapped[datetime] = ...   # unchanged
```

Keep the column definitions exactly as they are now. Export `ModelBase` from `app/models/__init__.py`.
In `app/alembic/env.py`, set `target_metadata = ModelBase.metadata`. It's the same object, but the name makes
that explicit.

**Check:** `docker compose exec backend alembic check` must report no changes to the existing
tables before you add the new model. Run it once right after this refactor.

### 1.3 `app/models/outbox/outbox_event.py` (and `app/models/outbox/__init__.py`)

```python
class OutboxTopic(StrEnum):
    SEARCH_PRODUCT = "search.product"
    SEARCH_PRODUCT_CATEGORY = "search.product_category"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class OutboxEvent(ModelBase):
    __tablename__ = "outbox_event"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="ck_outbox_event_status"),
        Index("ix_outbox_event_pending", "available_at", "id",
              postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    topic: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(10), default=OutboxStatus.PENDING,
                                        server_default=OutboxStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   default=get_datetime_utc, server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=get_datetime_utc, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

Export `OutboxEvent`, `OutboxTopic` and `OutboxStatus` from `app/models/__init__.py`.

### 1.4 `app/alembic/versions/0003_create_outbox_event_table.py`

Write it by hand in the style of 0002, with `revision = "0003"` and `down_revision = "0002"`. Use `sa.BigInteger()`
plus `sa.Identity()` for `id`, the check constraint, and the partial index. In `downgrade()`, drop the index, then the table.

You can use `alembic revision --autogenerate` to compare, but the file you commit must be clean and hand-edited.

### 1.5 `tests/conftest.py`

In the `db` fixture teardown, add `session.execute(delete(OutboxEvent))` **before** the other deletes.

**Done when:** `alembic upgrade head` works, `alembic downgrade -1 && alembic upgrade head` works,
`alembic check` is clean, and tests and lint pass.

---

## Step 2: Outbox listener and `OutboxRepository`

**Spec:** FR-2. **ACs:** AC-1 (outbox part), AC-2, AC-3, AC-4

### 2.1 `app/repositories/outbox/outbox_repository.py`

`OutboxEvent` doesn't extend `Base`, so this is a **plain class** that does not extend `BaseRepository`. It takes a `Session`.
None of these methods commit. The caller owns the transaction.

| Method | Behaviour |
|---|---|
| `add_many(topic: OutboxTopic, aggregate_ids: Iterable[uuid.UUID]) -> None` | `session.add_all(...)`. Public API for bulk writers (FR-2.4) |
| `claim_batch(limit: int) -> list[OutboxEvent]` | `select(OutboxEvent).where(status == PENDING, available_at <= func.now()).order_by(id).limit(limit).with_for_update(skip_locked=True)` |
| `mark_done(events: Sequence[OutboxEvent]) -> None` | `status=DONE`, `processed_at=now` |
| `mark_retry(event: OutboxEvent, error: str, *, max_attempts: int) -> None` | `attempts += 1`, `last_error = error[:2000]`. Then, if `attempts >= max_attempts`, set `status=FAILED`. Otherwise set `available_at = now + backoff(attempts)` |
| `purge_done(older_than: datetime) -> int` | `DELETE ... WHERE status='done' AND processed_at < :older_than`. Returns the row count |
| `retry_failed() -> int` | `UPDATE ... SET status='pending', attempts=0, available_at=now(), last_error=NULL WHERE status='failed'`. Returns the row count |
| `stats() -> OutboxStats` | Counts of pending and failed events, and the oldest pending `created_at` (a small dataclass) |

Write `backoff(attempts: int) -> timedelta` as a module-level pure function:
`min(timedelta(seconds=2 * 2 ** (attempts - 1)), timedelta(minutes=5))`. That gives 2s, 4s, 8s and so on, capped at 5 min.

Export the class from `app/repositories/__init__.py`.

### 2.2 `app/outbox/listeners.py` (plus `app/outbox/__init__.py`)

```python
PRODUCT_SEARCH_FIELDS = ("name", "description", "sku", "category_uuid", "is_deleted")
CATEGORY_SEARCH_FIELDS = ("name", "is_deleted")


@event.listens_for(Session, "before_flush")
def _emit_search_events(session: Session, flush_context: UOWTransaction, instances: object) -> None:
    ...
```

Logic:
- For each `obj` in `session.new`:
  - A `Product` adds an `OutboxEvent(topic=SEARCH_PRODUCT, aggregate_id=obj.id)`.
  - A `ProductCategory` adds one with `SEARCH_PRODUCT_CATEGORY`.
- For each `obj` in `session.dirty`: emit the same event, but **only if** one of the listed fields changed. Check with
  `inspect(obj).attrs[field].history.has_changes()`. Ignore everything else (FR-2.3).
- **Gotcha: `obj.id` may be `None` on new objects.** The `default=uuid.uuid4` only runs at INSERT.
  For new instances with `id is None`, assign `obj.id = uuid.uuid4()` yourself before creating the event.
- Add events with `session.add(...)`. Objects added in `before_flush` are included in the same flush.
  Don't create an event for `OutboxEvent` objects themselves.
- Leave `ARG001` alone for the unused listener args: name them `_flush_context` and `_instances` if
  ruff complains.

**Registration:** the listener has to be registered in every process: API, worker, CLI and tests.
Add `import app.outbox.listeners  # noqa: F401  (registers SQLAlchemy listeners)` to
`app/core/db.py`. Everything that touches the DB imports it.

### 2.3 Tests: `tests/outbox/test_listeners.py` and `tests/repositories/outbox/test_outbox_repository.py`

Add an autouse fixture in `tests/outbox/conftest.py` (and reuse it for the search tests in Step 4) that deletes all
`OutboxEvent` rows before each test.

Listener tests (use `create_random_product` / `create_random_category`):
- **AC-1:** creating a product produces exactly one `search.product` event with that product's id.
- **AC-2:** add a `Product` to a session, `flush()`, `rollback()`. There's no product and no event.
- **AC-3:** changing only `stock` or `price` and saving produces no new event.
- **AC-4:** changing `name` produces one new event. Repeat for `description`, `sku`, `category_uuid`
  and `is_deleted` (soft delete through `ProductRepository.delete`). A parametrized test is fine.
- Creating a category produces one event, and so do a category `name` change and a category soft delete.
  A category `code` change produces none.

Repository tests:
- `backoff()` values for attempts 1 through 10 (the cap holds).
- `mark_retry` sets `failed` once `max_attempts` is reached.
- `purge_done` and `retry_failed` return the right counts.
- **AC-12:**
  - Open two `Session(engine)` objects with 4 pending events in the table.
  - Session A runs `claim_batch(2)` and doesn't commit. Session B runs `claim_batch(10)`.
  - The ID sets must not overlap, and B must get exactly the other 2.
  - Roll back both sessions.

**Done when:** the existing test suite still passes unchanged. The listener must not break any current
product or category test.

---

## Step 3: Index definition (`app/search/products_index.py`)

**Spec:** FR-1, FR-5.3. **ACs:** AC-14, AC-15

### 3.1 Repository additions: `app/repositories/products/product_repository.py`

All three methods **intentionally skip `_live()`**. Say so in a short comment.

| Method | Returns |
|---|---|
| `get_many_with_category(ids: Collection[uuid.UUID]) -> list[tuple[Product, ProductCategory]]` | `select(Product, ProductCategory).join(ProductCategory, Product.category_uuid == ProductCategory.id).where(Product.id.in_(ids))` |
| `list_ids_by_category(category_ids: Collection[uuid.UUID]) -> list[uuid.UUID]` | Every product ID in these categories, deleted or not |
| `iter_indexable(batch_size: int) -> Iterator[tuple[Product, ProductCategory]]` | Live product in a live category, using `.execution_options(yield_per=batch_size)` |
| `count_indexable() -> int` | Count matching the same filter as `iter_indexable` |

Add tests next to the existing ones in `tests/repositories/products/test_product_repositories.py`.

### 3.2 `app/search/products_index.py`

```python
def alias() -> str                                        # settings.ELASTICSEARCH_PRODUCTS_ALIAS, read at call time
def new_index_name() -> str                               # f"{alias()}_{datetime.now(UTC):%Y%m%d%H%M%S%f}"
def index_body() -> dict[str, Any]                        # settings + mappings, exactly FR-1.2 / FR-1.3
def ensure_index(es: Elasticsearch) -> str                # creates first index + alias if alias missing; returns physical index name
def create_index(es: Elasticsearch, name: str) -> None
def is_indexable(product: Product, category: ProductCategory) -> bool
def to_document(product: Product, category: ProductCategory) -> dict[str, Any]
def version(product: Product, category: ProductCategory) -> int   # max(updated_at) as epoch microseconds
```

The `index_body()` mappings:

```json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "sku_normalizer": { "type": "custom", "filter": ["lowercase", "asciifolding"] }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "name":          { "type": "text", "analyzer": "english" },
      "description":   { "type": "text", "analyzer": "english" },
      "sku":           { "type": "keyword", "normalizer": "sku_normalizer" },
      "category_name": { "type": "text", "analyzer": "english" },
      "updated_at":    { "type": "date", "index": false }
    }
  }
}
```

- `to_document` returns **exactly** these five keys, with `updated_at` as an ISO-8601 string.
- `version()` uses `int(dt.timestamp() * 1_000_000)`. Compute it with integer math
  (`(dt - EPOCH) // timedelta(microseconds=1)`) to avoid float rounding.
- `ensure_index`: if `es.indices.exists_alias(name=alias())`, return the index behind it. Otherwise create
  `new_index_name()` with `aliases={alias(): {}}` in the same create call.

### 3.3 Search test fixtures: `tests/search/conftest.py`

- `es_alias` (autouse in `tests/search/`):
  - `monkeypatch.setattr(settings, "ELASTICSEARCH_PRODUCTS_ALIAS", f"test_products_{uuid4().hex[:8]}")`.
  - Yield, then delete every index matching `f"{alias}_*"` with `es.indices.delete(index=..., ignore_unavailable=True)`.
- Reuse the outbox-clearing fixture from Step 2.
- `refresh()` helper: `get_es().indices.refresh(index=alias())`. Call it before every search assertion.

### 3.4 Tests: `tests/search/test_products_index.py`

- `to_document` keys are exactly the FR-1.2 set, and a null `description` is allowed.
- `ensure_index` is idempotent. The second call returns the same index name.
- Indexing a document with an extra field fails, because of strict mapping.
- **AC-14:** index a product named "Run Shoe". A `match` query on `name` for "running shoes" finds it.
- **AC-15:** SKU `ABC-123` is found by `term` `abc-123`, but not by `term` `abc`.

---

## Step 4: Indexer core (`app/search/indexer.py`)

**Spec:** FR-3, FR-4. **ACs:** AC-1, AC-5 to AC-10

### 4.1 Public API

```python
@dataclass
class BatchResult:
    claimed: int = 0
    indexed: int = 0
    deleted: int = 0
    retried: int = 0
    failed: int = 0


INDEXER_LOCK_KEY: Final = <fixed bigint constant>   # shared with reindex (Step 5)


def process_once(session: Session, es: Elasticsearch) -> BatchResult
```

### 4.2 `process_once` algorithm (one transaction; the caller passes a fresh `Session(engine)`)

1. **Pause check:** `session.scalar(select(func.pg_try_advisory_xact_lock_shared(INDEXER_LOCK_KEY)))`.
   If it returns false, a reindex is running: return `BatchResult()` without claiming anything (FR-5.2).
2. `events = OutboxRepository(session).claim_batch(settings.SEARCH_OUTBOX_BATCH_SIZE)`. If there are none, commit and return.
3. **Expand events to products.** Build `targets: dict[uuid.UUID, set[int]]`, mapping product ID to the set of event IDs that caused it:
   - A `search.product` event maps to `{aggregate_id}`.
   - A `search.product_category` event maps to `ProductRepository.list_ids_by_category(...)`. Make **one call**
     for all category events in the batch, then map the results back to their events.
   - An event can map to zero products, for example a new category. That event succeeds as soon as it's processed.
4. `rows = ProductRepository(session).get_many_with_category(targets.keys())`.
5. Build actions, one per product ID (deduplication, FR-3.3):
   - Indexable: `{"_op_type": "index", "_index": alias(), "_id": str(pid), "_source": to_document(...), "version": version(...), "version_type": "external"}`
   - Not indexable: `{"_op_type": "delete", ..., "version": version(...), "version_type": "external"}`
   - Product ID not found in Postgres: `{"_op_type": "delete", "_index": alias(), "_id": str(pid)}` with no version.
6. Send with
   `helpers.streaming_bulk(es, actions, chunk_size=500, raise_on_error=False, raise_on_exception=False, max_retries=0)`.
   For each `(ok, item)` result:
   - `ok`: success.
   - Status `409`: success (FR-3.7).
   - `delete` with status `404`: success.
   - Anything else: the product failed. Record `item[op]["error"]` as text.
7. **Map product outcomes to events.** An event succeeds if **all** of its products succeeded. Otherwise call
   `mark_retry(event, error, max_attempts=settings.SEARCH_OUTBOX_MAX_ATTEMPTS)`. Successful events go to `mark_done`.
8. If the bulk call itself raises (`elasticsearch.ApiError`, `elasticsearch.TransportError`, or the
   `ConnectionError` subclasses), call `mark_retry` on **every** claimed event with `repr(exc)`.
9. `session.commit()`. Log one INFO line with the `BatchResult` fields (FR-7.4). Return the result.

Keep steps 3, 5 and 7 as small private functions so they can be tested and type-checked.

### 4.3 Tests: `tests/search/test_indexer.py`

Each test creates data with the existing helpers, then runs `process_once(Session(engine), get_es())`, then
calls `refresh()` and asserts against ES (`es.get` / `es.exists` on `alias()`) and against `outbox_event`.

- **AC-1:** create a product, then process it. The document exists with exactly the FR-1.2 fields, and the event is `done`.
- **AC-4:** rename a product, then process it. The document has the new name.
- **AC-5:** soft-delete a product, then process it. The document is gone.
- **AC-6:**
  - Create a category with 3 products and process them.
  - Soft-delete the 3 products and then the category **through the repositories**, and process.
  - All 3 documents are gone.
  - Then un-delete one product (`is_deleted=False`, save) and process. It stays out of the index.

  For FR-4.2, add a variant that soft-deletes the category while its products are still live. All of their documents must be removed.
- **AC-7:** rename a category with 2 live products, then process. Both documents have the new `category_name`.
- **AC-8:** call `OutboxRepository.add_many` with the same product ID 5 times, then process. `BatchResult.indexed == 1`
  and all 5 events are `done`.
- **AC-9:** process an event, `enqueue` the same product again, and process. The ES `_version` is unchanged and the event is `done`.
- **AC-10:**
  - Monkeypatch `helpers.streaming_bulk` in the indexer module to raise `elasticsearch.ConnectionError`.
  - The event stays `pending` with `attempts == 1` and `available_at > now`.
  - Then set `attempts = 9` and `available_at = now()`, and process again. The event is `failed`.
- **Reindex pause:**
  - In another session, take `pg_advisory_lock(INDEXER_LOCK_KEY)`.
  - `process_once` returns an empty result and the event stays `pending`.
  - Release the lock in a `finally` block.

---

## Step 5: CLI (`app/search/__main__.py`) and reindex

**Spec:** FR-5, FR-8. **ACs:** AC-11, AC-13

### 5.1 `reindex_all(es: Elasticsearch) -> str` in `app/search/indexer.py`

1. Open a **dedicated connection** with `engine.connect()` and take
   `pg_advisory_lock(INDEXER_LOCK_KEY)` on it. This blocks until in-flight batches finish.
   Release it in `finally` with `pg_advisory_unlock`.
2. Call `create_index(es, new_name)`.
3. Stream every indexable product into it, in a `Session(engine)`:
   `helpers.bulk(es, (index action for (p, c) in repo.iter_indexable(500)), chunk_size=500)`.
   Use external versions as in Step 4.
4. Run `es.indices.refresh(index=new_name)`.
5. Do an atomic alias swap in one `es.indices.update_aliases(actions=[{"remove": {"index": "*", "alias": alias()}}, {"add": {"index": new_name, "alias": alias()}}])` call.
   If the alias doesn't exist yet (first run), send only the `add` action.
6. Delete the old physical indices that were behind the alias.
7. Return `new_name`.

### 5.2 CLI

Use `argparse` with subcommands. Write output with `sys.stdout.write`. Call `logging.basicConfig(level=INFO)` in `main()`.

| Command | Implementation |
|---|---|
| `run` | `worker.run()` (Step 6) |
| `process --once` | `ensure_index` then one `process_once`. Print the `BatchResult`. Exit 1 if `failed > 0 or retried > 0` |
| `process --drain` | Loop `process_once` until `claimed == 0`. Print the totals, with the same exit rule |
| `enqueue <uuid>...` | Parse the arguments with `uuid.UUID`. On `ValueError`, write to stderr and exit 2. Then `add_many(SEARCH_PRODUCT, ids)` and commit |
| `retry-failed` | `retry_failed()` and commit. Print the count |
| `reindex` | `reindex_all(get_es())`. Print the new index name |
| `status` | `stats()`, the alias target (`es.indices.get_alias(name=alias())`), `es.count(index=alias())` and `count_indexable()`. Print one `key: value` per line |

Expose `main(argv: Sequence[str] | None = None) -> int` and end the module with `raise SystemExit(main())` under `if __name__ == "__main__":`.
This lets tests call `main([...])` directly.

### 5.3 `backend/scripts/reindex.sh`

```bash
#!/usr/bin/env bash
set -e
set -x

python -m app.search reindex "$@"
```

### 5.4 Tests: `tests/search/test_cli.py`

- `main(["enqueue", "not-a-uuid"]) == 2`.
- `main(["enqueue", str(product.id)])` followed by `main(["process", "--once"]) == 0`. The document exists.
- **AC-11:** create a `failed` event. `main(["retry-failed"])` makes it `pending`, and `process --drain` makes it `done`.
- `reindex`:
  - Create 2 products, then run `main(["reindex"])`.
  - The alias points to a new index that contains both documents.
  - The previous physical index is gone.
- **AC-13:**
  - Hold the advisory lock as in the Step 4 pause test, to simulate a running reindex.
  - Create a product. `process --once` leaves its event `pending`.
  - Release the lock, then `process --once`. The document exists.

  This covers the mechanism. Testing a truly concurrent reindex isn't necessary.
- `status` returns 0 and its output contains the `pending:` and `failed:` lines (use `capsys`).

---

## Step 6: Long-running worker (`app/search/worker.py`)

**Spec:** FR-6, FR-7. **ACs:** AC-16

```python
HEARTBEAT_PATH: Final = Path("/tmp/indexer-heartbeat")  # noqa: S108 if flagged
PURGE_INTERVAL: Final = timedelta(minutes=10)


class Worker:
    def __init__(self, es: Elasticsearch) -> None: ...
    def request_stop(self, *_: object) -> None        # sets self._stop (threading.Event)
    def run_iteration(self) -> BatchResult            # one process_once + heartbeat + purge-if-due
    def run(self) -> None                             # loop until stop requested


def run() -> None:                                    # entry used by the CLI
    worker = Worker(get_es())
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    ensure_index(get_es())
    worker.run()
```

How the loop behaves:
- Each iteration runs `process_once` in a fresh `with Session(engine) as session:` block.
- If `result.claimed == settings.SEARCH_OUTBOX_BATCH_SIZE`, loop again straight away (FR-3.1).
  Otherwise wait with `self._stop.wait(settings.SEARCH_OUTBOX_POLL_SECONDS)`. Use the event wait, not
  `time.sleep`, so SIGTERM interrupts the idle wait.
- Catch and log (`logger.exception`) any unexpected exception from an iteration, wait one poll interval, and continue.
  ES or DB hiccups must not kill the process.
- The stop flag is checked only **between** iterations, so a running batch always finishes and commits (FR-7.2).
- After every iteration, `HEARTBEAT_PATH.touch()`.
- When `PURGE_INTERVAL` has passed since the last purge, run
  `purge_done(now - timedelta(days=settings.SEARCH_OUTBOX_RETENTION_DAYS))` in its own session and commit (FR-6.1).

### Tests: `tests/search/test_worker.py`

- `run_iteration` touches the heartbeat. Monkeypatch `HEARTBEAT_PATH` to a `tmp_path` file.
- `run_iteration` purges old `done` rows when it's due and leaves `failed` rows alone (FR-6.2).
- **AC-16:**
  - Start `worker.run()` in a `threading.Thread`, with a product event pending.
  - Wait until the event is `done`, then call `worker.request_stop()`.
  - `thread.join(timeout=10)` must return, and the thread must not be alive.
- An exception raised by `process_once` (monkeypatched) is logged, and the loop keeps running.

---

## Step 7: Compose and docs

**Spec:** §7

### 7.1 `compose.dev.yml`

Add this service after `celery-beat`:

```yaml
  # Outbox consumer: syncs product changes into Elasticsearch (see backend/docs/specs/product-search-indexer.md)
  search-indexer:
    <<: *backend
    command: ["watchfiles", "--filter", "python", "python -m app.search run", "app"]
    volumes:
      - *code-volume
    depends_on:
      prestart:
        condition: service_completed_successfully
      db:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "test $$(( $$(date +%s) - $$(stat -c %Y /tmp/indexer-heartbeat) )) -lt 30"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 20s
```

Remove the `elasticsearch` entry from the `backend` service's `depends_on` (spec §7). Leave `celery-worker` unchanged.

### 7.2 `compose.prod.yml`

Add the same service. Use the command `["python", "-m", "app.search", "run"]` with no code volume and a `deploy.resources.limits.memory: 256M`.
Remove `elasticsearch` from `backend.depends_on` there too.

### 7.3 Docs

- `backend/README.md`: add a short **"Search Indexer"** section after "Initial Data". Cover what it does, a
  link to the spec, the CLI commands, and the note to run `reindex` once on first deploy.
- `development.md`: add `search-indexer` to the list of services the stack starts.

### 7.4 Manual smoke test (record the output in the PR description)

```bash
docker compose up -d --build
docker compose ps search-indexer                             # healthy
docker compose exec backend python -m app.search reindex
# create a product via http://localhost:8000/docs (POST /api/v1/products/)
docker compose exec backend python -m app.search status      # pending: 0
curl -s 'localhost:9200/products/_search?q=name:<word from product name>' | jq '.hits.total'
```

---

## Definition of done

- [ ] All 7 steps are committed separately, and each commit passes `tests-start.sh` and `lint.sh`.
- [ ] AC-1 through AC-16 each have at least one test. Add the AC ID in the test name or docstring.
- [ ] `alembic downgrade -1 && alembic upgrade head` works.
- [ ] Coverage for `app/search/` and `app/outbox/` is ≥ 90% (`htmlcov/`).
- [ ] The manual smoke test in 7.4 passes.
- [ ] No changes to existing endpoints, services or schemas, apart from the items in 0.4/Step 1
      (`ModelBase` split, conftest teardown, `db.py` import).

## Out of scope (don't build)

- Anything beyond `GET /products/search` (FR-1.5): facets, suggestions, highlighting.
- The bulk importer.
- `LISTEN/NOTIFY`, metrics endpoints, or a dead-letter UI.
