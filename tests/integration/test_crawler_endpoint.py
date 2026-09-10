from decimal import Decimal

from fastapi.testclient import TestClient

from scout_api.main import app
from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.crawler.router import get_product_scrape_service


class FakeScrapeService:
    def scrape(self, url: str) -> ProductPriceItem:
        return ProductPriceItem(
            store="magazineluiza",
            country="BR",
            product_id="240590700",
            sku="240590700",
            title="Produto de teste",
            seller="magazineluiza",
            url=url,
            canonical_url=url,
            currency="BRL",
            price=Decimal("4399.00"),
            pix_price=Decimal("4399.00"),
            available=True,
            availability="available",
        )


def test_crawl_endpoint_returns_normalized_product() -> None:
    app.dependency_overrides[get_product_scrape_service] = FakeScrapeService
    try:
        response = TestClient(app).post(
            "/crawl",
            json={"url": "https://www.magazineluiza.com.br/p/240590700"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["product_id"] == "240590700"
    assert response.json()["pix_price"] == "4399.00"
