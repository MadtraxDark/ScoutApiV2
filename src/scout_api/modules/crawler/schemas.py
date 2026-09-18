from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl = Field(description="URL pública do produto ou da oferta na loja.")
    include_images: bool = Field(
        default=False,
        description=(
            "Quando true, extrai e normaliza a galeria de imagens do produto "
            "(ignorado no scraping só de oferta)."
        ),
    )


class CrawlError(BaseModel):
    code: str
    message: str
    url: str | None = None
    upstream_status: int | None = None
    retryable: bool = False
    retry_after: int | None = None


class CrawlErrorResponse(BaseModel):
    detail: CrawlError
