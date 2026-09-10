from pydantic import BaseModel, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl


class CrawlError(BaseModel):
    code: str
    message: str
    url: str | None = None
    upstream_status: int | None = None
    retryable: bool = False
    retry_after: int | None = None


class CrawlErrorResponse(BaseModel):
    detail: CrawlError
