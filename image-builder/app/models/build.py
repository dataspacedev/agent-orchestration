"""Pydantic v2 schemas for the image-builder service."""
from __future__ import annotations

import base64
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Container config ──────────────────────────────────────────────────────────


class ContainerConfig(BaseModel):
    """OCI container-level config applied on top of any generated runtime."""

    model_config = ConfigDict(frozen=True)

    cmd: list[str] | None = None
    entrypoint: list[str] | None = None
    workdir: str = "/app"
    env: dict[str, str] = Field(default_factory=dict)
    expose: list[int] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    user: str | None = None

# ── Source models ─────────────────────────────────────────────────────────────


class GitSource(BaseModel):
    """A Git repository used as the build context."""

    model_config = ConfigDict(frozen=True)

    type: Literal["git"] = "git"
    url: str
    ref: str = "main"
    subpath: str | None = None


class InlineSource(BaseModel):
    """A base64-encoded tar.gz archive used as the build context."""

    model_config = ConfigDict(frozen=True)

    type: Literal["inline"] = "inline"
    content: str  # base64-encoded tar.gz — newlines are stripped automatically

    @field_validator("content")
    @classmethod
    def _normalize_and_validate_base64(cls, v: str) -> str:
        # Strip whitespace so macOS `base64` (which wraps at 76 chars) works out of the box
        v = v.strip().replace("\n", "").replace("\r", "")
        if not v:
            raise ValueError("content must be a non-empty base64-encoded tar.gz")
        try:
            base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError(f"content is not valid base64: {exc}") from exc
        return v


Source = Annotated[GitSource | InlineSource, Field(discriminator="type")]


# ── Runtime models ────────────────────────────────────────────────────────────


class PythonRuntime(BaseModel):
    """Python runtime descriptor — generates a Python Dockerfile."""

    model_config = ConfigDict(frozen=True)

    type: Literal["python"] = "python"
    version: str = "3.13"
    packages: list[str] = Field(default_factory=list)


class NodeRuntime(BaseModel):
    """Node.js runtime descriptor — generates a Node Dockerfile."""

    model_config = ConfigDict(frozen=True)

    type: Literal["node"] = "node"
    version: str = "20"
    packages: list[str] = Field(default_factory=list)


class RawRuntime(BaseModel):
    """Raw Dockerfile content — passed directly to kaniko."""

    model_config = ConfigDict(frozen=True)

    type: Literal["raw"] = "raw"
    dockerfile: str


Runtime = Annotated[PythonRuntime | NodeRuntime | RawRuntime, Field(discriminator="type")]


# ── Build status ──────────────────────────────────────────────────────────────


class BuildStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


# ── Request / Response schemas ────────────────────────────────────────────────


class BuildRequest(BaseModel):
    """Incoming build request from a caller."""

    source: Source
    runtime: Runtime
    image_ref: str
    container: ContainerConfig = Field(default_factory=ContainerConfig)


class BuildJobResponse(BaseModel):
    """Response schema for a BuildJob — can be constructed from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: BuildStatus
    source_type: str
    runtime_type: str
    image_ref: str
    k8s_job_name: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class BuildListResponse(BaseModel):
    """Paginated list of build jobs."""

    items: list[BuildJobResponse]
    total: int
    limit: int
    offset: int


__all__ = [
    "Source",
    "Runtime",
    "BuildRequest",
    "BuildJobResponse",
    "BuildListResponse",
    "BuildStatus",
    "ContainerConfig",
    "GitSource",
    "InlineSource",
    "PythonRuntime",
    "NodeRuntime",
    "RawRuntime",
]
