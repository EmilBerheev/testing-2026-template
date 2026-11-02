"""Дымовые тесты самого учебного приложения. Их не нужно менять."""

from bookshop.variants import VARIANTS


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_variant_matches_params(client, params):
    assert client.get("/api/variant").json()["variant"] == params.variant


def test_catalog_has_books(client):
    books = client.get("/api/books").json()
    assert len(books) == 8


def test_openapi_schema_is_published(client):
    schema = client.get("/openapi.json").json()
    assert "/api/orders" in schema["paths"]


def test_web_pages_are_served(client):
    assert "Книжная лавка" in client.get("/").text
    assert "Заказ" in client.get("/order").text


def test_all_variants_are_consistent():
    for params in VARIANTS.values():
        assert params.silver_pct < params.gold_pct
        assert params.max_discount_pct < params.gold_pct + params.bulk_pct + params.promo_pct
