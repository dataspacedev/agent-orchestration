---
phase: quick-2
plan: 01
subsystem: image-builder
tags: [fastapi, kaniko, kubernetes, sqlalchemy, pydantic-v2, alembic, tdd]
dependency_graph:
  requires: []
  provides:
    - image-builder FastAPI service at image-builder/
    - Pydantic v2 discriminated unions for Source and Runtime
    - KanikoBuilder dispatching k8s BatchV1 Jobs
    - SQLAlchemy BuildJob model + Alembic migration
  affects:
    - agent-inventory-api (pattern reference — no code changes)
tech_stack:
  added:
    - image-builder service (Python 3.13, FastAPI 0.115, uvicorn)
    - pydantic-settings 2.6+ for config
    - SQLAlchemy 2.x async + asyncpg + alembic
    - kubernetes-asyncio 29+ for BatchV1 Job creation
    - kaniko (gcr.io/kaniko-project/executor) as build executor
  patterns:
    - Pydantic v2 discriminated unions with Literal type discriminators
    - SQLAlchemy 2.x Mapped[] columns with explicit __init__ for Python-level defaults
    - kubernetes_asyncio async BatchV1Api / CoreV1Api job management
    - asynccontextmanager lifespan pattern (K8s client init/teardown)
    - asyncio.create_task for fire-and-forget build dispatch
key_files:
  created:
    - image-builder/app/models/build.py
    - image-builder/app/builders/abc.py
    - image-builder/app/sources/abc.py
    - image-builder/app/builders/kaniko.py
    - image-builder/app/db/models/build_job.py
    - image-builder/app/db/base.py
    - image-builder/app/db/session.py
    - image-builder/app/core/config.py
    - image-builder/app/api/v1/routes/builds.py
    - image-builder/app/api/v1/routes/health.py
    - image-builder/app/api/v1/router.py
    - image-builder/app/main.py
    - image-builder/alembic/versions/0001_create_build_jobs_table.py
    - image-builder/config/rbac.yaml
    - image-builder/config/api.yaml
    - image-builder/Dockerfile
    - image-builder/Makefile
    - image-builder/pyproject.toml
    - image-builder/tests/test_models.py
  modified: []
decisions:
  - "Used Pydantic v2 Literal type discriminators (not str+pattern) for discriminated unions — required for Pydantic's discriminated union engine to infer variant at decode time"
  - "Added explicit __init__ to BuildJob SQLAlchemy model to provide Python-level defaults (server_default only applies at flush/INSERT time, not at object construction)"
  - "KanikoBuilder.build() creates a ConfigMap for generated Dockerfiles (Python/Node runtimes) and a Secret for inline source archives, then mounts them into the kaniko container"
  - "get_logs() is an async generator (not a coroutine returning an iterator), consistent with the Builder ABC pattern"
  - "StrEnum used for BuildStatus (UP042 ruff rule) instead of (str, Enum)"
metrics:
  duration: "~9 minutes"
  completed_date: "2026-05-02"
  tasks_completed: 2
  files_created: 33
---

# Phase quick-2 Plan 01: Image Builder Service Summary

**One-liner:** FastAPI image-builder service with Pydantic v2 discriminated unions (git/inline sources, python/node/raw runtimes), KanikoBuilder dispatching Kubernetes BatchV1 Jobs, SQLAlchemy + asyncpg + Alembic persistence, and four CRUD routes for builds.

## What Was Built

A complete `image-builder/` service from scratch, mirroring `agent-inventory-api` conventions:

- **Pydantic v2 schemas** (`app/models/build.py`): `Source` union (`GitSource | InlineSource`), `Runtime` union (`PythonRuntime | NodeRuntime | RawRuntime`), `BuildRequest`, `BuildJobResponse`, `BuildStatus` (StrEnum)
- **ABCs** (`app/builders/abc.py`, `app/sources/abc.py`): `Builder` with `build/cancel/get_logs` abstract methods; `SourceProvider` with `prepare`
- **KanikoBuilder** (`app/builders/kaniko.py`): Creates k8s ConfigMaps for generated Dockerfiles, Secrets for inline archives, then dispatches `BatchV1Api.create_namespaced_job` named `image-builder-{job_id}`
- **SQLAlchemy model** (`app/db/models/build_job.py`): `BuildJob` with all required columns; explicit `__init__` for Python-level `status="pending"` default
- **FastAPI routes** (`app/api/v1/routes/builds.py`): POST /builds (202+background dispatch), GET /builds/{id}, GET /builds/{id}/logs (StreamingResponse), DELETE /builds/{id}
- **Alembic migration** `0001_create_build_jobs_table` (revision `b1c2d3e4f5a6`)
- **RBAC** (`config/rbac.yaml`): ServiceAccount + ClusterRole granting batch/jobs and core pods/log/configmaps/secrets
- **Deployment** (`config/api.yaml`): Deployment with init container for `alembic upgrade head`, readiness/liveness probes at `/api/v1/health`, non-root securityContext
- **Tooling**: `pyproject.toml` (hatchling, Python 3.13), `Dockerfile` (multi-stage), `Makefile` (PORT=8006, all standard targets)

## Test Results

24 unit tests passing (`tests/test_models.py`):
- Discriminated union validation (Source and Runtime)
- BuildRequest JSON round-trip
- BuildStatus enum values
- BuildJobResponse from_attributes construction
- Builder and SourceProvider ABC enforcement
- BuildJob column set and Python-level defaults

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Discriminator fields required Literal type, not str+pattern**
- **Found during:** Task 1 RED→GREEN
- **Issue:** Pydantic v2 discriminated union engine requires `Literal["git"]` type annotation, not `str = Field("git", pattern="^git$")`. Triggered `PydanticUserError` at collection time.
- **Fix:** Changed all discriminator fields in `GitSource`, `InlineSource`, `PythonRuntime`, `NodeRuntime`, `RawRuntime` to use `Literal["git"]` etc.
- **Files modified:** `app/models/build.py`

**2. [Rule 1 - Bug] SQLAlchemy server_default does not set Python attribute before flush**
- **Found during:** Task 1 GREEN
- **Issue:** `server_default="pending"` on a `Mapped[str]` column only applies at the DB INSERT level; accessing `job.status` after `BuildJob(...)` construction returns `None`.
- **Fix:** Added explicit `__init__` to `BuildJob` with `status: str = "pending"` keyword argument default.
- **Files modified:** `app/db/models/build_job.py`

**3. [Rule 1 - Bug] Ruff lint fixes: StrEnum, sorted imports, UP037/UP043**
- **Found during:** Task 2 verification
- **Issue:** `BuildStatus(str, Enum)` should use `StrEnum` (UP042); type annotation had quoted string (UP037/UP043); import block unsorted (I001).
- **Fix:** Changed to `BuildStatus(StrEnum)`, moved `AsyncGenerator` import to module level, let ruff auto-fix remainder.
- **Files modified:** `app/models/build.py`, `app/api/v1/routes/builds.py`

**4. [Rule 1 - Bug] mypy: volume_mounts required V1VolumeMount objects, not dict**
- **Found during:** Task 2 mypy check
- **Issue:** `client.V1Container(volume_mounts=...)` expects `list[V1VolumeMount]` not `list[dict]`.
- **Fix:** Construct `client.V1VolumeMount(...)` objects from the volume mount dicts before passing to `V1Container`.
- **Files modified:** `app/builders/kaniko.py`

**5. [Rule 1 - Bug] get_logs is async generator, not a coroutine**
- **Found during:** Task 2 mypy check
- **Issue:** `await builder.get_logs(job_id)` in route handler — `get_logs` returns an `AsyncIterator`, not an `Awaitable`. `await` on an `AsyncIterator` raises a type error.
- **Fix:** Removed `await` from the `async for` call in `_log_stream`.
- **Files modified:** `app/api/v1/routes/builds.py`

## Self-Check: PASSED

All key files verified present. Commits 15ca8fe and 2f2b7e3 both exist.
