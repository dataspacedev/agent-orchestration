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
PORT       := 8006
MSG        ?= "new migration"

IMG        ?= image-builder:latest
NAMESPACE  ?= agent-system

.DEFAULT_GOAL := help

.PHONY: help venv activate install install-dev run test lint typecheck check clean \
        db-up db-down db-migrate db-rollback db-revision db-reset \
        docker-build docker-push deploy undeploy port-forward k8s-logs k8s-status

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
	@echo ""
	@echo "  docker-build   Build the container image (IMG=$(IMG))"
	@echo "  docker-push    Push the container image to a registry"
	@echo "  deploy         Build image and deploy service to the cluster"
	@echo "  undeploy       Remove service from the cluster"
	@echo "  port-forward   Forward cluster port to localhost:$(PORT)"
	@echo "  k8s-logs       Tail API pod logs"
	@echo "  k8s-status     Show pods, services, and deployments in $(NAMESPACE)"

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

# ── Kubernetes ────────────────────────────────────────────────────────────────

docker-build:
	docker build --platform linux/arm64 -t $(IMG) .

docker-push:
	docker push $(IMG)

deploy: docker-build
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f config/rbac.yaml
	kubectl apply -f config/api.yaml
	kubectl -n $(NAMESPACE) rollout status deployment/image-builder --timeout=120s
	@echo "Deploy complete. Run 'make port-forward' to access the API at http://localhost:$(PORT)"

undeploy:
	kubectl delete -f config/api.yaml --ignore-not-found
	kubectl delete -f config/rbac.yaml --ignore-not-found

port-forward:
	kubectl -n $(NAMESPACE) port-forward svc/image-builder $(PORT):8000

k8s-logs:
	kubectl -n $(NAMESPACE) logs -l app.kubernetes.io/name=image-builder -f --max-log-requests=5

k8s-status:
	kubectl -n $(NAMESPACE) get pods,services,deployments \
	  -l 'app.kubernetes.io/name=image-builder'
