# Phase 1: Runtime Foundation - Research

**Researched:** 2026-04-22
**Domain:** Kubernetes controller-runtime (Go), Python FastAPI/SQLAlchemy, a2a-sdk 0.3.26
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**registry-announcer: delivery model**
- Standalone Go binary with its own Dockerfile, in a top-level `registry-announcer/` directory
- Built and pushed as a separate image (versioned independently from the controller)
- Controller injects it as a sidecar container when building the Deployment spec in `buildDeploymentSpec()`
- Identity injected via Downward API env vars: `POD_NAME`, `POD_NAMESPACE`, `AGENT_NAME` — no runtime k8s API call for identity
- ReadinessGate mechanism: after writing AgentDirectory, announcer patches its own Pod's status with a custom PodCondition (e.g., `AgentDirectoryReady=True`); controller adds this condition to `spec.readinessGates` when building the pod template
- Fix `AutomountServiceAccountToken: ptr(false)` → `ptr(true)` in `buildDeploymentSpec()` so the sidecar can read its SA token to call the k8s API

**AgentDirectory: resource model**
- One AgentDirectory CR per Agent CR (1:1), same name, same namespace
- Namespace-scoped resource
- Controller (AgentReconciler) pre-creates an empty AgentDirectory CR alongside the Deployment — CR lifecycle is controller-owned via ownerReference
- registry-announcer patches (never creates) its own AgentDirectory CR
- `cardHash` = SHA-256 of the canonical AgentCard JSON fetched from the agent's `/.well-known/agent.json` endpoint — idempotency check: announcer skips re-write if hash matches existing CR
- `readyAt` is set (or updated) by the registry-announcer after a successful write

**task-store: service layout**
- New top-level `task-store/` directory, parallel to `agent-inventory-api/` and `core-tools-lib/`
- Mirrors `agent-inventory-api` structure: `app/api/v1/`, `app/db/`, `app/core/config.py`, SQLAlchemy async, alembic for migrations
- Deviations: no outbox processor, no k8s client dependency
- HTTP API: implements the A2A TaskStore interface endpoints only, plus `/health`
- No `/metrics` endpoint in P1
- Dedicated Postgres database + PgBouncer — not shared with inventory-api
- Deployed with 2+ replicas (HA requirement per INFRA-08)
- No auth in P1: TaskStoreClient sends HTTP with no auth header

**ClusterAgentPolicy: P1 scope**
- Full CRD schema defined now: `spec.auth`, `spec.otel`, `spec.resilience` — no incremental CRD migrations
- AgentPolicy CRD also defined in P1 (namespace-scoped counterpart)
- AgentPolicyReconciler in P1 merges **OTEL and resilience fields only** into namespace AgentPolicy objects — auth fields present in schema but not read until P2
- Reconciler trigger: watch ClusterAgentPolicy + namespace list; reconcile when either changes

### Claude's Discretion
- AgentDirectory printer columns (beyond kubebuilder defaults)
- PgBouncer pool mode and connection limits for task-store
- Exact retry backoff for registry-announcer inventory-api secondary write
- Specific resilience default values in the ClusterAgentPolicy sample manifest

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | AgentDirectory CRD deployed with entries (agentName, version, URL, skills[], cardHash, readyAt) | CRD type file pattern established; kubebuilder markers from agent_types.go |
| INFRA-02 | AgentReconciler injects registry-announcer sidecar into every agent pod | `buildDeploymentSpec()` at line 158 is the injection point; `Containers` slice append |
| INFRA-03 | registry-announcer patches AgentDirectory CR as primary write (blocks pod ReadinessGate) | `corev1.PodReadinessGate` type confirmed in k8s.io/api@v0.31.0; announcer patches pod `.status.conditions` |
| INFRA-04 | registry-announcer writes inventory-api as secondary write (best-effort background retry queue) | inventory-api runs at known cluster DNS; registry-announcer uses background goroutine with retry |
| INFRA-05 | registry-announcer re-announces on restart using idempotent cardHash comparison | SHA-256 of canonical AgentCard JSON; announcer fetches current CR, compares hash before patching |
| INFRA-06 | task-store service implements A2A TaskStore interface over HTTP | `TaskStore` ABC has exactly 3 methods: `save`, `get`, `delete` — confirmed in a2a-sdk 0.3.26 |
| INFRA-07 | task-store deployed with dedicated Postgres + PgBouncer (not shared with inventory-api DB) | Separate postgres.yaml + pgbouncer.yaml manifests; asyncpg requires `prepared_statement_cache_size=0` with PgBouncer in transaction mode |
| INFRA-08 | task-store deployed with 2+ replicas (HA verified before P4) | `replicas: 2` in Deployment manifest; no shared in-process state since task-store is stateless over DB |
| INFRA-09 | TaskStoreClient in core-tools-lib reads TASK_STORE_URL; falls back to InMemoryTaskStore in dev | `httpx.AsyncClient`-based implementation; env var check in `TaskStore.from_env()` factory |
| INFRA-10 | create_agent_app() uses TaskStore.from_env() by default | Replace hardcoded `InMemoryTaskStore()` at agent.py:46 with `TaskStore.from_env()` |
| INFRA-11 | ClusterAgentPolicy CRD deployed with auth, OTEL, and resilience defaults | Cluster-scoped CRD; kubebuilder `+kubebuilder:resource:scope=Cluster` marker |
| INFRA-12 | AgentPolicyReconciler merges ClusterAgentPolicy defaults into namespace AgentPolicy | Watch two sources; `CreateOrUpdate` pattern from existing controller; OTEL+resilience merge only in P1 |
</phase_requirements>

---

## Summary

Phase 1 builds on a well-established codebase. The agent-controller already has a functioning `AgentReconciler` with `buildDeploymentSpec()`, `controllerutil.CreateOrUpdate`, and `ptr[T]()` helpers — all directly reusable. Three new CRD types need to be added to `api/v1alpha1/` and registered, with `make generate` run after. The registry-announcer is a new standalone Go binary that uses the same Kubernetes client-go patterns as the controller but runs as a sidecar, patching its own Pod's status condition to drive the ReadinessGate.

The task-store Python service mirrors inventory-api structurally but is simpler (no outbox, no k8s client). The a2a-sdk 0.3.26 `TaskStore` ABC has exactly three abstract methods (`save`, `get`, `delete`); the SDK's own `DatabaseTaskStore` demonstrates the SQLAlchemy async pattern to reference. The `TaskStoreClient` in core-tools-lib needs to implement those same three methods over HTTP. PgBouncer in transaction pool mode requires `prepared_statement_cache_size=0` in the asyncpg connection string to avoid prepared statement conflicts.

The ClusterAgentPolicy and AgentPolicy CRDs follow the same kubebuilder pattern as Agent. AgentPolicyReconciler watches two sources and merges only OTEL/resilience fields in P1 — auth fields are schema-present but deliberately ignored until Phase 2.

**Primary recommendation:** Start with the three new CRD type files and `make generate` (unblocks all other Go work), then registry-announcer binary, then task-store service, then core-tools-lib changes — in that order to respect dependencies.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| controller-runtime | v0.19.0 | Controller reconcile loop, fake client for tests | Already in go.mod; project standard |
| k8s.io/api | v0.31.0 | PodReadinessGate, PodCondition types | Already in go.mod |
| k8s.io/client-go | v0.31.0 | SA token auth for registry-announcer | Already in go.mod |
| controller-gen | v0.20.1 | Generates deepcopy + CRD manifests from markers | Already in Makefile |
| a2a-sdk | >=0.3.26 | TaskStore ABC, InMemoryTaskStore, AgentCard types | Already in core-tools-lib pyproject.toml |
| SQLAlchemy asyncio | >=2.0.0 | Async DB access | Already in inventory-api; reuse for task-store |
| asyncpg | >=0.30.0 | PostgreSQL async driver | Already in inventory-api; reuse for task-store |
| alembic | >=1.14.0 | DB migrations | Already in inventory-api; reuse for task-store |
| pydantic-settings | >=2.6.0 | Config from env vars | Already in inventory-api; reuse for task-store |
| httpx | >=0.27.0 | Async HTTP client for TaskStoreClient | Already in core-tools-lib deps |
| fastapi | >=0.115.0 | HTTP framework for task-store | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| crypto/sha256 (Go stdlib) | stdlib | SHA-256 of AgentCard JSON for cardHash | registry-announcer |
| encoding/json (Go stdlib) | stdlib | Canonical JSON marshaling for cardHash | registry-announcer |
| k8s.io/apimachinery/pkg/util/wait | v0.31.0 | Exponential backoff for retry loops | registry-announcer inventory-api secondary write |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `DatabaseTaskStore` from a2a-sdk | Custom ORM model | a2a-sdk's DatabaseTaskStore uses SQLAlchemy; this is actually usable directly but requires yielding schema control to the SDK's `Base`/`TaskModel` — custom model is cleaner for alembic migrations |
| asyncpg directly in task-store | `a2a-sdk[postgresql]` + `DatabaseTaskStore` | Using sdk's DatabaseTaskStore avoids custom HTTP layer but defeats the purpose of a shared HTTP service; HTTP layer is required for multi-replica use |
| PgBouncer session mode | transaction mode | Transaction mode allows higher concurrency but requires `prepared_statement_cache_size=0` in asyncpg; session mode is simpler but requires more Postgres connections |

**Installation (task-store):**
```bash
# In task-store/pyproject.toml
# fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, httpx
```

**Installation (registry-announcer go.mod):**
```
# Shares go.mod with agent-controller OR has its own — decision: own module in registry-announcer/
require (
    k8s.io/api v0.31.0
    k8s.io/apimachinery v0.31.0
    k8s.io/client-go v0.31.0
    sigs.k8s.io/controller-runtime v0.19.0
)
```

---

## Architecture Patterns

### Recommended Project Structure

**New top-level directories:**
```
registry-announcer/
├── cmd/main.go              # entrypoint
├── internal/announcer/      # core announce logic
├── Dockerfile               # distroless/static:nonroot, same as controller
├── go.mod                   # own module: github.com/justinbrewer/agent-orchestration/registry-announcer
└── Makefile                 # build/docker-build targets

task-store/
├── app/
│   ├── api/v1/routes/tasks.py    # save/get/delete over HTTP
│   ├── core/config.py            # pydantic-settings (mirrors inventory-api)
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/task.py        # SQLAlchemy Task model
│   └── main.py
├── alembic/
├── alembic.ini
├── config/
│   ├── postgres/postgres.yaml    # task-store-specific Postgres
│   ├── pgbouncer/pgbouncer.yaml  # PgBouncer sidecar or separate deploy
│   └── api/api.yaml              # 2+ replicas
├── Dockerfile
└── pyproject.toml

agent-controller/api/v1alpha1/
├── agent_types.go                # existing
├── agentdirectory_types.go       # new: INFRA-01
├── clusterpolicy_types.go        # new: INFRA-11
├── agentpolicy_types.go          # new: INFRA-12
├── groupversion_info.go          # add Register calls
└── zz_generated.deepcopy.go      # regenerated by make generate
```

### Pattern 1: CRD Type Registration (kubebuilder markers)
**What:** Every new CRD type file adds a marker comment block and `init()` call to register with SchemeBuilder
**When to use:** All three new type files (AgentDirectory, ClusterAgentPolicy, AgentPolicy)
**Example:**
```go
// Source: agent-controller/api/v1alpha1/agent_types.go (existing pattern)

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Namespaced,shortName=ad
// +kubebuilder:printcolumn:name="CardHash",type=string,JSONPath=`.spec.cardHash`
// +kubebuilder:printcolumn:name="ReadyAt",type=date,JSONPath=`.spec.readyAt`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

type AgentDirectory struct {
    metav1.TypeMeta   `json:",inline"`
    metav1.ObjectMeta `json:"metadata,omitempty"`
    Spec   AgentDirectorySpec   `json:"spec,omitempty"`
    Status AgentDirectoryStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true
type AgentDirectoryList struct { ... }

func init() {
    SchemeBuilder.Register(&AgentDirectory{}, &AgentDirectoryList{})
}
```

For ClusterAgentPolicy: `scope=Cluster` (no namespace):
```go
// +kubebuilder:resource:scope=Cluster,shortName=cap
```

### Pattern 2: Sidecar Injection in buildDeploymentSpec
**What:** Append sidecar container + ReadinessGate to the DeploymentSpec; fix AutomountServiceAccountToken
**When to use:** All agent pods — the controller always injects it

Exact injection point is `buildDeploymentSpec()` at `agent_controller.go:158`. The fix and additions are:

```go
// Source: agent-controller/internal/controller/agent_controller.go (to be modified)

// 1. Fix: ptr(true) not ptr(false)
AutomountServiceAccountToken: ptr(true),

// 2. Add ReadinessGate to PodSpec
ReadinessGates: []corev1.PodReadinessGate{
    {ConditionType: "agents.orchestration.io/directory-ready"},
},

// 3. Append sidecar container to Containers slice
// (after existing agent container)
{
    Name:            "registry-announcer",
    Image:           "registry-announcer:latest", // from AgentSpec or controller config
    ImagePullPolicy: corev1.PullIfNotPresent,
    Env: []corev1.EnvVar{
        {Name: "POD_NAME",      ValueFrom: &corev1.EnvVarSource{FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.name"}}},
        {Name: "POD_NAMESPACE", ValueFrom: &corev1.EnvVarSource{FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.namespace"}}},
        {Name: "AGENT_NAME",    ValueFrom: &corev1.EnvVarSource{FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.labels['app.kubernetes.io/instance']"}}},
    },
    SecurityContext: &corev1.SecurityContext{
        AllowPrivilegeEscalation: ptr(false),
        ReadOnlyRootFilesystem:   ptr(true),
        RunAsNonRoot:             ptr(true),
        Capabilities: &corev1.Capabilities{Drop: []corev1.Capability{"ALL"}},
    },
},
```

### Pattern 3: registry-announcer Announce Loop
**What:** On startup, fetch AgentCard, compute cardHash, compare to existing CR, patch if different, set pod condition
**When to use:** registry-announcer main logic

```go
// Source: k8s.io/api v0.31.0 + client-go patterns

// Patch pod status condition to satisfy ReadinessGate
condition := corev1.PodCondition{
    Type:               "agents.orchestration.io/directory-ready",
    Status:             corev1.ConditionTrue,
    LastTransitionTime: metav1.Now(),
    Reason:             "DirectoryWritten",
    Message:            "AgentDirectory entry is current",
}
// Use strategic merge patch on pod/status
patch := map[string]interface{}{
    "status": map[string]interface{}{
        "conditions": []corev1.PodCondition{condition},
    },
}
```

The announcer needs `pods/status` patch RBAC on its ServiceAccount.

### Pattern 4: controllerutil.CreateOrUpdate for AgentDirectory pre-creation
**What:** AgentReconciler pre-creates an empty AgentDirectory CR; announces reconcileAgentDirectory step
**When to use:** In AgentReconciler.Reconcile(), alongside existing reconcileDeployment

```go
// Source: agent-controller (existing CreateOrUpdate pattern)
func (r *AgentReconciler) reconcileAgentDirectory(ctx context.Context, agent *agentsv1alpha1.Agent) error {
    dir := &agentsv1alpha1.AgentDirectory{
        ObjectMeta: metav1.ObjectMeta{
            Name:      agent.Name,
            Namespace: agent.Namespace,
        },
    }
    _, err := controllerutil.CreateOrUpdate(ctx, r.Client, dir, func() error {
        // Spec left intentionally sparse; announcer fills it in via patch
        return controllerutil.SetControllerReference(agent, dir, r.Scheme)
    })
    return err
}
```

### Pattern 5: TaskStore.from_env() factory in core-tools-lib
**What:** Factory reads `TASK_STORE_URL`; falls back to InMemoryTaskStore
**When to use:** Replaces hardcoded `InMemoryTaskStore()` in `create_agent_app()`

```python
# Source: core-tools-lib/src/core_tools/agent.py (to be modified)
# a2a-sdk 0.3.26: TaskStore ABC has save/get/delete

import os
from a2a.server.tasks.task_store import TaskStore
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

class RemoteTaskStoreClient(TaskStore):
    """HTTP client wrapping the task-store service."""
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url)

    async def save(self, task: Task, context=None) -> None:
        await self._client.post("/tasks", content=task.model_dump_json())

    async def get(self, task_id: str, context=None) -> Task | None:
        r = await self._client.get(f"/tasks/{task_id}")
        if r.status_code == 404:
            return None
        return Task.model_validate_json(r.content)

    async def delete(self, task_id: str, context=None) -> None:
        await self._client.delete(f"/tasks/{task_id}")

def from_env() -> TaskStore:
    url = os.getenv("TASK_STORE_URL")
    if url:
        return RemoteTaskStoreClient(url)
    return InMemoryTaskStore()
```

### Pattern 6: AgentPolicyReconciler — watching two sources
**What:** Watches ClusterAgentPolicy (cluster-scoped) and Namespaces; reconciles all AgentPolicy objects per namespace
**When to use:** New `AgentPolicyReconciler` in agent-controller

```go
// Source: controller-runtime v0.19.0 multi-source watch
func (r *AgentPolicyReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&agentsv1alpha1.ClusterAgentPolicy{}).
        Watches(
            &corev1.Namespace{},
            handler.EnqueueRequestsFromMapFunc(r.namespaceToPolicy),
        ).
        Complete(r)
}
```

### Anti-Patterns to Avoid
- **Creating AgentDirectory from the registry-announcer:** The announcer must only patch, never create. Creating would race with the controller-owned CR and break ownerReference cleanup.
- **Sharing the inventory-api Postgres for task-store:** INFRA-07 explicitly prohibits this. Separate DB = separate PVC, Service, Secret.
- **Using `make generate` result only locally:** CI must block PRs where `*_types.go` changed without regeneration. The `git diff --exit-code` check is mandatory.
- **Setting `AutomountServiceAccountToken: ptr(false)`:** The existing test at `agent_controller_test.go:101` asserts `false`; this test MUST be updated when the fix is applied to `ptr(true)`.
- **asyncpg + PgBouncer transaction mode without disabling prepared statement cache:** asyncpg prepares statements by name and PgBouncer transaction mode resets the connection between transactions, causing "prepared statement already exists" errors. Mitigation: set `prepared_statement_cache_size=0` in the asyncpg connect args.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DeepCopy methods for CRD types | Manual DeepCopy | `make generate` (controller-gen) | Required by controller-runtime; missing deepcopy causes runtime panics |
| CRD manifest YAML | Hand-authored YAML | `make manifests` (controller-gen from kubebuilder markers) | Markers auto-generate OpenAPI validation, printer columns, subresource schema |
| SHA-256 hash | Custom hash | Go `crypto/sha256` + `encoding/json` | stdlib; no dependency |
| SA token reading for registry-announcer | Custom auth | `k8s.io/client-go/rest.InClusterConfig()` | Reads `/var/run/secrets/kubernetes.io/serviceaccount/token` automatically |
| Task serialization in task-store HTTP API | Custom serializer | `Task.model_dump_json()` / `Task.model_validate_json()` from a2a-sdk | Pydantic v2 JSON methods handle nested types correctly |
| Async DB session management | Manual session lifecycle | `async_sessionmaker` + `get_db()` dependency (inventory-api pattern) | Handles commit/rollback on error; matches FastAPI dependency injection |

**Key insight:** The a2a-sdk's `TaskStore` ABC and `InMemoryTaskStore` are the ground truth for the interface. The task-store HTTP service is simply a network layer in front of database persistence implementing those same three methods.

---

## Common Pitfalls

### Pitfall 1: Existing test asserts `AutomountServiceAccountToken=false`
**What goes wrong:** `TestReconcile_CreatesAllResources` at line 101 asserts `*AutomountServiceAccountToken == false`. After fixing to `ptr(true)`, this test fails.
**Why it happens:** The test was written to verify the security hardening that is being deliberately reversed.
**How to avoid:** Update the test assertion to expect `ptr(true)` in the same commit that changes `buildDeploymentSpec`.
**Warning signs:** `go test ./...` fails after applying the fix.

### Pitfall 2: controller-gen not re-run after adding *_types.go
**What goes wrong:** CRD manifests diverge from Go types; `make install` deploys stale schema; controller panics on unrecognized fields.
**Why it happens:** `zz_generated.deepcopy.go` and `config/crd/bases/*.yaml` are generated artifacts.
**How to avoid:** Run `make generate && make manifests` after every change to `*_types.go`; add CI check `make generate && git diff --exit-code`.
**Warning signs:** `git status` shows no changes to `zz_generated.deepcopy.go` after editing types.

### Pitfall 3: registry-announcer races pod condition with ReadinessGate
**What goes wrong:** Pod reaches Running but ReadinessGate condition is never set → pod stuck NotReady forever.
**Why it happens:** `spec.readinessGates` specifies a condition the kubelet will check; if no process sets `status.conditions[type=AgentDirectoryReady]`, the pod never turns Ready.
**How to avoid:** announcer must patch `pod/status` immediately after a successful AgentDirectory write; it needs `pods/status` patch RBAC.
**Warning signs:** `kubectl get pods` shows `0/1 READY` but containers are Running; `kubectl describe pod` shows readiness gate condition `False`.

### Pitfall 4: ClusterAgentPolicy scope must be Cluster, not Namespaced
**What goes wrong:** Using `scope=Namespaced` for ClusterAgentPolicy causes `kubectl apply` to expect a namespace; AgentPolicyReconciler can't watch across namespaces correctly.
**Why it happens:** CRD scope defaults to Namespaced unless `+kubebuilder:resource:scope=Cluster` marker is present.
**How to avoid:** Add `scope=Cluster` marker; verify with `make manifests` that generated YAML has `scope: Cluster`.
**Warning signs:** CRD YAML shows `scope: Namespaced`.

### Pitfall 5: PgBouncer transaction mode + asyncpg prepared statements
**What goes wrong:** `asyncpg.exceptions.DuplicatePreparedStatementError` when task-store runs multiple workers behind PgBouncer in transaction mode.
**Why it happens:** asyncpg caches prepared statements per connection; PgBouncer reuses connections across sessions without clearing state.
**How to avoid:** Pass `prepared_statement_cache_size=0` to asyncpg (via SQLAlchemy `connect_args`), OR use PgBouncer in session mode (simpler but fewer connections).
**Warning signs:** Errors in task-store logs mentioning "prepared statement already exists"; only appears under concurrent load or after scaling.

### Pitfall 6: AgentDirectory created by registry-announcer instead of patched
**What goes wrong:** If announcer calls `Create` instead of `Patch`, it races with controller; second create returns 409; ownerReference is not set → orphaned CRs on agent deletion.
**Why it happens:** Common mistake when writing k8s clients — `Apply` vs `Create`.
**How to avoid:** announcer uses `Patch` with strategic merge or apply; controller pre-creates the empty CR via `CreateOrUpdate`.
**Warning signs:** AgentDirectory CRs accumulating without ownerReferences; `kubectl get agentdirectory` shows entries with no owner.

### Pitfall 7: cardHash computed on non-canonical JSON
**What goes wrong:** Hash changes on each fetch due to field ordering in JSON → unnecessary re-writes; idempotency breaks.
**Why it happens:** JSON marshaling order is not guaranteed in Python unless `sort_keys=True` or Pydantic's `model_dump_json()` is used consistently.
**How to avoid:** In Go (registry-announcer): marshal AgentCard with `encoding/json` which uses struct field order deterministically. Ensure Pydantic JSON output is used consistently.
**Warning signs:** `cardHash` field in AgentDirectory changes on every restart even when agent hasn't changed.

---

## Code Examples

Verified patterns from official sources and existing codebase:

### AgentDirectory CRD Type Fields
```go
// Source: CONTEXT.md locked decisions + kubebuilder patterns from agent_types.go

type AgentDirectorySpec struct {
    AgentName string            `json:"agentName"`
    Version   string            `json:"version"`
    URL       string            `json:"url"`
    Skills    []string          `json:"skills,omitempty"`
    CardHash  string            `json:"cardHash,omitempty"`
    ReadyAt   *metav1.Time      `json:"readyAt,omitempty"`
}
```

### ClusterAgentPolicy CRD Type Fields (P1 full schema)
```go
// Source: CONTEXT.md locked decisions

type ClusterAgentPolicySpec struct {
    Auth       AuthSpec       `json:"auth,omitempty"`
    OTEL       OTELSpec       `json:"otel,omitempty"`
    Resilience ResilienceSpec `json:"resilience,omitempty"`
}

type AuthSpec struct {
    TokenAudience string `json:"tokenAudience,omitempty"`
    Mode          string `json:"mode,omitempty"` // "serviceaccount" | "none"
}

type OTELSpec struct {
    Endpoint string  `json:"endpoint,omitempty"`
    Sampling float64 `json:"sampling,omitempty"`
}

type ResilienceSpec struct {
    TimeoutMs int32 `json:"timeoutMs,omitempty"`
    Retries   int32 `json:"retries,omitempty"`
}
```

### Downward API env vars for sidecar
```go
// Source: k8s.io/api v0.31.0 corev1 types
corev1.EnvVar{
    Name: "POD_NAME",
    ValueFrom: &corev1.EnvVarSource{
        FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.name"},
    },
},
corev1.EnvVar{
    Name: "POD_NAMESPACE",
    ValueFrom: &corev1.EnvVarSource{
        FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.namespace"},
    },
},
```

### a2a-sdk TaskStore abstract methods (verified from source)
```python
# Source: /opt/miniconda3/lib/python3.13/site-packages/a2a/server/tasks/task_store.py
# a2a-sdk version 0.3.26

class TaskStore(ABC):
    @abstractmethod
    async def save(self, task: Task, context: ServerCallContext | None = None) -> None: ...

    @abstractmethod
    async def get(self, task_id: str, context: ServerCallContext | None = None) -> Task | None: ...

    @abstractmethod
    async def delete(self, task_id: str, context: ServerCallContext | None = None) -> None: ...
```

### asyncpg + PgBouncer transaction mode configuration
```python
# Source: SQLAlchemy asyncpg dialect docs (verified in local site-packages)
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    settings.database_url,  # postgresql+asyncpg://user:pass@pgbouncer:5432/taskstore
    echo=settings.debug,
    connect_args={"prepared_statement_cache_size": 0},  # Required for PgBouncer transaction mode
    pool_size=5,
    max_overflow=10,
)
```

### PodReadinessGate type (verified in k8s.io/api@v0.31.0)
```go
// Source: k8s.io/api@v0.31.0/core/v1/types.go (verified)
corev1.PodReadinessGate{
    ConditionType: corev1.PodConditionType("agents.orchestration.io/directory-ready"),
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded `InMemoryTaskStore()` | `TaskStore.from_env()` factory | This phase | Agents get remote task persistence without code changes |
| `AutomountServiceAccountToken: ptr(false)` | `ptr(true)` for sidecar pods | This phase (explicit fix in CONTEXT.md) | registry-announcer can call k8s API |

**Deprecated/outdated:**
- `a2a-sdk 0.3.24` (in envs/a2a conda env): project uses `>=0.3.26` — verify TaskStore interface is identical between 0.3.24 and 0.3.26 (confirmed: same 3 methods, compatible)

---

## Open Questions

1. **registry-announcer Go module placement**
   - What we know: CONTEXT.md says "top-level `registry-announcer/` directory"; no existing go.mod there
   - What's unclear: Should it share the agent-controller module (`agent-controller/cmd/announcer/`) or have its own (`registry-announcer/go.mod`)? CONTEXT.md says "separate image versioned independently" which implies separate module.
   - Recommendation: Separate `registry-announcer/go.mod` — allows independent versioning and a simpler Dockerfile; copy agent-controller's go.mod as starting point.

2. **registry-announcer RBAC ServiceAccount**
   - What we know: The announcer needs to patch its own `pods/status` and patch `agentdirectories`; it uses the agent pod's ServiceAccount.
   - What's unclear: Should the controller create a separate SA for the sidecar, or reuse the agent's SA?
   - Recommendation: Reuse the agent SA (already created by AgentReconciler); add the required verbs (`patch pods/status`, `get/patch agentdirectories`) to a ClusterRole that AgentReconciler creates per-namespace via RoleBinding. This is clean and keeps resources consolidated under the agent's ownership.

3. **task-store HTTP API path design**
   - What we know: Must implement save/get/delete for `Task` objects; CONTEXT.md says "implements the A2A TaskStore interface endpoints only"
   - What's unclear: Exact URL paths (`/tasks/{id}`, `/v1/tasks/{id}`, or `/api/v1/tasks/{id}`?)
   - Recommendation: Use `/tasks/{task_id}` (flat, versioning deferred); aligns with the minimal scope and avoids inventory-api's `/api/v1/` prefix which is richer than needed here.

4. **PgBouncer pool mode selection**
   - What we know: Transaction mode allows more connections but requires `prepared_statement_cache_size=0`; session mode is simpler
   - What's unclear: Expected concurrent task-store load in P1 (likely low)
   - Recommendation: Use transaction mode with `prepared_statement_cache_size=0` — future-proof for Phase 4 when platform agents create load; document the asyncpg requirement.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (Go) | `go test` (stdlib) — already in Makefile as `make test` |
| Framework (Python) | pytest + pytest-asyncio (asyncio_mode = "auto") — already in inventory-api; replicate for task-store |
| Go config | No separate config file; `go test ./... -v -count=1` |
| Python config | `[tool.pytest.ini_options] asyncio_mode = "auto"` in pyproject.toml |
| Quick run (Go) | `cd agent-controller && go test ./... -count=1` |
| Quick run (Python) | `cd task-store && pytest tests/ -x` |
| Full suite | `cd agent-controller && go test ./... && cd task-store && pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | AgentDirectory CRD fields present | unit | `cd agent-controller && go test ./api/... -run TestAgentDirectory` | Wave 0 |
| INFRA-02 | buildDeploymentSpec injects sidecar container | unit | `cd agent-controller && go test ./internal/controller/ -run TestBuildDeploymentSpec_HasSidecar` | Wave 0 |
| INFRA-02 | buildDeploymentSpec adds ReadinessGate | unit | `cd agent-controller && go test ./internal/controller/ -run TestBuildDeploymentSpec_ReadinessGate` | Wave 0 |
| INFRA-02 | AutomountServiceAccountToken is true | unit | Update existing `TestReconcile_CreatesAllResources` line 101 | ✅ (update needed) |
| INFRA-03 | AgentReconciler pre-creates AgentDirectory | unit | `cd agent-controller && go test ./internal/controller/ -run TestReconcile_CreatesAgentDirectory` | Wave 0 |
| INFRA-04 | secondary write queued on startup | unit | `cd registry-announcer && go test ./... -run TestSecondaryWrite` | Wave 0 |
| INFRA-05 | announcer skips re-write when hash matches | unit | `cd registry-announcer && go test ./... -run TestIdempotentAnnounce` | Wave 0 |
| INFRA-06 | task-store save/get/delete work | integration | `cd task-store && pytest tests/test_tasks.py -x` | Wave 0 |
| INFRA-07 | task-store uses dedicated DB (config check) | unit | `cd task-store && pytest tests/test_config.py -run test_db_url_separate` | Wave 0 |
| INFRA-08 | task-store manifest has 2+ replicas | manual | Review `config/api/api.yaml` replicas field | manual |
| INFRA-09 | TASK_STORE_URL set → RemoteTaskStoreClient | unit | `cd core-tools-lib && pytest tests/test_task_store.py -run test_from_env_with_url` | Wave 0 |
| INFRA-09 | TASK_STORE_URL unset → InMemoryTaskStore | unit | `cd core-tools-lib && pytest tests/test_task_store.py -run test_from_env_no_url` | Wave 0 |
| INFRA-10 | create_agent_app uses from_env | unit | `cd core-tools-lib && pytest tests/test_agent.py -run test_uses_from_env` | Wave 0 |
| INFRA-11 | ClusterAgentPolicy CRD scope=Cluster | unit | Verify `config/crd/bases/` after `make manifests`; check `scope: Cluster` | Wave 0 |
| INFRA-12 | AgentPolicyReconciler merges OTEL+resilience | unit | `cd agent-controller && go test ./internal/controller/ -run TestAgentPolicyReconciler` | Wave 0 |

### Sampling Rate
- **Per task commit:** Quick run for that component (Go: `go test ./internal/controller/`, Python: `pytest tests/ -x`)
- **Per wave merge:** Full suite: `make test` in agent-controller + `pytest` in task-store + `pytest` in core-tools-lib
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `agent-controller/internal/controller/agent_controller_test.go` — update line 101 assertion (`ptr(false)` → `ptr(true)`)
- [ ] `agent-controller/internal/controller/agent_controller_test.go` — add `TestReconcile_CreatesAgentDirectory`, `TestBuildDeploymentSpec_HasSidecar`, `TestBuildDeploymentSpec_ReadinessGate`
- [ ] `registry-announcer/internal/announcer/announcer_test.go` — covers INFRA-04, INFRA-05
- [ ] `task-store/tests/test_tasks.py` — covers INFRA-06
- [ ] `task-store/tests/test_config.py` — covers INFRA-07
- [ ] `task-store/tests/conftest.py` — shared DB fixture (sqlite in-memory for unit tests)
- [ ] `task-store/pyproject.toml` — `[tool.pytest.ini_options] asyncio_mode = "auto"`
- [ ] `core-tools-lib/tests/test_task_store.py` — covers INFRA-09
- [ ] `core-tools-lib/tests/test_agent.py` — covers INFRA-10
- [ ] `agent-controller/internal/controller/agentpolicy_reconciler_test.go` — covers INFRA-12
- [ ] CI workflow `.github/workflows/ci.yml` — `make generate && git diff --exit-code` check

---

## Sources

### Primary (HIGH confidence)
- Local codebase read — `agent-controller/internal/controller/agent_controller.go`, `api/v1alpha1/agent_types.go`, `groupversion_info.go`, `Makefile`, test file
- Local codebase read — `core-tools-lib/src/core_tools/agent.py`, `health.py`, `pyproject.toml`
- Local codebase read — `agent-inventory-api/app/core/config.py`, `app/db/session.py`, `app/main.py`, `config/postgres/postgres.yaml`, `config/api/api.yaml`
- Local a2a-sdk 0.3.26 source — `/opt/miniconda3/lib/python3.13/site-packages/a2a/server/tasks/task_store.py`, `inmemory_task_store.py`, `database_task_store.py`
- Local k8s.io/api v0.31.0 — `PodReadinessGate`, `PodCondition` types confirmed
- Local SQLAlchemy asyncpg dialect — PgBouncer transaction mode `prepared_statement_cache_size=0` requirement verified

### Secondary (MEDIUM confidence)
- `a2a/types.py` local source — `Task`, `AgentCard` Pydantic types reviewed

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified from local go.mod, pyproject.toml, and installed packages
- Architecture: HIGH — patterns derived directly from existing codebase and locked CONTEXT.md decisions
- Pitfalls: HIGH — most pitfalls derived from direct code inspection (existing test assertion, asyncpg note in local site-packages)
- a2a-sdk interface: HIGH — read directly from installed 0.3.26 source

**Research date:** 2026-04-22
**Valid until:** 2026-07-22 (stable stack; a2a-sdk minor versions move faster, re-verify if upgrading beyond 0.3.x)
