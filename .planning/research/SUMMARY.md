# Project Research Summary

**Project:** Federated Agent Stack v2 — agent-orchestration platform
**Domain:** Kubernetes-native AI agent orchestration with A2A + MCP federation
**Researched:** 2026-04-21
**Confidence:** HIGH

## Executive Summary

This project delivers a v2 milestone for a Kubernetes-native AI agent orchestration platform. The core architectural shift is decoupling the runtime skill-discovery plane (AgentDirectory CRD + skill-resolver sidecar) from the management plane (inventory API), replacing static `PEER_*_URL` environment variables with dynamic, informer-driven resolution. All new components are k8s-native: sidecars injected by the existing agent-controller, CRDs registered in the existing `agents.orchestration.io/v1alpha1` group, and reconcilers added to the existing controller-runtime manager. The design is explicitly layered — the current God Object AgentStack is decomposed into composable CRDs (AgentStack, AgentPolicy, AgentRoute, AgentAccessPolicy) so each concern is independently evolvable.

The recommended approach is a strict 7-phase delivery where each phase is independently deployable without breaking the prior phase. The critical constraint is that mandatory SA token auth (P2) must be live and verified before platform agents (P4) deploy — the architecture document explicitly identifies deferring auth as a structural error that leaves action-executor callable unauthenticated. Similarly, the task-store service must reach HA (2+ replicas + PgBouncer + backup) before P4 proceeds because it is the sole persistent task state for all platform agents. Both represent hard sequential gates, not soft recommendations.

The primary implementation risks are: (1) a non-trivial conversion webhook needed in P3 to migrate existing AgentStack CRs to the composable spec without a service window, (2) the `AutomountServiceAccountToken: false` hardening currently in place that will silently block all sidecar k8s API access unless changed in P1, (3) per-replica (not cluster-wide) rate limiting in P4 that must be explicitly documented to avoid false compliance assumptions, and (4) the 8KB HTTP header limit for AgentRubric payloads that is a hard proxy-layer constraint requiring a ref-based fallback in P5. These risks are all well-understood and have defined mitigations — none are blockers if addressed in the correct phase.

## Key Findings

### Recommended Stack

The stack is predominantly additive to what already exists. Go dependencies added are `github.com/Masterminds/semver/v3` (semver constraint parsing in AgentStackReconciler) and `github.com/lestrrat-go/jwx/v2` (OIDC JWKS token validation). Python dependencies added are `PyJWT>=2.8` (SA token validation), `limits>=3.13` (per-stack rate limiting in StackIsolationMiddleware), `tenacity>=8.5` (retry logic in registry-announcer), and the `kubernetes` Python client (CRD writes from registry-announcer). Infrastructure additions are a dedicated Postgres instance for task-store (must NOT share inventory-api's instance) and a PgBouncer sidecar alongside it. The skill-resolver is a standalone Go binary (`skill-resolver/` with its own `go.mod`) — not part of the controller binary.

Key avoided over-engineering: no Redis until P7 (in-process rate limiting is sufficient for v1.0), no gRPC (HTTP localhost is debuggable and sufficient), no service mesh (auth/routing/observability handled by k8s-native CRDs and sidecars), no admission webhooks for policy enforcement (call-time enforcement via skill-resolver is structurally correct).

**Core technologies:**
- `github.com/Masterminds/semver/v3` v3.3.x: semver constraint parsing — de-facto standard in Go k8s ecosystem (Helm, controller-runtime use it)
- `github.com/lestrrat-go/jwx/v2` v2.1.x: OIDC JWKS validation — mature, supports auto-refresh and exp claim caching; avoids TokenReview API latency on hot path
- `PyJWT>=2.8`: Python SA token validation — lighter than python-jose for OIDC JWKS; sufficient for v1.0 auth mode
- `limits>=3.13`: per-stack rate limiting in StackIsolationMiddleware — FastAPI-compatible async, in-memory moving window; Redis backend deferred to P7
- `tenacity>=8.5`: retry logic in registry-announcer secondary write queue — exponential backoff with jitter, clean abstraction
- PgBouncer sidecar: connection pooling for task-store — 50 agent connections collapse to ~10 Postgres connections
- `controller-runtime v0.19.0` (existing): all new reconcilers join the existing manager — no version change required

### Expected Features

The v1.0 milestone is the full federated agent stack v2. All 7 phases must complete for the milestone to be coherent — there is no reduced scope delivery.

**Must have (table stakes — v1.0 structurally incomplete without these):**
- AgentDirectory CRD with structured entries (agentName, version, url, skills[], cardHash) — all runtime consumers read from here; without it the controller still depends on inventory API HTTP at reconcile time
- registry-announcer sidecar — dual write to AgentDirectory (primary, blocking pod Ready gate) + inventory API (best-effort background retry); bridge between management and runtime plane
- skill-resolver sidecar — localhost:2020 resolution API; in-process hashmap hot path; init container readiness gate required
- task-store service (FastAPI + Postgres + PgBouncer) — centralized task state; must be HA before P4
- ClusterAgentPolicy CRD — cluster-scoped auth, OTEL, and resilience defaults; cluster-governed, platform team owned
- Mandatory SA token auth enforced from P2 — OIDC JWKS local validation; no opt-out by design
- AgentAccessPolicy CRD — cross-stack permission grants; namespace-scoped in target namespace; enforced by skill-resolver at resolution time
- StackIsolationMiddleware — auto-injected when PLATFORM_AGENT=true; X-Stack-Id required; per-stack rate limits and audit log
- AgentStack minimal spec — composable CRD replacing God Object; semver constraints on peerStacks capabilities
- Semver constraint validation — Masterminds/semver/v3 in Go; CapabilityVersionWarning condition on unmet constraints
- AgentDirectory drift detection — 60s interval; three-way comparison of Agent CRs, AgentDirectory entries, inventory API

**Should have (differentiators that make this production-worthy):**
- skill-resolver pre-flight AgentAccessPolicy enforcement — access control at the single chokepoint before any network call, stronger guarantee than middleware-only
- AgentRubric CRD with per-request behavioral config — domain teams change risk classification by patching a CRD, not redeploying; 8KB header threshold with ref-based fallback for large configs
- Versioned tool naming in MCP aggregator (agent_v1__tool) — LLM clients detect schema changes; generation-based swap for in-flight safety
- Per-stack rate limits with PriorityClass differentiation — prod stacks get headroom; non-prod stacks isolated
- AgentPromotion process with RBAC enforcement — structured promotion gates (versioned API contract, integration tests, SLO declaration, on-call runbook)
- Helm chart wrapping composable CRDs — domain team onboarding UX; one values.yaml generates all four CRDs

**Defer to v1.x:**
- JWKS rotation handling (trigger: first 401 after key rotation in production)
- Rubric versioning and changelog tracking
- AgentPromotion GitHub Action validation (trigger: first promotion PR)

**Defer to v2+:**
- Cross-cluster AgentDirectory federation (requires federated registry service; entirely different complexity class)
- OAuth/MTLS auth modes (SA token is mandatory v1.0 mode only)
- Real-time agent streaming

### Architecture Approach

The architecture is an extension of the existing agent-controller pattern. All new CRDs join `agents.orchestration.io/v1alpha1` via the existing SchemeBuilder — no new API group. All new reconcilers register with the existing controller-runtime manager in `main.go`. The skill-resolver is a standalone Go binary (`skill-resolver/` with its own `go.mod`) that runs as a sidecar injected by AgentReconciler into orchestrator pods. The registry-announcer is a Python sidecar injected similarly. task-store, MCP aggregator, and platform agents are independent services. Two existing gaps must be fixed in P1: `create_agent_app()` hardcodes `InMemoryTaskStore()` and `AutomountServiceAccountToken` is currently `ptr(false)` — both must change before sidecars can function.

**Major components:**
1. **AgentDirectory CRD** — namespace-scoped; single source of truth for all runtime skill consumers; written by registry-announcer, read by skill-resolver/AgentStackReconciler/MCP aggregator
2. **registry-announcer sidecar** — Python; dual write (AgentDirectory primary, inventory API best-effort); idempotent patch by agentName + cardHash comparison; background retry queue for inventory API failures
3. **skill-resolver sidecar** — Go binary; localhost:2020 HTTP; in-process hashmap backed by k8s informer (cluster-scoped ClusterRoleBinding); pre-flight AgentAccessPolicy check; AgentRubric header injection; 8KB rubric threshold enforcement
4. **task-store service** — Python FastAPI; implements a2a-sdk TaskStore interface over HTTP; PgBouncer connection pooling; dedicated Postgres instance; must be HA before P4
5. **AgentStackReconciler** — validates semver constraints against live AgentDirectory; emits CapabilityVersionWarning; enforces that platform namespace stacks require active ClusterAgentPolicy auth
6. **StackIsolationMiddleware** — auto-injected into platform agents; requires X-Stack-Id header; per-stack in-process rate limiter (per-replica, not cluster-wide in v1.0); audit log per call
7. **MCP aggregator** — Python/FastMCP; watches AgentDirectory via informer; generation-based tool registry swap; versioned tool naming ({agent}_{version_major}v__{tool})
8. **Platform agents (7)** — deployed in agent-platform namespace; all require StackIsolationMiddleware, AgentAccessPolicy grants, and task-store

### Critical Pitfalls

1. **AutomountServiceAccountToken=false blocks all sidecar k8s API access (P1)** — Change `buildDeploymentSpec` to `ptr(true)` for sidecar-injected pods in P1. Defer fine-grained projected volume mounts to P7.

2. **controller-gen not re-run after new CRD type files (P1)** — `zz_generated.deepcopy.go` will be missing DeepCopy methods; controller panics at startup. Add a CI check: `make generate && git diff --exit-code` blocking any PR that adds `*_types.go`.

3. **Platform agents deployed before auth is enforced (P4)** — action-executor makes external system calls; if live before P2 auth, any pod in the cluster can call it unauthenticated. Hard gate: AgentStackReconciler refuses to mark agent-platform namespace stacks Ready if ClusterAgentPolicy auth.mode is not serviceAccountToken.

4. **AgentStack CRD conversion webhook downtime window (P3)** — If the controller removes old field handlers before the conversion webhook is live, existing stacks enter an unrecoverable error state. Deploy conversion webhook and AgentPolicy CRD BEFORE deploying the updated controller. Run old and new field handling in parallel for one release cycle.

5. **AgentRubric header exceeds 8KB nginx/envoy defaults (P5)** — Large legal clause library rubrics silently fail at the proxy layer. skill-resolver must enforce the 8KB hard limit and use X-Agent-Rubric-Ref above threshold. Mandatory in P5, not optional.

Additional phase-specific pitfalls:
- P1: registry-announcer partial write failure — idempotent re-announcement on restart + dead-letter retry queue for inventory API
- P1: task-store not HA before P4 — hard gate in STATE.md
- P2: OIDC dev environment JWKS unavailability — AUTH_MODE=none override for kind/minikube with loud warning log
- P2: token audience mismatch — A2AClient must request token with same audience as ClusterAgentPolicy.spec.auth.tokenAudience
- P3: skill-resolver init container race — init container polls localhost:2020/health; skill-resolver only returns 200 after cache.WaitForCacheSync
- P3: skill-resolver informer scoped to wrong namespace — must use cluster-scoped informer (ClusterRoleBinding, not RoleBinding)
- P5: unsatisfiable semver constraint infinite requeue — use ctrl.Result{RequeueAfter: 5 * time.Minute}, not Requeue: true
- P7: drift detection false positives on rolling restarts — 120s grace period; only flag drift persisting across 2 consecutive health check runs AND pod Ready for >60s

## Implications for Roadmap

The architecture document defines a 7-phase plan. Research confirms this ordering is correct and tightly dependency-constrained. The roadmap should follow these phases closely.

### Phase 1: Runtime Foundation
**Rationale:** AgentDirectory CRD is the dependency root — every subsequent component reads from or writes to it. task-store must be HA before P4. Both must be stable before auth (P2) can be meaningfully enforced.
**Delivers:** AgentDirectory CRD + controller-gen regen, registry-announcer sidecar (dual write), task-store service (FastAPI + PgBouncer + dedicated Postgres), ClusterAgentPolicy CRD with defaults, TaskStoreClient in core-tools-lib
**Addresses:** AgentDirectory CRD, registry-announcer dual write, task-store service, ClusterAgentPolicy CRD
**Avoids:** AutomountServiceAccountToken=false blocking sidecars (fix in P1), controller-gen CI check (add in P1), registry-announcer partial write divergence
**Hard gates before P2:** task-store HA verified; AgentDirectory CRD applies cleanly; registry-announcer stable with idempotent re-announcement

### Phase 2: Mandatory Auth
**Rationale:** Auth must be live and verified before platform agents (P4) deploy. auth.mode=serviceAccountToken is cluster-governed and non-optional — deferring is a structural error per the architecture doc.
**Delivers:** ClusterAgentPolicy active + enforced, A2AClient updated with SA token injection (OIDC JWKS audience-matched), AgentAccessPolicy CRD available
**Addresses:** Mandatory SA token auth, AgentAccessPolicy CRD
**Avoids:** action-executor callable unauthenticated (P4 must confirm P2 verified), token audience mismatch, dev environment OIDC failure (AUTH_MODE=none override), AgentAccessPolicy wrong-namespace deployment (kubebuilder validation marker)

### Phase 3: Skill-Resolver + Composable CRDs
**Rationale:** skill-resolver depends on AgentDirectory (P1) and auth (P2) before injecting X-Stack-Id headers. The AgentStack conversion webhook is the riskiest delivery in the entire roadmap — it must deploy before the controller removes old field handlers.
**Delivers:** skill-resolver sidecar (localhost:2020, cluster-scoped informer, pre-flight access check, rubric injection), AgentStack minimal spec, AgentPolicy + AgentRoute CRDs, AgentStackReconciler, AgentAccessReconciler, conversion webhook for existing AgentStack CRs
**Addresses:** skill-resolver sidecar, AgentStack minimal spec, composable CRDs, skill-resolver 503/403 response format
**Avoids:** Conversion webhook downtime window (webhook before controller update), init container race (localhost:2020/health gate), cluster-scoped informer (not namespace-scoped)
**Research flag:** Conversion webhook implementation warrants a dedicated spike before P3 planning — non-trivial and failure mode is unrecoverable without manual CR deletion.

### Phase 4: Platform Stack Deployment
**Rationale:** Cannot proceed until P2 auth is verified (hard gate) and task-store is HA (hard gate). StackIsolationMiddleware depends on skill-resolver (P3) injecting X-Stack-Id headers.
**Delivers:** 7 platform agents in agent-platform namespace, StackIsolationMiddleware auto-injected (PLATFORM_AGENT=true), PLATFORM_AGENT env var injection from AgentReconciler
**Addresses:** StackIsolationMiddleware, platform agent deployment, AgentAccessPolicy required for all platform skills
**Avoids:** Per-replica rate limit misrepresentation (document explicitly: cluster limit / expected replicas = per-replica limit), platform agents live before auth

### Phase 5: Domain Stack Onboarding
**Rationale:** peerStacks semver constraints depend on AgentDirectory entries (P1) having version fields and skill-resolver (P3) validating them. AgentRubric depends on skill-resolver header injection (P3).
**Delivers:** peerStacks semver constraint validation (Masterminds/semver/v3), AgentRubric CRD, skill-resolver rubric header injection with 8KB threshold + ref-based fallback, CapabilityVersionWarning condition
**Addresses:** Semver constraint validation, AgentRubric CRD + header injection, AgentRubric 8KB threshold
**Avoids:** Unsatisfiable constraint infinite requeue (RequeueAfter: 5m), AgentRubric header exceeding 8KB limits (mandatory ref-based fallback)

### Phase 6: MCP Aggregator
**Rationale:** MCP aggregator watches AgentDirectory (P1) and deploys only when AgentStack.spec.mcp.aggregated: true (P3 CRD). Low-risk phase; standard k8s informer + FastMCP patterns.
**Delivers:** MCP aggregator service (FastMCP), AgentDirectory informer watch, versioned tool naming (agent_name_v1__tool), generation-based swap on add/update events
**Addresses:** MCP aggregator, versioned tool names, generation-based tool swap
**Avoids:** LLM client stale tool schema (versioned names; old version removed after 30-day deprecation window)

### Phase 7: Governance + Multi-Tenancy Hardening
**Rationale:** All structural components are live. P7 adds observability, compliance, and operational tooling that requires the prior phases to be stable enough to observe.
**Delivers:** ClusterAgentDirectoryHealthCheck (drift detection with 120s grace period), per-stack rate limits enforcement review + Redis backend planning, audit logging data contract (schema, retention, tamper-evidence), SLO dashboards (Grafana), AgentPromotion tooling scaffolding
**Addresses:** AgentDirectory drift detection, per-stack rate limits, audit logging, AgentPromotion tooling, SLO dashboards
**Avoids:** Drift detection false positives (120s grace period, 2-consecutive-run threshold), audit log format undefined for regulated domains (contract must be ratified before regulated stacks go live)
**Research flag:** Audit log compliance requirements (GDPR 90-day minimum, clinical 7-year retention) and tamper-evidence design warrant targeted research before P7 begins.

### Phase Ordering Rationale

- Dependency chain is hard: AgentDirectory (P1) → Auth (P2) → skill-resolver + composable CRDs (P3) → platform agents (P4) → domain stacks (P5) → MCP (P6) → hardening (P7). Skipping any phase or reordering P1-P4 breaks downstream components in non-recoverable ways.
- Two parallel tracks converge at P4: task-store HA and registry-announcer stability both must be achieved in P1 and verified before P4. These should be tracked as independent workstreams within P1.
- P3 conversion webhook is the highest-risk delivery: it is the only phase item where failure causes an unrecoverable cluster state without manual intervention. Deserves a dedicated spike before P3 begins.
- Auth before platform agents is non-negotiable: the architecture document identifies this as the one ordering constraint that must not be relaxed for security reasons.
- MCP aggregator (P6) is the lowest-risk phase: standard patterns, no migration concerns, no hard gates beyond AgentDirectory and AgentStack CRD existing.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (conversion webhook):** controller-runtime conversion webhook setup is non-trivial; CR migration logic (decomposing old AgentStack fields into AgentPolicy resources) has no standard recipe. Failure mode is unrecoverable. Warrants a spike before P3 planning.
- **Phase 7 (audit log compliance):** GDPR, clinical, and financial retention requirements vary. Tamper-evidence design depends on regulated domain specifics not fully defined in the architecture doc.
- **Phase 1 (a2a-sdk TaskStore interface):** Exact TaskStore abstract method signatures must be verified against installed a2a-sdk before TaskStoreClient is implemented. Known open question from architecture research.

Phases with standard patterns (skip research-phase):
- **Phase 6 (MCP aggregator):** FastMCP + k8s informer watch is well-documented; generation-based swap is a standard pattern.
- **Phase 2 (SA token auth):** OIDC JWKS local validation with PyJWT is well-established; audience validation is standard k8s SA token practice.
- **Phase 5 (semver constraints):** Masterminds/semver/v3 is well-documented; controller-runtime reconciler requeue patterns are standard.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Existing go.mod and pyproject.toml verified directly; new library choices are well-established ecosystem standards. No live Context7 verification due to researcher rate limit. |
| Features | HIGH | Primary source is the principal-architect architecture doc reviewed directly. Existing controller code inspected for gaps. Feature list derived from authoritative spec, not inference. |
| Architecture | HIGH | Direct code inspection of agent_controller.go, main.go, agent.py confirmed current state. Build order and integration boundaries derived from authoritative design doc. |
| Pitfalls | MEDIUM-HIGH | Derived from well-established k8s controller/sidecar/FastAPI failure mode patterns. Not verified against live docs due to researcher rate limit, but these patterns are stable. |

**Overall confidence:** HIGH

### Gaps to Address

- **a2a-sdk TaskStore interface signatures:** Must verify exact method signatures from installed package before implementing TaskStoreClient in P1. Resolution: inspect the installed a2a-sdk package in the repo Python environment before writing TaskStoreClient.
- **Cross-namespace AgentDirectory watch scope for skill-resolver:** ClusterRole must explicitly allow cluster-wide agentdirectories watch (not per-namespace RoleBinding). Must be applied and tested before P3 skill-resolver deployment.
- **MCP aggregator 1:1 relationship with AgentStack:** One aggregator per AgentStack with mcp.aggregated: true is stated but the controller deployment logic is not fully specified. Needs planning detail before P6.
- **Audit log data contract for regulated domains:** GDPR minimum 90 days; some clinical regulations require 7 years. Tamper-evidence design depends on regulatory requirements not fully defined. Must be resolved before any regulated domain stack enters production in P7.

## Sources

### Primary (HIGH confidence)
- `docs/federated-agent-stack.md` (2026-04-21) — principal-architect architecture document; authoritative source for feature scope, phase ordering, and design decisions
- `agent-controller/internal/controller/agent_controller.go` — confirmed current state: no sidecar injection, AutomountServiceAccountToken: ptr(false), existing reconciler patterns
- `agent-controller/cmd/main.go` — confirmed single reconciler registration, scheme registration pattern
- `core-tools-lib/src/core_tools/agent.py` — confirmed InMemoryTaskStore() hardcoded, no task_store param, no StackIsolationMiddleware
- `agent-controller/api/v1alpha1/agent_types.go` — confirmed CRD group agents.orchestration.io/v1alpha1, pattern for new CRD types
- `.planning/PROJECT.md` — milestone scope, constraints, key decisions

### Secondary (MEDIUM confidence)
- `agent-controller/go.mod` — confirmed controller-runtime v0.19.0, k8s 1.31 in use
- `agent-inventory-api/pyproject.toml` — confirmed asyncpg, FastAPI, SQLAlchemy in use
- `core-tools-lib/pyproject.toml` — confirmed FastMCP, httpx in dependency tree
- General ecosystem knowledge: Masterminds/semver standard in Go k8s ecosystem; PyJWT for OIDC; limits library for FastAPI rate limiting; nginx 8KB per-header default; envoy 60KB total header default; cache.WaitForCacheSync pattern for sidecar readiness gates

### Tertiary (LOW confidence — validate during implementation)
- a2a-sdk TaskStore abstract method signatures — not verified against installed package; must confirm before TaskStoreClient implementation
- Exact OIDC JWKS endpoint URL format for kind/minikube dev clusters — dev setup docs must verify reachability before P2 cutover

---
*Research completed: 2026-04-21*
*Ready for roadmap: yes*
