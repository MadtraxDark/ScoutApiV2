from fastapi import FastAPI

from scout_api.api.router import api_router
from scout_api.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(api_router)
