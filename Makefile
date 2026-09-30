.PHONY: lint typecheck test check db-up db-down

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
