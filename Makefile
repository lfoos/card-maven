# Card Maven developer entry point. Run `make help` for the list of targets.
SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml
export CARD_MAVEN_TEST_DATABASE_URL ?= postgresql+psycopg://card_maven:card_maven@localhost:5432/card_maven_test

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- Setup -------------------------------------------------------------------
.PHONY: install
install: ## Install Python and web dependencies, and git hooks
	uv sync
	cd apps/web && pnpm install
	uv run pre-commit install

# ---- Local stack -------------------------------------------------------------
.PHONY: up down reset logs
up: ## Start Postgres, Kafka, SeaweedFS (S3), and Keycloak
	$(COMPOSE) up -d --wait postgres kafka seaweedfs keycloak
	$(COMPOSE) up kafka-init

down: ## Stop the local stack (keeps data)
	$(COMPOSE) down

reset: ## Stop the local stack and delete its data
	$(COMPOSE) down -v

logs: ## Follow local stack logs
	$(COMPOSE) logs -f

# ---- Database ----------------------------------------------------------------
.PHONY: migrate migration seed bootstrap
migrate: ## Apply database migrations
	uv run alembic -c db/alembic.ini upgrade head

migration: ## Generate a migration from model changes: make migration m="add sale table"
	@test -n "$(m)" || (echo 'usage: make migration m="description"'; exit 1)
	uv run alembic -c db/alembic.ini revision --autogenerate -m "$(m)"

seed: ## Load sports/brands and sync tracked sets from config/
	uv run card-maven seed
	uv run card-maven sync-tracked-sets

bootstrap: up migrate seed ## Start the stack, migrate, and seed (first run)

# ---- Run ---------------------------------------------------------------------
.PHONY: api web relay
api: ## Run the API with reload on http://localhost:8000
	CARD_MAVEN_LOG_JSON=false uv run flask --app card_maven_api.wsgi:app run --port 8000 --reload

web: ## Run the web app on http://localhost:5173
	cd apps/web && pnpm dev

relay: ## Run the outbox relay
	CARD_MAVEN_LOG_JSON=false uv run card-maven outbox-relay

# ---- Quality -----------------------------------------------------------------
.PHONY: lint format typecheck test test-python test-web check-config check
lint: ## Lint Python and web
	uv run ruff check .
	uv run ruff format --check .
	cd apps/web && pnpm lint && pnpm format:check

format: ## Auto-format Python and web
	uv run ruff format .
	uv run ruff check --fix .
	cd apps/web && pnpm format

typecheck: ## Typecheck Python and web
	uv run mypy packages/card_maven/src services/api/src services/workers/src
	cd apps/web && pnpm typecheck

test-python: ## Python tests with coverage (needs `make up`)
	uv run pytest --cov --cov-report=term --cov-fail-under=90

test-web: ## Web tests with coverage
	cd apps/web && pnpm coverage

test: test-python test-web ## All tests

check-config: ## Validate config/ files
	uv run card-maven check-config

check: lint typecheck check-config test ## Everything CI runs (except infra and images)
