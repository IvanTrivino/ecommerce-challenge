# FastAPI Project - Backend

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

The first superuser is seeded by `./backend/app/initial_data.py`, which calls `init_db()` in `./backend/app/core/db.py` and then makes sure the S3 bucket exists. It is idempotent: if a user with the `FIRST_SUPERUSER` email already exists, nothing is created.

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
