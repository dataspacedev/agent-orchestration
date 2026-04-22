# Pitfalls Research

**Domain:** Kubernetes-native AI agent orchestration platform — federated agent stack v2
**Researched:** 2026-04-21
**Confidence:** MEDIUM-HIGH (based on known k8s controller, sidecar, and FastAPI patterns; not verified via researcher due to rate limit)

---

## Critical Pitfalls by Phase

### P1 Pitfalls — Runtime Foundation

**P1-1: AutomountServiceAccountToken=false blocks sidecar k8s API access**
- **What breaks:** registry-announcer and skill-resolver sidecars use the pod SA token to patch AgentDirectory CRs. Current `buildDeploymentSpec` sets `AutomountServiceAccountToken: ptr(false)` as a security hardening measure. Sidecars will get 401 from k8s API.
- **Prevention:** In P1, change `buildDeploymentSpec` to `ptr(true)` for pods receiving sidecars. Document that P7 will introduce explicit projected volume token mounts (mount only in sidecar containers, not agent container).

**P1-2: controller-gen not re-run after new CRD type files**
- **What breaks:** `zz_generated.deepcopy.go` will not have DeepCopy methods for new types. Controller panics at startup when scheme registration calls DeepCopy. CRD YAML manifests are stale — controller watches a CRD that doesn't exist in the cluster.
- **Prevention:** Every PR that adds a new `*_types.go` file MUST include the `make generate manifests` step and commit the generated output. Add a CI check: `make generate && git diff --exit-code`.

**P1-3: registry-announcer partial write failure divergence**
- **What breaks:** Announcer patches AgentDirectory CR (primary), then crashes before writing inventory-api (secondary). After restart, inventory-api entry is stale or missing. The `DirectoryInSync` condition will fire, but if no alert is wired, the divergence is silent.
- **Prevention:** On announcer restart, always re-read own AgentDirectory entry and re-announce if cardHash mismatches (idempotent re-announcement). The inventory-api write must be in a background retry queue with dead-letter behavior, not a fire-and-forget. Wire `DirectoryInSync=False` to a Prometheus alert in P1 (not P7).

**P1-4: task-store not HA before P4 dependency**
- **What breaks:** Platform agents deployed in P4 use task-store as their sole persistent task state. If task-store is a single-replica deployment, any restart or rescheduling loses all in-flight task state for every platform agent simultaneously.
- **Prevention:** task-store must reach 2+ replicas + PgBouncer + backup before P4 proceeds. Make it a hard gate in STATE.md: "task-store HA verified" must be checked before AgentStack platform stack goes live.

---

### P2 Pitfalls — Auth Mandatory

**P2-1: Dev environment breaks when OIDC endpoint is unavailable**
- **What breaks:** Platform agents validate SA tokens via OIDC JWKS. Local dev (kind/minikube) may not expose the OIDC discovery endpoint at the expected URL, or the JWKS URL returns a self-signed cert. Platform agents reject all tokens; all cross-stack calls fail with 401.
- **Prevention:** Make OIDC JWKS URL configurable via `K8S_OIDC_JWKS_URL` env var. In dev/test environments, allow `AUTH_MODE=none` override (set explicitly, with a loud warning log). Validate that the dev cluster's OIDC endpoint is reachable as part of P2 dev setup docs.

**P2-2: Token audience mismatch causes 401 on all platform agent calls**
- **What breaks:** k8s SA tokens are scoped to a specific audience claim. If the token projected by the pod uses audience `kubernetes.default.svc` but platform agents validate against audience `agents.orchestration.io`, every token validation fails.
- **Prevention:** Platform agents must use the `tokenAudience` from `ClusterAgentPolicy.spec.auth.tokenAudience`. A2AClient must request a token with the same audience when calling `serviceaccounts/token`. Document this in ClusterAgentPolicy CRD spec and add a validation webhook or status condition check.

**P2-3: AgentAccessPolicy deployed in wrong namespace**
- **What breaks:** `AgentAccessPolicy` must be created in the TARGET (platform) namespace, not the caller namespace. Domain teams will instinctively create it in their own namespace (`agent-legal`). The AgentAccessReconciler watches the platform namespace — it won't see a policy in agent-legal.
- **Prevention:** Kubebuilder validation marker or webhook to enforce that `AgentAccessPolicy` is in the namespace that owns the skills being accessed. Clear error message in AgentStackReconciler condition when a required policy is missing.

---

### P3 Pitfalls — Skill-Resolver Sidecar + Composable CRDs

**P3-1: AgentStack CRD conversion webhook downtime window**
- **What breaks:** The existing AgentStack CRs (if any exist) have fields being moved to AgentPolicy. If the controller is updated (removing old field handlers) before the conversion webhook is live, existing stacks enter an error state with no recovery path except manual CR deletion and re-creation.
- **Prevention:** Deploy the conversion webhook and AgentPolicy CRD BEFORE deploying the updated controller that removes old AgentStack field handling. Run both old and new field handling in parallel for one release cycle (deprecated, not removed). The conversion webhook migrates old fields to AgentPolicy resources in the same namespace.

**P3-2: skill-resolver init container race — agent starts before resolver is ready**
- **What breaks:** On pod startup, the agent container may start before the skill-resolver sidecar has populated its AgentDirectory informer cache. The first skill resolution call returns 503, and if the orchestrator treats 503 as fatal (not retriable), it errors out immediately.
- **Prevention:** Add an init container that polls `localhost:2020/health` before the agent container starts. The skill-resolver's `/health` endpoint returns 200 only after its informer cache has synced (`cache.WaitForCacheSync`). Document in orchestrator implementation guide: 503 from skill-resolver = degraded-mode signal, not fatal error.

**P3-3: skill-resolver informer watches wrong namespace**
- **What breaks:** The skill-resolver in an orchestrator pod in `agent-legal` namespace needs to resolve skills from `agent-platform` namespace. If the informer is scoped to the local namespace only, it returns "no agent satisfying skill" for all platform skills.
- **Prevention:** skill-resolver must use a cluster-scoped informer (cross-namespace watch) for `AgentDirectory` CRDs, backed by a ClusterRole that allows `agentdirectories` watch cluster-wide. This is already implied by the ClusterRoleBinding approach but must be explicitly implemented in the skill-resolver informer factory setup.

---

### P4 Pitfalls — Platform Stack Deployment

**P4-1: Platform agents deployed before auth is enforced**
- **What breaks:** action-executor makes external system calls. If it's live before ClusterAgentPolicy auth is active (P2), any pod in the cluster can call it unauthenticated. This is a security incident.
- **Prevention:** Hard sequential gate: P4 requires a "P2 auth verified" checklist item. The `AgentStack` controller can enforce this: refuse to mark an AgentStack in `agent-platform` namespace as Ready if `ClusterAgentPolicy.spec.auth.mode == none`.

**P4-2: StackIsolationMiddleware in-process rate limiting is per-replica**
- **What breaks:** At 3 platform agent replicas, a stack with a 100 req/s limit can actually send 300 req/s (100 to each replica, each replica doesn't know about the others). For loose quotas this is acceptable; for strict compliance quotas it is not.
- **Prevention:** Document the per-replica behavior explicitly in `ClusterAgentPolicy` CRD spec and README. Set the per-replica limit = cluster_limit / expected_replicas. Plan for Redis-backed cluster-wide limiting in P7. Don't silently let teams think the quota is cluster-wide.

---

### P5 Pitfalls — Domain Stack Onboarding

**P5-1: Unsatisfiable semver constraint causes infinite requeue**
- **What breaks:** If a domain stack declares `minVersion: "2.0"` for a platform skill that only has `v1.2.0` deployed, the AgentStackReconciler emits `CapabilityVersionWarning` and requeues. Without a backoff, this becomes a hot requeue loop flooding the controller logs.
- **Prevention:** Use `ctrl.Result{RequeueAfter: 5 * time.Minute}` (not `ctrl.Result{Requeue: true}`) for unsatisfiable constraint conditions. The condition `CapabilityVersionWarning` must include the constraint and what's available so platform teams can act on it.

**P5-2: AgentRubric header exceeds nginx/envoy default limits**
- **What breaks:** nginx defaults to 8KB per header value. HTTP/1.1 total header block limit is often 64KB. A legal clause library rubric with hundreds of patterns will silently fail — nginx drops the request with 400 before the platform agent sees it. The orchestrator gets a cryptic 400 with no body.
- **Prevention:** skill-resolver enforces an 8KB hard limit on `X-Agent-Rubric` header value before sending. Above 8KB, the sidecar uses `X-Agent-Rubric-Ref: <namespace/name>` instead and the platform agent fetches the AgentRubric CR from the k8s API (cached per generation). This must be implemented in P5, not treated as a future concern.

---

### P6 Pitfalls — MCP Aggregator

**P6-1: LLM client caches stale tool schemas**
- **What breaks:** When a platform agent tool's schema changes (new parameter, renamed field), the MCP aggregator rebuilds its tool registry. But LLM clients (Claude, etc.) cache tool lists from the session start. They send calls with the old schema. The aggregator proxies with the new schema and the platform agent rejects the call.
- **Prevention:** Tool names include version: `document_intelligence_v1__parse_document`. Schema changes increment the version suffix: `document_intelligence_v2__parse_document`. LLM clients see the old and new tools simultaneously during transition. Old version is removed after the documented deprecation window (30 days per the architecture doc).

---

### P7 Pitfalls — Governance + Hardening

**P7-1: Drift detection false positives from slow announcer re-sync**
- **What breaks:** The `ClusterAgentDirectoryHealthCheck` runs every 60s. If a pod just restarted and the announcer hasn't finished its first AgentDirectory patch, the health check sees a Ready Agent CR with no AgentDirectory entry and fires a `DirectoryDriftDetected` event. If this fires alerts, on-call gets woken up for every rolling restart.
- **Prevention:** Add a 120s grace period: only flag drift if the discrepancy persists across 2 consecutive health check runs AND the pod has been Ready for >60s. Implement as a small in-memory map of (agentName → firstDriftSeen timestamp) in the health check reconciler.

**P7-2: Audit log format left undefined for regulated domains**
- **What breaks:** If clinical or legal stacks go into production before the audit log format, retention, and query access are formally specified, the audit data is collected but unusable for compliance audits. Retroactively changing format breaks existing log analysis tooling.
- **Prevention:** Define the audit log data contract before P7 merges: schema, retention (minimum 90 days for GDPR, 7 years for some clinical regs), who can query, tamper-evidence (append-only with hash chaining or write to immutable store). Block regulated domain stacks from production until contract is ratified.

---

## Summary: Phase-to-Prevention Map

| Phase | Key Prevention |
|-------|---------------|
| P1 | Fix AutomountServiceAccountToken; CI check for make generate; announcer idempotent re-announce; task-store HA gate |
| P2 | OIDC dev mode override; token audience validation; AgentAccessPolicy namespace enforcement |
| P3 | Conversion webhook before controller update; init container readiness gate; cluster-scoped informer |
| P4 | Hard auth gate before platform stack; document per-replica rate limit behavior |
| P5 | Requeue backoff for unsatisfiable constraints; 8KB rubric header limit with ref fallback |
| P6 | Versioned tool names; 30-day deprecation window |
| P7 | Drift grace period; audit log contract before regulated domains go live |
