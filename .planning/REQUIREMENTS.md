# Requirements: Federated Agent Stack v2

**Defined:** 2026-04-22
**Core Value:** Agents can be deployed, discovered, and called across domain boundaries via k8s-native APIs — with zero per-agent configuration of auth, routing, or observability.

## v1 Requirements

### INFRA — Runtime Foundation

- [ ] **INFRA-01**: AgentDirectory CRD deployed with entries (agentName, version, URL, skills[], cardHash, readyAt)
- [ ] **INFRA-02**: AgentReconciler injects registry-announcer sidecar into every agent pod
- [ ] **INFRA-03**: registry-announcer patches AgentDirectory CR as primary write (blocks pod ReadinessGate)
- [ ] **INFRA-04**: registry-announcer writes inventory-api as secondary write (best-effort background retry queue)
- [ ] **INFRA-05**: registry-announcer re-announces on restart using idempotent cardHash comparison
- [ ] **INFRA-06**: task-store service implements A2A TaskStore interface over HTTP
- [ ] **INFRA-07**: task-store deployed with dedicated Postgres + PgBouncer (not shared with inventory-api DB)
- [ ] **INFRA-08**: task-store deployed with 2+ replicas (HA verified before P4)
- [ ] **INFRA-09**: TaskStoreClient in core-tools-lib reads TASK_STORE_URL; falls back to InMemoryTaskStore in dev
- [ ] **INFRA-10**: create_agent_app() uses TaskStore.from_env() by default (not hardcoded InMemoryTaskStore)
- [ ] **INFRA-11**: ClusterAgentPolicy CRD deployed with auth, OTEL, and resilience defaults
- [ ] **INFRA-12**: AgentPolicyReconciler merges ClusterAgentPolicy defaults into namespace AgentPolicy

### AUTH — Mandatory Authentication

- [ ] **AUTH-01**: A2AClient in core-tools-lib injects SA token on all A2A calls
- [ ] **AUTH-02**: A2AClient requests token with audience matching ClusterAgentPolicy.spec.auth.tokenAudience
- [ ] **AUTH-03**: Platform agents validate SA tokens via OIDC JWKS (cached per exp claim, not TokenReview per-call)
- [ ] **AUTH-04**: AgentAccessPolicy CRD deployed in target namespace for cross-stack permission grants
- [ ] **AUTH-05**: AgentAccessReconciler enforces RBAC roles from AgentAccessPolicy
- [ ] **AUTH-06**: AUTH_MODE=none dev override available with loud warning log (kind/minikube support)
- [ ] **AUTH-07**: NetworkPolicy in agent-system namespace blocks unauthenticated A2A calls

### ROUT — Routing & Composable CRDs

- [ ] **ROUT-01**: AgentReconciler injects skill-resolver sidecar into orchestrator pods
- [ ] **ROUT-02**: skill-resolver serves GET /resolve?skill=X&minVersion=Y&stackId=Z at localhost:2020
- [ ] **ROUT-03**: skill-resolver returns 503 when skill unavailable; 403 when AgentAccessPolicy denies
- [ ] **ROUT-04**: skill-resolver uses cluster-scoped informer to watch AgentDirectory across all namespaces
- [ ] **ROUT-05**: Init container polls localhost:2020/health before agent container starts (prevents sidecar race)
- [ ] **ROUT-06**: AgentReconciler creates ClusterRoleBinding per agent SA (skill-resolver-reader ClusterRole)
- [ ] **ROUT-07**: AgentStack CRD updated to minimal spec (membership + topology + semver agentRef)
- [ ] **ROUT-08**: AgentPolicy CRD available for namespace-level observability overrides
- [ ] **ROUT-09**: AgentRoute CRD available for per-skill routing and load balancing
- [ ] **ROUT-10**: Conversion webhook deployed before controller removes old AgentStack fields (zero-downtime migration)
- [ ] **ROUT-11**: AgentStackReconciler deployed; watches AgentStack + AgentDirectory CRDs

### PLAT — Platform Agent Tier

- [ ] **PLAT-01**: 7 platform agents deployed in agent-platform namespace (document-intelligence, search-retrieval, action-executor, memory-context, risk-classifier, generate-report, store-memory)
- [ ] **PLAT-02**: StackIsolationMiddleware auto-injected when PLATFORM_AGENT=true env var set
- [ ] **PLAT-03**: X-Stack-Id header required and validated on all cross-stack A2A calls
- [ ] **PLAT-04**: Per-stack in-process rate limits enforced (documented as per-replica, not cluster-wide)
- [ ] **PLAT-05**: Audit log written for each cross-stack call (stack-id, skill, task-id, timestamp, response code)
- [ ] **PLAT-06**: AgentReconciler injects PLATFORM_AGENT=true and TASK_STORE_URL into platform agent pods
- [ ] **PLAT-07**: AgentStackReconciler refuses platform namespace stacks Ready if ClusterAgentPolicy auth not active

### DOM — Domain Stack Onboarding

- [ ] **DOM-01**: peerStacks semver constraints validated by AgentStackReconciler against live AgentDirectory
- [ ] **DOM-02**: CapabilityVersionWarning condition emitted when semver constraint unmet
- [ ] **DOM-03**: Unsatisfied semver constraints requeue with RequeueAfter: 5m (no hot-loop)
- [ ] **DOM-04**: AgentRubric CRD available for per-request behavioral config on platform agents
- [ ] **DOM-05**: skill-resolver injects X-Agent-Rubric header on platform agent calls
- [ ] **DOM-06**: skill-resolver enforces 8KB limit on X-Agent-Rubric; sends X-Agent-Rubric-Ref for larger rubrics
- [ ] **DOM-07**: Platform agents read rubric from X-Agent-Rubric header or fetch by ref from k8s API (cached per generation)

### MCP — MCP Aggregator

- [ ] **MCP-01**: MCP aggregator deployed per AgentStack with spec.mcp.aggregated: true
- [ ] **MCP-02**: MCP aggregator watches AgentDirectory via k8s informer; refreshes tool registry on add/update events
- [ ] **MCP-03**: Tool names versioned as {agent_name}_v{major}__{tool_name}
- [ ] **MCP-04**: Generation-based tool registry swap (in-flight requests complete against old registry)

### GOV — Governance & Hardening

- [ ] **GOV-01**: ClusterAgentDirectoryHealthCheck runs on 60s interval; three-way comparison of Agent CRs, AgentDirectory, inventory-api
- [ ] **GOV-02**: Drift detection uses 120s grace period + 2-consecutive-run threshold before firing
- [ ] **GOV-03**: DirectoryDriftDetected event emitted on divergence; Prometheus counter incremented; alert at 5-minute drift
- [ ] **GOV-04**: Audit log data contract defined (schema, retention policy, tamper-evidence) before regulated domain stacks go live
- [ ] **GOV-05**: SLO dashboards for all 7 platform agents in Grafana
- [ ] **GOV-06**: AgentPromotion process documented with RBAC enforcement (versioned API contract, integration tests, SLO declaration, on-call runbook)

## v2 Requirements

Deferred to future milestone.

### Cross-Cluster Federation

- **FED-01**: Federated registry service aggregating multiple clusters' AgentDirectory CRs
- **FED-02**: Agent mesh gateway for cross-cluster A2A routing

### Auth Modes

- **AUTH-08**: OAuth 2.0 auth mode support in ClusterAgentPolicy
- **AUTH-09**: mTLS auth mode support in ClusterAgentPolicy

### Hardening

- **GOV-07**: Redis-backed cluster-wide rate limiting in StackIsolationMiddleware (replaces per-replica in-process)
- **GOV-08**: JWKS key rotation handling (re-fetch on first 401 after rotation)
- **DOM-08**: AgentRubric versioning and changelog tracking

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cross-cluster federation | Single k8s cluster assumption; different discovery mechanism required; v2 concern |
| Service mesh (Istio/Linkerd) | Auth/routing/observability handled by k8s-native CRDs and sidecars — would duplicate concerns |
| gRPC for skill-resolver API | HTTP localhost is debuggable and sufficient; gRPC adds protobuf schema maintenance |
| Admission webhooks for AgentAccessPolicy enforcement | Call-time enforcement via skill-resolver sidecar is the correct enforcement point (webhooks don't block runtime calls) |
| Real-time agent streaming | Current A2A request/response model sufficient for v1.0 |

## Traceability

Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |
| INFRA-06 | Phase 1 | Pending |
| INFRA-07 | Phase 1 | Pending |
| INFRA-08 | Phase 1 | Pending |
| INFRA-09 | Phase 1 | Pending |
| INFRA-10 | Phase 1 | Pending |
| INFRA-11 | Phase 1 | Pending |
| INFRA-12 | Phase 1 | Pending |
| AUTH-01 | Phase 2 | Pending |
| AUTH-02 | Phase 2 | Pending |
| AUTH-03 | Phase 2 | Pending |
| AUTH-04 | Phase 2 | Pending |
| AUTH-05 | Phase 2 | Pending |
| AUTH-06 | Phase 2 | Pending |
| AUTH-07 | Phase 2 | Pending |
| ROUT-01 | Phase 3 | Pending |
| ROUT-02 | Phase 3 | Pending |
| ROUT-03 | Phase 3 | Pending |
| ROUT-04 | Phase 3 | Pending |
| ROUT-05 | Phase 3 | Pending |
| ROUT-06 | Phase 3 | Pending |
| ROUT-07 | Phase 3 | Pending |
| ROUT-08 | Phase 3 | Pending |
| ROUT-09 | Phase 3 | Pending |
| ROUT-10 | Phase 3 | Pending |
| ROUT-11 | Phase 3 | Pending |
| PLAT-01 | Phase 4 | Pending |
| PLAT-02 | Phase 4 | Pending |
| PLAT-03 | Phase 4 | Pending |
| PLAT-04 | Phase 4 | Pending |
| PLAT-05 | Phase 4 | Pending |
| PLAT-06 | Phase 4 | Pending |
| PLAT-07 | Phase 4 | Pending |
| DOM-01 | Phase 5 | Pending |
| DOM-02 | Phase 5 | Pending |
| DOM-03 | Phase 5 | Pending |
| DOM-04 | Phase 5 | Pending |
| DOM-05 | Phase 5 | Pending |
| DOM-06 | Phase 5 | Pending |
| DOM-07 | Phase 5 | Pending |
| MCP-01 | Phase 6 | Pending |
| MCP-02 | Phase 6 | Pending |
| MCP-03 | Phase 6 | Pending |
| MCP-04 | Phase 6 | Pending |
| GOV-01 | Phase 7 | Pending |
| GOV-02 | Phase 7 | Pending |
| GOV-03 | Phase 7 | Pending |
| GOV-04 | Phase 7 | Pending |
| GOV-05 | Phase 7 | Pending |
| GOV-06 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 49 total
- Mapped to phases: 49
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-22*
*Last updated: 2026-04-22 after initial definition*
