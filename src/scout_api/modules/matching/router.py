"""HTTP routes for product matching and offer refresh."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Generator, Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from scout_api.core.config import get_settings
from scout_api.core.database import get_db_session
from scout_api.core.db_errors import classify_database_error
from scout_api.modules.auth.deps import enforce_rate_limit, require_permission
from scout_api.modules.auth.schemas import AuthenticatedPrincipal
from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.schemas import CrawlErrorResponse
from scout_api.modules.crawler.spiders.registry import stores_supporting_search
from scout_api.modules.crawler.stores import STORE_CONFIGS
from scout_api.modules.matching.offer_refresh_service import OfferRefreshService
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.product_registration_service import (
    ProductRegistrationService,
)
from scout_api.modules.matching.schemas import (
    MatchProgressEvent,
    MatchRequest,
    MatchResponse,
    OfferRefreshRequest,
    OfferRefreshResponse,
    ProductListResponse,
    ProductRegisterRequest,
    ProductRegisterResponse,
    ProductSearchResponse,
    ProductUpdateRequest,
    ProductView,
    StoreInfo,
    StoreListResponse,
)

router = APIRouter(
    dependencies=[Depends(enforce_rate_limit("default"))],
)


def _optional_db_session() -> Generator[Session | None, None, None]:
    settings = get_settings()
    if not settings.database_url:
        yield None
        return
    yield from get_db_session()


def get_match_service(
    session: Annotated[Session | None, Depends(_optional_db_session)],
) -> ProductMatchService:
    return ProductMatchService(session=session)


def get_refresh_service(
    session: Annotated[Session | None, Depends(_optional_db_session)],
) -> OfferRefreshService:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "DATABASE_URL não configurada",
                "retryable": False,
            },
        )
    return OfferRefreshService(session=session)


def get_registration_service(
    session: Annotated[Session | None, Depends(_optional_db_session)],
) -> ProductRegistrationService:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "DATABASE_URL não configurada",
                "retryable": False,
            },
        )
    return ProductRegistrationService(session=session)


@router.post(
    "/products",
    response_model=ProductRegisterResponse,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de escrita."},
        409: {
            "model": CrawlErrorResponse,
            "description": "Conflito de integridade ao persistir o produto.",
        },
        422: {
            "model": CrawlErrorResponse,
            "description": "Dados de cadastro inválidos.",
        },
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("products:write"))],
    summary="Cadastrar produto",
    description=(
        "Cadastra um produto canônico ou reutiliza um já existente "
        "sem sobrescrita silenciosa. "
        "Pode anexar um listing de loja quando store "
        "e identificadores forem informados."
    ),
)
def register_product(
    payload: ProductRegisterRequest,
    service: Annotated[ProductRegistrationService, Depends(get_registration_service)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:write"))
    ],
) -> ProductRegisterResponse:
    try:
        return service.register(payload, owner=principal)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc


@router.get(
    "/products",
    response_model=ProductListResponse,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de leitura."},
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("products:read"))],
    summary="Listar produtos",
    description=(
        "Lista produtos canônicos visíveis ao usuário autenticado, "
        "com paginação por limit/offset e ordenação por updated_at."
    ),
)
def list_products(
    service: Annotated[ProductRegistrationService, Depends(get_registration_service)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:read"))
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListResponse:
    try:
        return service.list_products(viewer=principal, limit=limit, offset=offset)
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc


@router.get(
    "/stores",
    response_model=StoreListResponse,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
    },
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("products:read"))],
    summary="Listar lojas do crawler",
    description=(
        "Retorna o registry estático de lojas suportadas pelo crawler "
        "(não é cadastro dinâmico)."
    ),
)
def list_stores(
    _principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:read"))
    ],
) -> StoreListResponse:
    search_keys = set(stores_supporting_search())
    stores = [
        StoreInfo(
            key=key,
            country=config.country,
            currency=config.currency,
            domains=list(config.domains),
            implemented=config.implemented,
            supports_search=key in search_keys,
            supports_images=config.supports_images,
            image_fetch_cost=config.image_fetch_cost,
            default_include_images=config.default_include_images,
        )
        for key, config in STORE_CONFIGS.items()
    ]
    return StoreListResponse(stores=stores)


@router.get(
    "/products/search",
    response_model=ProductSearchResponse,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de leitura."},
        422: {
            "model": CrawlErrorResponse,
            "description": "Informe ao menos brand, model ou variant.",
        },
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("products:read"))],
    summary="Buscar produtos",
    description=(
        "Filtra o catálogo canônico por brand, model, variant e atributos "
        "opcionais (category-aware). Model identifica a família base; "
        "variant só restringe quando informado."
    ),
)
def search_products(
    service: Annotated[ProductRegistrationService, Depends(get_registration_service)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:read"))
    ],
    brand: Annotated[
        str | None, Query(description="Marca (opcional, case-insensitive).")
    ] = None,
    model: Annotated[
        str | None,
        Query(
            description=(
                "Modelo base pesquisável (ex.: GeForce RTX 5070). Não exige variant."
            )
        ),
    ] = None,
    variant: Annotated[
        str | None,
        Query(
            description=(
                "Refinamento comercial opcional (ex.: Dual OC Edition). "
                "Quando omitido, retorna todas as implementações do modelo."
            )
        ),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="Categoria do perfil (gpu, ram, smartphone, …)."),
    ] = None,
    vram: Annotated[str | None, Query(description="Filtro de VRAM (GPU).")] = None,
    memory_type: Annotated[
        str | None, Query(description="DDR5 / GDDR7 / …")
    ] = None,
    capacity: Annotated[
        str | None, Query(description="Capacidade (RAM/SSD/storage).")
    ] = None,
    frequency: Annotated[str | None, Query(description="Frequência (RAM).")] = None,
    chipset: Annotated[str | None, Query(description="Chipset (placa-mãe).")] = None,
    socket: Annotated[str | None, Query(description="Socket (CPU/MB).")] = None,
    storage: Annotated[str | None, Query(description="Armazenamento.")] = None,
    refresh_rate: Annotated[
        str | None, Query(description="Taxa de atualização (monitor/TV).")
    ] = None,
    wattage: Annotated[str | None, Query(description="Potência (PSU/charger).")] = None,
    panel: Annotated[str | None, Query(description="Painel (OLED/IPS/…).")] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Máximo de produtos retornados.")
    ] = 50,
) -> ProductSearchResponse:
    attribute_filters = {
        key: value
        for key, value in {
            "vram": vram,
            "memory_type": memory_type,
            "capacity": capacity,
            "frequency": frequency,
            "chipset": chipset,
            "socket": socket,
            "storage": storage,
            "refresh_rate": refresh_rate,
            "wattage": wattage,
            "panel": panel,
        }.items()
        if value
    }
    try:
        return service.search_products(
            viewer=principal,
            brand=brand,
            model=model,
            variant=variant,
            category=category,
            attribute_filters=attribute_filters or None,
            limit=limit,
        )
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc


@router.get(
    "/products/{product_id}",
    response_model=ProductView,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de leitura."},
        404: {"model": CrawlErrorResponse, "description": "Produto não encontrado."},
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("products:read"))],
    summary="Consultar produto",
    description=(
        "Retorna o produto canônico e seus listings vinculados, "
        "respeitando a visibilidade do usuário autenticado."
    ),
)
def get_product(
    product_id: Annotated[UUID, Path(description="Identificador do produto canônico.")],
    service: Annotated[ProductRegistrationService, Depends(get_registration_service)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:read"))
    ],
) -> ProductView:
    product = service.get_product(product_id, viewer=principal)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PRODUCT_NOT_FOUND",
                "message": "Produto canônico não encontrado",
                "retryable": False,
            },
        )
    return product


@router.patch(
    "/products/{product_id}",
    response_model=ProductView,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de escrita."},
        404: {"model": CrawlErrorResponse, "description": "Produto não encontrado."},
        422: {"model": CrawlErrorResponse, "description": "Dados inválidos."},
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("products:write"))],
    summary="Atualizar produto",
    description="Atualiza campos editáveis do produto canônico (title, brand, model, variant, attributes).",
)
def update_product(
    product_id: Annotated[UUID, Path(description="Identificador do produto canônico.")],
    payload: ProductUpdateRequest,
    service: Annotated[ProductRegistrationService, Depends(get_registration_service)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:write"))
    ],
) -> ProductView:
    try:
        return service.update_product(product_id, payload, owner=principal)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Produtos"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de escrita."},
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    dependencies=[Depends(require_permission("products:write"))],
    summary="Excluir produto",
    description=(
        "Remove o produto canônico e listings associados (cascade). "
        "Idempotente quando o produto já não existe."
    ),
    response_class=Response,
)
def delete_product(
    product_id: Annotated[UUID, Path(description="Identificador do produto canônico.")],
    service: Annotated[ProductRegistrationService, Depends(get_registration_service)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("products:write"))
    ],
) -> Response:
    try:
        service.delete_product(product_id, owner=principal)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/match",
    response_model=MatchResponse,
    tags=["Correspondência"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de matching."},
        422: {
            "model": CrawlErrorResponse,
            "description": "URL inválida, loja sem suporte ou falha de parsing.",
        },
        429: {
            "model": CrawlErrorResponse,
            "description": "Limite de requisições excedido.",
        },
        502: {
            "model": CrawlErrorResponse,
            "description": "Bloqueio ou falha ao acessar loja de origem.",
        },
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco indisponível quando persist=true.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_permission("match")),
        Depends(enforce_rate_limit("crawler")),
    ],
    summary="Corresponder produto entre lojas",
    description=(
        "A partir da URL de referência, busca candidatos nas lojas informadas "
        "(ou no conjunto padrão) e classifica cada hit "
        "como auto_match, review ou reject. "
        "Com persist=true, grava o produto canônico e os listings no banco."
    ),
)
def match_product(
    payload: MatchRequest,
    service: Annotated[ProductMatchService, Depends(get_match_service)],
) -> MatchResponse:
    if payload.persist and get_settings().database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": (
                    "DATABASE_URL não configurada; "
                    "use persist=false ou configure o Postgres"
                ),
                "retryable": False,
            },
        )
    try:
        return service.match(payload)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "url": exc.url,
                "upstream_status": exc.upstream_status,
                "retryable": exc.retryable,
                "retry_after": exc.retry_after,
            },
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PARSE_ERROR",
                "message": str(exc),
                "url": str(payload.reference_url),
                "retryable": False,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc


@router.post(
    "/match/stream",
    tags=["Correspondência"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de matching."},
        422: {
            "model": CrawlErrorResponse,
            "description": "URL inválida, loja sem suporte ou falha de parsing.",
        },
        429: {
            "model": CrawlErrorResponse,
            "description": "Limite de requisições excedido.",
        },
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco indisponível quando persist=true.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_permission("match")),
        Depends(enforce_rate_limit("crawler")),
    ],
    summary="Corresponder produto com progresso SSE",
    description=(
        "Executa o mesmo Product Match de POST /match uma única vez, "
        "emitindo eventos SSE de progresso por loja até o resultado final."
    ),
)
def match_product_stream(
    payload: MatchRequest,
    service: Annotated[ProductMatchService, Depends(get_match_service)],
) -> StreamingResponse:
    if payload.persist and get_settings().database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": (
                    "DATABASE_URL não configurada; "
                    "use persist=false ou configure o Postgres"
                ),
                "retryable": False,
            },
        )

    def event_stream() -> Iterator[str]:
        progress_q: queue.SimpleQueue[MatchProgressEvent | BaseException | None] = (
            queue.SimpleQueue()
        )

        def on_progress(event: MatchProgressEvent) -> None:
            progress_q.put(event)

        def worker() -> None:
            try:
                service.match(payload, on_progress=on_progress)
            except BaseException as exc:  # noqa: BLE001 — delivered via SSE
                progress_q.put(exc)
            finally:
                progress_q.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while True:
            item = progress_q.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                if isinstance(item, RequestError):
                    detail = {
                        "type": "error",
                        "stage": "error",
                        "status": "error",
                        "message": str(item),
                        "code": item.code,
                    }
                elif isinstance(item, ParseError):
                    detail = {
                        "type": "error",
                        "stage": "error",
                        "status": "error",
                        "message": str(item),
                        "code": "PARSE_ERROR",
                    }
                else:
                    detail = {
                        "type": "error",
                        "stage": "error",
                        "status": "error",
                        "message": "Falha interna no Product Match",
                        "code": "INTERNAL_ERROR",
                    }
                yield f"data: {json.dumps(detail, default=str)}\n\n"
                break
            yield (
                "data: "
                + item.model_dump_json(exclude_none=False)
                + "\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/offers/refresh",
    response_model=OfferRefreshResponse,
    tags=["Ofertas"],
    responses={
        401: {"model": CrawlErrorResponse, "description": "Não autenticado."},
        403: {"model": CrawlErrorResponse, "description": "Sem permissão de refresh."},
        422: {
            "model": CrawlErrorResponse,
            "description": "Pedido inválido ou falha ao interpretar a página.",
        },
        429: {
            "model": CrawlErrorResponse,
            "description": "Limite de requisições excedido.",
        },
        502: {
            "model": CrawlErrorResponse,
            "description": "Bloqueio ou falha ao acessar loja de origem.",
        },
        503: {
            "model": CrawlErrorResponse,
            "description": "Banco de dados indisponível ou não configurado.",
        },
    },
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_permission("offers:refresh")),
        Depends(enforce_rate_limit("crawler")),
    ],
    summary="Atualizar ofertas",
    description=(
        "Reexecuta o scraping das ofertas indicadas por produto canônico, "
        "listing_ids ou urls e registra mudanças de preço, vendedor ou disponibilidade."
    ),
)
def refresh_offers(
    payload: OfferRefreshRequest,
    service: Annotated[OfferRefreshService, Depends(get_refresh_service)],
    registration: Annotated[
        ProductRegistrationService, Depends(get_registration_service)
    ],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("offers:refresh"))
    ],
) -> OfferRefreshResponse:
    if get_settings().database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "DATABASE_URL não configurada",
                "retryable": False,
            },
        )
    if (
        payload.canonical_product_id is None
        and not payload.listing_ids
        and not payload.urls
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_REQUEST",
                "message": "Informe canonical_product_id, listing_ids ou urls",
                "retryable": False,
            },
        )
    if payload.canonical_product_id is not None:
        owned = registration.get_product(payload.canonical_product_id, viewer=principal)
        if owned is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Produto canônico não encontrado",
                    "retryable": False,
                },
            )
    try:
        return service.refresh(payload)
    except RequestError as exc:
        raise HTTPException(
            status_code=_status_for_request_error(exc),
            detail={
                "code": exc.code,
                "message": str(exc),
                "url": exc.url,
                "upstream_status": exc.upstream_status,
                "retryable": exc.retryable,
                "retry_after": exc.retry_after,
            },
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PARSE_ERROR",
                "message": str(exc),
                "retryable": False,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _http_for_database_error(exc) from exc


def _http_for_database_error(exc: SQLAlchemyError) -> HTTPException:
    failure = classify_database_error(exc)
    http_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if failure.code == "DATABASE_UNAVAILABLE"
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    if failure.code == "DATABASE_INTEGRITY_ERROR":
        http_status = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=http_status,
        detail={
            "code": failure.code,
            "message": failure.message,
            "retryable": failure.retryable,
        },
    )


def _status_for_request_error(exc: RequestError) -> int:
    if exc.code in {"DUPLICATE_REQUEST", "RATE_LIMITED"}:
        return status.HTTP_429_TOO_MANY_REQUESTS
    if exc.code in {"DATABASE_UNAVAILABLE"}:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if exc.code in {"INVALID_REQUEST", "UNSUPPORTED_STORE", "SEARCH_UNSUPPORTED"}:
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code == "PRODUCT_NOT_FOUND":
        return status.HTTP_404_NOT_FOUND
    if exc.code == "FORBIDDEN":
        return status.HTTP_403_FORBIDDEN
    if exc.code == "AUTH_REQUIRED":
        return status.HTTP_401_UNAUTHORIZED
    return status.HTTP_502_BAD_GATEWAY
