# FastAPI Project - Frontend

The frontend is built with [Vite](https://vitejs.dev/), [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [TanStack Query](https://tanstack.com/query), [TanStack Router](https://tanstack.com/router), [Tailwind CSS](https://tailwindcss.com/), and [shadcn/ui](https://ui.shadcn.com/).

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose (runs the backend and its services)
- [Node.js](https://nodejs.org/) with `npx` (only to bootstrap Bun)
- [Bun](https://bun.sh/) is installed as a dev dependency, so you don't need a global install

## Run the app (backend + frontend)

Run everything from the project root.

1. **Check the root `.env` file.** It defines the first superuser (`FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`, default `admin@example.com` / `changethis`) and `COMPOSE_FILE=compose.dev.yml`.

2. **Start the backend stack** (API, Postgres, Redis, Elasticsearch, RustFS, Celery, search indexer, Mailpit):

   ```bash
   docker compose up -d --wait
   ```

   The `prestart` service applies the migrations and creates the first superuser. Check it with `curl http://localhost:8000/api/v1/utils/health-check/` (should print `true`). If you can't log in as the superuser (for example the database was reset), create it manually:

   ```bash
   docker compose exec -w /app/backend backend python -m app.initial_data
   ```

3. **Install the frontend dependencies.** Bun is a dev dependency; bootstrap it once, then use `npx bun`:

   ```bash
   npx -y bun@1.4.3 install
   ```

4. **Configure the frontend** (optional). `frontend/.env` already points to the local API:

   ```env
   VITE_API_URL=http://localhost:8000
   VITE_APP_NAME=Ecommerce
   ```

5. **Start the frontend dev server:**

   ```bash
   npx bun run dev
   ```

6. **Open the app:**

   | URL | What |
   |---|---|
   | <http://localhost:5173/> | Storefront (public) |
   | <http://localhost:5173/login> | Log in. As the first superuser you land on `/admin` |
   | <http://localhost:5173/signup> | Create a customer account |
   | <http://localhost:8000/docs> | Backend API docs (Swagger) |
   | <http://localhost:8025> | Mailpit (password recovery emails) |

7. **Add some data.** Log in as the superuser, create a category under **Categories**, then add products under **Products**. They show up in the storefront right away, and in search after about 2 seconds (Elasticsearch is updated asynchronously).

To stop everything: stop the dev server with `Ctrl+C` and run `docker compose down` (add `-v` to also wipe the database).

### Useful commands

```bash
npx bun run --filter frontend build   # type-check (strict) and production build
npx bun run lint                      # Biome (auto-fixes)
npx bun x tsc --noEmit -p frontend    # type-check app and tests
npx bun x playwright test             # end-to-end tests (see below)
```

## Removing the Frontend

If you are developing an API-only app and want to remove the frontend, you can do it easily:

* Remove the `./frontend` directory.

* The backend no longer serves or builds the frontend, so nothing else needs to change there.

* In the `.fastapicloudignore` file, remove the `!backend/app/frontend/` entry.

Done, you now have an API-only app. 🤓

## Generate Client

### Automatically

* From the project root, run the script:

```bash
bash ./scripts/generate-client.sh
```

* Commit the changes.

### Manually

* Make sure the backend is running.

* Download the OpenAPI JSON file from `http://localhost:8000/api/v1/openapi.json` and copy it to a new file `openapi.json` at the root of the `frontend` directory.

* To generate the frontend client, run:

```bash
bun run generate-client
```

* Commit the changes.

Regenerate the client whenever backend changes affect the OpenAPI schema.

## App Name

The app name shown in page titles, the footer and the logo `alt` text comes from `VITE_APP_NAME` (default: `Ecommerce`). Set it in `frontend/.env`:

```env
VITE_APP_NAME=My Store
```

## Routes

The frontend has a public storefront and an admin-only backoffice. The route files live in `frontend/src/routes`.

| Route | Page | Access |
|---|---|---|
| `/` | Product catalog (`?category=&page=`) | public |
| `/search?q=&page=` | Product search | public |
| `/products/:productId` | Product detail | public |
| `/account` | Account settings | logged in |
| `/login?redirect=`, `/signup`, `/recover-password`, `/reset-password` | Auth screens | logged out |
| `/admin` | Overview | superuser |
| `/admin/products` | Products CRUD | superuser |
| `/admin/categories` | Categories CRUD | superuser |
| `/admin/imports`, `/admin/imports/:importId` | CSV product imports: upload, history, progress, errors | superuser |
| `/admin/users` | Users CRUD | superuser |
| `/admin/settings` | Own account settings | superuser |

After logging in, superusers go to `/admin` and customers go to `/`, unless a safe relative `redirect` search param is present.

All categories are preloaded by the `_store` and `admin` layout routes (`src/lib/queries/categories.ts`), so product pages can show category names without one request per product.

## Using a Remote API

By default, the built frontend uses the same origin as the FastAPI app. If you want to use a remote API while running the Vite development server, you can set the environment variable `VITE_API_URL` to the URL of the remote API. For example, you can set it in the `frontend/.env` file:

```env
VITE_API_URL=https://my-domain.example.com
```

Then, when you run the frontend, it will use that URL as the base URL for the API.

## Code Structure

The frontend code is structured as follows:

* `frontend/src` - The main frontend code.
* `frontend/public` - Static assets.
* `frontend/src/client` - The generated OpenAPI client.
* `frontend/src/components` - The components of the frontend, including the shadcn/ui components in `frontend/src/components/ui`.
* `frontend/src/hooks` - Custom hooks.
* `frontend/src/lib` - Shared frontend utilities.
* `frontend/src/routes` - The frontend routes and pages.

### Product images

Admins add, replace and remove a product image from the backoffice dialogs. See the [spec](../backend/docs/specs/product-images.md).

* `frontend/src/lib/productImages.ts` - Allowed types and size, the browser-side check and the upload to storage.
* `frontend/src/hooks/useProductImageUpload.ts` - Presigns, uploads with progress and aborts on close.
* `frontend/src/components/Backoffice/Products/ProductImageField.tsx` - The Image field of the product dialogs.
* `frontend/src/components/Store/ProductImage.tsx` - Shows `image_url`, with the placeholder as a fallback.

Uploads go **directly** to object storage (RustFS), never through the API, with a presigned POST. Storage only accepts requests from `FRONTEND_HOST` (CORS), so in dev it must match the origin of the dev server (`http://localhost:5173`). If you serve the frontend from another origin, set `FRONTEND_HOST` in `.env` and run `docker compose exec backend python app/initial_data.py` to apply it to the bucket.

### Product imports

Admins create and update products in bulk from a CSV at `/admin/imports`. See the [spec](../backend/docs/specs/product-imports.md).

* `frontend/src/lib/productImports.ts` - Size limit, the browser-side check, summary text and the error report builder (cells starting with `= + - @` are prefixed with `'`).
* `frontend/src/lib/queries/productImports.ts` - Queries. The list and detail queries poll with `refetchInterval` while an import is pending or running, and stop when it ends.
* `frontend/src/hooks/useProductImportUpload.ts` - Validates, presigns and uploads the CSV with progress.
* `frontend/src/components/Backoffice/Imports/` - Upload card, progress panel, history columns, errors table and `useImportFinished` (refreshes products and categories and toasts when polling sees an import end).
* `frontend/src/routes/admin/imports.index.tsx`, `imports.$importId.tsx` - The pages. All import state comes from the API, so leaving the page does not affect a running import.

Like images, the CSV goes **directly** to object storage with a presigned POST, into a private bucket, so `FRONTEND_HOST` must match the dev origin (CORS on the imports bucket). Category names are unique, so the Playwright specs generate random ones.

## End-to-End Testing with Playwright

The end-to-end tests cover the storefront, the backoffice, access control, the auth flows and keyboard/mobile (360px) checks.

1. Start the whole backend stack (the tests also create data through the API and need Elasticsearch for the search test):

   ```bash
   docker compose up -d --wait
   ```

2. Install the browser once:

   ```bash
   npx bun x playwright install chromium
   ```

3. Run the tests from the project root. Playwright starts the Vite dev server by itself if nothing is listening on port 5173:

   ```bash
   npx bun run test
   ```

   Or from `frontend/`: `npx bun x playwright test`. Use `--ui` for UI mode. To reuse a dev server you already started, set `PLAYWRIGHT_BASE_URL=http://localhost:5173`.

The tests log in as the first superuser from the root `.env`. If the database is empty, create it with `docker compose exec -w /app/backend backend python -m app.initial_data`. Tests create their own uniquely named data and clean up most of it. To wipe everything, run `docker compose down -v`.

To update the tests, navigate to the tests directory and modify the existing test files or add new ones as needed.

For more information on writing and running Playwright tests, refer to the official [Playwright documentation](https://playwright.dev/docs/intro).
