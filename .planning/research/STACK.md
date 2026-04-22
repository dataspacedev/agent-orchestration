# Stack Research

**Domain:** Kubernetes-native AI agent orchestration platform — federated agent stack v2
**Researched:** 2026-04-21
**Confidence:** MEDIUM-HIGH (based on well-established Go/Python k8s ecosystem knowledge; not verified against live Context7 docs due to researcher rate limit)

---

## New Stack Additions Required

### Go (agent-controller + skill-resolver sidecar)

| Library | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| `github.com/Masterminds/semver/v3` | v3.3.x | Semver constraint parsing (`^`, `~`, `>=`, range) in AgentStackReconciler | De-facto standard; used in Helm and controller-runtime ecosystem |
| `github.com/lestrrat-go/jwx/v2` | v2.1.x | OIDC JWKS token validation (offline, cached) in platform agents (Go) | Mature, widely used; supports JWKS auto-refresh, `exp` claim caching |
| `sigs.k8s.io/controller-runtime/pkg/client` | v0.19.0 (already in use) | In-cluster k8s informer for skill-resolver sidecar binary | No new dependency — reuse existing version |
| `k8s.io/client-go` | v0.31.x (already in use) | Informer factory for skill-resolver standalone binary | Already transitive dependency |

**skill-resolver sidecar implementation:** standalone Go binary (NOT part of the controller binary). Separate `go.mod` under `skill-resolver/`. Uses `k8s.io/client-go` informer factory with in-cluster config. Does not need controller-runtime's reconcile loop — it's a read-only informer + HTTP server.

**No new Go libs needed** for new CRD types (all Go type additions use existing `controller-gen` and `controller-runtime`).

### Python (core-tools-lib, task-store, registry-announcer, platform agents)

| Library | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| `python-jose[cryptography]` or `PyJWT` | PyJWT>=2.8 | OIDC SA token validation (JWKS) in platform agents | PyJWT is lighter; python-jose has wider JWKS support |
| `limits` | >=3.13 | Per-stack rate limiting in `StackIsolationMiddleware` | FastAPI-compatible async rate limiting; supports in-memory moving window |
| `asyncpg` | >=0.30 (already in inventory-api) | task-store Postgres connections via PgBouncer | Reuse existing version; confirm same `asyncpg` ver in task-store pyproject.toml |
| `tenacity` | >=8.5 | Retry logic in registry-announcer secondary write queue | Clean retry abstraction; exponential backoff with jitter |
| `kubernetes` (python k8s client) | >=31.0 | registry-announcer CRD writes (AgentDirectory patch) | Standard Python k8s client for in-cluster CRD operations |
| `httpx` | >=0.27 (likely already in core-tools-lib) | `A2AClient` HTTP calls with SA token | Async-native, already used in ecosystem |

**Rate limiter backend decision:** Use in-process token bucket (`limits` library) for v1.0. At 2+ platform agent replicas, this gives per-replica limits — acceptable for the initial quota model. Document this tradeoff in ClusterAgentPolicy; defer Redis-backed cluster-wide limiting to P7 hardening. Adding `PLATFORM_RATE_LIMITER_BACKEND=redis` env var support can be added in P7 without breaking P4 deployments.

**OIDC JWKS validation approach:** Platform agents fetch the cluster OIDC JWKS endpoint once at startup, cache verified tokens by `exp` claim. Avoid `TokenReview` API calls on the hot path — 5ms latency per call adds up at scale. JWKS URL is injected via env var `K8S_OIDC_JWKS_URL` set by the controller from ClusterAgentPolicy.

### Infrastructure (not libraries — deployment requirements)

| Component | What's Needed | Notes |
|-----------|--------------|-------|
| PgBouncer | Sidecar container alongside task-store Postgres | Session pooling; 10 connections to Postgres from PgBouncer; agents connect to PgBouncer |
| Postgres (dedicated) | Separate instance from inventory-api | task-store must NOT share inventory-api's Postgres |
| ClusterRole + ClusterRoleBinding | k8s RBAC for skill-resolver SA | `agentdirectories`, `agentaccesspolicies`, `agentrubrics` get/list/watch |

---

## What NOT to Add

| Temptation | Why to Avoid |
|-----------|--------------|
| Admission webhooks for `AgentAccessPolicy` enforcement | Webhooks reject resource creation, not call-time access. skill-resolver sidecar is the correct enforcement point. Webhooks add a webhook server to operate. |
| Redis in P1-P6 | Over-engineering for initial platform scale. In-process rate limiting is sufficient until P7 hardening. |
| gRPC for skill-resolver API | HTTP is simpler, debuggable with curl, and sufficient for localhost latency. gRPC adds protobuf schema maintenance. |
| Service mesh (Istio/Linkerd) | The design explicitly handles auth, routing, and observability via k8s-native CRDs and sidecars. A service mesh would duplicate these concerns. |
| CRD validation webhooks (beyond defaulting) | controller-gen kubebuilder validation markers cover structural validation. Defaulting webhooks may be useful for ClusterAgentPolicy propagation but are not required in v1.0. |

---

## Integration With Existing Stack

- **controller-runtime v0.19.0**: All new reconcilers use the existing manager. New CRD types register via the existing `SchemeBuilder`. No version change required.
- **FastAPI + asyncpg**: task-store reuses the same pattern as inventory-api. Can copy the `docker-compose.yml` + Alembic setup from inventory-api.
- **FastMCP**: MCP aggregator uses FastMCP from core-tools-lib. The aggregator is a FastMCP server that proxies tools from discovered agents — not a novel framework choice.
- **a2a-sdk**: `TaskStoreClient` must implement the a2a-sdk `TaskStore` abstract protocol exactly. Verify method signatures from the installed package before implementing.

---

## Sources

- docs/federated-agent-stack.md — architecture decisions (authoritative)
- agent-controller go.mod — confirmed controller-runtime v0.19.0, k8s 1.31 in use
- agent-inventory-api pyproject.toml — confirmed asyncpg, FastAPI, SQLAlchemy in use
- core-tools-lib pyproject.toml — confirmed FastMCP, httpx in dependency tree
- General ecosystem knowledge: Masterminds/semver standard in Go; PyJWT for OIDC; limits library for FastAPI rate limiting
