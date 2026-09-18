import logging
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from scout_api.api.router import api_router
from scout_api.core.config import get_settings
from scout_api.core.http_errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from scout_api.core.log_redaction import install_log_redaction

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.scraper_log_level.upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
install_log_redaction()

_is_production = settings.environment.lower() == "production"
_docs_url: str | None = None if _is_production else "/docs"
_redoc_url: str | None = None if _is_production else "/redoc"
_openapi_url: str | None = None if _is_production else "/openapi.json"

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug and not _is_production,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    openapi_tags=[
        {
            "name": "Saúde da API",
            "description": "Verificação de disponibilidade da API.",
        },
        {
            "name": "Autenticação",
            "description": "Login Google, sessão e usuário autenticado.",
        },
        {
            "name": "Crawler",
            "description": "Scraping de produto e oferta a partir de URL.",
        },
        {
            "name": "Produtos",
            "description": "Cadastro e consulta de produtos canônicos.",
        },
        {
            "name": "Correspondência",
            "description": "Matching de produto entre lojas suportadas.",
        },
        {
            "name": "Ofertas",
            "description": "Atualização de preço e disponibilidade de ofertas.",
        },
    ],
)

origins = [
    part.strip()
    for part in (settings.cors_allowed_origins or "").split(",")
    if part.strip() and part.strip() != "*"
]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

ExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]
app.add_exception_handler(
    StarletteHTTPException,
    cast(ExceptionHandler, http_exception_handler),
)
app.add_exception_handler(
    RequestValidationError,
    cast(ExceptionHandler, validation_exception_handler),
)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)
