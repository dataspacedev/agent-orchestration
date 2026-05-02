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


def test_source_discriminated_git() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Source)
    s = ta.validate_python({"type": "git", "url": "https://github.com/org/repo", "ref": "main"})
    assert isinstance(s, GitSource)


def test_source_discriminated_inline() -> None:
    from pydantic import TypeAdapter
    ta = TypeAdapter(Source)
    s = ta.validate_python({"type": "inline", "content": "abc123"})
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
