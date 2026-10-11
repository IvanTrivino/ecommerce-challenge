# FastAPI Project - Backend

## Requirements

* [Docker](https://www.docker.com/).
* [uv](https://docs.astral.sh/uv/) for Python package and environment management.

## Local Development

Run the backend locally and connect it to PostgreSQL in Docker Compose.

From the project root, start PostgreSQL and Mailpit:

```console
$ docker compose up -d db mailpit
```

Then, from `./backend/`, install the dependencies, prepare the database, and start the development server:

```console
$ uv sync
$ uv run bash scripts/prestart.sh
$ uv run fastapi dev
```

The API is available at `http://localhost:8000`, with automatic interactive docs at `http://localhost:8000/docs`.

## General Workflow

Run backend commands from `./backend/` with `uv run`. Make sure your editor uses the Python interpreter at `.venv/bin/python` in the project root.

The backend is layered, with a domain subfolder (for example `users/`) inside each layer:

* `app/api/`: routes (`routes/<domain>/router.py`) and dependencies (`deps/`).
* `app/services/`: business logic.
* `app/repositories/`: database access. Extend `BaseRepository` in `repositories/base.py` and build queries on `_live()` so soft-deleted rows are excluded.
* `app/models/`: SQLAlchemy ORM models. Extend `Base` (`models/base.py`), which provides `id`, `is_deleted`, `created_at` and `updated_at`.
* `app/schemas/`: Pydantic DTOs for requests and responses.

Dependencies flow one way: api → services → repositories → models.

## VS Code

There are already configurations in place to run the backend through the VS Code debugger, so that you can use breakpoints, pause and explore variables, etc.

The setup is also already configured so you can run the tests through the VS Code Python tests tab.

## Full Stack with Docker Compose

To run the backend and its services (Postgres, Redis, Celery, Elasticsearch, RustFS) in Docker Compose:

```console
$ docker compose run --rm backend bash scripts/prestart.sh
$ docker compose up -d
```

The API is available at `http://localhost:8000`. The frontend is not served by this stack..

### Compose Files

`compose.dev.yml` is the development stack: published ports, a bind mount of `./backend`, and backend reloads. The root `.env` sets `COMPOSE_FILE=compose.dev.yml`, so plain `docker compose` commands use it. Production is `compose.prod.yml`, run with `--env-file .env.prod`.

To open a shell in the backend container:

```console
$ docker compose exec backend bash
```

## Backend Tests

To test the backend from the `backend` directory, run:

```console
$ uv run bash scripts/test.sh
```

The tests run with Pytest. Modify existing tests or add new ones in `./backend/tests/`.

### Test a Running Stack

If your stack is already up and you just want to run the tests, you can use:

```bash
docker compose exec backend bash scripts/tests-start.sh
```

The `/app/backend/scripts/tests-start.sh` script calls `pytest`. If you need to pass extra arguments to `pytest`, you can pass them to that command and they will be forwarded.

For example, to stop on first error:

```bash
docker compose exec backend bash scripts/tests-start.sh -x
```

### Test Coverage

When the tests run, they generate `htmlcov/index.html`. Open it in your browser to inspect the test coverage.

## Migrations

Make sure you create a revision of your models and upgrade the database with that revision every time you change them. From the `backend` directory, use `uv` to run Alembic against the PostgreSQL container:

* Alembic is already configured to import the models through `Base.metadata` (models are exported from `./backend/app/models/`). Make sure a new model is imported there so autogenerate sees it.

* After changing a model (for example, adding a column), create a revision:

```console
$ uv run alembic revision --autogenerate -m "Add column last_name to User model"
```

* Commit to the git repository the files generated in the alembic directory.

* After creating the revision, run the migration in the database (this is what will actually change the database):

```console
$ uv run alembic upgrade head
```

To start over without any previous revision, remove the revision files (`.py` files) under `./backend/app/alembic/versions/` and create a first migration as described above.

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
