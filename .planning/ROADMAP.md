# Roadmap: Agent Orchestration Platform

## Overview

Seven tightly dependency-ordered phases transform the existing single-reconciler controller into a full federated agent stack: a runtime-authoritative skill map (AgentDirectory CRD), mandatory service-account-token auth, a dynamic skill-resolver sidecar replacing env-var injection, a dedicated task-store service, seven platform agents behind StackIsolationMiddleware, an MCP aggregator with versioned tool registry, and governance instrumentation. Each phase is independently deployable without breaking the prior one. The dependency chain is hard: P1 runtime foundation gates P2 auth, which gates P4 platform agents; task-store HA in P1 must be verified before P4 proceeds.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Runtime Foundation** - AgentDirectory CRD, registry-announcer sidecar, task-store service, ClusterAgentPolicy CRD, and TaskStoreClient in core-tools-lib
- [ ] **Phase 2: Mandatory Auth** - Cluster-wide SA-token auth enforced via ClusterAgentPolicy, A2AClient token injection, AgentAccessPolicy CRD
- [ ] **Phase 3: Skill-Resolver + Composable CRDs** - skill-resolver sidecar, AgentStack minimal spec, AgentPolicy/AgentRoute CRDs, conversion webhook, AgentStackReconciler
- [ ] **Phase 4: Platform Stack Deployment** - 7 platform agents in agent-platform namespace with StackIsolationMiddleware, per-stack rate limits, and audit logging
- [ ] **Phase 5: Domain Stack Onboarding** - peerStacks semver constraints, AgentRubric CRD with 8KB header threshold enforcement
- [ ] **Phase 6: MCP Aggregator** - MCP aggregator per AgentStack, versioned tool naming, generation-based registry swap
- [ ] **Phase 7: Governance & Hardening** - Drift detection, audit log data contract, SLO dashboards, AgentPromotion process

## Phase Details

### Phase 1: Runtime Foundation
**Goal**: The runtime plane is operational — agents announce themselves to AgentDirectory, task state is durable and highly available, and the platform has cluster-scoped auth/observability defaults ready for enforcement in Phase 2.
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INFRA-07, INFRA-08, INFRA-09, INFRA-10, INFRA-11, INFRA-12
**Success Criteria** (what must be TRUE):
  1. An agent pod deployed via Agent CR has a registry-announcer sidecar injected automatically; the pod does not reach Ready until the announcer has written a valid AgentDirectory entry (readyAt set, cardHash present).
  2. AgentDirectory entries survive registry-announcer restarts: on restart the announcer re-patches using idempotent cardHash comparison and the entry is current within one reconcile cycle.
  3. task-store service is reachable at its cluster DNS name, implements the A2A TaskStore HTTP interface, and runs with 2+ replicas backed by a dedicated Postgres + PgBouncer (not shared with inventory-api DB).
  4. An agent using core-tools-lib with TASK_STORE_URL set creates and retrieves tasks from the remote task-store; an agent without the env var falls back to InMemoryTaskStore without error.
  5. ClusterAgentPolicy CR is applied to the cluster with auth, OTEL, and resilience defaults; AgentPolicyReconciler merges those defaults into namespace AgentPolicy objects.
**Hard gates (must be verified before Phase 2 begins)**: task-store HA confirmed (2+ replicas, PgBouncer healthy, backup tested); AgentDirectory CRD applies cleanly to production cluster; registry-announcer stable with no divergence across 10+ restart cycles.
**Implementation note**: Fix `AutomountServiceAccountToken: ptr(false)` to `ptr(true)` in `buildDeploymentSpec` for sidecar-injected pods in this phase. Add CI check: `make generate && git diff --exit-code` blocking any PR that adds `*_types.go` without re-running controller-gen.
**Plans**: TBD

### Phase 2: Mandatory Auth
**Goal**: Service-account-token auth is active and enforced cluster-wide; no A2A call can succeed without a valid SA token; cross-stack permission grants are declarable via CRD.
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07
**Success Criteria** (what must be TRUE):
  1. An A2A call made by an agent in core-tools-lib carries a valid SA token in the Authorization header with audience matching ClusterAgentPolicy.spec.auth.tokenAudience; calls without a token are rejected 401 at the receiving agent.
  2. A platform agent validates the incoming SA token via OIDC JWKS local verification (not TokenReview per-call); tokens are cached per exp claim; a valid token with correct audience reaches the handler; an invalid token is rejected before the handler executes.
  3. A NetworkPolicy in agent-system namespace blocks unauthenticated A2A calls; verified by attempting an unauthenticated call from a test pod and receiving a connection refusal.
  4. An AgentAccessPolicy CR deployed in a target namespace grants the declared cross-stack RBAC roles; AgentAccessReconciler creates the corresponding RoleBinding; removing the CR removes the binding.
  5. A developer running kind or minikube can set AUTH_MODE=none and reach agents without SA tokens; a loud warning log is emitted on startup confirming the override is active.
**Hard gate (must be verified before Phase 4 begins)**: ClusterAgentPolicy auth.mode=serviceAccountToken is active and verified against the production cluster; no unauthenticated A2A call can succeed.
**Plans**: TBD

### Phase 3: Skill-Resolver + Composable CRDs
**Goal**: Orchestrator pods resolve skills dynamically via a localhost sidecar rather than env-var injection; the AgentStack CRD is decomposed into composable CRDs; existing AgentStack CRs are migrated with zero downtime.
**Depends on**: Phase 2
**Requirements**: ROUT-01, ROUT-02, ROUT-03, ROUT-04, ROUT-05, ROUT-06, ROUT-07, ROUT-08, ROUT-09, ROUT-10, ROUT-11
**Success Criteria** (what must be TRUE):
  1. Conversion webhook is live and tested on all existing AgentStack CRs before the controller update removing old field handlers is applied; existing stacks continue operating without manual intervention through the controller rollout.
  2. An orchestrator pod injected with the skill-resolver sidecar resolves GET localhost:2020/resolve?skill=X to the correct agent URL; the agent container does not start until the init container confirms localhost:2020/health returns 200 (cache warm).
  3. skill-resolver returns 503 when the requested skill has no healthy AgentDirectory entry; returns 403 when the calling agent's SA lacks AgentAccessPolicy permission for the target skill.
  4. skill-resolver uses a cluster-scoped informer (backed by a ClusterRoleBinding per agent SA) and resolves skills from all namespaces — not just the pod's own namespace.
  5. AgentStack, AgentPolicy, and AgentRoute CRDs are deployed and recognized by the cluster; AgentStackReconciler watches both AgentStack and AgentDirectory CRDs and reconciles their relationship.
**Critical note (highest-risk phase)**: The conversion webhook for existing AgentStack CRs MUST be deployed and verified on live CRs BEFORE the controller update that removes old field handlers. Failure leaves existing stacks in an unrecoverable error state requiring manual CR deletion. Treat this as a mandatory pre-deployment gate, not a nice-to-have ordering preference.
**Plans**: TBD

### Phase 4: Platform Stack Deployment
**Goal**: Seven platform agents are running in agent-platform namespace, protected by StackIsolationMiddleware, with per-stack rate limits and a complete audit trail for every cross-stack call.
**Depends on**: Phase 3 (and Phase 2 auth hard gate verified)
**Requirements**: PLAT-01, PLAT-02, PLAT-03, PLAT-04, PLAT-05, PLAT-06, PLAT-07
**Success Criteria** (what must be TRUE):
  1. All 7 platform agents (document-intelligence, search-retrieval, action-executor, memory-context, risk-classifier, generate-report, store-memory) are Running in agent-platform namespace with PLATFORM_AGENT=true and TASK_STORE_URL injected by AgentReconciler.
  2. A cross-stack A2A call to a platform agent without an X-Stack-Id header is rejected 400 before reaching the handler; a call with a valid X-Stack-Id header is processed and produces an audit log entry (stack-id, skill, task-id, timestamp, response code).
  3. Per-stack rate limits are enforced in-process; exceeding the limit returns 429; rate limits are documented as per-replica values (not cluster-wide) to prevent false compliance assumptions.
  4. AgentStackReconciler refuses to mark any agent-platform namespace stack Ready if ClusterAgentPolicy auth.mode is not serviceAccountToken — preventing deployment of platform agents before auth is enforced.
**Hard gate check**: Confirm Phase 1 task-store HA and Phase 2 auth enforcement before beginning Phase 4 deployment.
**Plans**: TBD

### Phase 5: Domain Stack Onboarding
**Goal**: Domain teams can declare semver capability constraints on peer stacks and configure per-request agent behavior via AgentRubric CRDs; the skill-resolver enforces the 8KB header threshold.
**Depends on**: Phase 4
**Requirements**: DOM-01, DOM-02, DOM-03, DOM-04, DOM-05, DOM-06, DOM-07
**Success Criteria** (what must be TRUE):
  1. An AgentStack with a peerStacks semver constraint (e.g., >=1.2.0) that is not met by the live AgentDirectory version emits a CapabilityVersionWarning condition; the reconciler requeues with RequeueAfter: 5m (not a hot-loop Requeue: true).
  2. A domain team patches an AgentRubric CR; the skill-resolver injects the rubric content as X-Agent-Rubric on the next platform agent call without a pod restart.
  3. skill-resolver correctly sends X-Agent-Rubric-Ref (not inline content) for rubrics whose serialized size exceeds 8KB; the platform agent fetches the rubric by ref from the k8s API and caches it per generation.
  4. A platform agent receiving X-Agent-Rubric-Ref fetches and applies the rubric correctly; a rubric with unchanged generation uses the cached copy without a k8s API call.
**Critical note**: AgentRubric 8KB header threshold enforcement is mandatory, not optional. The 8KB limit is an nginx/envoy proxy-layer hard constraint — rubrics exceeding it silently fail at the network layer without this mitigation.
**Plans**: TBD

### Phase 6: MCP Aggregator
**Goal**: An AgentStack with spec.mcp.aggregated: true gets a dedicated MCP aggregator that presents all skills in the stack as versioned MCP tools, refreshing dynamically as AgentDirectory changes.
**Depends on**: Phase 5
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04
**Success Criteria** (what must be TRUE):
  1. An AgentStack with spec.mcp.aggregated: true has a corresponding MCP aggregator deployed; LLM clients can enumerate tools from it via the MCP protocol.
  2. When a new agent is added to AgentDirectory (or an existing entry is updated), the MCP aggregator refreshes its tool registry; tool names follow the {agent_name}_v{major}__{tool_name} versioning scheme.
  3. In-flight MCP tool calls complete against the registry generation that was active when the call started; the new tool registry generation is only exposed to new calls after the swap.
**Plans**: TBD

### Phase 7: Governance & Hardening
**Goal**: The platform has continuous drift detection between its three state planes, a ratified audit log data contract, SLO dashboards for all platform agents, and a documented promotion process for new agents.
**Depends on**: Phase 6
**Requirements**: GOV-01, GOV-02, GOV-03, GOV-04, GOV-05, GOV-06
**Success Criteria** (what must be TRUE):
  1. ClusterAgentDirectoryHealthCheck runs every 60 seconds and performs a three-way comparison of Agent CRs, AgentDirectory entries, and inventory-api records; a DirectoryDriftDetected event and Prometheus counter increment are observable when divergence persists across 2 consecutive runs AND the affected pod has been Ready for >60s (prevents false positives on rolling restarts).
  2. A Grafana dashboard exists for each of the 7 platform agents showing SLO metrics (error rate, latency p99, request rate); dashboards are queryable in the production cluster.
  3. The audit log data contract (schema, retention policy, tamper-evidence mechanism) is documented and ratified before any regulated domain stack (legal, clinical, financial) goes live in the cluster.
  4. The AgentPromotion process is documented with enforced RBAC gates covering: versioned API contract, integration test suite, SLO declaration, and on-call runbook; a test promotion run completes successfully end-to-end.
**Research flag (before planning)**: Audit log compliance requirements (GDPR 90-day minimum, clinical 7-year retention) and tamper-evidence design must be resolved before Phase 7 planning begins. Do not defer to implementation.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Runtime Foundation | 0/TBD | Not started | - |
| 2. Mandatory Auth | 0/TBD | Not started | - |
| 3. Skill-Resolver + Composable CRDs | 0/TBD | Not started | - |
| 4. Platform Stack Deployment | 0/TBD | Not started | - |
| 5. Domain Stack Onboarding | 0/TBD | Not started | - |
| 6. MCP Aggregator | 0/TBD | Not started | - |
| 7. Governance & Hardening | 0/TBD | Not started | - |
