---
phase: 1
slug: runtime-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | go test (controller), pytest 7.x (task-store, core-tools-lib) |
| **Config file** | `agent-controller/Makefile` (Go), `task-store/pyproject.toml` (Python) |
| **Quick run command** | `make test` (Go) / `pytest -x -q` (Python) |
| **Full suite command** | `make test` (Go) + `pytest` (Python) + `make generate && git diff --exit-code` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `make test` (Go) or `pytest -x -q` (Python) depending on component touched
- **After every plan wave:** Run full suite (Go + Python + generate check)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | INFRA-01 | unit | `make test ./internal/...` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | INFRA-01 | unit | `make test ./internal/...` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | INFRA-02 | unit | `make test ./internal/...` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | INFRA-03 | integration | `make test ./internal/...` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | INFRA-04 | unit | `pytest -x -q tests/` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | INFRA-05 | unit | `pytest -x -q tests/` | ❌ W0 | ⬜ pending |
| 1-02-03 | 02 | 2 | INFRA-06 | integration | `pytest -x -q tests/` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 1 | INFRA-07 | unit | `pytest -x -q tests/` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | INFRA-08 | integration | `pytest -x -q tests/` | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 2 | INFRA-09 | unit | `make test ./internal/...` | ❌ W0 | ⬜ pending |
| 1-04-02 | 04 | 2 | INFRA-10 | unit | `make test ./internal/...` | ❌ W0 | ⬜ pending |
| 1-05-01 | 05 | 3 | INFRA-11 | integration | manual + `pytest -x -q` | ❌ W0 | ⬜ pending |
| 1-05-02 | 05 | 3 | INFRA-12 | integration | manual + `make test` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `agent-controller/internal/controller/agent_controller_test.go` — update `ptr(false)→ptr(true)` assertion for INFRA-01
- [ ] `task-store/tests/test_task_store_client.py` — stubs for INFRA-04, INFRA-05
- [ ] `task-store/tests/test_task_store_api.py` — stubs for INFRA-06, INFRA-08
- [ ] `task-store/tests/conftest.py` — async SQLAlchemy test fixtures, PgBouncer mock
- [ ] `core-tools-lib/tests/test_task_store_factory.py` — TASK_STORE_URL env var switching stubs for INFRA-07
- [ ] `agent-controller/internal/controller/agentpolicy_reconciler_test.go` — stubs for INFRA-09, INFRA-10

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| registry-announcer sidecar injected into agent pod on deploy | INFRA-01 | Requires live k8s cluster and pod scheduling | `kubectl apply -f samples/agent.yaml && kubectl get pod -w && kubectl describe pod <name>` — confirm sidecar container and readinessGate condition |
| AgentDirectory entry survives 10 announcer restarts without divergence | INFRA-02 | Loop restart testing needs live cluster | `kubectl rollout restart deploy/<agent>` × 10, check `kubectl get agentdirectory <name> -o json` each time |
| task-store cluster DNS reachable at 2+ replicas | INFRA-05, INFRA-08 | Requires deployed Postgres + PgBouncer | `kubectl exec <pod> -- curl http://task-store/health` + `kubectl get pods -l app=task-store` |
| task-store HA confirmed (PgBouncer healthy, backup tested) | INFRA-08 | Hard gate — requires live PgBouncer metrics | Check PgBouncer stats, simulate primary failover, verify reconnect |
| AgentDirectory CRD applies cleanly to production cluster | INFRA-03 | Requires production cluster access | `kubectl apply -f config/crd/bases/ --dry-run=server` on prod |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
