"""Abstract base class for source providers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.build import Source


class SourceProvider(ABC):
    """Contract for build context source backends."""

    @abstractmethod
    async def prepare(self, source: Source, workspace_path: str) -> str:
        """Prepare the build context at *workspace_path* and return the context path."""


__all__ = ["SourceProvider"]
