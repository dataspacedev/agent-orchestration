"""Build job CRUD + log streaming routes."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.builders.kaniko import KanikoBuilder
from app.db.models.build_job import BuildJob
from app.db.session import get_db
from app.models.build import BuildJobResponse, BuildRequest, BuildStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["builds"])


def _not_found() -> None:
    raise HTTPException(status_code=404, detail="Build job not found")


# ── POST /builds ──────────────────────────────────────────────────────────────


@router.post("", response_model=BuildJobResponse, status_code=202)
async def create_build(
    payload: BuildRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BuildJob:
    """Accept a build request, persist a pending job, and dispatch it asynchronously."""
    job = BuildJob(
        source_type=payload.source.type,
        runtime_type=payload.runtime.type,
        image_ref=payload.image_ref,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    builder: KanikoBuilder = request.app.state.builder
    asyncio.create_task(
        _dispatch_build(builder, payload, job.id, db),
        name=f"build-{job.id}",
    )
    return job


async def _dispatch_build(
    builder: KanikoBuilder,
    payload: BuildRequest,
    job_id: str,
    db: AsyncSession,
) -> None:
    """Background task: call builder.build() and persist status updates."""
    async with db.begin():
        result = await db.execute(select(BuildJob).where(BuildJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Build job %s not found for dispatch", job_id)
            return
        try:
            await builder.build(payload, job)
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            job.status = BuildStatus.failed.value
            job.error = str(exc)
            await db.commit()
            logger.error("Build job %s failed: %s", job_id, exc)


# ── GET /builds/{job_id} ──────────────────────────────────────────────────────


@router.get("/{job_id}", response_model=BuildJobResponse)
async def get_build(job_id: str, db: AsyncSession = Depends(get_db)) -> BuildJob:
    """Return the build job record or 404."""
    result = await db.execute(select(BuildJob).where(BuildJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        _not_found()
    return job  # type: ignore[return-value]


# ── GET /builds/{job_id}/logs ─────────────────────────────────────────────────


@router.get("/{job_id}/logs")
async def get_build_logs(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream logs from the kaniko Job or return 404/501 stubs."""
    result = await db.execute(select(BuildJob).where(BuildJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Build job not found")
    if job.k8s_job_name is None:
        raise HTTPException(status_code=404, detail="job not yet dispatched")

    builder: KanikoBuilder = request.app.state.builder

    async def _log_stream() -> AsyncGenerator[bytes]:
        async for line in builder.get_logs(job_id):
            yield (line + "\n").encode()

    return StreamingResponse(_log_stream(), media_type="text/plain")


# ── DELETE /builds/{job_id} ───────────────────────────────────────────────────


@router.delete("/{job_id}", status_code=204)
async def cancel_build(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel the build job and mark its status as cancelled."""
    result = await db.execute(select(BuildJob).where(BuildJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        _not_found()
        return  # unreachable — satisfies mypy

    builder: KanikoBuilder = request.app.state.builder
    await builder.cancel(job_id)
    job.status = BuildStatus.cancelled.value
    await db.commit()
