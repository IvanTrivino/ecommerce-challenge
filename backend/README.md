# Mercato - Backend

## Requirements

* [Docker](https://www.docker.com/).
* [uv](https://docs.astral.sh/uv/) (optional, only to give your editor a local environment).

## Development

The backend runs in Docker Compose together with its services. From the project root:

```console
$ docker compose up -d
```

The API is available at `http://localhost:8000`, with automatic interactive docs at `http://localhost:8000/docs`. `./backend` is mounted into the containers, so your changes apply immediately without restarts or rebuilds (rebuild with `docker compose up -d --build` only when dependencies change).

## General Workflow

Run backend commands inside the container with `docker compose exec backend <command>` from the project root. To open a shell: `docker compose exec backend bash`.

For editor autocomplete, optionally run `uv sync` from the project root and select `.venv/bin/python`. This environment is only for the editor.

The backend is layered, with a domain subfolder (for example `users/`) inside each layer:

* `app/api/`: routes (`routes/<domain>/router.py`) and dependencies (`deps/`).
* `app/services/`: business logic.
* `app/repositories/`: database access. Extend `BaseRepository` in `repositories/base.py` and build queries on `_live()` so soft-deleted rows are excluded.
* `app/models/`: SQLAlchemy ORM models. Extend `Base` (`models/base.py`), which provides `id`, `is_deleted`, `created_at` and `updated_at`.
* `app/schemas/`: Pydantic DTOs for requests and responses.

Dependencies flow one way: api → services → repositories → models.

## VS Code

The debugger configuration in `.vscode/launch.json` runs the backend on your machine, not in the container. To use it, create the local environment with `uv sync` and stop the `backend` container first (`docker compose stop backend`) so port 8000 is free; it connects to the other services through the ports published on `localhost`.

## Compose Files

`compose.dev.yml` is the development stack: published ports, a bind mount of `./backend`, and backend reloads. The root `.env` sets `COMPOSE_FILE=compose.dev.yml`, so plain `docker compose` commands use it. Production is `compose.prod.yml`, run with `--env-file .env.prod` (see [../development.md](../development.md)).

## Backend Tests

With the stack running, run the tests inside the backend container:

```console
$ docker compose exec backend bash scripts/tests-start.sh
```

The tests run with Pytest. Modify existing tests or add new ones in `./backend/tests/`. Extra arguments are forwarded to `pytest`, for example to stop on the first error:

```console
$ docker compose exec backend bash scripts/tests-start.sh -x
```

### Test Coverage

When the tests run, they generate `htmlcov/index.html`. Open it in your browser to inspect the test coverage.

## Migrations

Make sure you create a revision of your models and upgrade the database with that revision every time you change them. Run Alembic inside the backend container:

* Alembic is already configured to import the models through `Base.metadata` (models are exported from `./backend/app/models/`). Make sure a new model is imported there so autogenerate sees it.

* After changing a model (for example, adding a column), create a revision:

```console
$ docker compose exec backend alembic revision --autogenerate -m "Add column last_name to User model"
```

* Commit to the git repository the files generated in the alembic directory (they appear in your local folder through the bind mount).

* After creating the revision, run the migration in the database (this is what will actually change the database):

```console
$ docker compose exec backend alembic upgrade head
```

To start over without any previous revision, remove the revision files (`.py` files) under `./backend/app/alembic/versions/` and create a first migration as described above.

## Initial Data (Superuser)

The first superuser is seeded by `./backend/app/initial_data.py`, which calls `init_db()` in `./backend/app/core/db.py` and then makes sure the S3 buckets exist (the private one, the public product images one and the private product imports one). It is idempotent: if a user with the `FIRST_SUPERUSER` email already exists, nothing is created.

The email and password come from the `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` variables in `.env` (`.env.prod` in production). The script runs automatically as the last step of `scripts/prestart.sh`, in the `prestart` service, after the migrations. To run it again by hand:

```console
$ docker compose exec backend python app/initial_data.py
```

Changing the variables later doesn't update an existing superuser; change their password through the API instead.

## Search Indexer

Product changes reach Elasticsearch through a transactional outbox: a SQLAlchemy `before_flush` listener writes an `outbox_event` row in the same transaction as the change, and the `search-indexer` service consumes those events and syncs the `products` index. The API never talks to Elasticsearch when writing. See the [spec](docs/specs/product-search-indexer.md).

Everything the service does can also be run by hand with `python -m app.search <command>`:

```console
$ docker compose exec backend python -m app.search status          # backlog, failed events, index and document counts
$ docker compose exec backend python -m app.search process --drain # process pending events until none are left
$ docker compose exec backend python -m app.search enqueue <product-uuid>...
$ docker compose exec backend python -m app.search retry-failed    # put failed events back to pending
$ docker compose exec backend python -m app.search reindex         # full rebuild with an atomic alias swap
```

Run `reindex` once on the first deploy to load the products that already exist. Writes that skip the ORM flush (Core `insert()`/`update()`, `COPY`, raw SQL) must call `OutboxRepository.add_many` in the same transaction.

## Product Images

Each product can have one image. The browser uploads it straight to object storage and the API never sees the bytes. See the [spec](docs/specs/product-images.md).

1. A superuser calls `POST /api/v1/products/images/presign` with the content type (`image/jpeg`, `image/png` or `image/webp`) and the file size (up to 5 MB). The backend answers with an upload ticket: a POST `url`, the form `fields` to send before the file, and the `key` the object will have.
2. The browser POSTs the file to that URL. The POST policy pins the key, the content type and the size range.
3. The client sends the `key` as `image_key` when it creates or updates the product. The backend checks that the object exists, is small enough and really is the declared image type, then stores the key. `ProductPublic` returns `image_key` and a computed `image_url`.

Images live in a separate, publicly readable bucket (`S3_PRODUCT_IMAGES_BUCKET`): anonymous users can read `products/*` but not list the bucket or write to it. Prestart creates the bucket and applies its policy and CORS rule (allowed origin: `FRONTEND_HOST`).

| Setting | Default | Purpose |
|---|---|---|
| `S3_PRODUCT_IMAGES_BUCKET` | `product-images` | Public images bucket |
| `S3_PRODUCT_IMAGES_PUBLIC_URL` | empty | Browser-reachable bucket URL. Empty: `<S3_PUBLIC_ENDPOINT_URL>/<bucket>`. Set it for a CDN or a managed provider |
| `PRODUCT_IMAGE_MAX_BYTES` | `5242880` | Largest allowed upload |
| `PRODUCT_IMAGE_UPLOAD_EXPIRES_SECONDS` | `300` | How long an upload ticket is valid |
| `PRODUCT_IMAGE_ORPHAN_GRACE_HOURS` | `24` | Minimum age before an unreferenced upload can be swept |
| `S3_CA_BUNDLE` | empty | CA file for the storage endpoint, only for self-signed certificates |

Replaced, removed and abandoned uploads are deleted by a Celery beat task that runs daily at 03:30 UTC. It removes objects older than the grace period that no product row references (soft-deleted products count as references). To run it by hand:

```console
$ docker compose exec celery-worker celery -A app.core.celery_app call app.tasks.sweep_product_images
```

In production the browser talks to the storage endpoint directly, so it must use the same scheme as the frontend page, or browsers block the upload and the images (spec D5). `compose.prod.yml` runs the bundled RustFS with native TLS on `https://${STORAGE_DOMAIN}:9000`, with the same certificates as nginx. A managed S3-compatible provider works by changing the `S3_*` variables only.

## Product Imports

Admins create and update products in bulk from a CSV file. See the [spec](docs/specs/product-imports.md).

1. A superuser calls `POST /api/v1/product-imports/presign` with the file name (`*.csv`) and size (up to 10 MB) and uploads the file straight to storage with the returned ticket, like a product image.
2. `POST /api/v1/product-imports` with the `key` records a `product_import` row and queues the Celery task `run_product_import` (`app/tasks.py`). Calling it again with the same key returns the same import.
3. The task streams the file from storage and applies it in batches of `PRODUCT_IMPORT_BATCH_SIZE` rows. Rows are upserted by SKU, unknown categories are created, and invalid rows are skipped and reported (`GET /product-imports/{id}/errors`).
4. Clients poll `GET /product-imports/{id}`: `progress` is `bytes_processed / total_bytes`.

The CSV bucket (`S3_PRODUCT_IMPORTS_BUCKET`) is private: the browser can only POST to it and no presigned GET is ever issued. Prestart creates it and applies its CORS rule.

The reader is byte-exact (`app/services/products/imports/csv_records.py`): it knows the offset of every record, and each batch commits together with a checkpoint (`bytes_processed`, counters, row errors). A crashed or redelivered task resumes at the checkpoint with a ranged GET pinned to the upload's ETag, so no batch is applied twice. A Postgres advisory lock on the import id keeps two workers from running the same import, and only one import can be active at a time.

**Bulk product writes go through `ProductRepository.upsert_many`.** It is a Core `INSERT ... ON CONFLICT DO UPDATE`, which bypasses the ORM listener that emits search events, so the method adds the `search.product` outbox events itself in the same transaction. Don't write products in bulk any other way.

| Setting | Default | Purpose |
|---|---|---|
| `S3_PRODUCT_IMPORTS_BUCKET` | `product-imports` | Private imports bucket |
| `PRODUCT_IMPORT_MAX_BYTES` | `10485760` | Largest allowed upload |
| `PRODUCT_IMPORT_UPLOAD_EXPIRES_SECONDS` | `300` | How long an upload ticket is valid |
| `PRODUCT_IMPORT_BATCH_SIZE` | `10` | Rows per transaction. Small on purpose in dev so progress and resume are visible; `compose.prod.yml` defaults to `500` |
| `PRODUCT_IMPORT_MAX_RECORD_BYTES` | `65536` | Longest allowed CSV record (guards unterminated quotes) |
| `PRODUCT_IMPORT_MAX_STORED_ERRORS` | `1000` | Row errors kept per import (all are still counted and logged) |
| `PRODUCT_IMPORT_RETENTION_DAYS` | `7` | Age after which uploaded CSVs are deleted |
| `PRODUCT_IMPORT_STALE_MINUTES` | `10` | Silence after which an active import is considered dead |

Two Celery beat jobs keep things tidy. `sweep_product_import_files` runs daily at 03:45 UTC and deletes CSVs older than the retention period (except those of active imports), after which the import can no longer be retried. `reap_stale_product_imports` runs every 5 minutes and marks active imports with no heartbeat (and no advisory lock) as failed, so the single active slot is freed and the import can be retried. To run them by hand:

```console
$ docker compose exec celery-worker celery -A app.core.celery_app call app.tasks.sweep_product_import_files
$ docker compose exec celery-worker celery -A app.core.celery_app call app.tasks.reap_stale_product_imports
```

Accepted trade-off: imports aren't queued (a second one gets a 409), and admin edits made during an import aren't coordinated with it. On the same SKU, whichever commits last wins. SKU inserts can't collide, because the upsert is atomic. See the spec, section 8.

## Orders

Customers build a cart and place orders, and admins fulfil them. See the [spec](docs/specs/checkout.md).

The cart is the customer's single **Draft** order. Placing it runs the checkout in one transaction, and admins move placed orders on:

```
            "+ Add"             place (checkout)            admin: Complete
  (none) ───────────▶ draft ───────────────────▶ in_progress ──────────────▶ completed
                                                     │
                                                     │ admin: Cancel (restock)
                                                     ▼
                                                 cancelled
```

- `POST /api/v1/cart/items` is "+ Add". `POST /api/v1/cart/place` takes the Draft's `order_id` and the `expected_total` the customer saw. It locks the order and then its products (in id order), checks stock and prices, decrements stock, fixes the prices and weights onto the lines, charges, and commits. Placing the same order twice returns the same result.
- **Payments are mocked.** `MockPaymentsGateway` always approves, behind the `PaymentsGateway` protocol (`app/services/orders/payments.py`), so a real provider is a new adapter. Tests swap in declining and failing doubles through `get_payments_gateway`.
- Admins list, cancel (restocks) and complete orders under `/api/v1/orders`. Customers read their own placed orders under `/api/v1/users/me/orders`.
- **Emails go through an outbox.** The `order_notification` row is written in the same transaction as the state change, and the API then enqueues the Celery task `send_order_notification`. The `requeue-order-notifications` beat job (every minute) re-enqueues rows that are still pending, which covers a lost enqueue and retries with backoff. Delivery is at-least-once. Templates are React Email components (`packages/react-email/emails/order_*.tsx`) exported with `npx bun run email:export`.

| Setting | Default | Purpose |
|---|---|---|
| `CART_MAX_ITEMS` | `50` | Distinct lines per cart |
| `ORDER_CURRENCY` | `USD` | Currency stored on every order |
| `ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS` | `120` | Wait before beat picks up a notification the API failed to enqueue |
| `ORDER_NOTIFICATION_MAX_ATTEMPTS` | `5` | Sends before a notification is marked failed |
| `ORDER_NOTIFICATION_BACKOFF_SECONDS` | `30` | First retry delay, doubled on each failed attempt |

## Email Templates

The email templates are written with [React Email](https://react.email) in `./packages/react-email/`. The `emails` directory holds one component per email and the `ui` directory holds the shared components (layout, heading, button, link, callout).

The rendered HTML in `./backend/app/email-templates/` is generated from those components. It is what the application sends and should not be edited by hand.

To preview the emails while editing them, start the dev server from the root of the project:

```console
$ bun run email:dev
```

Values coming from the backend are declared as Jinja placeholders in the component props, for example `username = "{{ username }}"`. The context for each email is built in `generate_*_email()` in `./backend/app/services/email/email_service.py`, so a new placeholder needs to be added there too.

Once you are done, regenerate the templates used by the application:

```console
$ bun run email:export
```
