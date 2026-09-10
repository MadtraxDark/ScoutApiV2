from fastapi import APIRouter

from scout_api.modules.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
