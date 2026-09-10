class CrawlerError(Exception):
    """Base crawler exception."""


class ParseError(CrawlerError):
    """The page shape is not understood; never emit fabricated prices."""


class MissingPriceError(ParseError):
    pass


class ProductUnavailable(CrawlerError):
    pass
