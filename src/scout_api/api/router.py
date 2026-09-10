from fastapi import APIRouter

from scout_api.modules.crawler.router import router as crawler_router
from scout_api.modules.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(crawler_router)
