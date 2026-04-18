from __future__ import annotations

from spike.config import RETAILERS, RetailerTier, retailer_by_slug


def test_registry_has_all_tier1_retailers() -> None:
    expected = {
        "nykaa", "amazon_in", "tira", "purplle",
        "minimalist", "plum", "mcaffeine", "dot_and_key", "the_derma_co",
    }
    assert {r.slug for r in RETAILERS} == expected


def test_shopify_retailers_have_products_json_url() -> None:
    shopify = [r for r in RETAILERS if r.tier is RetailerTier.SHOPIFY]
    assert len(shopify) == 5
    for r in shopify:
        assert r.products_json_url is not None
        assert r.products_json_url.endswith("/products.json")


def test_marketplace_retailers_have_sample_urls() -> None:
    marketplaces = [r for r in RETAILERS if r.tier is RetailerTier.MARKETPLACE]
    assert len(marketplaces) == 4
    for r in marketplaces:
        assert len(r.sample_product_urls) >= 8, f"{r.slug} needs >=8 sample URLs"


def test_retailer_by_slug_roundtrip() -> None:
    assert retailer_by_slug("nykaa").name == "Nykaa"
