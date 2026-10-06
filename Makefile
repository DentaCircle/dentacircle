.PHONY: lint typecheck test check db-up db-down api-dev migrate web-dev web-build api-types create-user

lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && pnpm lint

typecheck:
	cd apps/api && uv run mypy
	cd apps/web && pnpm typecheck

test:
	cd apps/api && uv run pytest
	cd apps/web && pnpm test

check: lint typecheck test

db-up:
	docker compose up -d db

db-down:
	docker compose down

api-dev:
	cd apps/api && uv run uvicorn dentacircle.main:app --reload --port 8000 --no-access-log

migrate:
	cd apps/api && uv run alembic upgrade head

web-dev:
	cd apps/web && pnpm dev

web-build:
	cd apps/web && pnpm build

create-user:
	cd apps/api && uv run python scripts/create_user.py $(ARGS)

api-types:
	cd apps/api && uv run python scripts/export_openapi.py
	cd apps/web && pnpm exec openapi-typescript ../api/openapi.json -o lib/api/schema.d.ts
