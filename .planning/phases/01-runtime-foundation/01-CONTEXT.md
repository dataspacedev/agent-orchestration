# Phase 1: Runtime Foundation - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

The runtime plane becomes operational: agents announce themselves to AgentDirectory when their pod starts, task state is durable in a dedicated task-store service, and cluster-scoped observability/resilience defaults are declared via ClusterAgentPolicy. Auth enforcement is Phase 2 — Phase 1 lays the CRD schema and reconciler scaffold only.

</domain>

<decisions>
## Implementation Decisions

### registry-announcer: delivery model
- Standalone Go binary with its own Dockerfile, in a top-level `registry-announcer/` directory
- Built and pushed as a separate image (versioned independently from the controller)
- Controller injects it as a sidecar container when building the Deployment spec in `buildDeploymentSpec()`
- Identity injected via Downward API env vars: `POD_NAME`, `POD_NAMESPACE`, `AGENT_NAME` — no runtime k8s API call for identity
- ReadinessGate mechanism: after writing AgentDirectory, announcer patches its own Pod's status with a custom PodCondition (e.g., `AgentDirectoryReady=True`); controller adds this condition to `spec.readinessGates` when building the pod template
- Fix `AutomountServiceAccountToken: ptr(false)` → `ptr(true)` in `buildDeploymentSpec()` so the sidecar can read its SA token to call the k8s API

### AgentDirectory: resource model
- One AgentDirectory CR per Agent CR (1:1), same name, same namespace
- Namespace-scoped resource (consistent with Agent CR; skill-resolver in P3 uses cluster-scoped informer to read across namespaces)
- Controller (AgentReconciler) pre-creates an empty AgentDirectory CR alongside the Deployment — CR lifecycle is controller-owned via ownerReference
- registry-announcer patches (never creates) its own AgentDirectory CR
- `cardHash` = SHA-256 of the canonical AgentCard JSON fetched from the agent's `/.well-known/agent.json` endpoint — idempotency check: announcer skips re-write if hash matches existing CR
- `readyAt` is set (or updated) by the registry-announcer after a successful write

### task-store: service layout
- New top-level `task-store/` directory, parallel to `agent-inventory-api/` and `core-tools-lib/`
- Mirrors `agent-inventory-api` structure: `app/api/v1/`, `app/db/`, `app/core/config.py`, SQLAlchemy async, alembic for migrations
- Deviations from inventory-api: no outbox processor, no k8s client dependency
- HTTP API: implements the A2A TaskStore interface endpoints only, plus `/health` (same health router pattern as core-tools-lib)
- No `/metrics` endpoint in P1 (deferred to Phase 7 when SLO dashboards are built)
- Dedicated Postgres database + PgBouncer — not shared with inventory-api
- Deployed with 2+ replicas (HA requirement per INFRA-08)
- No auth in P1: TaskStoreClient sends HTTP with no auth header; auth header injection added in P2

### ClusterAgentPolicy: P1 scope
- Full CRD schema defined now: `spec.auth` (tokenAudience, mode), `spec.otel` (endpoint, sampling), `spec.resilience` (timeoutMs, retries) — no incremental CRD migrations between phases
- AgentPolicy CRD also defined in P1 (namespace-scoped counterpart that reconciler creates/patches)
- AgentPolicyReconciler in P1 merges **OTEL and resilience fields only** into namespace AgentPolicy objects — auth fields are present in the schema but not read or merged until P2
- Reconciler trigger: watch ClusterAgentPolicy + namespace list; reconcile when either changes

### Claude's Discretion
- AgentDirectory printer columns (beyond what kubebuilder defaults provide)
- PgBouncer pool mode and connection limits for task-store
- Exact retry backoff for registry-announcer inventory-api secondary write (best-effort background queue)
- Specific resilience default values in the ClusterAgentPolicy sample manifest

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `buildDeploymentSpec()` (`agent-controller/internal/controller/agent_controller.go:158`): existing injection point for sidecar container and ReadinessGate additions
- `ptr[T any]()` helper (`agent_controller.go:452`): reuse for bool pointer fields in new CRD types
- `agent-inventory-api/app/core/config.py` + `app/db/session.py`: copy as scaffolding template for task-store service
- `core-tools-lib/src/core_tools/health.py` health router: reuse in task-store
- `a2a.server.tasks.inmemory_task_store.InMemoryTaskStore`: existing import in `create_agent_app()` — `TaskStore.from_env()` replaces the hardcoded instantiation

### Established Patterns
- CRD group: `agents.orchestration.io/v1alpha1` — all new CRDs (AgentDirectory, ClusterAgentPolicy, AgentPolicy) must use this group
- Controller-gen pipeline: `make generate` in `agent-controller/Makefile` regenerates deepcopy and CRD manifests — any new `*_types.go` file must be followed by `make generate`; CI check required (`git diff --exit-code` post-generate)
- `pydantic-settings` + `.env` file pattern (inventory-api `config.py`): use for task-store config
- SQLAlchemy async engine + `async_sessionmaker` (inventory-api `session.py`): use for task-store DB layer

### Integration Points
- `AgentReconciler.buildDeploymentSpec()`: where sidecar injection, Downward API env vars, and ReadinessGate spec are added
- `create_agent_app()` in `core-tools-lib/src/core_tools/agent.py`: hardcoded `InMemoryTaskStore()` in `DefaultRequestHandler` needs to become `TaskStore.from_env()`
- `agent-controller/api/v1alpha1/`: new `agentdirectory_types.go`, `clusterpolicy_types.go`, `agentpolicy_types.go` added here; `groupversion_info.go` registers them

</code_context>

<specifics>
## Specific Ideas

- The roadmap implementation note explicitly calls out: fix `AutomountServiceAccountToken: ptr(false)` to `ptr(true)` in `buildDeploymentSpec` for sidecar-injected pods
- Add CI check: `make generate && git diff --exit-code` blocking any PR that adds `*_types.go` without re-running controller-gen (from roadmap)
- STATE.md blocker: verify exact a2a-sdk TaskStore abstract method signatures before implementing TaskStoreClient (check `a2a.server.tasks` module)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-runtime-foundation*
*Context gathered: 2026-04-22*
