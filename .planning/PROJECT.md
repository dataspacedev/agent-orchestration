# Agent Orchestration Platform

## What This Is

A Kubernetes-native platform for deploying, discovering, and orchestrating AI agents using the A2A and MCP protocols. Operators declare agents as CRs; the platform handles lifecycle, inter-agent routing, task state, and governance. Targets platform engineering teams building shared agent infrastructure for multiple domain teams.

## Core Value

Agents can be deployed, discovered, and called across domain boundaries via k8s-native APIs — with zero per-agent configuration of auth, routing, or observability.

## Current Milestone: v1.0 — Federated Agent Stack v2

**Goal:** Implement the federated agent stack v2 architecture from docs/federated-agent-stack.md — introducing AgentDirectory, composable CRDs, mandatory auth, skill-resolver sidecar, task-store service, platform agent tier, and MCP aggregator as incrementally deployable phases.

**Target features:**
- AgentDirectory CRD as runtime-authoritative skill map
- skill-resolver sidecar replacing env-var skill injection
- Composable CRDs (AgentStack, AgentPolicy, AgentRoute, AgentAccessPolicy, ClusterAgentPolicy, AgentRubric)
- Mandatory service-account-token auth enforced from P2
- Dedicated task-store service (separate from inventory-api DB)
- Platform agent tier with StackIsolationMiddleware and per-stack quotas
- MCP aggregator with dynamic AgentDirectory-based tool refresh
- Governance: AgentPromotion process, drift detection, SLO dashboards

## Requirements

### Validated

<!-- Inferred from existing code — shipped and relied upon. -->

- ✓ Agent CR → Deployment/Service/ServiceAccount/ConfigMap/HPA reconciliation (agent-controller)
- ✓ Inventory API CRUD for agent registry in Postgres (agent-inventory-api)
- ✓ Outbox processor syncing inventory API to k8s Agent CRs
- ✓ A2A protocol types, InMemoryTaskStore, A2ARouter in core-tools-lib
- ✓ MCP protocol support via FastMCP in core-tools-lib
- ✓ `create_agent_app()` factory wiring A2A + MCP + health endpoints
- ✓ Example agent pattern: Agent CR with Dockerfile, config/agent.yaml
- ✓ Agent registry UI (React/Vite, agent-registry-ui)

### Active

<!-- Current milestone: v1.0 — Federated Agent Stack v2 -->

- [ ] AgentDirectory CRD (k8s-native skill→URL map written by registry-announcer)
- [ ] registry-announcer sidecar writes to AgentDirectory + inventory API
- [ ] skill-resolver sidecar (watches AgentDirectory, serves localhost resolution API)
- [ ] task-store service (FastAPI + Postgres + PgBouncer, dedicated from inventory-api DB)
- [ ] ClusterAgentPolicy CRD (cluster-scoped auth, OTEL, resilience defaults)
- [ ] Mandatory SA-token auth enforced cluster-wide from P2
- [ ] AgentAccessPolicy CRD (cross-stack permission grants)
- [ ] AgentStack minimal spec (membership + topology only)
- [ ] AgentPolicy CRD (namespace-level observability overrides)
- [ ] AgentRoute CRD (per-skill routing and load balancing)
- [ ] AgentRubric CRD (per-request behavioral config for platform agents)
- [ ] Platform agent tier: 7 platform agents in agent-platform namespace
- [ ] StackIsolationMiddleware in core-tools-lib (injected by PLATFORM_AGENT=true)
- [ ] MCP aggregator (watches AgentDirectory, versioned tool registry)
- [ ] AgentDirectory drift detection and health reconciliation
- [ ] Semver version constraints on peerStacks capabilities
- [ ] Governance: AgentPromotion process + SLO dashboards

### Out of Scope

- Cross-cluster federation — design assumes single k8s cluster (v2 concern)
- Real-time agent streaming — current A2A request/response model is sufficient
- OAuth/MTLS auth modes — SA token is mandatory cluster default for v1.0

## Context

- **Architecture reference:** docs/federated-agent-stack.md (v2, 2026-04-21) — principal-architect critique of v1 design, 9 architectural changes, 7-phase migration plan.
- **Key shift:** separate management plane (inventory-api) from runtime plane (AgentDirectory CRD); controller never calls inventory API at reconcile time.
- **Controller language:** Go (controller-runtime v0.19.0, k8s 1.31); agents and SDK are Python 3.13.
- **A2A SDK:** core-tools-lib migrated from hand-rolled to a2a-sdk (per existing memory).
- **Existing CRD group:** agents.orchestration.io/v1alpha1 (Agent CR already live).

## Constraints

- **Tech Stack**: Controller is Go; agents and SDK are Python 3.13 — no language mixing per service.
- **Compatibility**: New CRDs must use agents.orchestration.io/v1alpha1 group for consistency.
- **Migration**: Each phase must be independently deployable without breaking the previous phase.
- **Auth**: SA-token auth is mandatory cluster-wide from P2 — no unauthenticated A2A calls allowed after that point.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| AgentDirectory CRD as runtime source of truth | Eliminates controller dependency on inventory API HTTP at reconcile time | — Pending |
| skill-resolver sidecar over env-var injection | Dynamic skill resolution without pod restarts | — Pending |
| Dedicated task-store service | Decouples task state from agent registry, independent scaling | — Pending |
| SA token as mandatory auth mode | Auth cannot be deferred or skipped by domain teams | — Pending |
| Composable CRDs over God Object AgentStack | Each concern independently evolvable, per-team ownership | — Pending |

---
*Last updated: 2026-04-21 after v1.0 milestone start*
