---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - image-builder/pyproject.toml
  - image-builder/Dockerfile
  - image-builder/Makefile
  - image-builder/alembic.ini
  - image-builder/alembic/env.py
  - image-builder/alembic/script.py.mako
  - image-builder/alembic/versions/0001_create_build_jobs_table.py
  - image-builder/app/__init__.py
  - image-builder/app/main.py
  - image-builder/app/core/__init__.py
  - image-builder/app/core/config.py
  - image-builder/app/db/__init__.py
  - image-builder/app/db/base.py
  - image-builder/app/db/session.py
  - image-builder/app/db/models/__init__.py
  - image-builder/app/db/models/build_job.py
  - image-builder/app/models/__init__.py
  - image-builder/app/models/build.py
  - image-builder/app/builders/__init__.py
  - image-builder/app/builders/abc.py
  - image-builder/app/builders/kaniko.py
  - image-builder/app/sources/__init__.py
  - image-builder/app/sources/abc.py
  - image-builder/app/api/__init__.py
  - image-builder/app/api/v1/__init__.py
  - image-builder/app/api/v1/router.py
  - image-builder/app/api/v1/routes/__init__.py
  - image-builder/app/api/v1/routes/builds.py
  - image-builder/app/api/v1/routes/health.py
  - image-builder/config/rbac.yaml
  - image-builder/config/api.yaml
  - image-builder/tests/__init__.py
  - image-builder/tests/test_models.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "POST /builds accepts a BuildRequest with discriminated Source and Runtime and returns a BuildJobResponse with status=pending"
    - "GET /builds/{id} returns the build job record or 404"
    - "GET /builds/{id}/logs returns 501 (stub) or live kaniko logs when job exists"
    - "DELETE /builds/{id} cancels the k8s Job and marks status=cancelled"
    - "KanikoBuilder.build() creates a kubernetes_asyncio BatchV1 Job named image-builder-{job_id} in namespace image-builder-system"
    - "GitSource and InlineSource discriminate via type field using Pydantic v2 model_validator / discriminated union"
    - "PythonRuntime, NodeRuntime, RawRuntime discriminate via type field"
    - "BuildJob SQLAlchemy model persists id, status, source_type, runtime_type, image_ref, k8s_job_name, logs_url, error, created_at, updated_at"
  artifacts:
    - path: "image-builder/app/models/build.py"
      provides: "Pydantic schemas: Source union, Runtime union, BuildRequest, BuildJobResponse, BuildStatus enum"
      exports: ["Source", "Runtime", "BuildRequest", "BuildJobResponse", "BuildStatus", "GitSource", "InlineSource", "PythonRuntime", "NodeRuntime", "RawRuntime"]
    - path: "image-builder/app/builders/abc.py"
      provides: "Builder ABC with async build/cancel/get_logs abstract methods"
      exports: ["Builder"]
    - path: "image-builder/app/sources/abc.py"
      provides: "SourceProvider ABC with async prepare abstract method"
      exports: ["SourceProvider"]
    - path: "image-builder/app/builders/kaniko.py"
      provides: "KanikoBuilder implementing Builder ABC via kubernetes_asyncio BatchV1 Jobs"
      exports: ["KanikoBuilder"]
    - path: "image-builder/app/api/v1/routes/builds.py"
      provides: "FastAPI router: POST /builds, GET /builds/{id}, GET /builds/{id}/logs, DELETE /builds/{id}"
    - path: "image-builder/app/db/models/build_job.py"
      provides: "SQLAlchemy BuildJob model"
      contains: "class BuildJob"
    - path: "image-builder/alembic/versions/0001_create_build_jobs_table.py"
      provides: "Initial migration creating build_jobs table"
  key_links:
    - from: "image-builder/app/api/v1/routes/builds.py"
      to: "image-builder/app/db/models/build_job.py"
      via: "SQLAlchemy async session from get_db() dependency"
      pattern: "Depends(get_db)"
    - from: "image-builder/app/api/v1/routes/builds.py"
      to: "image-builder/app/builders/kaniko.py"
      via: "KanikoBuilder instance from app.state (set in lifespan)"
      pattern: "request.app.state.builder"
    - from: "image-builder/app/builders/kaniko.py"
      to: "kubernetes_asyncio BatchV1Api"
      via: "create_namespaced_job / delete_namespaced_job / read_namespaced_pod_log"
      pattern: "BatchV1Api.*create_namespaced_job"
---

<objective>
Create the image-builder service from scratch: a FastAPI application that accepts image build
requests and dispatches Kubernetes Jobs using kaniko to build container images.

Purpose: Provides the build layer for the agent orchestration platform — callers POST a source
(git repo or inline tarball) plus a runtime descriptor (Python/Node/Raw Dockerfile) and receive
a BuildJob they can poll for status and logs.

Output: A fully-structured new service at image-builder/ mirroring agent-inventory-api conventions
with Pydantic v2 discriminated unions for extensibility, SQLAlchemy + asyncpg + Alembic for
persistence, a kaniko Job backend, and FastAPI routes for CRUD + log streaming.
</objective>

<execution_context>
@/Users/justinbrewer/.claude/get-shit-done/workflows/execute-plan.md
@/Users/justinbrewer/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md

<interfaces>
<!-- Patterns extracted from agent-inventory-api — use these directly, no exploration needed -->

From agent-inventory-api/app/core/config.py:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    app_name: str = "..."
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/..."
    k8s_namespace: str = "agent-system"
    k8s_in_cluster: bool = True
```

From agent-inventory-api/app/db/session.py:
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
async def get_db() -> AsyncGenerator[AsyncSession]: ...
```

From agent-inventory-api/app/db/models/agent.py (SQLAlchemy pattern):
```python
from sqlalchemy.orm import Mapped, mapped_column
class Agent(Base):
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

From agent-inventory-api/app/main.py (lifespan pattern):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    k8s_client = K8sAgentClient(...)
    await k8s_client.setup()
    yield
    await k8s_client.close()
```

From agent-inventory-api/app/k8s/client.py (kubernetes_asyncio pattern):
```python
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
if in_cluster: config.load_incluster_config()
else: await config.load_kube_config()
self._api_client = ApiClient()
```

From agent-inventory-api/pyproject.toml (dependency versions):
  fastapi>=0.115.0, uvicorn[standard]>=0.32.0, pydantic>=2.9.0, pydantic-settings>=2.6.0,
  sqlalchemy[asyncio]>=2.0.0, asyncpg>=0.30.0, alembic>=1.14.0, kubernetes-asyncio>=29.0.0
  dev: pytest>=8.3.0, pytest-asyncio>=0.24.0, httpx>=0.27.0, ruff>=0.8.0, mypy>=1.13.0

From agent-inventory-api/Dockerfile (multi-stage pattern):
  base (python:3.13-slim) → deps (pip install .) → production (addgroup/adduser 1000, copy site-packages)

From agent-inventory-api/alembic/env.py:
  config.set_main_option("sqlalchemy.url", settings.database_url)
  target_metadata = Base.metadata
  asyncio.run(run_async_migrations())
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pydantic schemas, ABCs, and SQLAlchemy model</name>
  <files>
    image-builder/app/models/__init__.py
    image-builder/app/models/build.py
    image-builder/app/builders/abc.py
    image-builder/app/sources/abc.py
    image-builder/app/db/base.py
    image-builder/app/db/models/__init__.py
    image-builder/app/db/models/build_job.py
    image-builder/tests/__init__.py
    image-builder/tests/test_models.py
  </files>
  <behavior>
    - GitSource(type="git", url=str, ref="main", subpath=None) validates correctly
    - InlineSource(type="inline", content="base64...") validates correctly
    - Source = Annotated[GitSource | InlineSource, Field(discriminator="type")] — wrong type raises ValidationError
    - PythonRuntime(type="python", version="3.13", packages=["fastapi"]) validates
    - NodeRuntime(type="node", version="20", packages=["express"]) validates
    - RawRuntime(type="raw", dockerfile="FROM python:3.13\n...") validates
    - Runtime = Annotated[PythonRuntime | NodeRuntime | RawRuntime, Field(discriminator="type")]
    - BuildRequest(source=GitSource(...), runtime=PythonRuntime(...), image_ref="registry/img:tag") round-trips through JSON
    - BuildStatus enum has: pending, running, succeeded, failed, cancelled
    - BuildJobResponse has id, status, source_type, runtime_type, image_ref, k8s_job_name, error, created_at, updated_at with model_config = ConfigDict(from_attributes=True)
    - Builder ABC has abstractmethods: async build(request: BuildRequest) -> BuildJob, async cancel(job_id: str) -> None, async get_logs(job_id: str) -> AsyncIterator[str]
    - SourceProvider ABC has abstractmethod: async prepare(source: Source, workspace_path: str) -> str
    - BuildJob SQLAlchemy model: id (UUID str pk), status (String, default="pending"), source_type (String), runtime_type (String), image_ref (String), k8s_job_name (String nullable), logs_url (String nullable), error (String nullable), created_at (DateTime tz), updated_at (DateTime tz)
  </behavior>
  <action>
    Write tests in image-builder/tests/test_models.py first (RED), then implement.

    image-builder/app/models/build.py:
    - Use Pydantic v2 model_config = ConfigDict(frozen=True) on each source/runtime leaf type
    - Discriminated unions: Source = Annotated[GitSource | InlineSource, Field(discriminator="type")]
      Runtime = Annotated[PythonRuntime | NodeRuntime | RawRuntime, Field(discriminator="type")]
    - BuildStatus(str, Enum): pending="pending", running="running", succeeded="succeeded",
      failed="failed", cancelled="cancelled"
    - BuildRequest(BaseModel): source: Source, runtime: Runtime, image_ref: str
    - BuildJobResponse(BaseModel): id, status: BuildStatus, source_type, runtime_type, image_ref,
      k8s_job_name: str|None, error: str|None, created_at: datetime, updated_at: datetime,
      model_config = ConfigDict(from_attributes=True)

    image-builder/app/builders/abc.py:
    - from abc import ABC, abstractmethod
    - from collections.abc import AsyncIterator
    - class Builder(ABC): with three @abstractmethod async methods

    image-builder/app/sources/abc.py:
    - class SourceProvider(ABC): with one @abstractmethod async prepare method

    image-builder/app/db/base.py:
    - DeclarativeBase subclass named Base (same pattern as agent-inventory-api)

    image-builder/app/db/models/build_job.py:
    - class BuildJob(Base): __tablename__ = "build_jobs"
    - All columns using Mapped[] typed columns as shown in interfaces
    - status server_default="pending"
  </action>
  <verify>
    <automated>cd /Users/justinbrewer/Documents/repos/agent-orchestration/image-builder && .venv/bin/pytest tests/test_models.py -v 2>&1 | tail -20</automated>
  </verify>
  <done>All model/schema/ABC unit tests pass. BuildJob, Source union, Runtime union, Builder ABC, SourceProvider ABC all importable and correctly typed.</done>
</task>

<task type="auto">
  <name>Task 2: KanikoBuilder, FastAPI app, config, DB session, Alembic, and scaffolding</name>
  <files>
    image-builder/pyproject.toml
    image-builder/Dockerfile
    image-builder/Makefile
    image-builder/alembic.ini
    image-builder/alembic/env.py
    image-builder/alembic/script.py.mako
    image-builder/alembic/versions/0001_create_build_jobs_table.py
    image-builder/app/__init__.py
    image-builder/app/core/__init__.py
    image-builder/app/core/config.py
    image-builder/app/db/__init__.py
    image-builder/app/db/session.py
    image-builder/app/builders/__init__.py
    image-builder/app/builders/kaniko.py
    image-builder/app/sources/__init__.py
    image-builder/app/api/__init__.py
    image-builder/app/api/v1/__init__.py
    image-builder/app/api/v1/router.py
    image-builder/app/api/v1/routes/__init__.py
    image-builder/app/api/v1/routes/builds.py
    image-builder/app/api/v1/routes/health.py
    image-builder/app/main.py
    image-builder/config/rbac.yaml
    image-builder/config/api.yaml
  </files>
  <action>
    Create all remaining files to wire the complete service.

    image-builder/pyproject.toml:
    - name = "image-builder", version = "0.1.0", requires-python = ">=3.13"
    - hatchling build backend, packages = ["app"]
    - Same deps as agent-inventory-api PLUS no a2a-sdk needed
    - dev extras same: pytest, pytest-asyncio, httpx, ruff, mypy

    image-builder/Dockerfile:
    - Exact same multi-stage pattern as agent-inventory-api/Dockerfile
    - COPY app/ + alembic/ + alembic.ini, user 1000, port 8000
    - CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

    image-builder/Makefile:
    - Mirror agent-inventory-api/Makefile structure
    - PORT := 8006, IMG ?= image-builder:latest, NAMESPACE ?= agent-system
    - Include all same targets: venv, install, install-dev, run, test, lint, typecheck, check,
      clean, db-up, db-down, db-migrate, db-rollback, db-revision, db-reset,
      docker-build, docker-push, deploy, undeploy, port-forward, k8s-logs, k8s-status
    - typecheck target: $(MYPY) app/

    image-builder/app/core/config.py:
    - Settings with pydantic-settings BaseSettings
    - app_name = "image-builder", app_version = "0.1.0"
    - database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/image_builder"
    - k8s_namespace: str = "agent-system", k8s_in_cluster: bool = True
    - kaniko_image: str = "gcr.io/kaniko-project/executor:latest"
    - builder_namespace: str = "image-builder-system" (namespace for kaniko jobs)
    - log_level: str = "INFO", debug: bool = False, environment: str = "development"

    image-builder/app/db/session.py:
    - Identical pattern to agent-inventory-api: create_async_engine, async_sessionmaker, get_db

    image-builder/alembic.ini:
    - Copy from agent-inventory-api/alembic.ini (script_location = alembic)

    image-builder/alembic/env.py:
    - Copy pattern from agent-inventory-api/alembic/env.py
    - Import: from app.db.models.build_job import BuildJob  # noqa: F401
    - from app.db.base import Base; target_metadata = Base.metadata

    image-builder/alembic/script.py.mako:
    - Copy from agent-inventory-api/alembic/script.py.mako

    image-builder/alembic/versions/0001_create_build_jobs_table.py:
    - revision = "b1c2d3e4f5a6", down_revision = None
    - upgrade(): op.create_table("build_jobs", id String pk, status String default "pending",
        source_type String not null, runtime_type String not null, image_ref String not null,
        k8s_job_name String nullable, logs_url String nullable, error String nullable,
        created_at DateTime(timezone=True) server_default now(), updated_at DateTime(timezone=True) server_default now())
    - downgrade(): op.drop_table("build_jobs")

    image-builder/app/builders/kaniko.py — KanikoBuilder(Builder):
    - __init__(self, k8s_api_client: ApiClient, namespace: str, kaniko_image: str, builder_namespace: str)
    - async build(self, request: BuildRequest, db_job: BuildJob) -> None:
        job_name = f"image-builder-{db_job.id}"
        Construct BatchV1 Job spec:
          - name = job_name, namespace = builder_namespace
          - restartPolicy = Never, backoffLimit = 0
          - container image = kaniko_image, name = "kaniko"
          - args based on runtime type:
            PythonRuntime: generate inline Dockerfile (FROM python:{version}, pip install {packages})
              pass as --dockerfile=/kaniko/dockerfile with a configmap volume OR use --build-arg
              For simplicity: build a Dockerfile string and pass via env var DOCKERFILE_CONTENT
              (executor reads from stdin alternative: use --dockerfile flag with emptyDir volume)
              Pragmatic approach: write Dockerfile content as a k8s ConfigMap-mounted file is
              complex; instead, use RawRuntime path where the Dockerfile is an arg. For
              PythonRuntime/NodeRuntime, generate a Dockerfile string in-process and store it in
              a ConfigMap named image-builder-{job_id}-dockerfile, mount as volume at
              /workspace/Dockerfile, pass --dockerfile=/workspace/Dockerfile --no-push (or
              --destination=image_ref). Keep it simple: PythonRuntime generates:
                FROM python:{version}\nRUN pip install {" ".join(packages)}
              NodeRuntime generates:
                FROM node:{version}\nRUN npm install -g {" ".join(packages)}
              RawRuntime uses the dockerfile field directly.
          - destination: --destination={request.image_ref}
          - For GitSource: pass --context=git+{url}#{ref} (kaniko supports git context)
          - For InlineSource: store base64 content in a Secret, mount as /workspace/context.tar.gz,
            pass --context=tar:///workspace/context.tar.gz
        Create the ConfigMap (if needed) then create the Job via BatchV1Api.create_namespaced_job
        Update db_job.status = "running", db_job.k8s_job_name = job_name
    - async cancel(self, job_id: str) -> None:
        job_name = f"image-builder-{job_id}"
        BatchV1Api.delete_namespaced_job(job_name, builder_namespace, propagation_policy="Foreground")
        Swallow 404 (already gone)
    - async get_logs(self, job_id: str) -> AsyncIterator[str]:
        job_name = f"image-builder-{job_id}"
        CoreV1Api.list_namespaced_pod(builder_namespace, label_selector=f"job-name={job_name}")
        For each pod: CoreV1Api.read_namespaced_pod_log(pod.metadata.name, builder_namespace, follow=False)
        Yield log lines split by "\n"
    - Include class-level async setup()/close() mirroring K8sAgentClient pattern

    image-builder/app/api/v1/routes/builds.py:
    - POST /builds: accept BuildRequest, create BuildJob ORM row (status=pending), call
      builder.build(request, job_row) in background (asyncio.create_task), return 202 + BuildJobResponse
    - GET /builds/{job_id}: select BuildJob by id, 404 if not found, return BuildJobResponse
    - GET /builds/{job_id}/logs: select BuildJob, 404 if not found, if k8s_job_name is None
      return 404 with detail "job not yet dispatched"; stream logs via
      StreamingResponse(builder.get_logs(job_id), media_type="text/plain")
    - DELETE /builds/{job_id}: select BuildJob, 404 if not found, call builder.cancel(job_id),
      set status=cancelled, commit, return 204
    - Access builder via: request.app.state.builder (NOT via Depends — set in lifespan)

    image-builder/app/api/v1/routes/health.py:
    - GET /health returns {"status": "ok"}

    image-builder/app/api/v1/router.py:
    - from fastapi import APIRouter; api_router = APIRouter()
    - api_router.include_router(builds_router, prefix="/builds")
    - api_router.include_router(health_router)

    image-builder/app/main.py:
    - @asynccontextmanager lifespan: init KanikoBuilder, await builder.setup(), app.state.builder = builder, yield, await builder.close()
    - create_app() with title, lifespan, CORS middleware, include api_router at /api/v1
    - app = create_app()

    image-builder/config/rbac.yaml:
    - ServiceAccount: name=image-builder, namespace=agent-system
    - ClusterRole: image-builder-role, rules:
        apiGroups: ["batch"], resources: ["jobs"], verbs: [get, list, create, delete]
        apiGroups: [""], resources: ["pods", "pods/log", "configmaps", "secrets"], verbs: [get, list, create, delete]
    - ClusterRoleBinding binding the above

    image-builder/config/api.yaml:
    - Deployment: name=image-builder, namespace=agent-system, serviceAccountName=image-builder
    - initContainer: alembic upgrade head (same pattern as agent-inventory-api)
    - container port 8000, readinessProbe/livenessProbe at /api/v1/health
    - resources: requests cpu=100m mem=128Mi, limits cpu=500m mem=256Mi
    - securityContext: runAsNonRoot, allowPrivilegeEscalation=false, readOnlyRootFilesystem=true
    - Service: ClusterIP port 8000

    All __init__.py files: empty (0 bytes) except app/db/models/__init__.py which re-exports BuildJob.
  </action>
  <verify>
    <automated>cd /Users/justinbrewer/Documents/repos/agent-orchestration/image-builder && python -c "from app.main import app; from app.builders.kaniko import KanikoBuilder; from app.api.v1.routes.builds import router; print('imports ok')"</automated>
  </verify>
  <done>
    All files exist. Service imports cleanly. pyproject.toml installs without errors (pip install -e .).
    All four route handlers registered. KanikoBuilder class implements all three Builder ABC methods.
    alembic/versions/0001 migration file exists with upgrade/downgrade.
    config/rbac.yaml grants batch/jobs and core pods/log/configmaps/secrets permissions.
  </done>
</task>

</tasks>

<verification>
After both tasks complete:
- cd image-builder && make install-dev runs without error
- python -c "from app.models.build import Source, Runtime, BuildRequest, BuildJobResponse, BuildStatus; from app.builders.abc import Builder; from app.sources.abc import SourceProvider; from app.builders.kaniko import KanikoBuilder; print('all imports ok')"
- pytest tests/test_models.py -v passes all discriminated union and schema tests
- ruff check app/ returns no errors
- mypy app/ passes (or has only known stub-missing warnings for kubernetes_asyncio)
- alembic upgrade head runs against a local postgres (if available)
</verification>

<success_criteria>
- image-builder/ service directory exists with complete file structure mirroring agent-inventory-api
- Pydantic v2 discriminated unions for Source and Runtime are validated by tests
- Builder and SourceProvider ABCs enforce abstractmethods
- KanikoBuilder creates/cancels/logs kubernetes BatchV1 Jobs
- Four FastAPI routes registered: POST /builds, GET /builds/{id}, GET /builds/{id}/logs, DELETE /builds/{id}
- SQLAlchemy BuildJob model and Alembic migration in place
- config/rbac.yaml and config/api.yaml exist with correct permissions and deployment manifests
- Service is pip-installable and all modules import without errors
</success_criteria>

<output>
After completion, create .planning/quick/2-build-image-builder-service-schemas-exte/2-SUMMARY.md
following the standard summary template.
</output>
