# ── Variables ──────────────────────────────────────────────────────────────────
REGISTRY  ?=
TAG       ?= latest
PLATFORM  ?= linux/arm64
NAMESPACE ?= agent-system

# Prefix image names with registry when set
_prefix        := $(if $(REGISTRY),$(REGISTRY)/,)
API_IMG        := $(_prefix)agent-inventory-api:$(TAG)
CONTROLLER_IMG := $(_prefix)agent-controller:$(TAG)
UI_IMG         := $(_prefix)agent-registry-ui:$(TAG)
EXAMPLE_IMG    := $(_prefix)example-agent:$(TAG)

KIND_CLUSTER ?= kind

.DEFAULT_GOAL := help

.PHONY: help \
        dev-api dev-ui \
        build build-api build-controller build-ui build-example \
        push push-api push-controller push-ui \
        load load-api load-controller load-ui \
        deploy deploy-namespace deploy-crds deploy-postgres \
        deploy-controller deploy-api deploy-ui \
        undeploy undeploy-ui undeploy-api undeploy-controller \
        undeploy-postgres undeploy-crds \
        status logs-api logs-controller logs-ui \
        port-forward-api port-forward-ui

# ── Development ────────────────────────────────────────────────────────────────

dev-api: ## Start inventory API + postgres via docker-compose (hot-reload)
	cd agent-inventory-api && docker-compose up

dev-ui: ## Start UI dev server on :3000 (proxies /api → localhost:8000)
	cd agent-registry-ui && npm run dev

# ── Build ──────────────────────────────────────────────────────────────────────

build: build-api build-controller build-ui ## Build all Docker images

build-api: ## Build agent-inventory-api image
	docker build --platform $(PLATFORM) -t $(API_IMG) ./agent-inventory-api

build-controller: ## Build agent-controller image
	docker build --platform $(PLATFORM) -t $(CONTROLLER_IMG) ./agent-controller

build-ui: ## Build agent-registry-ui image
	docker build --platform $(PLATFORM) -t $(UI_IMG) ./agent-registry-ui

build-example: ## Build example-agent image (must run from repo root)
	docker build --platform $(PLATFORM) -f example-agent/Dockerfile -t $(EXAMPLE_IMG) .

# ── Push ───────────────────────────────────────────────────────────────────────

push: push-api push-controller push-ui ## Push all images to registry

push-api: ## Push agent-inventory-api
	docker push $(API_IMG)

push-controller: ## Push agent-controller
	docker push $(CONTROLLER_IMG)

push-ui: ## Push agent-registry-ui
	docker push $(UI_IMG)

# ── Load (local kind cluster) ──────────────────────────────────────────────────

load: load-api load-controller load-ui ## Load all images into local kind cluster

load-api: ## Load agent-inventory-api into kind
	kind load docker-image $(API_IMG) --name $(KIND_CLUSTER)

load-controller: ## Load agent-controller into kind
	kind load docker-image $(CONTROLLER_IMG) --name $(KIND_CLUSTER)

load-ui: ## Load agent-registry-ui into kind
	kind load docker-image $(UI_IMG) --name $(KIND_CLUSTER)

# ── Deploy ─────────────────────────────────────────────────────────────────────

deploy: deploy-namespace deploy-crds deploy-postgres deploy-controller deploy-api deploy-ui ## Deploy all components to Kubernetes

deploy-namespace: ## Create agent-system namespace
	kubectl apply -f agent-controller/config/rbac/namespace.yaml

deploy-crds: ## Install Agent CRDs
	kubectl apply -f agent-controller/config/crd/bases/

deploy-postgres: ## Deploy PostgreSQL and wait until ready
	kubectl apply -f agent-inventory-api/config/postgres/
	kubectl -n $(NAMESPACE) rollout status deployment/postgres --timeout=120s

deploy-controller: ## Deploy agent-controller (RBAC + manager)
	kubectl apply -f agent-controller/config/rbac/
	kubectl apply -f agent-controller/config/manager/
	kubectl -n $(NAMESPACE) rollout status deployment/agent-controller --timeout=60s

deploy-api: ## Deploy agent-inventory-api (runs migrations via initContainer)
	kubectl apply -f agent-inventory-api/config/api/
	kubectl -n $(NAMESPACE) rollout status deployment/agent-inventory-api --timeout=120s

deploy-ui: ## Deploy agent-registry-ui
	kubectl apply -f agent-registry-ui/config/
	kubectl -n $(NAMESPACE) rollout status deployment/agent-registry-ui --timeout=60s

redeploy-ui: build-ui ## Rebuild image and restart agent-registry-ui pod
	kubectl -n $(NAMESPACE) rollout restart deployment/agent-registry-ui
	kubectl -n $(NAMESPACE) rollout status deployment/agent-registry-ui --timeout=60s

# ── Undeploy ───────────────────────────────────────────────────────────────────

undeploy: undeploy-ui undeploy-api undeploy-controller undeploy-postgres undeploy-crds ## Remove all components from Kubernetes

undeploy-ui: ## Remove agent-registry-ui
	kubectl delete -f agent-registry-ui/config/ --ignore-not-found=true

undeploy-api: ## Remove agent-inventory-api
	kubectl delete -f agent-inventory-api/config/api/ --ignore-not-found=true

undeploy-controller: ## Remove agent-controller
	kubectl delete -f agent-controller/config/manager/ --ignore-not-found=true
	kubectl delete -f agent-controller/config/rbac/ --ignore-not-found=true

undeploy-postgres: ## Remove PostgreSQL
	kubectl delete -f agent-inventory-api/config/postgres/ --ignore-not-found=true

undeploy-crds: ## Remove Agent CRDs (deletes all Agent custom resources)
	kubectl delete -f agent-controller/config/crd/bases/ --ignore-not-found=true

# ── Observe ────────────────────────────────────────────────────────────────────

status: ## Show pods, services, and deployments in agent-system
	kubectl -n $(NAMESPACE) get pods,services,deployments -o wide

logs-api: ## Stream agent-inventory-api logs
	kubectl -n $(NAMESPACE) logs -l app.kubernetes.io/name=agent-inventory-api --follow --tail=100

logs-controller: ## Stream agent-controller logs
	kubectl -n $(NAMESPACE) logs -l app.kubernetes.io/name=agent-controller --follow --tail=100

logs-ui: ## Stream agent-registry-ui logs
	kubectl -n $(NAMESPACE) logs -l app.kubernetes.io/name=agent-registry-ui --follow --tail=100

port-forward-api: ## Forward localhost:8000 → agent-inventory-api service
	kubectl -n $(NAMESPACE) port-forward svc/agent-inventory-api 8000:8000

port-forward-ui: ## Forward localhost:3000 → agent-registry-ui service
	kubectl -n $(NAMESPACE) port-forward svc/agent-registry-ui 3000:80

# ── Help ───────────────────────────────────────────────────────────────────────

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
