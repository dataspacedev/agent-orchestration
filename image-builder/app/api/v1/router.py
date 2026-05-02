"""API v1 router aggregating all sub-routers."""
from fastapi import APIRouter

from app.api.v1.routes.builds import router as builds_router
from app.api.v1.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(builds_router, prefix="/builds")
api_router.include_router(health_router)
