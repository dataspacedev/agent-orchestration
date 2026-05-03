"""Build job CRUD + log streaming routes."""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.builders.kaniko import KanikoBuilder
from app.db.models.build_job import BuildJob
from app.db.session import AsyncSessionLocal, get_db
from app.models.build import (
    BuildJobResponse,
    BuildListResponse,
    BuildRequest,
    BuildStatus,
    ContainerConfig,
    InlineSource,
    Runtime,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["builds"])


class SortBy(str, Enum):
    created_at = "created_at"
    updated_at = "updated_at"
    status = "status"
    image_ref = "image_ref"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


def _not_found() -> None:
    raise HTTPException(status_code=404, detail="Build job not found")


# ── shared: persist job record + kick off background dispatch ─────────────────

_runtime_adapter: TypeAdapter[Runtime] = TypeAdapter(Runtime)


async def _persist_and_dispatch(
    payload: BuildRequest,
    request: Request,
    db: AsyncSession,
) -> BuildJob:
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
        _dispatch_build(builder, payload, job.id),
        name=f"build-{job.id}",
    )
    return job


# ── POST /builds ──────────────────────────────────────────────────────────────


@router.post("", response_model=BuildJobResponse, status_code=202)
async def create_build(
    payload: BuildRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BuildJob:
    """Submit a build request as JSON (source, runtime, container config, image_ref)."""
    return await _persist_and_dispatch(payload, request, db)


# ── POST /builds/upload ───────────────────────────────────────────────────────


@router.post("/upload", response_model=BuildJobResponse, status_code=202)
async def create_build_from_upload(
    request: Request,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(..., description="tar.gz build context"),
    runtime: str = Form(
        ...,
        description='Runtime config as JSON. Example: {"type":"python","version":"3.13","packages":["fastapi","uvicorn"]}',
    ),
    image_ref: str = Form(..., description="Target image ref. Example: my-registry/my-image:v1.0.0"),
    container: str = Form(
        default="{}",
        description='Container config as JSON. Example: {"cmd":["uvicorn","app.main:app","--host","0.0.0.0"]}',
    ),
) -> BuildJob:
    """Upload a tar.gz build context directly (usable from Swagger UI).

    - **file**: tar.gz archive of your build context
    - **runtime**: JSON — `{"type":"python"|"node"|"raw", ...}`
    - **image_ref**: destination image reference
    - **container**: JSON — `{"cmd":[...], "workdir":"/app", "env":{}, "expose":[], ...}` (optional)
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    content_b64 = base64.b64encode(raw).decode()

    try:
        runtime_obj = _runtime_adapter.validate_json(runtime)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid runtime JSON: {exc}") from exc

    try:
        container_obj = ContainerConfig.model_validate_json(container)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid container JSON: {exc}") from exc

    payload = BuildRequest(
        source=InlineSource(type="inline", content=content_b64),
        runtime=runtime_obj,
        image_ref=image_ref,
        container=container_obj,
    )
    return await _persist_and_dispatch(payload, request, db)


async def _dispatch_build(
    builder: KanikoBuilder,
    payload: BuildRequest,
    job_id: str,
) -> None:
    """Background task: dispatch the kaniko Job, then poll until completion.

    Opens its own DB session — the request session is closed before this runs.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BuildJob).where(BuildJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Build job %s not found for dispatch", job_id)
            return

        # Phase 1: create the K8s Job (sets job.status → running)
        try:
            await builder.build(payload, job)
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            job.status = BuildStatus.failed.value
            job.error = str(exc)
            await db.commit()
            logger.error("Build job %s failed to dispatch: %s", job_id, exc)
            return

        # Phase 2: poll until the kaniko Job finishes
        try:
            succeeded = await builder.wait_for_completion(job_id)
            job.status = BuildStatus.succeeded.value if succeeded else BuildStatus.failed.value
            if not succeeded:
                job.error = job.error or "kaniko Job failed or timed out"
            await db.commit()
            logger.info("Build job %s → %s", job_id, job.status)
        except Exception as exc:  # noqa: BLE001
            job.status = BuildStatus.failed.value
            job.error = str(exc)
            await db.commit()
            logger.error("Build job %s failed during execution: %s", job_id, exc)


# ── GET /builds ───────────────────────────────────────────────────────────────


@router.get("", response_model=BuildListResponse)
async def list_builds(
    db: AsyncSession = Depends(get_db),
    status: Annotated[list[BuildStatus] | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    runtime_type: Annotated[str | None, Query()] = None,
    image_ref: Annotated[str | None, Query(description="Substring match against image_ref")] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    sort_by: Annotated[SortBy, Query()] = SortBy.created_at,
    sort_order: Annotated[SortOrder, Query()] = SortOrder.desc,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BuildListResponse:
    """List build jobs with optional filtering, sorting, and pagination."""
    stmt = select(BuildJob)

    if status:
        stmt = stmt.where(BuildJob.status.in_([s.value for s in status]))
    if source_type:
        stmt = stmt.where(BuildJob.source_type == source_type)
    if runtime_type:
        stmt = stmt.where(BuildJob.runtime_type == runtime_type)
    if image_ref:
        stmt = stmt.where(BuildJob.image_ref.contains(image_ref))
    if created_after:
        stmt = stmt.where(BuildJob.created_at >= created_after)
    if created_before:
        stmt = stmt.where(BuildJob.created_at <= created_before)

    total: int = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_col = getattr(BuildJob, sort_by.value)
    ordered = sort_col.desc() if sort_order == SortOrder.desc else sort_col.asc()
    result = await db.execute(stmt.order_by(ordered).limit(limit).offset(offset))
    items = list(result.scalars().all())

    return BuildListResponse(
        items=[BuildJobResponse.model_validate(job) for job in items],
        total=total,
        limit=limit,
        offset=offset,
    )


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
