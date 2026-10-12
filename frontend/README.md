# FastAPI Project - Frontend

The frontend is built with [Vite](https://vitejs.dev/), [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [TanStack Query](https://tanstack.com/query), [TanStack Router](https://tanstack.com/router), [Tailwind CSS](https://tailwindcss.com/), and [shadcn/ui](https://ui.shadcn.com/).

## Requirements

- [Bun](https://bun.sh/) (installed as a dev dependency; bootstrap once with `npx -y bun@1.4.3 install`, then use `npx bun …`)

## Quick Start

From the project root, install the dependencies and start the frontend development server:

```bash
bun install
bun run dev
```

Then open <http://localhost:5173/> in your browser.

Start the backend with `docker compose up` from the project root. See [../development.md](../development.md) for the complete setup.

Check `frontend/package.json` to see the other available commands.

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

## End-to-End Testing with Playwright

The frontend includes initial end-to-end tests using Playwright. To run the tests, you need to have the Docker Compose stack running. Start the stack with the following command:

```bash
docker compose up -d --wait backend
```

Then, you can run the tests with the following command:

```bash
npx bun x playwright test
```

The tests log in as the first superuser from the root `.env`, so run `python -m app.initial_data` in the backend container once if the database is empty.

You can also run your tests in UI mode to see the browser and interact with it running:

```bash
bunx playwright test --ui
```

To stop and remove the Docker Compose stack and clean the data created in tests, use the following command:

```bash
docker compose down -v
```

To update the tests, navigate to the tests directory and modify the existing test files or add new ones as needed.

For more information on writing and running Playwright tests, refer to the official [Playwright documentation](https://playwright.dev/docs/intro).
