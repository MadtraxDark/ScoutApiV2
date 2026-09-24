"""Parse saved Terabyte live HTML with the updated spider."""

from __future__ import annotations

import json
from pathlib import Path

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.spiders.brazil.terabyteshop import TerabyteShopSpider

HTML = Path("memory/working/_terabyte_probe/curl_cffi_clean.html")
URL = (
    "https://www.terabyteshop.com.br/produto/22809/"
    "placa-mae-gigabyte-b650m-aorus-elite-chipset-b650-amd-am5-atx-ddr5"
    "?gclid=x"
)
OUT = Path("memory/working/_terabyte_probe/parser_after.json")


def main() -> None:
    html = HTML.read_text(encoding="utf-8", errors="replace")
    response = HtmlResponse(
        URL, body=html.encode("utf-8"), encoding="utf-8", request=Request(URL)
    )
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(response)
    details = spider.extract_details(response)
    images = spider.extract_images(response)
    payload = {
        "offer": offer.model_dump(mode="json"),
        "details": details.model_dump(mode="json"),
        "images_count": len(images),
        "images_sample": images[:8],
        "spec_keys": list(details.specifications.keys())[:20],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main()
