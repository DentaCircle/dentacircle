# Dentacircle

Coordination workflow for an outpatient clinic. See PRODUCT.md for scope.

## Setup

1. Install [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), and Docker.
2. Clone this repo and `cd` into it.
3. Copy `.env.example` to `.env`.
4. Start PostgreSQL: `make db-up`. Wait until `docker compose ps` shows the database as healthy.
5. Install and check both apps: `make check`.
6. Apply database migrations: `make migrate`.
7. Start the API: `make api-dev`. It listens on port 8000. `curl http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
8. Start the web app: `make web-dev`. It listens on port 3000. Open `/` for the shell and `/status` for API and database health.

`API_BASE_URL` is read by the web server when it calls the API. It defaults to `http://127.0.0.1:8000`. Regenerate the typed client after an API shape change with `make api-types`.

`make check` lints, type checks and tests `apps/api` and `apps/web`. Database tests, including the smoke test, run only when `DATABASE_URL` is set. Export it from `.env` before `make check` if you want those tests to connect:

```sh
set -a && source .env && set +a && make check
```

Stop the database with `make db-down`.

Python 3.12 is pinned in `apps/api/.python-version`. `uv sync` installs it. Node 22 or newer is required for `apps/web`.

`LOG_LEVEL` defaults to `INFO`. Set `LOG_LEVEL=DEBUG` in `.env` on your machine when you need a full traceback. That is for local work with synthetic data.
