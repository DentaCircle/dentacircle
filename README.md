# Dentacircle

Coordination workflow for an outpatient clinic. See PRODUCT.md for scope.

## Setup

1. Install [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), and Docker.
2. Clone this repo and `cd` into it.
3. Copy `.env.example` to `.env`.
4. Start PostgreSQL: `make db-up`. Wait until `docker compose ps` shows the database as healthy.
5. Install and check both apps: `make check`.

`make check` lints, type checks and tests `apps/api` and `apps/web`. The database smoke test runs only when `DATABASE_URL` is set. Export it from `.env` before `make check` if you want that test to connect:

```sh
set -a && source .env && set +a && make check
```

Stop the database with `make db-down`.

Python 3.12 is pinned in `apps/api/.python-version`. `uv sync` installs it. Node 22 or newer is required for `apps/web`.
