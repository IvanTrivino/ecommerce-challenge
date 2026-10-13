# Builds the frontend and publishes it to the frontend-dist volume that nginx
# serves (see compose.prod.yml). Building lives here only: the nginx image is
# never rebuilt for a frontend release, and upgrading nginx never touches it.

FROM oven/bun:1.4.3 AS build

WORKDIR /app

# Workspace manifests first, so dependencies are cached until they change
COPY package.json bun.lock /app/
COPY frontend/package.json /app/frontend/
COPY packages/react-email/package.json /app/packages/react-email/

RUN bun install --frozen-lockfile

COPY ./frontend /app/frontend

# frontend/.env.production leaves VITE_API_URL empty: same-origin /api/v1 calls
RUN bun run --filter frontend build

FROM alpine:3.22

COPY --from=build /app/frontend/dist /dist
COPY frontend/scripts/publish.sh /publish.sh

CMD ["sh", "/publish.sh", "/dist", "/target"]
