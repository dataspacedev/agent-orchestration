from fastapi import APIRouter

from app.api.v1.routes import agents, health

api_router = APIRouter()

api_router.include_router(health.router, prefix="")
api_router.include_router(agents.router, prefix="")
