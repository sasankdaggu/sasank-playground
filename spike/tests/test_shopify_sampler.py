from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from spike.samplers.shopify import ShopifySampler


@pytest.fixture()
def minimalist_fixture(sample_fixture_dir: Path) -> Path:
    path = sample_fixture_dir / "minimalist_products.json"
    if not path.exists():
        path.write_text(json.dumps({
            "products": [
                {
                    "id": 1,
                    "title": "Niacinamide 10% Face Serum",
                    "vendor": "Minimalist",
                    "product_type": "Serum",
                    "handle": "niacinamide-10",
                    "body_html": "<p>Balances oil. Fades marks.</p>",
                    "tags": "face,serum,oily-skin",
                    "images": [{"src": "https://cdn.shopify.com/img/niacinamide.jpg"}],
                    "variants": [
                        {"id": 10, "title": "Default Title", "price": "449.00",
                         "compare_at_price": "549.00", "available": True, "sku": "NIA-10-30"}
                    ],
                },
                {
                    "id": 2,
                    "title": "Salicylic Acid 2% Face Wash",
                    "vendor": "Minimalist",
                    "product_type": "",
                    "handle": "salicylic-2",
                    "body_html": "",
                    "tags": "",
                    "images": [],
                    "variants": [
                        {"id": 20, "title": "100ml", "price": "299.00",
                         "compare_at_price": None, "available": True, "sku": "SAL-2-100"},
                        {"id": 21, "title": "50ml", "price": "179.00",
                         "compare_at_price": None, "available": False, "sku": "SAL-2-50"},
                    ],
                },
            ]
        }))
    return path


@respx.mock
async def test_shopify_sampler_returns_n_parsed_samples(
    minimalist_fixture: Path, tmp_path: Path
) -> None:
    body = minimalist_fixture.read_text()
    respx.get("https://beminimalist.co/products.json").mock(
        return_value=Response(200, text=body, headers={"content-type": "application/json"})
    )

    raw_dir = tmp_path / "raw"
    parsed_dir = tmp_path / "parsed"
    sampler = ShopifySampler(retailer_slug="minimalist")

    samples = await sampler.sample(n=2, raw_dir=raw_dir, parsed_dir=parsed_dir)

    assert len(samples) == 2
    names = {s.canonical_name for s in samples}
    assert names == {"Niacinamide 10% Face Serum", "Salicylic Acid 2% Face Wash"}

    raw_files = list((raw_dir / "minimalist").glob("*.json"))
    assert len(raw_files) == 1

    parsed_files = list((parsed_dir / "minimalist").glob("*.json"))
    assert len(parsed_files) == 2


@respx.mock
async def test_shopify_sampler_marks_missing_fields(
    minimalist_fixture: Path, tmp_path: Path
) -> None:
    body = minimalist_fixture.read_text()
    respx.get("https://beminimalist.co/products.json").mock(
        return_value=Response(200, text=body)
    )

    sampler = ShopifySampler(retailer_slug="minimalist")
    samples = await sampler.sample(n=2, raw_dir=tmp_path / "raw", parsed_dir=tmp_path / "parsed")

    salicylic = next(s for s in samples if s.canonical_name.startswith("Salicylic"))
    assert "description" in salicylic.missing_fields
    assert "category_hint" in salicylic.missing_fields
    assert "ingredients" in salicylic.missing_fields


@respx.mock
async def test_shopify_sampler_captures_multi_variant_product(
    minimalist_fixture: Path, tmp_path: Path
) -> None:
    body = minimalist_fixture.read_text()
    respx.get("https://beminimalist.co/products.json").mock(
        return_value=Response(200, text=body)
    )
    sampler = ShopifySampler(retailer_slug="minimalist")
    samples = await sampler.sample(n=2, raw_dir=tmp_path / "raw", parsed_dir=tmp_path / "parsed")

    salicylic = next(s for s in samples if s.canonical_name.startswith("Salicylic"))
    assert len(salicylic.variants) == 2
    sizes = {v.option_value for v in salicylic.variants}
    assert sizes == {"100ml", "50ml"}
