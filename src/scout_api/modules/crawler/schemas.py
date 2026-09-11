from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl
    include_images: bool = Field(
        default=False,
        description="When true, extract and normalize the product image gallery.",
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
