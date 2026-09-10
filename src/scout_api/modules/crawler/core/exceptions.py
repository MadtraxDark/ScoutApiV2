class CrawlerError(Exception):
    """Base crawler exception."""


class ParseError(CrawlerError):
    """The page shape is not understood; never emit fabricated prices."""


class MissingPriceError(ParseError):
    pass


class ProductUnavailable(CrawlerError):
    pass


class RequestError(CrawlerError):
    """The store response cannot be treated as a product state."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "REQUEST_ERROR",
        url: str | None = None,
        upstream_status: int | None = None,
        retryable: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.url = url
        self.upstream_status = upstream_status
        self.retryable = retryable
        self.retry_after = retry_after
