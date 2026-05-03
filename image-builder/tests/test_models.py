"""Tests for Pydantic schemas, ABCs, and SQLAlchemy model."""
import inspect
from abc import ABC
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.build import (
    BuildJobResponse,
    BuildRequest,
    BuildStatus,
    ContainerConfig,
    GitSource,
    InlineSource,
    NodeRuntime,
    PythonRuntime,
    RawRuntime,
    Runtime,
    Source,
)


# ── Source discriminated union ────────────────────────────────────────────────


def test_git_source_valid() -> None:
    src = GitSource(type="git", url="https://github.com/org/repo", ref="main")
    assert src.url == "https://github.com/org/repo"
    assert src.ref == "main"
    assert src.subpath is None


def test_git_source_with_subpath() -> None:
    src = GitSource(type="git", url="https://github.com/org/repo", ref="v1.0", subpath="services/api")
    assert src.subpath == "services/api"


def test_inline_source_valid() -> None:
    src = InlineSource(type="inline", content="SGVsbG8gV29ybGQ=")
    assert src.content == "SGVsbG8gV29ybGQ="


def test_inline_source_strips_newlines() -> None:
    # macOS `base64` wraps at 76 chars — validator must strip before storing
    multiline = "SGVsbG8g\nV29ybGQ="
    src = InlineSource(type="inline", content=multiline)
    assert "\n" not in src.content
    assert src.content == "SGVsbG8gV29ybGQ="


def test_inline_source_empty_raises() -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        InlineSource(type="inline", content="")


def test_inline_source_invalid_base64_raises() -> None:
    with pytest.raises(ValidationError, match="valid base64"):
        InlineSource(type="inline", content="not!!valid**base64")


def test_source_discriminated_git() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Source)
    s = ta.validate_python({"type": "git", "url": "https://github.com/org/repo", "ref": "main"})
    assert isinstance(s, GitSource)


def test_source_discriminated_inline() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Source)
    s = ta.validate_python({"type": "inline", "content": "dGVzdCBjb250ZXh0"})
    assert isinstance(s, InlineSource)


def test_source_wrong_type_raises() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Source)
    with pytest.raises(ValidationError):
        ta.validate_python({"type": "unknown", "url": "https://github.com/org/repo"})


# ── Runtime discriminated union ───────────────────────────────────────────────


def test_python_runtime_valid() -> None:
    rt = PythonRuntime(type="python", version="3.13", packages=["fastapi", "uvicorn"])
    assert rt.version == "3.13"
    assert rt.packages == ["fastapi", "uvicorn"]


def test_node_runtime_valid() -> None:
    rt = NodeRuntime(type="node", version="20", packages=["express"])
    assert rt.version == "20"
    assert rt.packages == ["express"]


def test_raw_runtime_valid() -> None:
    rt = RawRuntime(type="raw", dockerfile="FROM python:3.13\nRUN echo hi")
    assert "FROM python:3.13" in rt.dockerfile


def test_runtime_discriminated_python() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Runtime)
    r = ta.validate_python({"type": "python", "version": "3.13", "packages": []})
    assert isinstance(r, PythonRuntime)


def test_runtime_discriminated_node() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Runtime)
    r = ta.validate_python({"type": "node", "version": "20", "packages": ["express"]})
    assert isinstance(r, NodeRuntime)


def test_runtime_discriminated_raw() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Runtime)
    r = ta.validate_python({"type": "raw", "dockerfile": "FROM scratch"})
    assert isinstance(r, RawRuntime)


def test_runtime_wrong_type_raises() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Runtime)
    with pytest.raises(ValidationError):
        ta.validate_python({"type": "deno", "version": "1"})


# ── ContainerConfig ───────────────────────────────────────────────────────────


def test_container_config_defaults() -> None:
    cfg = ContainerConfig()
    assert cfg.workdir == "/app"
    assert cfg.cmd is None
    assert cfg.entrypoint is None
    assert cfg.env == {}
    assert cfg.expose == []
    assert cfg.labels == {}
    assert cfg.user is None


def test_container_config_with_values() -> None:
    cfg = ContainerConfig(
        cmd=["uvicorn", "app.main:app", "--host", "0.0.0.0"],
        entrypoint=["python"],
        workdir="/srv",
        env={"PORT": "8080", "LOG_LEVEL": "info"},
        expose=[8080],
        labels={"version": "1.0"},
        user="appuser",
    )
    assert cfg.cmd == ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
    assert cfg.workdir == "/srv"
    assert cfg.env["PORT"] == "8080"
    assert cfg.expose == [8080]
    assert cfg.user == "appuser"


def test_build_request_container_defaults() -> None:
    req = BuildRequest(
        source=GitSource(type="git", url="https://github.com/org/repo", ref="main"),
        runtime=PythonRuntime(type="python"),
        image_ref="registry/img:latest",
    )
    assert isinstance(req.container, ContainerConfig)
    assert req.container.workdir == "/app"


def test_build_request_with_container_config() -> None:
    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdA=="),
        runtime=PythonRuntime(type="python", packages=["fastapi"]),
        image_ref="registry/img:latest",
        container=ContainerConfig(
            cmd=["uvicorn", "app.main:app"],
            env={"PORT": "8080"},
            expose=[8080],
        ),
    )
    assert req.container.cmd == ["uvicorn", "app.main:app"]
    assert req.container.env == {"PORT": "8080"}
    assert req.container.expose == [8080]


# ── Dockerfile generation ─────────────────────────────────────────────────────


def test_generate_dockerfile_python_defaults() -> None:
    from app.builders.kaniko import _generate_dockerfile

    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdCBjb250ZXh0"),
        runtime=PythonRuntime(type="python", version="3.13", packages=["fastapi"]),
        image_ref="img:latest",
    )
    df = _generate_dockerfile(req)
    assert df is not None
    assert "FROM python:3.13-slim" in df
    assert "WORKDIR /app" in df
    assert "COPY . ." in df
    assert "pip install --no-cache-dir fastapi" in df


def test_generate_dockerfile_python_with_container_config() -> None:
    from app.builders.kaniko import _generate_dockerfile

    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdCBjb250ZXh0"),
        runtime=PythonRuntime(type="python", version="3.13", packages=["fastapi"]),
        image_ref="img:latest",
        container=ContainerConfig(
            cmd=["uvicorn", "app.main:app", "--host", "0.0.0.0"],
            workdir="/srv",
            env={"PORT": "8080"},
            expose=[8080],
            user="appuser",
        ),
    )
    df = _generate_dockerfile(req)
    assert df is not None
    assert "WORKDIR /srv" in df
    assert "ENV PORT='8080'" in df
    assert "EXPOSE 8080" in df
    assert "USER appuser" in df
    assert 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]' in df


def test_generate_dockerfile_node_with_container_config() -> None:
    from app.builders.kaniko import _generate_dockerfile

    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdCBjb250ZXh0"),
        runtime=NodeRuntime(type="node", version="20", packages=["express"]),
        image_ref="img:latest",
        container=ContainerConfig(cmd=["node", "index.js"]),
    )
    df = _generate_dockerfile(req)
    assert df is not None
    assert "FROM node:20-slim" in df
    assert "npm install express" in df
    assert 'CMD ["node", "index.js"]' in df


def test_generate_dockerfile_raw_returns_none() -> None:
    from app.builders.kaniko import _generate_dockerfile

    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdCBjb250ZXh0"),
        runtime=RawRuntime(type="raw", dockerfile="FROM scratch"),
        image_ref="img:latest",
        container=ContainerConfig(cmd=["ignored"]),
    )
    # RawRuntime returns None — container config is not applied to explicit Dockerfiles
    assert _generate_dockerfile(req) is None


def test_generate_dockerfile_entrypoint_and_cmd() -> None:
    from app.builders.kaniko import _generate_dockerfile

    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdCBjb250ZXh0"),
        runtime=PythonRuntime(type="python"),
        image_ref="img:latest",
        container=ContainerConfig(
            entrypoint=["python", "-m"],
            cmd=["app.main"],
        ),
    )
    df = _generate_dockerfile(req)
    assert df is not None
    assert 'ENTRYPOINT ["python", "-m"]' in df
    assert 'CMD ["app.main"]' in df


# ── BuildRequest round-trip ───────────────────────────────────────────────────


def test_build_request_round_trip() -> None:
    req = BuildRequest(
        source=GitSource(type="git", url="https://github.com/org/repo", ref="main"),
        runtime=PythonRuntime(type="python", version="3.13", packages=["fastapi"]),
        image_ref="registry.example.com/img:latest",
    )
    data = req.model_dump()
    req2 = BuildRequest.model_validate(data)
    assert req2.image_ref == "registry.example.com/img:latest"
    assert isinstance(req2.source, GitSource)
    assert isinstance(req2.runtime, PythonRuntime)


def test_build_request_json_round_trip() -> None:
    req = BuildRequest(
        source=InlineSource(type="inline", content="dGVzdA=="),
        runtime=NodeRuntime(type="node", version="20", packages=[]),
        image_ref="docker.io/org/img:1.0",
    )
    json_str = req.model_dump_json()
    req2 = BuildRequest.model_validate_json(json_str)
    assert isinstance(req2.source, InlineSource)
    assert isinstance(req2.runtime, NodeRuntime)


# ── BuildStatus enum ──────────────────────────────────────────────────────────


def test_build_status_values() -> None:
    assert BuildStatus.pending == "pending"
    assert BuildStatus.running == "running"
    assert BuildStatus.succeeded == "succeeded"
    assert BuildStatus.failed == "failed"
    assert BuildStatus.cancelled == "cancelled"


# ── BuildJobResponse ──────────────────────────────────────────────────────────


def test_build_job_response_from_attributes() -> None:
    now = datetime.now(tz=timezone.utc)

    class FakeJob:
        id = "abc-123"
        status = "pending"
        source_type = "git"
        runtime_type = "python"
        image_ref = "registry/img:tag"
        k8s_job_name = None
        error = None
        created_at = now
        updated_at = now

    resp = BuildJobResponse.model_validate(FakeJob(), from_attributes=True)
    assert resp.id == "abc-123"
    assert resp.status == BuildStatus.pending
    assert resp.k8s_job_name is None


# ── Builder ABC ───────────────────────────────────────────────────────────────


def test_builder_is_abstract() -> None:
    from app.builders.abc import Builder

    assert issubclass(Builder, ABC)
    abstract_methods = {
        name for name, _ in inspect.getmembers(Builder, predicate=inspect.isfunction)
        if getattr(getattr(Builder, name), "__isabstractmethod__", False)
    }
    assert "build" in abstract_methods
    assert "cancel" in abstract_methods
    assert "get_logs" in abstract_methods


def test_builder_cannot_instantiate() -> None:
    from app.builders.abc import Builder

    with pytest.raises(TypeError):
        Builder()  # type: ignore[abstract]


# ── SourceProvider ABC ────────────────────────────────────────────────────────


def test_source_provider_is_abstract() -> None:
    from app.sources.abc import SourceProvider

    assert issubclass(SourceProvider, ABC)
    abstract_methods = {
        name for name, _ in inspect.getmembers(SourceProvider, predicate=inspect.isfunction)
        if getattr(getattr(SourceProvider, name), "__isabstractmethod__", False)
    }
    assert "prepare" in abstract_methods


def test_source_provider_cannot_instantiate() -> None:
    from app.sources.abc import SourceProvider

    with pytest.raises(TypeError):
        SourceProvider()  # type: ignore[abstract]


# ── BuildJob SQLAlchemy model ─────────────────────────────────────────────────


def test_build_job_model_columns() -> None:
    from app.db.models.build_job import BuildJob

    mapper = BuildJob.__table__
    col_names = {c.name for c in mapper.columns}
    required_cols = {
        "id", "status", "source_type", "runtime_type", "image_ref",
        "k8s_job_name", "logs_url", "error", "created_at", "updated_at",
    }
    assert required_cols.issubset(col_names), f"Missing columns: {required_cols - col_names}"


def test_build_job_tablename() -> None:
    from app.db.models.build_job import BuildJob

    assert BuildJob.__tablename__ == "build_jobs"


def test_build_job_instantiable() -> None:
    from app.db.models.build_job import BuildJob

    job = BuildJob(
        source_type="git",
        runtime_type="python",
        image_ref="registry/img:tag",
    )
    assert job.status == "pending"
    assert job.k8s_job_name is None
