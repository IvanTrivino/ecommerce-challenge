# Functional Spec: Product Search Indexer

| | |
|---|---|
| **Status** | Draft |
| **Owner** | Ivan Trivino |
| **Last updated** | 2026-10-11 |
| **Components** | `backend` (outbox, indexer, CLI), `compose.dev.yml`, `compose.prod.yml` |

## 1. Summary

Products are stored in Postgres and searched through Elasticsearch (ES). This spec defines how catalog changes reach ES, using the **transactional outbox pattern**:

- Every catalog change that affects search writes an `outbox_event` row in the **same database transaction** as the change.
- A long-running **search indexer** process consumes those events and syncs the `products` index.
- A **CLI** runs the same logic manually for testing and maintenance.

The API never talks to ES when writing data. If ES is unavailable, writes still succeed, and events wait in the outbox until the indexer can process them.

## 2. Goals and non-goals

### Goals

- G1. Every product create, update or delete that affects search is reflected in ES, with no lost changes.
- G2. Writers (current endpoints, and a future bulk importer) depend only on Postgres.
- G3. Typical lag between a commit and searchability is ≤ 2 s.
- G4. Failed indexing is retried automatically, and permanent failures are visible.
- G5. The index can be fully rebuilt (for example, after a mapping change) with no downtime and no lost events.
- G6. Everything the worker does can also be triggered manually from a CLI.

### Non-goals

- The bulk importer itself. This spec only defines how it must emit outbox events (FR-2.4).
- Delivering events to consumers other than the search indexer. The outbox table is generic so this can be added later.
- Searching on price, stock, weight or dates.

## 3. Definitions

| Term | Meaning |
|---|---|
| **Indexable product** | A product where `product.is_deleted = false` **and** its category has `is_deleted = false`. |
| **Searchable fields** | `name`, `description`, `sku`, `category_name`. |
| **Outbox event** | A row in `outbox_event` saying an aggregate (product or category) may need re-indexing. |
| **Aggregate** | The entity an event refers to: a product or a product category. |
| **Alias** | The ES alias `products`. Readers and the indexer always use the alias, never a physical index name. |

## 4. Functional requirements

### FR-1 Search document

- **FR-1.1** Each indexable product is exactly one ES document. The document `_id` is the product UUID.
- **FR-1.2** The document contains only these fields:

  | Field | Source | ES type | Searchable |
  |---|---|---|---|
  | `name` | `product.name` | `text`, analyzer `english` | yes |
  | `description` | `product.description` (may be null) | `text`, analyzer `english` | yes |
  | `sku` | `product.sku` | `keyword`, normalizer `lowercase` + `asciifolding` | yes (exact, case-insensitive) |
  | `category_name` | `product_category.name` | `text`, analyzer `english` | yes |
  | `updated_at` | `max(product.updated_at, category.updated_at)` | `date`, `index: false` | no (internal) |

- **FR-1.3** The mapping uses `"dynamic": "strict"`. ES rejects any field not listed in FR-1.2.
- **FR-1.4** Search results return product IDs only. A consumer gets the full product data from Postgres.
- **FR-1.5** `GET /products/search` is the only way clients search. It queries the alias with a `multi_match` over `name`, `description`, `sku` and `category_name`, then loads the live products from Postgres in ranking order. Elasticsearch is never exposed to clients.

### FR-2 Emitting outbox events

- **FR-2.1** An event is written in the same transaction as the change. If the transaction rolls back, no event exists.
- **FR-2.2** Events are emitted automatically by a SQLAlchemy `before_flush` listener. Services, repositories and routes don't need to know about it.
- **FR-2.3** Event triggers:

  | Entity | Emit an event when | Topic |
  |---|---|---|
  | `Product` | it is created, or any of `name`, `description`, `sku`, `category_uuid`, `is_deleted` changes | `search.product` |
  | `ProductCategory` | it is created, or any of `name`, `is_deleted` changes | `search.product_category` |

  Changes to other fields (for example, a stock-only or price-only update) **must not** emit an event.
- **FR-2.4** Writes that skip the ORM flush (Core `insert()`/`update()`, `COPY`, raw SQL) must call `OutboxRepository.add_many(topic, aggregate_ids)` in the same transaction. The future bulk importer must follow this rule.

### FR-3 Processing events

- **FR-3.1** The indexer polls for pending events every `SEARCH_OUTBOX_POLL_SECONDS` (2 s). If a batch comes back full, it polls again right away.
- **FR-3.2** A batch is claimed with `status = 'pending' AND available_at <= now()`, ordered by `id`, limited to `SEARCH_OUTBOX_BATCH_SIZE`, using `FOR UPDATE SKIP LOCKED`. The whole batch is handled in one DB transaction.
- **FR-3.3** Events in a batch are deduplicated by aggregate. Several events for the same product produce at most one ES action.
- **FR-3.4** A `search.product_category` event is expanded to every product in that category, including deleted ones.
- **FR-3.5** For each affected product, the indexer reads the **current** row and its category from Postgres:
  - If the product is indexable, send an `index` action with the FR-1.2 document.
  - Otherwise (the product is deleted, its category is deleted, or the row doesn't exist), send a `delete` action.
- **FR-3.6** Every ES action uses `version_type=external` with `version` = `max(product.updated_at, category.updated_at)` in epoch microseconds. This stops an older state from overwriting a newer one.
- **FR-3.7** Per event, the outcome is:

  | ES result | Event outcome |
  |---|---|
  | Success | `status='done'`, `processed_at=now()` |
  | `409` version conflict | Treated as success (a newer version is already indexed) |
  | `404` on delete | Treated as success (already absent) |
  | Any other error, or ES unreachable | `attempts += 1`, `last_error` set, `available_at = now() + backoff` |

- **FR-3.8** Backoff starts at 2 s, doubles on each attempt, and is capped at 5 min. When `attempts` reaches `SEARCH_OUTBOX_MAX_ATTEMPTS` (10), the event becomes `status='failed'` and is no longer retried automatically.
- **FR-3.9** Several indexer instances can run at once. `SKIP LOCKED` guarantees that no event is claimed by two instances at the same time.

### FR-4 Deletion behaviour

- **FR-4.1** Soft-deleting a product removes its document from the index.
- **FR-4.2** Soft-deleting a category removes the documents of **all** its products. *Note:* today `ProductCategoryService.delete_category` refuses to delete a category that still has live products, so through the API this applies only to products that are already deleted. The indexer still implements the rule, so it holds for any other write path, such as the bulk importer or a manual fix.
- **FR-4.3** A later update to a product whose category is deleted must not add it back to the index (this follows from FR-3.5).
- **FR-4.4** Renaming a category updates `category_name` on all of its live products.

### FR-5 Full reindex

- **FR-5.1** A full reindex builds a new physical index `products_<UTC timestamp>` with the current mapping. It loads every indexable product, then atomically moves the `products` alias to the new index and deletes the old one.
- **FR-5.2** During a reindex, the indexer workers pause. The reindex holds an exclusive Postgres advisory lock, and each worker batch takes the same lock in shared mode. Events created during the reindex stay `pending` and are processed against the new index after the swap.
- **FR-5.3** If the alias doesn't exist when the indexer starts, the indexer creates the first physical index and the alias.
- **FR-5.4** On first deployment, pre-existing products are loaded by running a full reindex once.

### FR-6 Outbox retention

- **FR-6.1** About every 10 minutes, the indexer deletes `done` events older than `SEARCH_OUTBOX_RETENTION_DAYS` (7).
- **FR-6.2** `failed` events are never deleted automatically.

### FR-7 Long-running process

- **FR-7.1** Entry point: `python -m app.search run`.
- **FR-7.2** On `SIGTERM`/`SIGINT`, the indexer finishes the current batch, commits, and exits with code 0.
- **FR-7.3** After every loop iteration, the indexer touches `/tmp/indexer-heartbeat`. The container healthcheck fails if the file is older than 30 s.
- **FR-7.4** The indexer logs one line per batch: events claimed, documents indexed, documents deleted, retries and failures.

### FR-8 Manual CLI

All commands run with `python -m app.search <command>`. They work inside the backend container (`docker compose exec backend ...`) and locally. A wrapper `backend/scripts/reindex.sh` runs `reindex`.

| Command | Behaviour | Exit code |
|---|---|---|
| `run` | Runs the long-running indexer (FR-7). | 0 on clean shutdown |
| `process --once` | Claims and processes one batch, prints a summary, exits. | 0, or 1 if any event failed |
| `process --drain` | Processes batches until no eligible pending events remain. | 0, or 1 if any event failed |
| `enqueue <product-uuid>...` | Inserts `search.product` events for the given IDs. | 0, or 2 on an invalid UUID |
| `retry-failed` | Sets every `failed` event back to `pending` with `attempts=0` and `available_at=now()`. Prints the count. | 0 |
| `reindex` | Runs a full reindex (FR-5). | 0 on success |
| `status` | Prints the pending and failed counts, the age of the oldest pending event, the physical index behind the alias, the ES document count, and the count of indexable products in Postgres. | 0 |

## 5. Data model

### 5.1 `outbox_event` (migration `0003`)

| Column | Type | Constraints / default |
|---|---|---|
| `id` | `BIGINT` | identity, primary key |
| `topic` | `VARCHAR(50)` | not null |
| `aggregate_id` | `UUID` | not null |
| `status` | `VARCHAR(10)` | not null, default `'pending'`, one of `pending`, `done`, `failed` |
| `attempts` | `INTEGER` | not null, default `0` |
| `available_at` | `TIMESTAMPTZ` | not null, default `now()` |
| `last_error` | `TEXT` | nullable |
| `created_at` | `TIMESTAMPTZ` | not null, default `now()` |
| `processed_at` | `TIMESTAMPTZ` | nullable |

Index: `ix_outbox_event_pending` on `(available_at, id) WHERE status = 'pending'`.

### 5.2 Model base refactor

The shared columns move off the declarative base so that `OutboxEvent` doesn't inherit them:

- `ModelBase(DeclarativeBase)` holds only the metadata.
- `Base(ModelBase)` is abstract and keeps `id` (UUID), `is_deleted`, `created_at` and `updated_at`. All existing models keep using it.
- `OutboxEvent(ModelBase)` defines its own columns.

Alembic keeps using the same metadata.

## 6. Configuration

| Setting | Default | Purpose |
|---|---|---|
| `ELASTICSEARCH_PRODUCTS_ALIAS` | `products` | Alias the indexer writes to and readers query |
| `SEARCH_OUTBOX_POLL_SECONDS` | `2` | Idle poll interval |
| `SEARCH_OUTBOX_BATCH_SIZE` | `500` | Maximum events claimed per batch |
| `SEARCH_OUTBOX_MAX_ATTEMPTS` | `10` | Attempts before an event becomes `failed` |
| `SEARCH_OUTBOX_RETENTION_DAYS` | `7` | Age after which `done` events are deleted |

## 7. Deployment

- New compose service `search-indexer`, based on the shared `*backend` definition, in both compose files:
  - **Dev:** `watchfiles --filter python "python -m app.search run" app`, with the code volume mounted.
  - **Prod:** `python -m app.search run`, memory limit `256M`.
  - `depends_on`: `prestart` (completed successfully), `db` (healthy), `elasticsearch` (healthy).
  - Healthcheck as defined in FR-7.3.
- The `backend` service no longer requires `elasticsearch` to be healthy just to write data.

## 8. Code layout

| Path | Contents |
|---|---|
| `app/models/base.py` | `ModelBase` / `Base` split |
| `app/models/outbox/outbox_event.py` | `OutboxEvent` model |
| `app/outbox/listeners.py` | `before_flush` listener (FR-2) |
| `app/repositories/outbox/outbox_repository.py` | `add_many`, `claim_batch`, `mark_done`, `mark_retry`, `purge_done`, `retry_failed` |
| `app/repositories/products/product_repository.py` | `list_ids_by_category`, `get_many_with_category` (both include deleted rows) |
| `app/search/products_index.py` | Index settings and mapping, `ensure_index()`, `to_document()` |
| `app/search/indexer.py` | `process_once()`, `reindex_all()` |
| `app/search/worker.py` | Run loop, signal handling, heartbeat, retention |
| `app/search/__main__.py` | argparse CLI (FR-8) |
| `app/alembic/versions/0003_create_outbox_event_table.py` | Migration |
| `scripts/reindex.sh` | CLI wrapper |

## 9. Non-functional requirements

- **NFR-1 Latency:** p95 commit-to-searchable time ≤ 2 s under normal load.
- **NFR-2 Durability:** no change is lost when ES or the indexer is down. Events stay `pending` until processed.
- **NFR-3 Idempotency:** processing the same event any number of times leaves ES in the same state.
- **NFR-4 Write-path isolation:** the API's write latency and success don't depend on ES availability.
- **NFR-5 Observability:** the backlog size, the age of the oldest pending event, and failed events are visible through `status` and the logs.

## 10. Acceptance criteria

Each criterion is covered by an automated test. Worker tests run against the real ES with the alias `test_products`, which is deleted during teardown. `tests/conftest.py` also clears `outbox_event`.

| # | Scenario | Expected |
|---|---|---|
| AC-1 | Create a product | One `search.product` event in the same transaction. After `process --once`, the document exists with exactly the FR-1.2 fields. |
| AC-2 | Product insert rolls back | No product and no event. |
| AC-3 | Update only `stock` or `price` | No event created. |
| AC-4 | Update `name` | An event is created and the document's `name` is updated. |
| AC-5 | Soft-delete a product | The document is removed. |
| AC-6 | Soft-delete a category with 3 products | All 3 documents are removed. A later update to one of them doesn't add it back. |
| AC-7 | Rename a category | `category_name` is updated on all of its live products. |
| AC-8 | 5 events for one product in one batch | One ES action. All 5 events are `done`. |
| AC-9 | Same event processed twice | ES state is unchanged. The `409` counts as success. |
| AC-10 | ES unreachable | Events stay `pending` with `attempts` increased and `available_at` pushed back. After 10 attempts, `failed`. |
| AC-11 | `retry-failed` | Failed events become `pending` and are then processed. |
| AC-12 | Two concurrent `process --once` | No event is processed by both. |
| AC-13 | Product created during `reindex` | Its event stays `pending` until the alias swap, then appears in the new index. |
| AC-14 | English analysis | Searching "running shoes" matches a product named "Run Shoe". |
| AC-15 | SKU search | `abc-123` matches SKU `ABC-123`. `abc` does not. |
| AC-16 | `SIGTERM` during a batch | The batch commits and the process exits 0. |

## 11. Implementation order

1. `ModelBase` refactor, `OutboxEvent` model, migration 0003
2. Flush listener and `OutboxRepository`, with tests (AC-1 to AC-4)
3. Index mapping, `ensure_index`, `to_document` (AC-14, AC-15)
4. `process_once()` with retry logic, with tests (AC-5 to AC-12)
5. CLI: `process`, `enqueue`, `status`, `reindex`, `retry-failed` (AC-11, AC-13)
6. `run` loop: signals, heartbeat, retention (AC-16)
7. Compose services and README

## 12. Future work

- The bulk importer, emitting events per FR-2.4.
- Optional Postgres `LISTEN/NOTIFY` to wake the indexer early, with polling kept as the fallback.
- Other outbox consumers, through new topics.
