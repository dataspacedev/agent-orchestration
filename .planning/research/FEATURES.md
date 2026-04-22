# Feature Research

**Domain:** Federated Kubernetes-native AI agent orchestration platform (v2 milestone)
**Researched:** 2026-04-21
**Confidence:** HIGH — primary source is the principal-architect architecture document (docs/federated-agent-stack.md), supplemented by direct review of existing Go controller code and training knowledge of Kubernetes sidecar patterns, HTTP standards, semver libraries, and FastAPI middleware.

---

## Scope Note

This file covers ONLY new v2 milestone features. The following are already built and excluded:
Agent CR lifecycle reconciliation, inventory API CRUD, outbox sync, A2A/MCP protocol support in core-tools-lib, create_agent_app factory, example agent pattern, and agent registry UI.

---

## Feature Landscape

### Table Stakes (Required for v1.0 milestone to be coherent)

These are the features without which the v2 architecture is structurally incomplete. Missing any one of these means the stated goals (controller decoupled from inventory API, dynamic skill resolution, mandatory auth) are not met.

| Feature | Why Required | Complexity | Notes |
|---------|--------------|------------|-------|
| AgentDirectory CRD with structured entries | All v2 runtime consumers (skill-resolver, controller, MCP aggregator) read from this single source; without it the controller still depends on inventory API HTTP at reconcile time | MEDIUM | Fields: agentName, version, url, skills[], tags[], cardHash (SHA256), readyAt. Namespace-scoped. Group agents.orchestration.io/v1alpha1. The cardHash field is the staleness detection mechanism — announcer computes hash before write and skips write if hash matches. |
| registry-announcer sidecar — dual write to AgentDirectory + inventory API | The announcer is the bridge between management plane and runtime plane; without it AgentDirectory is never populated | HIGH | AgentDirectory write is primary (blocks pod Ready gate via readiness gate mechanism). Inventory API write is best-effort with background retry queue. Announcer must handle partial failure: written to AgentDirectory but inventory API call failed — this is acceptable; the reverse (inventory API written, AgentDirectory not written) is not. Restart mid-card-update requires idempotent patch semantics on the CR (patch by agentName key). |
| skill-resolver sidecar — localhost resolution API | Replaces static PEER_*_URL env vars; enables dynamic resolution without pod restarts | HIGH | Listens on localhost:2020. Watches AgentDirectory via informer — hot path is an in-process hashmap, not a network call. Init container readiness check pattern required: orchestrator container should not start until localhost:2020/health returns 200. Memory budget ~30MB per sidecar instance. Controller injects sidecar into orchestrator pods automatically (not domain team responsibility). |
| skill-resolver 503/403 response format | Orchestrators must handle degraded mode; without a structured error response they cannot distinguish "skill not found" from "skill unauthorized" from "agent unhealthy" | LOW | 503: {"error": "no agent satisfying skill=X and minVersion=Y is Ready", "retryAfter": N}. 403: {"error": "stack Z is not permitted to call skill X", "policyRef": "AgentAccessPolicy name"}. The retryAfter field on 503 enables orchestrators to implement degraded-mode with backoff instead of tight retry loops. |
| task-store service (FastAPI + Postgres + PgBouncer) | Decouples task state from inventory API DB; required before platform stack goes live (P4) | HIGH | Exposes A2A TaskStore interface over HTTP — agents call it rather than connecting to Postgres directly. This centralizes connection pooling: 50 agents → 50 connections to PgBouncer → pool of ~10 to Postgres. Controller injects TASK_STORE_URL env var; SDK picks it up via TaskStore.from_env(). Must have 2+ replica HA deployment and its own backup strategy before any domain stack depends on it. |
| ClusterAgentPolicy CRD — cluster-scoped auth + OTEL + resilience defaults | Auth cannot be per-team choice; without this SA token enforcement is unenforceable at cluster level | MEDIUM | Cluster-scoped (not namespace-scoped). Fields: tracing.endpoint, tracing.samplingRate, auth.mode (serviceAccountToken only for v1.0), auth.tokenAudience, resilience.defaultTimeoutSeconds, resilience.maxRetries, resilience.backoffMultiplier, resilience.circuitBreaker. Only one instance per cluster ("default"). Platform team owns it. |
| Mandatory SA token auth enforced from P2 | Auth that is opt-in is auth that gets skipped; the architecture document explicitly calls deferring auth to P6 (after federation is live) a structural error | HIGH | SA token injected by A2AClient in core-tools-lib on all outbound calls. Platform agents validate via local OIDC JWKS cache (not TokenReview per-call — TokenReview adds ~5ms and creates k8s API server load). Cached tokens validated against exp claim. Unauthenticated calls return 401. |
| AgentAccessPolicy CRD — cross-stack permission grants | action-executor and privileged skills must not be callable by default; without explicit grants the platform is ungoverned | MEDIUM | Namespace-scoped, lives in the target namespace (agent-platform). Rules: from.stackNamespace + from.stackName, allow.skills[]. requireAnnotation field for escalation-approved grants. Platform team is the approver — domain teams submit as PRs. Controller (AgentAccessReconciler) enforces the policy. |
| StackIsolationMiddleware in core-tools-lib | Noisy-neighbor isolation on platform agents; without it one domain stack can degrade all others | MEDIUM | Auto-injected when PLATFORM_AGENT=true env var is set by controller. Requires X-Stack-Id header (400 if missing). Per-stack rate limiter (check before forwarding). Audit log record per call (stack-id, skill, task-id, timestamp, response code). Rate limit returns 429. The X-Stack-Id is injected by skill-resolver sidecar on outbound A2A calls — domain agent code never sets it manually. |
| AgentStack minimal spec (membership + topology only) | Composable CRD decomposition; the God Object AgentStack is explicitly identified as a design flaw in the architecture doc | LOW | Fields: spec.agents[].name, spec.agents[].role, spec.agents[].agentRef.name, spec.agents[].agentRef.version (semver constraint), spec.peerStacks[].namespace, spec.peerStacks[].capabilities[].skill, spec.peerStacks[].capabilities[].minVersion, spec.peerStacks[].capabilities[].maxVersion, spec.mcp.aggregated. No auth, OTEL, or routing fields — those live in separate CRDs. |
| Semver constraint validation on peerStacks capabilities | Platform agents change versions; without constraints domain stacks silently break on major version bumps | MEDIUM | Go library: github.com/Masterminds/semver/v3 — this is the de-facto standard for semver constraint parsing in the Go ecosystem (supports ^, ~, >=, ranges). AgentStack controller validates constraints against live AgentDirectory entries before marking stack Ready. Emits CapabilityVersionWarning condition when constraint is satisfied only by a deprecated version. |
| AgentDirectory drift detection (ClusterAgentDirectoryHealthCheck) | Runtime divergence between AgentDirectory and live Agent CRs is undetectable without this | MEDIUM | Runs on 60s interval. Compares: active Agent CRs with Ready condition, corresponding AgentDirectory entries, corresponding inventory API entries. Divergence triggers DirectoryDriftDetected event and Prometheus counter. Alert threshold: drift > 5 minutes. DirectoryInSync condition on AgentDirectory CR. |

### Differentiators (What Makes This Platform Good)

These features are what distinguish this from a basic Kubernetes agent deployment tool and make it production-worthy for regulated domains.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| skill-resolver enforces AgentAccessPolicy pre-flight | Access control is enforced before any network call is made, at the single chokepoint that all skill lookups pass through | LOW | The sidecar checks the calling stack's access policy before returning a URL. This means no unauthorized traffic ever reaches the platform agent — it is rejected at resolution time, not at the platform agent's auth middleware. This is a stronger guarantee than middleware-only enforcement. |
| AgentRubric as per-request behavioral config | Domain teams change risk classification behavior by patching a CRD, not by redeploying a platform agent | HIGH | skill-resolver attaches active AgentRubric config as X-Agent-Rubric header on A2A calls. Platform agent reads rubric from request context and applies it for that request only. Header size threshold: 8KB (based on standard HTTP/1.1 header size limits — most servers/proxies reject headers > 8-16KB; nginx default is 8KB per header, 64KB total). Above 8KB, rubric must be referenced by CRD name and fetched by the platform agent from k8s API at request time (cached per rubric generation/resourceVersion). This ref-based fetch pattern avoids header size limits while keeping per-request config dynamic. |
| Versioned tool naming in MCP aggregator (agent_v1__tool) | LLM clients can detect when a tool schema changes between calls; prevents silent breakage during platform agent upgrades | LOW | Tool name format: {agent_name}_{version_major}v__{tool_name} (e.g., web_searcher_v1__search). Generation-based swap strategy: in-flight tools/call requests complete against the old tool registry; new requests use the updated one after AgentDirectory informer fires add/update event. No request cancellation on refresh. |
| AgentDirectory informer-driven MCP aggregator refresh | Tool registry stays current within the informer re-sync window (~1s) without polling or restarts | MEDIUM | Aggregator watches AgentDirectory CRD via k8s informer. On add/update events it rebuilds the tool proxy registry using the generation-based swap. The informer provides free caching, retries, and re-sync — no polling loop to maintain. |
| CardHash staleness detection on AgentDirectory entries | Announcer can detect when an agent's capability card has changed without re-reading the full card | LOW | SHA256 of AgentCard JSON stored in cardHash field. Announcer computes hash before each write; if hash matches existing entry the write is skipped, reducing etcd write pressure. Controller can also use cardHash to detect when an entry is stale without fetching the full card. |
| AgentPolicy namespace-level observability overrides | Domain teams can increase tracing sampling for their namespace without involving the platform team or touching cluster defaults | LOW | namespace-scoped. Inherits from ClusterAgentPolicy, can override samplingRate and eval.policyRef. Auth is NOT overridable — it is cluster-governed only. Owned by the domain team. |
| AgentRoute CRD — per-skill routing and load balancing | Platform team can configure routing policy (canary, weighted, active-active) for platform skills independently of deployment topology | MEDIUM | Independently evolvable from AgentStack membership. Platform team owns AgentRoute for platform skills. Enables rolling version transitions (parallel v1/v2 deployments with traffic splitting) during major version windows. |
| Per-stack rate limits with PriorityClass differentiation | Prod stacks get scheduler priority and rate limit headroom; non-prod stacks are isolated | LOW | k8s ResourceQuota limits total CPU/memory consumed by agents in platform-calling namespaces. PriorityClass differentiates prod from non-prod. StackIsolationMiddleware enforces per-stack rate limits via X-Stack-Id header. |
| AgentPromotion process with RBAC enforcement | Platform team controls what enters agent-platform namespace; RBAC on the namespace enforces this without relying on convention | MEDIUM | Domain team opens PR adding agent to agent-platform/platform-stack. PR requires: versioned API contract, integration test suite, SLO declaration, on-call runbook, StackIsolationMiddleware compatibility. GitHub Action validates required fields. RBAC: only platform team ServiceAccount can write to agent-platform namespace. |
| Helm chart wrapping all four composable CRDs | Domain teams interact with helm values; platform engineers interact with raw CRDs — learning surface is manageable | LOW | Single values.yaml generates AgentStack + AgentPolicy + AgentRoute + AgentAccessPolicy request from one file. Teams do not need to know about CRD decomposition to onboard. This is the primary UX surface for domain teams. |

### Anti-Features (Avoid These)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Polling-based AgentDirectory updates in skill-resolver | Simpler to implement than a k8s informer watch | Polling adds unnecessary latency (update visible only at next poll interval), increases k8s API server load linearly with number of sidecars, and requires tuning poll interval. Informers use Watch (HTTP long-poll over a single connection) and deliver updates in ~1s with free re-sync | Use k8s informer/cache pattern. The skill-resolver is a Go binary — controller-runtime's cache package is the right tool. |
| Per-agent TaskStore direct Postgres connections | Seems simpler than introducing task-store service | At 50 agents each with their own connection pool, you hit Postgres connection limits. Schema migrations on task state require coordinating all agent pods. No centralized connection pool management. | task-store service with PgBouncer proxy: agents call HTTP API, task-store manages the pool. |
| Shared inventory API DB for task state | Avoids a new service | Schema coupling between agent registry and task state. Connection pool exhaustion affects admin queries when agents are busy. Cannot scale task storage independently. | Dedicated task-store service with its own Postgres instance. Already a decided architecture change. |
| AgentRubric embedded in full as header for large configs | Simple — just serialize the whole rubric to JSON and put it in the header | HTTP/1.1 has no formal header size limit but servers enforce practical limits: nginx defaults to 8KB per header value and 64KB total header block; envoy defaults 60KB total; most HTTP clients truncate or error on headers > 8-16KB. Large rubric payloads (clause libraries with hundreds of patterns) will silently fail at the proxy layer before reaching the platform agent. | 8KB threshold: below threshold, inline in X-Agent-Rubric header. Above threshold, send rubric CRD reference as X-Agent-Rubric-Ref: {namespace}/{name}/{resourceVersion}. Platform agent fetches and caches per resourceVersion. |
| Optional auth with per-team opt-in | Easier to adopt incrementally | Auth that is opt-in is auth that gets skipped. The architecture document explicitly calls out deferring auth to P6 (after federation is live) as a structural error that creates a window where action-executor is accessible unauthenticated. | Mandatory SA token from P2 via ClusterAgentPolicy. No per-team choice on auth mode. |
| AgentAccessPolicy admission webhook enforcement | Admission webhooks provide immediate rejection on create/update | Admission webhooks are synchronous and add latency to every admission path; webhook unavailability blocks all resource creation in the cluster. For access control that is fundamentally about cross-namespace calls (not resource creation), controller-enforced policy at call time is more appropriate. | Controller-enforced: AgentAccessReconciler watches AgentAccessPolicy and propagates rules into the skill-resolver sidecar's in-process access map (via AgentDirectory annotations or a dedicated policy configmap). Admission webhook is appropriate for schema validation, not authorization logic. |
| Cross-cluster AgentDirectory federation | Logical extension — if we federate within a cluster, why not across clusters? | AgentDirectory is a namespace-scoped CRD. k8s informers do not cross cluster boundaries. Federating across clusters requires a separate discovery layer (federated registry service or agent mesh gateway) that is an entirely different architectural complexity class. | Single-cluster design for v1.0. Cross-cluster is explicitly out of scope in the architecture doc. Revisit in v2. |
| Behavioral change detection via semver alone | Semver is already required for API breaking changes | Semver signals structural API changes but not behavioral changes. A platform agent that changes its classify_risk scoring thresholds with the same schema is a semantic breaking change with no semver signal. | Convention: behavioral changes that affect downstream scoring must increment minor version AND include a changelog entry in AgentCard.metadata. Evaluation policy can compare rubric active at inference time with rubric at scoring time. |

---

## Feature Dependencies

```
AgentDirectory CRD
    └──required by──> registry-announcer sidecar (writes to it)
    └──required by──> skill-resolver sidecar (reads from it)
    └──required by──> MCP aggregator (watches it)
    └──required by──> AgentStack controller (validates semver constraints against it)
    └──required by──> AgentDirectory drift detection (reconciles against it)

registry-announcer sidecar
    └──required by──> AgentDirectory entries existing at all
    └──depends on──> inventory API (best-effort write path)
    └──depends on──> AgentDirectory CRD (primary write path)

skill-resolver sidecar
    └──required by──> dynamic skill resolution (no pod restarts needed)
    └──required by──> X-Stack-Id header injection on outbound calls
    └──required by──> AgentRubric header attachment
    └──required by──> pre-flight AgentAccessPolicy enforcement
    └──depends on──> AgentDirectory CRD (informer watch)
    └──depends on──> AgentAccessPolicy CRD (access rule cache)
    └──depends on──> AgentRubric CRD (rubric config lookup)

task-store service
    └──required by──> platform stack going live (P4)
    └──required by──> all agent pods that use TaskStore.from_env()
    └──independent of──> AgentDirectory (separate data plane concern)

ClusterAgentPolicy CRD
    └──required by──> mandatory SA token auth (P2)
    └──required by──> cluster-wide OTEL defaults
    └──inherited by──> AgentPolicy (namespace overrides)

AgentAccessPolicy CRD
    └──required by──> platform stack going live (any domain stack calling platform skills)
    └──enforced by──> skill-resolver sidecar (pre-flight check)
    └──enforced by──> AgentAccessReconciler in agent-controller

AgentStack minimal spec
    └──required by──> AgentPolicy (needs a stack to be namespace-scoped to)
    └──required by──> AgentRoute (routes are per-skill within a stack)
    └──required by──> semver constraint validation (agentRef.version field)
    └──replaces──> God Object AgentStack (one-time conversion webhook in P3)

StackIsolationMiddleware
    └──required by──> platform agents (PLATFORM_AGENT=true)
    └──requires──> X-Stack-Id header (injected by skill-resolver, not domain teams)
    └──requires──> per-stack rate limiter backend (Redis or in-process token bucket)

MCP aggregator
    └──depends on──> AgentDirectory CRD (informer watch for tool refresh)
    └──depends on──> AgentStack.spec.mcp.aggregated: true (controller deploys aggregator pod)
    └──produces──> versioned tool names (agent_v1__tool pattern)

Semver constraint validation
    └──depends on──> AgentDirectory entries with version field populated
    └──depends on──> AgentStack.spec.peerStacks[].capabilities[].minVersion
    └──uses──> github.com/Masterminds/semver/v3 in Go controller

AgentRubric CRD
    └──depends on──> skill-resolver sidecar (attaches rubric to outbound calls)
    └──consumed by──> platform agents that read X-Agent-Rubric or X-Agent-Rubric-Ref header
    └──independent of──> EvaluationPolicy (separate concerns, explicitly split in arch doc)

AgentDirectory drift detection
    └──depends on──> AgentDirectory CRD
    └──depends on──> Agent CR (compares against live CRs)
    └──depends on──> inventory API (three-way comparison)
    └──produces──> DirectoryDriftDetected event + Prometheus counter
```

### Dependency Notes

- **skill-resolver requires AgentDirectory CRD:** The sidecar watches the CRD via informer. Without the CRD existing in the API server, the informer registration fails at sidecar startup. Deploy CRD first (P1), sidecar second (P3).
- **task-store service must exist before P4:** The platform stack agents (7 agents in agent-platform namespace) require TASK_STORE_URL to be resolvable at pod start. task-store HA deployment and SLO must be validated before P4 begins.
- **Mandatory auth (P2) blocks cross-namespace calls:** Once ClusterAgentPolicy sets auth.mode: serviceAccountToken, any A2AClient that does not inject SA tokens will get 401. This affects all existing agents. core-tools-lib A2AClient must be updated before P2 cutover.
- **AgentStack conversion webhook (P3):** Migrating existing AgentStack CRs to the minimal spec requires a one-time conversion webhook. This is a non-trivial controller-runtime webhook — it must be tested thoroughly before P3. Existing AgentStack fields (OTEL, auth) must be decomposed into AgentPolicy resources in the same namespace.
- **AgentRubric conflicts with large-payload inline config:** The 8KB threshold is a hard constraint from HTTP infrastructure (nginx, envoy). Above it, the ref-based fetch pattern is mandatory, not optional.

---

## MVP Definition

### Launch With (v1.0 — all 7 phases must complete)

The v1.0 milestone IS the full federated agent stack v2. The phases define what goes in first, not what is deferred. Each phase must be independently deployable without breaking the previous phase.

- [x] **P1: Runtime foundation** — task-store service, AgentDirectory CRD, registry-announcer dual write, ClusterAgentPolicy CRD with defaults
- [x] **P2: Mandatory auth** — SA token enforced cluster-wide, A2AClient updated, AgentAccessPolicy CRD available
- [x] **P3: skill-resolver + composable CRDs** — sidecar injected by controller, AgentStack minimal spec, AgentPolicy + AgentRoute CRDs, conversion webhook for existing stacks
- [x] **P4: Platform stack deployment** — 7 platform agents in agent-platform namespace, AgentAccessPolicy required, StackIsolationMiddleware injected
- [x] **P5: Domain stack onboarding** — peerStacks semver constraints, AgentRubric CRD, controller validates constraints
- [x] **P6: MCP aggregator** — watches AgentDirectory, versioned tool names, generation-based swap
- [x] **P7: Governance + multi-tenancy hardening** — per-stack rate limits, audit logging, AgentPromotion tooling, drift detection, SLO dashboards

### Add After Validation (v1.x)

- [ ] **JWKS rotation handling in auth validation** — When cluster OIDC JWKS keys rotate, cached validators must refresh. The rotation window is typically 24h but edge cases exist. Trigger: first 401 from JWKS-validated token after key rotation.
- [ ] **Rubric versioning and changelog tracking** — AgentRubric changes affect evaluation accuracy for retrospective scoring. Add resourceVersion tracking in task trace to record which rubric was active at inference time.
- [ ] **Aggregated AgentDirectory across multiple namespaces** — The current design is namespace-scoped. Multi-namespace MCP aggregators need a cross-namespace read. Trigger: first domain stack that wants an MCP surface spanning multiple stacks.
- [ ] **AgentPromotion GitHub Action validation** — P7 mentions tooling but the GitHub Action is implementation detail, not a structural requirement. Trigger: first agent promotion PR.

### Future Consideration (v2+)

- [ ] **Cross-cluster federation** — Explicitly out of scope. Requires a federated registry service or agent mesh gateway. Revisit after v1.0 is stable.
- [ ] **OAuth/MTLS auth modes** — SA token is the mandatory v1.0 mode. OAuth and MTLS are explicitly excluded from v1.0 scope.
- [ ] **Real-time agent streaming** — Current A2A request/response model is sufficient. Streaming would require rethinking task-store write patterns.
- [ ] **Behavioral semver signals** — Formal convention for signaling behavioral changes (not just schema changes) in AgentCard.metadata. Needs platform-wide agreement before it can be enforced.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| AgentDirectory CRD | HIGH — everything reads from it | MEDIUM | P1 |
| registry-announcer sidecar | HIGH — populates AgentDirectory | HIGH | P1 |
| task-store service | HIGH — critical before P4 | HIGH | P1 |
| ClusterAgentPolicy CRD | HIGH — enables mandatory auth | MEDIUM | P1 |
| Mandatory SA token auth | HIGH — structural security requirement | HIGH | P2 |
| AgentAccessPolicy CRD | HIGH — governs privileged skill access | MEDIUM | P2 |
| skill-resolver sidecar | HIGH — enables dynamic resolution | HIGH | P3 |
| skill-resolver 503/403 format | MEDIUM — enables degraded mode handling | LOW | P3 |
| AgentStack minimal spec + conversion webhook | HIGH — CRD decomposition | HIGH | P3 |
| AgentPolicy + AgentRoute CRDs | MEDIUM — composability benefit | MEDIUM | P3 |
| StackIsolationMiddleware | HIGH — noisy-neighbor isolation | MEDIUM | P4 |
| 7 platform agents deployment | HIGH — core platform capability | HIGH | P4 |
| Semver constraint validation | HIGH — prevents silent breakage | MEDIUM | P5 |
| AgentRubric CRD + header injection | HIGH — per-request config without redeploy | HIGH | P5 |
| AgentRubric 8KB threshold + ref-based fetch | MEDIUM — handles large rubrics | MEDIUM | P5 |
| MCP aggregator with AgentDirectory watch | MEDIUM — MCP surface for LLM clients | MEDIUM | P6 |
| Versioned tool naming (agent_v1__tool) | MEDIUM — LLM client stability | LOW | P6 |
| Generation-based tool swap | MEDIUM — in-flight request safety | MEDIUM | P6 |
| AgentDirectory drift detection | MEDIUM — operational observability | MEDIUM | P7 |
| Per-stack rate limits enforcement | HIGH — platform stability | MEDIUM | P7 |
| Audit logging for cross-stack calls | HIGH — regulated domain requirement | MEDIUM | P7 |
| AgentPromotion tooling (GitHub Action) | LOW — process support | LOW | P7 |
| SLO dashboards in Grafana | MEDIUM — platform reliability visibility | LOW | P7 |
| Helm chart wrapping composable CRDs | MEDIUM — domain team onboarding UX | LOW | P3/P5 |

**Priority key:**
- P1: Must have before anything else (P1 phase)
- P2: Depends on P1 (P2 phase)
- P3/P4/P5/P6/P7: Corresponds to migration plan phases in architecture doc

---

## Competitor Feature Analysis

This platform occupies a specific niche: Kubernetes-native agent orchestration with protocol-level (A2A + MCP) federation and CRD-based governance. Direct competitors operating at this layer are sparse as of early 2026. The closest reference points are:

| Feature | KubeFlow Pipelines | Temporal (agent workflows) | Our Approach |
|---------|-------------------|---------------------------|--------------|
| Skill discovery | Static config / env vars | Service registry + SDK | AgentDirectory CRD (k8s-native, informer-watched) |
| Task state | Pipeline DB (shared) | Dedicated Temporal service | Dedicated task-store service |
| Auth | Namespace RBAC | mTLS / API keys | SA token mandatory, OIDC JWKS local validation |
| Multi-tenancy | Namespace isolation only | Namespace isolation | X-Stack-Id + per-stack rate limits + AgentAccessPolicy |
| Protocol | REST / gRPC pipeline | Temporal workflow SDK | A2A + MCP (open protocol standards) |
| Versioning | Image tags | Workflow versioning | Semver constraints on peerStacks capabilities |

The differentiating bets: (1) k8s-native CRD-based governance over a separate control plane, (2) A2A + MCP protocol support as first-class (not bolted on), (3) composable CRDs over a God Object, (4) mandatory auth from early phases.

---

## Sources

- `docs/federated-agent-stack.md` (2026-04-21) — principal-architect architecture document, primary source. HIGH confidence.
- `agent-controller/api/v1alpha1/agent_types.go` — existing Agent CR type; establishes CRD group, pattern for new CRDs. HIGH confidence.
- `agent-controller/internal/controller/agent_controller.go` — existing reconciler; establishes controller-runtime patterns (CreateOrUpdate, informer ownership, status patch). HIGH confidence.
- `.planning/PROJECT.md` — milestone scope, constraints, key decisions. HIGH confidence.
- Training knowledge: Kubernetes sidecar patterns, controller-runtime informer/cache, HTTP header size limits (nginx 8KB default, envoy 60KB total), github.com/Masterminds/semver/v3 for Go semver constraint parsing, FastAPI middleware patterns, k8s OIDC JWKS local validation vs TokenReview latency tradeoffs. MEDIUM confidence — not verified against live docs due to WebSearch unavailability, but these are well-established patterns not subject to rapid change.

---
*Feature research for: Federated Agent Stack v2 — agent-orchestration platform*
*Researched: 2026-04-21*
