API_DIR := apps/api

.PHONY: help install db-up db-down migrate run test lint format check docker-up docker-down

help:
	@echo "DevPilot — common tasks"
	@echo "  make install    Install API deps into apps/api/.venv (dev extras)"
	@echo "  make db-up       Start PostgreSQL via docker compose"
	@echo "  make db-down     Stop PostgreSQL"
	@echo "  make migrate     Apply Alembic migrations (local venv)"
	@echo "  make run         Run the API with reload (local venv)"
	@echo "  make test        Run pytest (dedicated test DB)"
	@echo "  make lint        Run ruff check"
	@echo "  make format      Run ruff format"
	@echo "  make check       Lint + format check + tests"
	@echo "  make docker-up   Build and run the full stack (postgres + migrate + api)"
	@echo "  make docker-down Stop the full stack"

install:
	cd $(API_DIR) && python3 -m venv .venv && . .venv/bin/activate && \
		python -m pip install --upgrade pip && pip install -e ".[dev]"

db-up:
	docker compose up -d postgres

db-down:
	docker compose stop postgres

migrate:
	cd $(API_DIR) && . .venv/bin/activate && alembic upgrade head

run:
	cd $(API_DIR) && . .venv/bin/activate && uvicorn app.main:app --reload

test:
	cd $(API_DIR) && . .venv/bin/activate && pytest -v

lint:
	cd $(API_DIR) && . .venv/bin/activate && ruff check .

format:
	cd $(API_DIR) && . .venv/bin/activate && ruff format .

check:
	cd $(API_DIR) && . .venv/bin/activate && \
		ruff check . && ruff format --check . && pytest -v

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
