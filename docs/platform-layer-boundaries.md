# Platform Layer Boundaries

This document summarizes the layer boundaries implied by the `.planning` documentation for the agent orchestration platform. It separates the system into four layers so ownership, interfaces, and change responsibility stay clear as the platform evolves.

The core architectural rule is: management concerns stay in the administration layer, reusable runtime capabilities stay in the platform feature layer, domain behavior stays in the agent stack layer, and user-facing interaction stays in the user layer.

Related: [Architecture Diagrams](./architecture-diagrams.md)

## Layer Model

| Layer | Primary purpose | Owned by | Main artifacts |
|---|---|---|---|
| User layer | Consume domain workflows and agent capabilities | Product teams, operators, client apps | UIs, MCP clients, A2A callers, reports, actions |
| Agent stack and domain layer | Encode domain workflows, policies, and business behavior | Domain teams | Domain agents, `AgentStack`, `AgentPolicy`, `AgentRubric`, `EvaluationPolicy`, agent images |
| Platform feature layer | Provide shared runtime capabilities every stack can consume | Platform teams | Platform agents, `AgentDirectory`, `skill-resolver`, `registry-announcer`, `task-store`, MCP aggregator, `core-tools-lib` |
| Platform administration layer | Govern the cluster, lifecycle, auth, routing, and compliance | Platform controller, security, and operations teams | `agent-controller`, CRD schemas, `ClusterAgentPolicy`, `AgentAccessPolicy`, RBAC, promotion process, drift detection, SLOs |

## 1. Boundary: Platform Administration vs Platform Features

This is the most important boundary in the planning docs. Administration defines policy and lifecycle. Features provide runtime capability. The administration layer is allowed to govern features, but features should not depend on administration hot paths to serve traffic.

### Administration layer owns

- Cluster-scoped policy and defaults such as `ClusterAgentPolicy`
- CRD schemas and reconcilers for `Agent`, `AgentStack`, `AgentPolicy`, `AgentRoute`, `AgentAccessPolicy`, `AgentRubric`, and `AgentDirectory`
- Sidecar injection and workload shaping through `agent-controller`
- RBAC, namespace write access, and promotion approval into `agent-platform`
- Governance controls such as drift detection, audit requirements, and SLO publication
- Management-plane CRUD and audit workflows in `inventory-api`

### Platform feature layer owns

- Runtime skill discovery through `AgentDirectory`
- Agent self-announcement through `registry-announcer`
- Dynamic in-pod skill lookup through `skill-resolver`
- Shared task persistence through `task-store`
- Shared platform capabilities exposed by the seven platform agents
- Shared SDK behaviors in `core-tools-lib`, including `A2AClient` and `StackIsolationMiddleware`
- Stack-level MCP exposure through the MCP aggregator

### Hard contract at this boundary

- Runtime discovery must read from `AgentDirectory`, not from `inventory-api`
- Administration can change policy and rollout behavior, but feature traffic should continue even if management APIs are slow or offline
- Auth is cluster-governed and mandatory; feature teams and domain teams do not opt out of it
- Shared runtime capabilities are platform assets and are not reimplemented separately by each domain

### What crosses this boundary

| From administration | To features | Why |
|---|---|---|
| CRDs and reconciler behavior | Sidecars, platform agents, aggregators | Defines what is deployed and how it is wired |
| `ClusterAgentPolicy` defaults | SDK and platform agents | Enforces auth, tracing, and resilience consistently |
| `AgentAccessPolicy` grants | `skill-resolver` and runtime access checks | Governs which stacks may call which skills |
| RBAC and namespace controls | Platform namespaces and sidecar API access | Prevents domains from mutating platform-owned runtime assets |

### What must not cross this boundary

- `inventory-api` must not sit on the runtime resolution path
- Domain-specific behavior must not be encoded in cluster-wide policy
- Platform agents must not require manual per-domain auth or routing setup

## 2. Boundary: Platform Features vs Agent Stack and Domain

This boundary separates reusable infrastructure from domain-specific workflow logic. The platform gives every domain stack a standard runtime substrate. The domain layer decides how to use it.

### Platform feature layer provides

- Authenticated A2A calling via `A2AClient`
- Dynamic skill resolution via `skill-resolver`
- Shared task persistence via `TaskStore.from_env()`
- Shared platform skills such as search, document intelligence, memory, reporting, and action execution
- Shared cross-stack protections such as `X-Stack-Id`, rate limiting, and audit logging
- Shared MCP aggregation for stacks that enable it

### Domain layer owns

- Domain agent logic and orchestration flow
- Namespace-scoped topology in `AgentStack`
- Namespace-scoped overrides in `AgentPolicy`
- Runtime behavioral configuration in `AgentRubric`
- Evaluation and scoring policy in `EvaluationPolicy`
- Semver expectations for peer stack capabilities

### Hard contract at this boundary

- Domain teams configure domain behavior; they do not wire auth, routing, stack isolation, or observability manually
- Platform capabilities are consumed through stable protocols and CRDs, not through direct database or sidecar internals
- Domain teams may declare what platform skills and versions they need, but they do not directly mutate platform runtime assets
- Access to privileged skills is granted explicitly through `AgentAccessPolicy`, not assumed by namespace membership

### Domain controls vs platform controls

| Domain team can control | Domain team cannot control |
|---|---|
| `AgentStack` membership and peer capability requirements | Cluster auth mode |
| `AgentPolicy` namespace-level observability overrides | Platform namespace RBAC |
| `AgentRubric` content for domain-specific behavior | `StackIsolationMiddleware` behavior for platform safety |
| Their own agent images and business logic | Direct writes to platform agents or platform-only CRDs |
| Degraded-mode handling in orchestration logic | Bypassing `skill-resolver`, SA token auth, or audit headers |

### Practical interpretation

If a concern should work the same way for legal, financial, or clinical stacks, it belongs in the platform feature layer. If a concern changes because a domain interprets risk, workflow, or output schema differently, it belongs in the domain layer.

## 3. Boundary: Agent Stack and Domain vs User Layer

The user layer should interact with domain workflows and exposed capabilities, not with cluster primitives. The domain layer translates user intent into orchestrated calls across the platform.

### User layer includes

- End users interacting with domain applications
- Operators using stack-level tools or UI surfaces
- Client applications calling A2A endpoints
- MCP clients calling aggregated tool surfaces

### Domain layer exposes to users

- Domain-specific workflows and responses
- Task progress and final results
- Reports, decisions, and external actions
- Stable MCP or A2A surfaces appropriate for that domain

### Hard contract at this boundary

- Users should see domain outcomes, not platform internals
- Headers such as `X-Stack-Id`, service account auth, and rubric transport are internal mechanics
- User-facing reliability should degrade through domain logic, not by exposing control-plane failure directly
- The inventory and administration surfaces are for platform operations, not for end-user runtime interaction

### What should remain hidden from users

- CRD structure and reconciliation details
- `AgentDirectory` and sidecar behavior
- Cross-stack access policy mechanics
- Platform rate-limiting and audit implementation details
- Controller rollout and drift-detection internals

## Ownership Rules

Use these rules when deciding where a new capability belongs:

- If it governs the whole cluster or multiple namespaces, it belongs in platform administration.
- If it is reusable runtime infrastructure consumed by many stacks, it belongs in platform features.
- If it changes with domain workflow, interpretation, or business policy, it belongs in the agent stack and domain layer.
- If it exists to capture human intent or present results, it belongs in the user layer.

## Boundary Summary

The planning docs describe a layered platform, not a flat collection of agents. Platform administration sets policy, lifecycle, and governance. Platform features supply reusable runtime capability. Domain stacks encode business logic and domain-specific policy. Users interact only with the domain-facing surface. The architecture stays coherent only if those boundaries remain explicit and enforced.

## Source Basis

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/FEATURES.md`
- `.planning/research/SUMMARY.md`
- `docs/federated-agent-stack.md`
