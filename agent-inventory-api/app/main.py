import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.k8s.client import K8sAgentClient
from app.outbox.processor import OutboxProcessor

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    k8s_client = K8sAgentClient(
        namespace=settings.k8s_namespace,
        in_cluster=settings.k8s_in_cluster,
    )
    await k8s_client.setup()
    processor = OutboxProcessor(
        session_factory=AsyncSessionLocal,
        k8s_client=k8s_client,
        poll_interval=settings.outbox_poll_interval,
        max_retries=settings.outbox_max_retries,
        processing_timeout=settings.outbox_processing_timeout,
    )
    task = asyncio.create_task(processor.run())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await k8s_client.close()
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
