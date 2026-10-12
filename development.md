# FastAPI Project - Development

## Local Development

Everything runs in Docker Compose, using `compose.dev.yml`. The root `.env` sets `COMPOSE_FILE=compose.dev.yml`, so plain `docker compose` commands use it.

From the project root, start the whole stack (backend, Celery, search indexer, Postgres, Redis, Elasticsearch, RustFS, Mailpit, Adminer):

```bash
docker compose up -d
```

Migrations, initial data and bucket creation run once in the `prestart` service before the backend starts. The first start can take a minute; follow it with `docker compose logs -f backend`.

`./backend` is bind-mounted into the containers at `/app/backend`, so any change you make on your machine is visible in the containers immediately. The API (`fastapi dev`) and Celery (through `watchfiles`) reload by themselves, with no restart or rebuild. You only need to rebuild after changing dependencies (`pyproject.toml` or `uv.lock`):

```bash
docker compose up -d --build
```

Now you can open these URLs:

Backend API: <http://localhost:8000>

Automatic interactive API documentation with Swagger UI: <http://localhost:8000/docs>

Adminer, database web administration: <http://localhost:8080>

RustFS (S3-compatible object storage) API: <http://localhost:9000>, web console: <http://localhost:9001>

Elasticsearch: <http://localhost:9200>

Redis cache: `localhost:6379`, Redis Celery broker: `localhost:6380`

Mailpit: <http://localhost:8025>

### Running Commands

Run backend commands inside the container:

```bash
docker compose exec backend bash              # open a shell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "Add column"
docker compose exec backend bash scripts/tests-start.sh
docker compose exec backend ruff check .
```

Files created in the container (for example new migrations) appear in your local `./backend` folder.

### Editor Support (optional)

The Python environment lives in the container. For autocomplete and type checking in your editor, you can also create a local environment from the project root with `uv sync` and point your editor to `.venv/bin/python`. You don't run the application with it.

### Frontend

The frontend is developed separately. Bun is installed as a dev dependency: bootstrap it once with `npx -y bun@1.4.3 install`, then use `npx bun …`. From the project root:

```bash
bun install
bun run dev
```

Frontend development server: <http://localhost:5173>. It uses the backend at `http://localhost:8000`, as configured in `frontend/.env`.

## Mailpit

[Mailpit](https://mailpit.axllent.org) captures emails sent during local development instead of delivering them. The backend connects to the `mailpit` service (SMTP on port 1025). Captured emails are available at <http://localhost:8025>.

## Docker Compose Files and Environment Variables

There are two standalone Compose files, one per environment:

* `compose.dev.yml`: local development. Every service is published on its own port, `./backend` is bind-mounted into the containers (no rebuild or restart; the API and Celery reload on change), and Mailpit, Adminer and RustFS run locally. `.env` sets `COMPOSE_FILE=compose.dev.yml`, so plain `docker compose` commands use it.
* `compose.prod.yml`: production. It is self-contained (Postgres, Redis, RustFS and Elasticsearch included), publishes only nginx (80/443, HTTPS) and the RustFS API (9000), restarts services automatically, has resource limits, and requires every secret. Copy `.env.prod.example` to `.env.prod` and run `docker compose --env-file .env.prod -f compose.prod.yml up -d --build`, so the development defaults in `.env` are never used. To run it locally, first create a self-signed certificate with `bash scripts/local-certs.sh`.

Docker Compose reads `.env` to fill the `${VAR}` placeholders in the Compose files, and passes the settings each container needs through its `environment:` block. The application inside the container does not read the file itself, so a new variable must also be added to that block.

After changing variables, make sure you restart the stack:

```bash
docker compose up -d
```

## The `.env` File

The tracked `.env` file contains local development defaults, passwords, and other configuration. Docker Compose overrides hostnames such as the database and SMTP server with their Compose service names inside the containers.

Do not store deployment secrets in `.env`. Production values go in `.env.prod`, which is not tracked by Git.

## Pre-commit Hooks and Code Linting

The project uses [prek](https://prek.j178.dev/), a modern alternative to [pre-commit](https://pre-commit.com/), for code linting and formatting.

You can find a file `.pre-commit-config.yaml` with configurations at the root of the project.

### Install `prek` to Run Automatically

`prek` is already part of the dependencies of the project.

From the project root, install the Git hook so that `prek` runs automatically before each commit:

```bash
uv run prek install -f
```

The `-f` flag forces the installation, in case there was already a `pre-commit` hook previously installed.

Now whenever you try to commit, for example with:

```bash
git commit
```

`prek` will check and format the code you are about to commit. If it modifies any files, add those files to Git again before committing.

### Run `prek` Manually

You can also run `prek` manually on all files from the project root:

```bash
uv run prek run --all-files
```
