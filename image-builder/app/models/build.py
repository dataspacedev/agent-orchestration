"""Pydantic v2 schemas for the image-builder service."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    content: str  # base64-encoded tar.gz


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


class BuildStatus(str, Enum):
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


__all__ = [
    "Source",
    "Runtime",
    "BuildRequest",
    "BuildJobResponse",
    "BuildStatus",
    "GitSource",
    "InlineSource",
    "PythonRuntime",
    "NodeRuntime",
    "RawRuntime",
]
