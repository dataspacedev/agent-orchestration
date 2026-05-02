"""Abstract base class for image builders."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.models.build import BuildRequest


class Builder(ABC):
    """Contract for all image builder backends."""

    @abstractmethod
    async def build(self, request: BuildRequest, db_job: object) -> None:
        """Dispatch a build job and update *db_job* in place.

        Implementors should set db_job.status = "running" and
        db_job.k8s_job_name before returning.
        """

    @abstractmethod
    async def cancel(self, job_id: str) -> None:
        """Cancel the running build identified by *job_id*."""

    @abstractmethod
    async def get_logs(self, job_id: str) -> AsyncIterator[str]:
        """Yield log lines for the build identified by *job_id*."""
        # This is an abstract async generator — implementations must use `yield`.
        # The type annotation satisfies static analysis while the pragma below
        # prevents the "empty generator" false-positive.
        return  # pragma: no cover
        yield  # make this an async generator to satisfy type checkers  # noqa: unreachable


__all__ = ["Builder"]
