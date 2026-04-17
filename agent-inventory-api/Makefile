PYTHON     := python3
VENV_DIR   := .venv
VENV_BIN   := $(VENV_DIR)/bin
PIP        := $(VENV_BIN)/python -m pip
UVICORN    := $(VENV_BIN)/uvicorn
PYTEST     := $(VENV_BIN)/pytest
RUFF       := $(VENV_BIN)/ruff
MYPY       := $(VENV_BIN)/mypy
ALEMBIC    := $(VENV_BIN)/alembic

HOST       := 0.0.0.0
PORT       := 8005
MSG        ?= "new migration"

.DEFAULT_GOAL := help

.PHONY: help venv activate install install-dev run test lint typecheck check clean \
        db-up db-down db-migrate db-rollback db-revision db-reset

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  venv           Create virtual environment at $(VENV_DIR)/"
	@echo "  activate       Print the command to activate the virtual environment"
	@echo "  install        Install production dependencies into the venv"
	@echo "  install-dev    Install all dependencies (prod + dev) into the venv"
	@echo "  run            Start the API server with hot-reload"
	@echo "  test           Run the test suite (requires postgres — run db-up first)"
	@echo "  lint           Lint and auto-fix with ruff"
	@echo "  typecheck      Run mypy static type checks"
	@echo "  check          Run lint + typecheck + tests"
	@echo "  clean          Remove the virtual environment and caches"
	@echo ""
	@echo "  db-up          Start postgres via docker compose"
	@echo "  db-down        Stop postgres via docker compose"
	@echo "  db-migrate     Run alembic migrations (upgrade head)"
	@echo "  db-rollback    Roll back last migration (downgrade -1)"
	@echo "  db-revision    Generate new migration  (MSG=\"describe change\")"
	@echo "  db-reset       Drop and recreate all tables (dev only)"

# ── Environment ──────────────────────────────────────────────────────────────

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "Virtual environment created at $(VENV_DIR)/"
	@echo "Run 'make activate' to see how to activate it."

activate:
	@echo "Run the following command to activate the virtual environment:"
	@echo ""
	@echo "    source $(VENV_DIR)/bin/activate"
	@echo ""

install: venv
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -e .
	@echo "Production dependencies installed."

install-dev: venv
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -e ".[dev]"
	@echo "Dev dependencies installed."

# ── Service ───────────────────────────────────────────────────────────────────

run: install-dev
	$(UVICORN) app.main:app --host $(HOST) --port $(PORT) --reload

# ── Quality ───────────────────────────────────────────────────────────────────

test: install-dev
	$(PYTEST) -v

lint: install-dev
	$(RUFF) check . --fix
	$(RUFF) format .

typecheck: install-dev
	$(MYPY) app/

check: lint typecheck test

# ── Database ──────────────────────────────────────────────────────────────────

db-up:
	docker compose up postgres -d
	@echo "Waiting for postgres to be ready..."
	@until docker compose exec postgres pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	@echo "Postgres is ready."

db-down:
	docker compose down

db-migrate: install-dev
	$(ALEMBIC) upgrade head

db-rollback: install-dev
	$(ALEMBIC) downgrade -1

db-revision: install-dev
	$(ALEMBIC) revision --autogenerate -m $(MSG)

db-reset: install-dev
	$(ALEMBIC) downgrade base
	$(ALEMBIC) upgrade head

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf $(VENV_DIR) .pytest_cache .mypy_cache .ruff_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "Cleaned."
