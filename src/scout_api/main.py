import logging

from fastapi import FastAPI

from scout_api.api.router import api_router
from scout_api.core.config import get_settings

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.scraper_log_level.upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(api_router)
