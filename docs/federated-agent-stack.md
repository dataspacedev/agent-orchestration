# Federated Agent Stack — Refined Architecture (v2)

**Date:** 2026-04-21  
**Status:** Draft — supersedes federated-agent-stack.md  
**Context:** Produced by applying principal-architect critique to v1 design.

---

## 1. Refined Architecture Overview

The v1 design had the right goal but introduced three structural problems: it made the
k8s controller dependent on a Python API at runtime, collapsed too many concerns into
a single CRD, and deferred auth and versioning until after federation was live. This
revision fixes all three.

The core shift: **separate the management plane from the runtime plane**, and treat
every concern (deployment, routing, observability, auth, access control) as an
independently composable resource rather than fields on a God Object CRD.

```
┌─────────────────────────────────────────────────────────────────────┐
│ Management Plane                                                      │
│                                                                       │
│  inventory-api ──────── AgentDirectory CR ◄── registry-announcer    │
│  (CRUD, admin,           (k8s-native,          sidecar              │
│   outbox sync)            skill→URL map,                             │
│                           watched by controller                      │
│                           and skill-resolver sidecar)                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ k8s watch (no HTTP)
┌────────────────────────────────▼────────────────────────────────────┐
│ Controller Plane                                                      │
│                                                                       │
│  agent-controller                                                     │
│  ├── AgentReconciler       → Deployment, Service, SA, HPA, ConfigMap │
│  ├── AgentStackReconciler  → AgentDirectory, NetworkPolicy,          │
│  │                           MCP aggregator Deployment               │
│  ├── AgentPolicyReconciler → injects ClusterAgentPolicy defaults     │
│  └── AgentAccessReconciler → enforces AgentAccessPolicy RBAC         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ reconciles
┌────────────────────────────────▼────────────────────────────────────┐
│ Runtime Plane                                                         │
│                                                                       │
│  Agent pod                                                            │
│  ├── agent container          (A2A + MCP, AgentExecutor)             │
│  ├── registry-announcer       (card → AgentDirectory + inventory-api)│
│  └── skill-resolver           (watches AgentDirectory, serves        │
│                                localhost skill→URL queries)           │
│                                                                       │
│  task-store service           (dedicated Postgres, shared by agents, │
│                                not shared with inventory-api DB)      │
│                                                                       │
│  MCP aggregator pod           (watches AgentDirectory, proxies       │
│                                tools/call, versioned tool registry)  │
└─────────────────────────────────────────────────────────────────────┘
```

**What is now different from v1:**

| Concern | v1 | v2 |
|---|---|---|
| Peer URL resolution | Controller calls inventory API at reconcile | Controller reads `AgentDirectory` CR (k8s-native) |
| Skill injection | Env vars baked into pod at start | `skill-resolver` sidecar, dynamic watch |
| Stack config | All fields on `AgentStack` | Composable: `AgentStack` + `AgentPolicy` + `AgentRoute` + `AgentAccessPolicy` |
| Task DB | Shared with inventory-api DB | Dedicated `task-store` service |
| Auth | Optional, deferred to P6 | Mandatory SA token, enforced from P2 |
| Platform agent versioning | None | Semver constraints on `peerStacks` capabilities |
| Agent behavior config | Injected via `EvaluationPolicy` | Separate `AgentRubric` CR |
| MCP aggregator updates | Undefined | Watches `AgentDirectory` CRD, push-driven |
| Multi-tenancy | None | `X-Stack-Id` + per-stack quota on platform agents |

---

## 2. Top Architectural Changes

### Change 1 — Introduce `AgentDirectory` as the runtime-authoritative skill map

**What is changing:**  
The controller no longer calls the inventory API during reconciliation. A new k8s CRD
— `AgentDirectory` — is introduced as the in-cluster, k8s-native source of truth for
skill→URL mappings. The registry-announcer sidecar writes to both the inventory API
(management plane) and the `AgentDirectory` CR (runtime plane). The controller and the
`skill-resolver` sidecar read exclusively from `AgentDirectory`.

```go
// AgentDirectory is a namespace-scoped CR maintained by registry-announcer.
// The controller watches it via informer — no HTTP calls during reconciliation.
type AgentDirectorySpec struct {
    Entries []AgentDirectoryEntry `json:"entries"`
}

type AgentDirectoryEntry struct {
    AgentName string   `json:"agentName"`
    Version   string   `json:"version"`
    URL       string   `json:"url"`           // derived: <name>.<ns>.svc.cluster.local:<port>
    Skills    []string `json:"skills"`
    Tags      []string `json:"tags"`
    CardHash  string   `json:"cardHash"`      // SHA256 of AgentCard JSON; staleness detection
    ReadyAt   string   `json:"readyAt"`
}
```

**Critique addressed:** Controller coupled to inventory API at reconciliation time.

**Why it's better:**  
Controllers must reconcile from k8s state only. Removing the HTTP dependency eliminates
an entire failure mode: inventory API downtime, slow queries, and schema changes can no
longer block controller reconciliation. The `AgentDirectory` CR is a pure data structure
— it's updated by the announcer and watched by consumers via the standard k8s informer
mechanism, which provides free caching, retries, and re-sync.

**Tradeoffs:**  
The announcer must now write to two places (inventory API + `AgentDirectory`). A write
failure to one creates temporary divergence. Mitigate: the announcer treats the
`AgentDirectory` write as the primary (blocks pod Ready gate); the inventory API write
is best-effort with a background retry queue. Divergence is observable via a controller
condition `DirectoryInSync`.

---

### Change 2 — Replace env-var skill injection with a `skill-resolver` sidecar

**What is changing:**  
`PEER_<SKILL>_URL` env vars injected at pod start are removed. Every orchestrator pod
gets a `skill-resolver` sidecar container (injected by the controller). It watches the
`AgentDirectory` CRD via an informer and maintains an in-process skill→URL cache. The
orchestrator calls `http://localhost:2020/resolve?skill=parse_document` to get a live
URL before making an A2A call.

```
skill-resolver sidecar
  GET /resolve?skill=parse_document&minVersion=1.0&stackId=legal-stack
  → 200 {"url": "http://document-intelligence.agent-platform.svc:8080",
          "version": "1.2.0", "skills": ["parse_document", "extract_entities"]}

  GET /resolve?skill=parse_document&stackId=legal-stack
  → 503 {"error": "no agent satisfying skill=parse_document and minVersion=1.0 is Ready"}
```

The sidecar also enforces `AgentAccessPolicy` — if the calling stack is not permitted to
use a skill, it returns 403 before any network call is made.

**Critique addressed:** Env-var skill injection is static; adding skill dependencies
requires pod restarts. Baked-in URLs break the moment platform agents are updated.

**Why it's better:**  
Dynamic resolution means skill availability changes (agent rolling update, version
upgrade, new agent registered) are reflected within the informer re-sync window (~1s)
without restarting any dependent pod. It also creates a single chokepoint for access
control enforcement, rate limit pre-flight checks, and observability of which stacks
are calling which skills.

**Tradeoffs:**  
Adds a sidecar to every orchestrator pod (memory ~30MB). Introduces a localhost network
hop on every skill resolution. Mitigate: the sidecar caches results in-process; the hot
path is a hashmap lookup, not a network call. Pod startup has a brief window where the
sidecar is initializing — the orchestrator container should use an init container
readiness check against `localhost:2020/health`.

---

### Change 3 — Decompose `AgentStack` into composable resources

**What is changing:**  
The God Object `AgentStack` CRD is split into four focused resources:

```
AgentStack          — membership and topology (who is in the stack, what roles)
AgentPolicy         — observability, defaults, auth mode (namespace-scoped; inherits from ClusterAgentPolicy)
AgentRoute          — routing and load balancing per skill pool
AgentAccessPolicy   — which stacks may call which skills; auth escalation grants
```

`AgentStack` becomes minimal:

```yaml
apiVersion: agents.orchestration.io/v1alpha1
kind: AgentStack
metadata:
  name: legal-stack
  namespace: agent-legal
spec:
  agents:
    - name: legal-intake
      role: orchestrator
      agentRef:
        name: legal-intake-agent
        version: "^1.0"           # semver constraint
  peerStacks:
    - namespace: agent-platform
      capabilities:
        - skill: parse_document
          minVersion: "1.0"
        - skill: semantic_search
          minVersion: "2.0"
        - skill: classify_risk
          minVersion: "1.0"
  mcp:
    aggregated: true
```

Observability and auth come from the namespace policy, not the stack spec:

```yaml
apiVersion: agents.orchestration.io/v1alpha1
kind: AgentPolicy                 # namespace-scoped; inherits ClusterAgentPolicy
metadata:
  name: default
  namespace: agent-legal
spec:
  tracing:
    samplingRate: 1.0             # override cluster default of 0.1
  eval:
    policyRef: legal-stack-evals
  # auth: inherited from ClusterAgentPolicy — not duplicated here
```

```yaml
apiVersion: agents.orchestration.io/v1alpha1
kind: ClusterAgentPolicy          # cluster-scoped; one per cluster
metadata:
  name: default
spec:
  tracing:
    endpoint: http://otel-collector.observability.svc:4317
    samplingRate: 0.1
  auth:
    mode: serviceAccountToken     # sa-token | mtls | none (none disallowed in prod)
    tokenAudience: agents.orchestration.io
  resilience:
    defaultTimeoutSeconds: 30
    maxRetries: 3
    backoffMultiplier: 2.0
```

**Critique addressed:** `AgentStack` is a God Object CRD; changing OTEL endpoint
cluster-wide requires touching every stack.

**Why it's better:**  
Changing the cluster OTEL endpoint is a one-line patch to `ClusterAgentPolicy`. A
namespace team can override sampling rate for their namespace without touching the stack
spec. Auth mode is cluster-governed, not per-team choice. Routing policy is independently
evolvable from deployment topology. Each resource has a clear owner: platform team owns
`ClusterAgentPolicy`; namespace teams own `AgentPolicy`; platform team owns `AgentRoute`
for platform skills.

**Tradeoffs:**  
More CRD types increases the learning surface for new teams. Mitigate: provide a
`helm install agent-stack` that generates all four resources from a single values file.
Teams interact with the helm values; platform engineers interact with the raw CRDs.

---

### Change 4 — Separate management plane from runtime discovery plane

**What is changing:**  
The inventory API retains its management-plane role (agent CRUD, outbox-to-CRD sync,
admin queries, audit logging) but is removed from all runtime hot paths. Runtime skill
discovery uses the `AgentDirectory` CRD exclusively. A read-through cache layer is
added in front of the inventory API's Postgres for admin queries; this does not affect
the runtime path.

```
Management plane (inventory-api):        Runtime plane (AgentDirectory CRD):
  POST /agents       (register)            Written by: registry-announcer sidecar
  GET  /agents       (admin query)         Read by:    skill-resolver sidecar
  PATCH /agents/:id  (update)                          AgentStack controller
  DELETE /agents/:id (deregister)                      MCP aggregator
  GET  /agents/audit (compliance)
```

The outbox processor continues to sync `Agent` CRs to the controller. The
`AgentDirectory` CR is the controller's read path, not the inventory API.

**Critique addressed:** Inventory API serves three incompatible operational profiles
(management CRUD, runtime skill queries, controller resolution) in one service.

**Why it's better:**  
The inventory API can be taken down for maintenance, schema migrations, or slowdowns
without impacting any running agent. The `AgentDirectory` CRD is purely in etcd — it
has the same availability guarantees as the k8s API server. Runtime task routing never
leaves the cluster's control plane.

**Tradeoffs:**  
Two systems must stay in sync (inventory API Postgres and `AgentDirectory` CR). The
announcer is the bridge — its reliability is now critical. Add a reconciliation loop in
the `AgentStack` controller that periodically compares `AgentDirectory` entries against
running `Agent` CRs and flags divergence as a condition.

---

### Change 5 — Mandatory auth from P2; `AgentAccessPolicy` for escalation

**What is changing:**  
Authentication is not optional. The `ClusterAgentPolicy` sets `auth.mode:
serviceAccountToken` as the cluster default. Every A2A call from an orchestrator
carries the calling pod's service account token as `Authorization: Bearer <sa-token>`.
Platform agents validate it via the k8s `TokenReview` API (or a local JWKS cache of
cluster OIDC keys — preferred for latency). Unauthenticated calls receive 401.

A new `AgentAccessPolicy` resource governs cross-stack and escalation permissions:

```yaml
apiVersion: agents.orchestration.io/v1alpha1
kind: AgentAccessPolicy
metadata:
  name: legal-stack-access
  namespace: agent-platform    # lives in the target namespace
spec:
  rules:
    - from:
        stackNamespace: agent-legal
        stackName: legal-stack
      allow:
        skills: [parse_document, semantic_search, classify_risk,
                 generate_structured_report, store_memory]
    - from:
        stackNamespace: agent-legal
        stackName: legal-stack
      allow:
        skills: [create_ticket]     # action-executor — explicit grant
        requireAnnotation: "agents.orchestration.io/escalation-approved=true"
```

`action-executor` requires an explicit `AgentAccessPolicy` grant with an approval
annotation. No domain stack can call it by default. The platform team reviews and
applies the annotation after confirming the use case.

**Critique addressed:** Auth deferred to P6, after federation is live with action-executor
accessible unauthenticated. No governance on who can call privileged skills.

**Why it's better:**  
Auth is structurally enforced at the platform layer — it cannot be forgotten or skipped
by a domain team. The `AgentAccessPolicy` creates an explicit, auditable record of every
cross-stack permission grant. The approval annotation provides a governance checkpoint
without requiring a separate review system.

**Tradeoffs:**  
`TokenReview` API calls add latency (~5ms on a warm k8s API server). Mitigate: platform
agents cache validated tokens for their TTL using the `exp` claim. For high-throughput
paths, use a local OIDC JWKS verification instead of `TokenReview`.

---

### Change 6 — Semver version contracts on platform agent capabilities

**What is changing:**  
`agentRef` becomes a structured reference with a semver constraint, not a `name:version`
string. `peerStacks` capabilities include `minVersion` and optionally `maxVersion`.
Platform agents expose their version in the `AgentCard` `version` field (already in the
A2A spec). The `AgentStack` controller validates version constraints against the live
`AgentDirectory` before marking the stack Ready.

```yaml
# agentRef — structured, not a string
agentRef:
  name: document-intelligence-agent
  version: "^1.0"          # semver: >=1.0.0 <2.0.0

# peerStacks capability with version constraint
peerStacks:
  - namespace: agent-platform
    capabilities:
      - skill: parse_document
        minVersion: "1.0"
        maxVersion: "1.x"  # will not auto-upgrade to 2.0 (breaking change)
```

Platform agents maintain `/v1` and `/v2` deployments in parallel during major version
transitions (minimum 30-day window). The controller emits a `CapabilityVersionWarning`
condition when a stack's declared constraint is satisfied by a deprecated version.

**Critique addressed:** Platform agent upgrades have no version contract; breaking
changes silently affect all domain stacks.

**Why it's better:**  
Domain teams control when they take breaking platform changes. The platform team can
ship new major versions without coordinating with every consumer simultaneously. The
`AgentDirectory` entry includes the deployed version, so the controller can validate
constraints before a stack goes live — not after a production incident.

**Tradeoffs:**  
Running parallel versions of platform agents increases resource usage during transitions.
Platform team must commit to a documented deprecation window per major version. Define
this in a published platform SLA document.

---

### Change 7 — Multi-tenancy isolation on platform agents

**What is changing:**  
Every cross-stack A2A call and MCP `tools/call` carries an `X-Stack-Id` header (injected
by the `skill-resolver` sidecar). Platform agents enforce per-stack rate limits and
resource quotas via middleware. k8s `ResourceQuota` limits total CPU/memory consumed by
agents in platform-calling namespaces. `PriorityClass` differentiates prod from non-prod
stacks on the platform scheduler.

```python
# Platform agent middleware (injected by core-tools-lib when PLATFORM_AGENT=true)
class StackIsolationMiddleware:
    async def __call__(self, request, call_next):
        stack_id = request.headers.get("X-Stack-Id")
        if not stack_id:
            return Response(status_code=400, content="X-Stack-Id required")
        if not await self.rate_limiter.check(stack_id):
            return Response(status_code=429)
        response = await call_next(request)
        await self.audit_log.record(stack_id, request, response.status_code)
        return response
```

Audit logging (stack-id, skill called, task-id, timestamp, response code) is written to
a centralized audit store for compliance — this is mandatory for regulated domains.

**Critique addressed:** Platform stack has no multi-tenancy isolation; noisy-neighbor
degrades all domains; no audit trail for regulated data.

**Why it's better:**  
A runaway domain stack cannot take down platform agents for others. Regulated domains
(clinical, legal) have an auditable record of every capability call. Rate limiting is
enforceable without modifying any domain agent code.

**Tradeoffs:**  
Requires platform agents to include the isolation middleware. The `core-tools-lib`
`create_agent_app()` function can inject it automatically when an env var
`PLATFORM_AGENT=true` is set by the controller — no manual wiring per agent.

---

### Change 8 — Dedicated `task-store` service; separate from inventory-api DB

**What is changing:**  
Task state (A2A task records, context history, memory-context agent state) moves to a
dedicated `task-store` service with its own Postgres instance and a PgBouncer connection
proxy. The inventory API's Postgres is strictly management-plane data (agent registry,
outbox, audit). Agents connect to the task store via a `TaskStoreClient` in
`core-tools-lib`, with the connection string injected by the controller.

```python
def create_agent_app(
    config: AgentConfig,
    executor: AgentExecutor,
    mcp_server: FastMCP | None = None,
    task_store: TaskStore | None = None,
    # controller injects TASK_STORE_URL env var; SDK picks it up automatically
) -> FastAPI:
    store = task_store or TaskStore.from_env()   # reads TASK_STORE_URL
```

The `task-store` service is a thin FastAPI/Postgres service that implements the A2A
`TaskStore` interface over HTTP — agents call it rather than connecting directly to
Postgres. This means connection pooling is centralized, and the DB is not exposed to
agent pods directly.

**Critique addressed:** Task store shares the inventory API's DB, creating schema
coupling and connection pool exhaustion at scale.

**Why it's better:**  
Independent scaling — the task store can be provisioned with a larger Postgres instance
and read replicas for high-throughput agent deployments without touching the inventory
API. Schema migrations on task state do not risk the agent registry. At 50 agents, 50
direct Postgres connections become 50 connections to PgBouncer which maintains a pool
of 10 to Postgres.

**Tradeoffs:**  
Adds a new service to operate. The task-store service is now a critical dependency for
all agent task lifecycle operations. It must have its own SLO, HA deployment (2+
replicas), and backup strategy.

---

### Change 9 — Separate `AgentRubric` from `EvaluationPolicy`

**What is changing:**  
`EvaluationPolicy` handles post-hoc scoring only (eval platform, sampling rate,
scorers). A new `AgentRubric` CR handles runtime behavioral configuration for platform
agents like `risk-classifier`:

```yaml
apiVersion: agents.orchestration.io/v1alpha1
kind: AgentRubric
metadata:
  name: legal-risk-rubric
  namespace: agent-legal
spec:
  targetSkill: classify_risk
  config:
    high_risk_patterns:
      - "indemnification without cap"
      - "perpetual license grant"
    jurisdiction: "us-gdpr"
    output_schema: "legal-risk-v1"
```

The `skill-resolver` sidecar attaches the active `AgentRubric` config as a header
(`X-Agent-Rubric`) on A2A calls to the platform `risk-classifier`. The platform agent
reads the rubric from the header and applies it for that request. This is per-request
behavioral configuration — it does not require redeploying the platform agent.

**Critique addressed:** `EvaluationPolicy` conflates runtime behavior (what to classify
as risky) with post-hoc scoring (was the classification correct).

**Why it's better:**  
Domain teams can change their risk rubric by patching an `AgentRubric` CR — no
redeployment, no eval config change. The evaluation system can compare output against
the rubric that was active at time of inference (stored in the task trace), enabling
accurate retrospective scoring. The concerns are now cleanly separated: rubric drives
behavior; eval policy judges it.

**Tradeoffs:**  
Platform agents must be designed to accept rubric config per-request rather than at
startup. This is a more complex implementation than static config, but it is the only
design that scales to many domain teams with divergent rubric needs without deploying
N copies of the same platform agent.

---

## 3. Platform Capabilities That Should Exist

These are not agent business logic — they are platform infrastructure that every agent
and every stack consumes. They should be owned by the platform team and not
reimplemented per domain.

| Capability | Implementation | Owner |
|---|---|---|
| **AgentDirectory** | k8s CRD, written by registry-announcer | Platform controller team |
| **skill-resolver sidecar** | Go binary, injected by controller, watches AgentDirectory | Platform controller team |
| **registry-announcer sidecar** | Python, polls card, writes to AgentDirectory + inventory API | Platform controller team |
| **task-store service** | FastAPI + Postgres + PgBouncer, A2A TaskStore HTTP interface | Platform data team |
| **MCP aggregator** | FastMCP proxy image, watches AgentDirectory for tool refresh | Platform tools team |
| **ClusterAgentPolicy** | CRD + reconciler; governs auth mode, OTEL, resilience defaults | Platform team |
| **AgentAccessPolicy** | CRD + reconciler; enforces cross-stack permissions | Security/platform team |
| **StackIsolationMiddleware** | Python middleware in core-tools-lib, injected via PLATFORM_AGENT env | Platform SDK team |
| **A2AClient** | Python client in core-tools-lib, SA token injection, retry/circuit breaker | Platform SDK team |
| **AgentRubric** | CRD; attached to requests by skill-resolver | Platform controller team |

### Platform SDK (`core-tools-lib`) surface

```python
# What domain teams actually import — everything else is injected
from core_tools import (
    AgentConfig,        # name, version, skills, auth declaration
    AgentExecutor,      # base class — implement execute() and cancel()
    create_agent_app,   # wires A2A + MCP + platform middleware
    TaskUpdater,        # updates task state in task-store
    A2AClient,          # calls peer agents with auth, retry, circuit breaker
    AgentRubric,        # reads active rubric config from request context
)
```

Everything else — OTEL instrumentation, SA token injection, `X-Stack-Id` propagation,
skill resolution, rate limit enforcement — happens automatically via middleware injected
by `create_agent_app()` based on env vars set by the controller. Domain teams do not
configure platform concerns; they configure domain logic.

---

## 4. Updated Boundaries and Responsibilities

### Platform team owns
- `agent-controller` and all CRD types
- `ClusterAgentPolicy` instance (cluster-wide defaults)
- Platform stack deployment in `agent-platform` namespace
- `task-store` service
- `core-tools-lib` (platform SDK)
- `AgentDirectory` CRD schema and reconciliation
- RBAC: only platform team can write to `agent-platform` namespace

### Domain team owns
- Their namespace (`agent-legal`, `agent-financial`, etc.)
- `AgentStack` CR (membership + topology)
- `AgentPolicy` CR (namespace-level observability overrides)
- `AgentRubric` CRs (domain-specific behavioral config)
- `EvaluationPolicy` CR (domain-specific scoring rubrics)
- `AgentAccessPolicy` grant requests (submitted as PRs, approved by platform team)
- Their own agent images

### Platform team approves
- `AgentAccessPolicy` grants for `action-executor` and any new privileged skills
- Agent promotions from domain to platform tier (via `AgentPromotion` PR process)
- Changes to `ClusterAgentPolicy` (affects all stacks)
- New platform agent versions with breaking changes

### Governance: Agent Promotion Process

A domain agent graduates to the platform tier via a documented process:
1. Domain team opens a PR adding the agent to `agent-platform/platform-stack`
2. PR requires: versioned API contract, integration test suite, SLO declaration,
   on-call runbook, and compatibility with `StackIsolationMiddleware`
3. Platform team reviews and approves
4. Agent runs in platform namespace with platform team as on-call owner
5. Domain team retains domain-specific configuration via `AgentRubric`

---

## 5. Scalability and Operational Improvements

### Resilience defaults via `ClusterAgentPolicy`

Every A2A call made through `A2AClient` respects the `ClusterAgentPolicy` resilience
defaults unless overridden by the domain team's `AgentPolicy`. This eliminates the
fragmented retry/timeout implementations that will emerge if each team writes their own:

```yaml
resilience:
  defaultTimeoutSeconds: 30
  maxRetries: 3
  backoffMultiplier: 2.0
  circuitBreaker:
    failureThreshold: 5
    halfOpenAfterSeconds: 30
```

Platform agents can advertise their own timeout requirements via the `AgentCard`
`metadata` field; `A2AClient` reads and applies this automatically.

### Platform stack SLO

The platform stack must publish a formal SLO before any regulated domain depends on it.
Minimum:

| Agent | Availability | p99 Latency | On-call |
|---|---|---|---|
| document-intelligence | 99.9% | 2s | Platform team |
| search-retrieval | 99.9% | 500ms | Platform team |
| action-executor | 99.5% | 5s | Platform team + security |
| memory-context | 99.9% | 100ms | Platform data team |

Domain stacks should degrade gracefully when platform agents are below SLO — the
`skill-resolver` sidecar returns a 503 with `Retry-After` rather than hanging. Domain
orchestrators must handle 503 from the resolver as a degraded-mode signal, not a fatal
error.

### AgentDirectory consistency monitoring

A controller `ClusterAgentDirectoryHealthCheck` runs on a 60s interval, comparing:
- Active `Agent` CRs with a Ready condition
- Corresponding entries in `AgentDirectory`
- Corresponding entries in the inventory API

Divergence triggers a `DirectoryDriftDetected` event and a Prometheus counter. An
alert fires if drift exceeds 5 minutes.

### MCP aggregator consistency

The aggregator watches the `AgentDirectory` CRD via a k8s informer. On add/update
events it rebuilds its tool proxy registry. In-flight `tools/call` requests complete
against the old registry; new requests use the updated one (generation-based swap). Tool
names include the agent version (`web_searcher_v1__search`) so LLM clients can detect
when a tool schema changes between calls.

---

## 6. Migration Plan

The migration is designed to be incremental: each phase is independently deployable and
does not break the phase before it.

### P1 — Runtime foundation (no user-visible changes)
- Deploy `task-store` service + Postgres; migrate `InMemoryTaskStore` to it in `core-tools-lib`
- Add `AgentDirectory` CRD to controller; registry-announcer writes to it (inventory API write unchanged)
- Add `ClusterAgentPolicy` CRD with cluster defaults (OTEL endpoint, resilience)
- Add skill-indexed query to inventory API (additive; no breaking change)

### P2 — Auth mandatory
- `ClusterAgentPolicy` sets `auth.mode: serviceAccountToken`
- `core-tools-lib` `A2AClient` injects SA token on all calls
- Platform agents validate tokens via k8s OIDC JWKS (local, cached)
- All existing agents in `agent-system` namespace get NetworkPolicy that requires auth
- `AgentAccessPolicy` CRD available; no grants required yet (platform stack not live)

### P3 — Skill-resolver sidecar + composable CRDs
- Controller injects `skill-resolver` sidecar into orchestrator pods
- `AgentStack` CRD updated to minimal spec (membership only)
- `AgentPolicy` and `AgentRoute` CRDs added
- Existing `AgentStack` CRs migrated via a one-time conversion webhook (old fields
  become `AgentPolicy` resources in the same namespace)
- Env-var skill injection removed from controller

### P4 — Platform stack deployment
- Deploy seven platform agents into `agent-platform` namespace
- `AgentAccessPolicy` required before any domain stack can reference platform skills
- `AgentPromotion` process documented and enforced via RBAC on `agent-platform`
- `StackIsolationMiddleware` auto-injected on platform agents via `PLATFORM_AGENT=true`

### P5 — Domain stack onboarding
- Domain stacks declare `peerStacks` with semver constraints
- Controller validates constraints against `AgentDirectory` before marking stack Ready
- `AgentRubric` CRD available; domain teams configure behavioral config for platform agents
- `EvaluationPolicy` updated to remove behavior injection (eval-only)

### P6 — MCP aggregator + domain MCP surface
- MCP aggregator image deployed; watches `AgentDirectory` for tool refresh
- Stack-level MCP endpoint registered in inventory API as stack capability
- Tool versioning (`agent_v1__tool`) enforced in aggregator

### P7 — Governance and multi-tenancy hardening
- Per-stack rate limits enforced on platform agents via `StackIsolationMiddleware`
- Audit logging live for all cross-stack calls
- `AgentPromotion` PR review process tooled (GitHub Action validates required fields)
- `ClusterAgentDirectoryHealthCheck` controller reconciling drift detection
- SLO dashboards for platform agents in Grafana

---

## 7. Remaining Risks and Open Questions

**1. AgentDirectory write reliability**  
The registry-announcer is now the single writer to a critical runtime resource. If it
fails or crashes after the pod is Ready but before `AgentDirectory` is updated, the
stack's skills are temporarily unreachable. Mitigation: the announcer uses a k8s
readiness gate — the pod is not marked Ready until the `AgentDirectory` write succeeds.
Open question: what is the re-sync behavior if the announcer restarts mid-way through a
card update?

**2. Cross-cluster federation is not addressed**  
This entire design assumes a single k8s cluster. Cross-cluster federation (separate
platform and domain clusters, multi-region) requires a different discovery mechanism —
the `AgentDirectory` CRD is cluster-scoped and k8s watchers don't cross clusters.
Options: a federated registry service that aggregates multiple clusters' `AgentDirectory`
CRs, or a dedicated agent mesh gateway. This is out of scope for v2 but must be
addressed before multi-cluster deployments.

**3. `task-store` service is a new critical dependency**  
The task-store service must have 99.9% availability before any domain stack depends on
it for long-running tasks. Its own HA deployment (multi-replica with leader election for
the Postgres connection pool), backup strategy, and SLO are required before P4. This is
non-trivial operational work that is easy to underestimate.

**4. Semver constraints on platform agents may not be expressive enough**  
Semver captures API breaking changes but not behavioral changes. A platform agent that
changes its `classify_risk` output format (same schema, different scoring thresholds)
is a semantic breaking change with no version signal. Define a convention: behavioral
changes that affect downstream scoring must increment minor version and include a
changelog entry in the agent's `AgentCard.metadata`.

**5. `AgentRubric` header size on A2A requests**  
Injecting rubric config as a request header works for small configs but breaks down for
large rubric datasets (e.g., a legal clause library with hundreds of patterns). Establish
a size limit on `X-Agent-Rubric` headers (~8KB); above that, the rubric must be
referenced by a CRD name and fetched by the platform agent from the k8s API at request
time (cached per rubric generation).

**6. The inventory API audit log is not formally specified**  
For regulated domains (clinical, legal), "audit logging to a centralized audit store"
is mentioned but not specified: what format, what retention, who can query it, and how
is it protected from tampering. This needs a formal data contract before clinical or
legal stacks go into production.
