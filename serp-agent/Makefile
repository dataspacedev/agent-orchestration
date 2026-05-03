NAME              ?= serp-agent
VERSION           ?= 0.1.0
IMG               ?= $(NAME):$(VERSION)
NAMESPACE         ?= agent-system
PORT              ?= 8080
LOCAL_PORT        ?= 18081
PLATFORM          ?= linux/arm64
# Auto-detect from kubectl context; override with CLUSTER_TYPE=kind|minikube|k3d|rancher-desktop|docker-desktop
CLUSTER_TYPE      ?= $(shell kubectl config current-context 2>/dev/null | \
    python3 -c "import sys; ctx=sys.stdin.read().strip(); \
    print('kind' if ctx.startswith('kind-') else \
          'minikube' if ctx == 'minikube' else \
          'k3d' if ctx.startswith('k3d-') else \
          'rancher-desktop' if ctx == 'rancher-desktop' else \
          'docker-desktop')")
CLUSTER_NAME      ?= kind
INVENTORY_LOCAL_PORT ?= 18000

# Mirrors make_crd_name() in the inventory API: lower-case, non-alphanumeric chars → "-"
CRD_NAME  := $(shell python3 -c "import re; print(re.sub(r'[^a-z0-9]+','-','$(NAME)-$(VERSION)').strip('-'))")
AGENT_URL := http://$(CRD_NAME).$(NAMESPACE).svc.cluster.local:$(PORT)
AGENT_JSON := {"name":"$(NAME)","version":"$(VERSION)","description":"SERP scraping agent with proxy rotation, UA randomization, and human-like delays","spec":{"image":"$(IMG)","port":$(PORT),"config":{"LOG_LEVEL":"info","SERP_SEARCH_URL":"https://html.duckduckgo.com/html/?q={query}","SERP_USE_BROWSER":"false","SERP_HEADLESS":"true","SERP_TIMEOUT_MS":"30000","SERP_PROXIES":"","AGENT_URL":"$(AGENT_URL)"},"resources":{"requests":{"cpu":"200m","memory":"512Mi"},"limits":{"cpu":"1000m","memory":"1Gi"}},"scaling":{"min_replicas":1,"max_replicas":3,"target_cpu_utilization_percentage":80}}}

ifeq ($(CLUSTER_TYPE),kind)
LOAD_CMD = kind load docker-image $(IMG) --name $(CLUSTER_NAME)
else ifeq ($(CLUSTER_TYPE),minikube)
LOAD_CMD = minikube image load $(IMG)
else ifeq ($(CLUSTER_TYPE),k3d)
LOAD_CMD = k3d image import $(IMG) -c $(CLUSTER_NAME)
else ifeq ($(CLUSTER_TYPE),rancher-desktop)
LOAD_CMD = docker save $(IMG) | nerdctl --address /var/run/docker/containerd/containerd.sock --namespace k8s.io load
else ifeq ($(CLUSTER_TYPE),docker-desktop)
LOAD_CMD = @echo "Docker Desktop shares the Docker daemon; image already available to Kubernetes."
else
LOAD_CMD = $(error Unknown CLUSTER_TYPE=$(CLUSTER_TYPE). Set to kind, minikube, k3d, rancher-desktop, or docker-desktop.)
endif

.DEFAULT_GOAL := help

.PHONY: help docker-build image-load docker-push register unregister \
        deploy undeploy verify logs status port-forward

help:
	@echo "Usage: make <target> [VAR=value ...]"
	@echo ""
	@echo "Key variables (current values):"
	@echo "  NAME              = $(NAME)"
	@echo "  VERSION           = $(VERSION)"
	@echo "  IMG               = $(IMG)"
	@echo "  NAMESPACE         = $(NAMESPACE)"
	@echo "  INVENTORY_LOCAL_PORT = $(INVENTORY_LOCAL_PORT)"
	@echo "  CLUSTER_TYPE      = $(CLUSTER_TYPE)  (auto-detected; or kind|minikube|k3d|rancher-desktop|docker-desktop)"
	@echo "  LOCAL_PORT        = $(LOCAL_PORT)"
	@echo "  CRD_NAME          = $(CRD_NAME)"
	@echo ""
	@echo "Targets:"
	@echo "  docker-build   Build the container image (build context: repo root)"
	@echo "  image-load     Load image into local cluster (kind/minikube/k3d/rancher-desktop)"
	@echo "  docker-push    Push image to a registry"
	@echo "  register       Register and deploy agent via the inventory API"
	@echo "  unregister     Remove agent from the inventory API"
	@echo "  deploy         docker-build + image-load + register"
	@echo "  undeploy       unregister (controller cascades all k8s resources)"
	@echo "  verify         Wait for rollout and probe all agent endpoints"
	@echo "  logs           Tail agent pod logs"
	@echo "  status         Show agent CR, deployment, pods, and service"
	@echo "  port-forward   Forward agent service to localhost:$(LOCAL_PORT)"

# ── Image ─────────────────────────────────────────────────────────────────────

docker-build:
	docker build --platform $(PLATFORM) -f Dockerfile -t $(IMG) ..

image-load:
	$(LOAD_CMD)

docker-push:
	docker push $(IMG)

# ── Orchestrator API ──────────────────────────────────────────────────────────

register:
	@echo "Registering $(NAME) v$(VERSION)..."
	@kubectl -n $(NAMESPACE) port-forward svc/agent-inventory-api $(INVENTORY_LOCAL_PORT):8000 >/dev/null 2>&1 & \
	PF_PID=$$!; \
	sleep 2; \
	HTTP_STATUS=$$(curl -s -o /tmp/.reg-resp.json -w '%{http_code}' \
	    -X POST "http://localhost:$(INVENTORY_LOCAL_PORT)/api/v1/agents" \
	    -H "Content-Type: application/json" \
	    -d '$(AGENT_JSON)'); \
	kill $$PF_PID 2>/dev/null; \
	if [ "$$HTTP_STATUS" = "201" ]; then \
	    echo "Registered $(NAME) v$(VERSION):"; \
	    python3 -m json.tool /tmp/.reg-resp.json; \
	elif [ "$$HTTP_STATUS" = "409" ]; then \
	    echo "$(NAME) v$(VERSION) already registered (409) -- skipping."; \
	else \
	    echo "Registration failed (HTTP $$HTTP_STATUS):"; \
	    cat /tmp/.reg-resp.json; \
	    exit 1; \
	fi

unregister:
	@echo "Unregistering $(NAME) v$(VERSION)..."
	@kubectl -n $(NAMESPACE) port-forward svc/agent-inventory-api $(INVENTORY_LOCAL_PORT):8000 >/dev/null 2>&1 & \
	PF_PID=$$!; \
	sleep 2; \
	ID=$$(curl -sf "http://localhost:$(INVENTORY_LOCAL_PORT)/api/v1/agents" \
	    | python3 -c "import json,sys; \
agents=json.load(sys.stdin); \
a=next((x for x in agents if x['name']=='$(NAME)' and x['version']=='$(VERSION)'),None); \
print(a['id'] if a else '')"); \
	if [ -z "$$ID" ]; then \
	    kill $$PF_PID 2>/dev/null; \
	    echo "$(NAME) v$(VERSION) not found in inventory -- nothing to do."; \
	else \
	    curl -sf -X DELETE "http://localhost:$(INVENTORY_LOCAL_PORT)/api/v1/agents/$$ID"; \
	    kill $$PF_PID 2>/dev/null; \
	    echo "Unregistered $(NAME) v$(VERSION) (id=$$ID)."; \
	fi

# ── Lifecycle ─────────────────────────────────────────────────────────────────

deploy: docker-build image-load register

undeploy: unregister

# ── Verification ──────────────────────────────────────────────────────────────

verify:
	@echo "==> Waiting for Agent CR $(CRD_NAME) to appear in $(NAMESPACE)..."
	@until kubectl -n $(NAMESPACE) get agent $(CRD_NAME) >/dev/null 2>&1; do \
	    printf "."; sleep 3; done; echo ""
	@echo "==> Waiting for Ready condition (timeout 120s)..."
	kubectl -n $(NAMESPACE) wait agent/$(CRD_NAME) --for=condition=Ready=True --timeout=120s
	@echo "==> Waiting for Deployment rollout..."
	kubectl -n $(NAMESPACE) rollout status deployment/$(CRD_NAME) --timeout=120s
	@echo "==> Probing endpoints via port-forward on localhost:$(LOCAL_PORT)..."
	@kubectl -n $(NAMESPACE) port-forward svc/$(CRD_NAME) $(LOCAL_PORT):$(PORT) >/dev/null 2>&1 & \
	PF_PID=$$!; \
	sleep 3; \
	echo "--- GET /health ---"; \
	curl -sf http://localhost:$(LOCAL_PORT)/health | python3 -m json.tool; \
	echo "--- GET /ready ---"; \
	curl -sf http://localhost:$(LOCAL_PORT)/ready | python3 -m json.tool; \
	echo "--- GET /.well-known/agent.json ---"; \
	curl -sf http://localhost:$(LOCAL_PORT)/.well-known/agent.json | python3 -m json.tool; \
	echo "--- POST / tasks/send (search test) ---"; \
	curl -sf -X POST http://localhost:$(LOCAL_PORT)/ \
	    -H "Content-Type: application/json" \
	    -d '{"jsonrpc":"2.0","id":"1","method":"tasks/send","params":{"message":{"role":"user","parts":[{"type":"text","text":"python asyncio tutorial"}]}}}' \
	    | python3 -m json.tool; \
	kill $$PF_PID 2>/dev/null; true

# ── Kubernetes ────────────────────────────────────────────────────────────────

logs:
	kubectl -n $(NAMESPACE) logs -l "app.kubernetes.io/instance=$(CRD_NAME)" -f --max-log-requests=5

status:
	@echo "==> Agent CR"
	kubectl -n $(NAMESPACE) get agent $(CRD_NAME) -o wide
	@echo ""
	@echo "==> Pods"
	kubectl -n $(NAMESPACE) get pods -l "app.kubernetes.io/instance=$(CRD_NAME)"
	@echo ""
	@echo "==> Service"
	kubectl -n $(NAMESPACE) get svc $(CRD_NAME)

port-forward:
	kubectl -n $(NAMESPACE) port-forward svc/$(CRD_NAME) $(LOCAL_PORT):$(PORT)
