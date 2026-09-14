from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from scout_api.core.database import check_database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable", "not_configured"]


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Liveness plus optional PostgreSQL probe.

    Always returns HTTP 200 so Docker/k8s liveness is not coupled to Postgres.
    Operators inspecting readiness should treat ``database=unavailable`` (when
    ``DATABASE_URL`` is set) as not ready for persist endpoints.
    """
    database = check_database()
    status: Literal["ok", "degraded"] = (
        "degraded" if database == "unavailable" else "ok"
    )
    return HealthResponse(status=status, database=database)
