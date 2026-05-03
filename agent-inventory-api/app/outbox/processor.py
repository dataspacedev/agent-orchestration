import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.agent import Agent
from app.db.models.outbox import AgentOutbox
from app.k8s.client import K8sAgentClient, make_crd_name
from app.models.agent import OutboxEventType, OutboxStatus

logger = logging.getLogger(__name__)


class OutboxProcessor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        k8s_client: K8sAgentClient,
        poll_interval: float,
        max_retries: int,
        processing_timeout: float,
    ) -> None:
        self._session_factory = session_factory
        self._k8s = k8s_client
        self._poll_interval = poll_interval
        self._max_retries = max_retries
        self._processing_timeout = processing_timeout

    async def _reconcile_on_startup(self) -> None:
        if not self._k8s.is_ready:
            logger.info("outbox: K8s client not ready, skipping startup reconciliation")
            return

        async with self._session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.spec.is_not(None)))
            agents = list(result.scalars().all())

        logger.info("outbox: reconciling %d agents to cluster on startup", len(agents))
        errors = 0
        for agent in agents:
            crd_name = make_crd_name(agent.name, agent.version)
            try:
                await self._k8s.apply(crd_name=crd_name, spec_payload=agent.spec)
            except Exception as exc:
                logger.warning("startup reconciliation failed for %s: %s", crd_name, exc)
                errors += 1

        logger.info(
            "outbox: startup reconciliation complete (%d synced, %d errors)",
            len(agents) - errors,
            errors,
        )

    async def _process_one(self) -> bool:
        stale_before = datetime.now(UTC) - timedelta(seconds=self._processing_timeout)

        async with self._session_factory() as db:
            result = await db.execute(
                select(AgentOutbox)
                .where(
                    or_(
                        AgentOutbox.status == OutboxStatus.pending,
                        and_(
                            AgentOutbox.status == OutboxStatus.processing,
                            AgentOutbox.processing_since < stale_before,
                        ),
                    )
                )
                .order_by(AgentOutbox.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            event = result.scalar_one_or_none()
            if event is None:
                return False

            event_id: str = event.id
            event_type: str = event.event_type
            payload: dict[str, Any] = event.payload
            event.status = OutboxStatus.processing
            event.processing_since = datetime.now(UTC)
            await db.commit()

        error: str | None = None
        try:
            if event_type in (OutboxEventType.created, OutboxEventType.updated):
                await self._k8s.apply(
                    crd_name=payload["crd_name"],
                    spec_payload=payload["spec"],
                )
            elif event_type in (OutboxEventType.deleted, OutboxEventType.stopped):
                await self._k8s.delete(crd_name=payload["crd_name"])
        except Exception as exc:
            error = str(exc)
            logger.warning("outbox event %s (%s) failed: %s", event_id, event_type, error)

        async with self._session_factory() as db:
            result = await db.execute(select(AgentOutbox).where(AgentOutbox.id == event_id))
            event = result.scalar_one_or_none()
            if event is None:
                return True
            if error is None:
                event.status = OutboxStatus.completed
                event.processed_at = datetime.now(UTC)
            else:
                event.attempts += 1
                event.last_error = error
                event.status = (
                    OutboxStatus.failed
                    if event.attempts >= self._max_retries
                    else OutboxStatus.pending
                )
            await db.commit()

        return True

    async def run(self) -> None:
        await self._reconcile_on_startup()
        while True:
            try:
                await self._process_one()
            except Exception as exc:
                logger.error("outbox processor unexpected error: %s", exc, exc_info=True)
            await asyncio.sleep(self._poll_interval)
