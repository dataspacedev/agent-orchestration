# Architecture Research

**Domain:** Kubernetes-native AI agent orchestration platform — federated agent stack v2
**Researched:** 2026-04-21
**Confidence:** HIGH (derived from direct code inspection + authoritative design doc)

---

## New vs Modified Components

### Modified (existing components with required changes)

| Component | File | What Changes |
|-----------|------|--------------|
| `AgentReconciler` | `agent-controller/internal/controller/agent_controller.go` | Add sidecar injection to `buildDeploymentSpec`; add `SidecarImages` struct; flip `AutomountServiceAccountToken` for sidecar-injected pods; inject `TASK_STORE_URL`, `PLATFORM_AGENT` env vars |
| `AgentReconciler` RBAC markers | same file | Add agentdirectories get/list/watch; create ClusterRoleBinding for skill-resolver |
| `main.go` | `agent-controller/cmd/main.go` | Register 3 new reconcilers + 1 Runnable; add sidecar image flags |
| `create_agent_app()` | `core-tools-lib/src/core_tools/agent.py` | Add `task_store` param with `TaskStore.from_env()` default; inject `StackIsolationMiddleware` when `PLATFORM_AGENT=true` |
| `core_tools/__init__.py` | `core-tools-lib/src/core_tools/__init__.py` | Export `A2AClient`, `TaskStore`, `StackIsolationMiddleware`, `AgentRubric` |
| `inventory-api` | `agent-inventory-api/app/` | Add skill-indexed query endpoint; add read-through cache (additive, no breaking changes) |

**Critical existing gap:** `create_agent_app()` hardcodes `InMemoryTaskStore()` — no `task_store` param, no `TASK_STORE_URL`, no `StackIsolationMiddleware`. `AutomountServiceAccountToken` is currently `ptr(false)` — must change for sidecar-injected pods.

### New (net-new components)

| Component | Location | Language | Phase |
|-----------|----------|----------|-------|
| `AgentDirectory` CRD type | `agent-controller/api/v1alpha1/agentdirectory_types.go` | Go | P1 |
| `ClusterAgentPolicy` CRD type | `agent-controller/api/v1alpha1/clusteragentpolicy_types.go` | Go | P1 |
| `AgentAccessPolicy` CRD type | `agent-controller/api/v1alpha1/agentaccesspolicy_types.go` | Go | P2 |
| `AgentStack` CRD type | `agent-controller/api/v1alpha1/agentstack_types.go` | Go | P3 |
| `AgentPolicy` CRD type | `agent-controller/api/v1alpha1/agentpolicy_types.go` | Go | P3 |
| `AgentRoute` CRD type | `agent-controller/api/v1alpha1/agentroute_types.go` | Go | P3 |
| `AgentRubric` CRD type | `agent-controller/api/v1alpha1/agentrubric_types.go` | Go | P5 |
| `AgentStackReconciler` | `agent-controller/internal/controller/agentstack_controller.go` | Go | P3 |
| `AgentPolicyReconciler` | `agent-controller/internal/controller/agentpolicy_controller.go` | Go | P1 |
| `AgentAccessReconciler` | `agent-controller/internal/controller/agentaccess_controller.go` | Go | P2 |
| `ClusterAgentDirectoryHealthCheck` | `agent-controller/internal/controller/directory_healthcheck.go` | Go | P7 |
| `registry-announcer` sidecar | `registry-announcer/` (new service) | Python | P1 |
| `skill-resolver` sidecar | `skill-resolver/` (new Go binary) | Go | P3 |
| `task-store` service | `task-store/` (new service) | Python (FastAPI) | P1 |
| `MCP aggregator` | `mcp-aggregator/` (new service) | Python (FastMCP) | P6 |
| `StackIsolationMiddleware` | `core-tools-lib/src/core_tools/middleware.py` | Python | P4 |
| `A2AClient` | `core-tools-lib/src/core_tools/client.py` | Python | P2 |
| `TaskStoreClient` | `core-tools-lib/src/core_tools/taskstore.py` | Python | P1 |
| Platform agents (7) | `agent-platform/` (new dir) | Python | P4 |

---

## CRD Group Integration

All new CRDs join `agents.orchestration.io/v1alpha1` — the existing group. No new API group needed.

Registration pattern (identical to existing `Agent` CR): add `SchemeBuilder.Register(&AgentDirectory{}, &AgentDirectoryList{})` in each new `*_types.go` init(). The existing `main.go` `init()` picks up all new types via `agentsv1alpha1.AddToScheme(scheme)` — no change to main.go init needed.

`controller-gen` must be re-run after each new type file to regenerate `zz_generated.deepcopy.go` and CRD YAML manifests. CRD YAMLs must be applied to cluster before the reconciler that watches them deploys.

| New CRD | Scope | Writer | Reader(s) |
|---------|-------|--------|-----------|
| `AgentDirectory` | Namespaced | registry-announcer sidecar | skill-resolver sidecar, AgentStackReconciler, MCP aggregator |
| `ClusterAgentPolicy` | Cluster | platform team | AgentPolicyReconciler, A2AClient (via env injection) |
| `AgentStack` | Namespaced | domain teams | AgentStackReconciler |
| `AgentPolicy` | Namespaced | domain teams | AgentPolicyReconciler |
| `AgentRoute` | Namespaced | domain teams | AgentStackReconciler |
| `AgentAccessPolicy` | Namespaced (target ns) | domain teams + platform approval | AgentAccessReconciler, skill-resolver sidecar |
| `AgentRubric` | Namespaced | domain teams | skill-resolver sidecar |

---

## Skill-Resolver In-Cluster RBAC

The skill-resolver sidecar uses the agent pod's service account token. `AgentReconciler` must be extended to create a `ClusterRoleBinding` attaching each agent SA to a shared `skill-resolver-reader` ClusterRole.

```yaml
# ClusterRole (applied once):
rules:
  - apiGroups: ["agents.orchestration.io"]
    resources: ["agentdirectories", "agentaccesspolicies", "agentrubrics"]
    verbs: ["get", "list", "watch"]
```

---

## Build Order (Critical Path)

```
P1: AgentDirectory CRD types + controller-gen
 → P1: CRD YAMLs applied + registry-announcer sidecar deployed
 → P1: task-store service + TaskStoreClient in core-tools-lib
 → P2: ClusterAgentPolicy active + A2AClient with SA token + AgentAccessPolicy CRD
 → P3: skill-resolver binary + AgentStack/AgentPolicy/AgentRoute CRDs + reconcilers
 → P4: Platform agents (7) + StackIsolationMiddleware
 → P5: Domain stacks with peerStacks semver + AgentRubric
 → P6: MCP aggregator
 → P7: Drift detection + audit logging + SLO dashboards
```

**Parallel tracks** that converge at P4:
- task-store service (P1) → must be HA before P4
- registry-announcer (P1) → must be stable before platform stack (P4)

---

## Integration Points

| Boundary | Communication | Notes |
|----------|---------------|-------|
| agent container ↔ skill-resolver | HTTP GET localhost:2020 | Init container waits for /health before agent starts |
| registry-announcer ↔ k8s API | client-go Patch on AgentDirectory CR | Uses pod SA token; requires write RBAC |
| skill-resolver ↔ k8s API | k8s informer watch | ClusterRoleBinding to skill-resolver-reader |
| A2AClient ↔ platform agents | HTTP + Authorization: Bearer + X-Stack-Id + X-Agent-Rubric | Token from pod SA file |
| platform agents ↔ OIDC JWKS | HTTP fetch, cached per token TTL | Avoids TokenReview latency on hot path |
| agents ↔ task-store | HTTP (TaskStoreClient) via TASK_STORE_URL | No direct Postgres from agent pods |
| MCP aggregator ↔ AgentDirectory | k8s informer watch | Generation-swapped tool registry on update |

---

## Open Questions

1. a2a-sdk `TaskStore` interface exact method signatures — must verify against installed package before implementing `TaskStoreClient`
2. Registry-announcer restart mid-card-update behavior — needs explicit idempotent patch semantics (patch by agentName key, compare cardHash before patching)
3. Cross-namespace AgentDirectory watch scope for skill-resolver — ClusterRole required (not per-namespace RoleBinding) since orchestrators read platform-namespace AgentDirectories
4. MCP aggregator relationship to AgentStack: 1 aggregator per AgentStack with `mcp.aggregated: true`

---

## Sources

- `docs/federated-agent-stack.md` — v2 design (2026-04-21). Authoritative. HIGH confidence.
- `agent-controller/internal/controller/agent_controller.go` — confirmed no sidecar injection, `AutomountServiceAccountToken: false`
- `agent-controller/cmd/main.go` — confirmed single reconciler, scheme registration pattern
- `core-tools-lib/src/core_tools/agent.py` — confirmed `InMemoryTaskStore()` hardcoded, no `task_store` param
