# Kibble Deal Selection & Product Catalog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a global kibble product catalog (monthly scrape), daily price refresh, and a deal-selection engine that fires when REORDER_NOW triggers — sending an FCM notification with a one-tap deep link to the best deal.

**Architecture:** Playwright sync-API scraper plugins (one class per retailer) feed a shared product catalog. Celery beat runs catalog refresh monthly and price refresh daily. On REORDER_NOW, ingest endpoint enqueues a deal-selection Celery task that scores live prices against hard filters and saves the winner to `pending_deals`. Android Orders screen displays the deal card and price comparison table.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic, Celery 5, Redis, Playwright (sync API), Kotlin, Jetpack Compose, Retrofit, Hilt

---

## File Map

### Backend — New
```
backend/app/models/product.py
backend/app/models/product_listing.py
backend/app/models/product_price.py
backend/app/models/pending_deal.py
backend/app/services/retailer_plugins/__init__.py
backend/app/services/retailer_plugins/base.py
backend/app/services/retailer_plugins/supertails.py
backend/app/services/retailer_plugins/huft.py
backend/app/services/retailer_plugins/amazon_in.py
backend/app/services/retailer_plugins/stubs.py          ← 8 stubs in one file
backend/app/celery_app.py
backend/app/tasks/__init__.py
backend/app/tasks/catalog.py
backend/app/tasks/prices.py
backend/app/tasks/deal_selection.py
backend/app/services/deal_selection.py
backend/app/routers/products.py
backend/app/routers/deals.py
backend/app/schemas/product.py
backend/app/schemas/deal.py
backend/alembic/versions/<hash>_catalog_tables.py
backend/alembic/versions/<hash>_dog_user_product_cols.py
backend/tests/test_products.py
backend/tests/test_deals.py
backend/tests/test_deal_selection_service.py
backend/tests/test_supertails_plugin.py
```

### Backend — Modified
```
backend/pyproject.toml                     ← add playwright, requests
backend/app/models/dog.py                  ← add product_id FK
backend/app/models/user.py                 ← add pinned_retailer_id, blacklisted_retailer_ids
backend/app/models/__init__.py             ← register new models
backend/app/routers/ingest.py              ← enqueue deal selection on REORDER_NOW
backend/app/schemas/user.py               ← add product_id to DogCreate/DogResponse
backend/app/main.py                        ← register products + deals routers
```

### Android — New
```
android/core/network/src/.../dto/ProductDto.kt
android/core/network/src/.../dto/DealDto.kt
android/feature/onboarding/src/.../product/ProductPickerScreen.kt
android/feature/onboarding/src/.../product/ProductPickerViewModel.kt
android/feature/orders/src/.../DealCard.kt
android/feature/orders/src/.../PriceComparisonTable.kt
```

### Android — Modified
```
android/core/network/src/.../KibbleApi.kt
android/core/network/src/.../dto/DogDto.kt
android/feature/onboarding/src/.../dog/DogScreen.kt
android/feature/onboarding/src/.../dog/DogViewModel.kt
android/feature/onboarding/src/.../OnboardingRepository.kt
android/feature/orders/src/.../OrdersScreen.kt
android/feature/orders/src/.../OrdersViewModel.kt
android/feature/settings/src/.../retailers/AddRetailerSheet.kt
```

---

### Task 1: Add Playwright dependency + seed retailers migration

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/seeds/retailers.py`
- Create: `backend/alembic/versions/<hash>_seed_retailers.py` (run `alembic revision` to get hash)

- [ ] **Step 1: Add dependencies to pyproject.toml**

```toml
# in [project] dependencies, add:
    "playwright==1.44.0",
    "requests==2.32.3",
```

- [ ] **Step 2: Install playwright browsers**

```bash
cd /Users/sdagguba/kibble-reorder/backend
pip install playwright==1.44.0 requests==2.32.3
playwright install chromium
```

Expected: `Chromium ... downloaded`

- [ ] **Step 3: Generate seed migration**

```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic revision --autogenerate -m "seed_retailers"
```

Open the generated file and replace the `upgrade()` body:

```python
def upgrade() -> None:
    import uuid
    retailers = [
        ("supertails",      "Supertails",       "https://www.supertails.com",          "SupertailsPlugin",    "standard"),
        ("huft",            "Heads Up For Tails","https://www.headsufortails.com",      "HuftPlugin",          "standard"),
        ("amazon_in",       "Amazon.in",         "https://www.amazon.in",               "AmazonInPlugin",      "standard"),
        ("flipkart",        "Flipkart",          "https://www.flipkart.com",            "FlipkartPlugin",      "standard"),
        ("petsworld",       "Petsworld",         "https://www.petsworld.in",            "PetsworldPlugin",     "standard"),
        ("zigly",           "Zigly",             "https://www.zigly.com",               "ZiglyPlugin",         "standard"),
        ("justdogs",        "Justdogs",          "https://www.justdogs.in",             "JustdogsPlugin",      "standard"),
        ("blinkit",         "Blinkit",           "https://blinkit.com",                 "BlinkitPlugin",       "quick_commerce"),
        ("zepto",           "Zepto",             "https://www.zeptonow.com",            "ZeptoPlugin",         "quick_commerce"),
        ("swiggy_instamart","Swiggy Instamart",  "https://www.swiggy.com/instamart",    "SwiggyInstamartPlugin","quick_commerce"),
        ("bigbasket",       "BigBasket",         "https://www.bigbasket.com",           "BigBasketPlugin",     "quick_commerce"),
    ]
    op.execute(
        "INSERT INTO retailers (id, name, base_url, plugin_class, retailer_type, is_active) VALUES "
        + ", ".join(
            f"('{uuid.uuid4()}', '{name}', '{url}', '{cls}', '{rtype}', true)"
            for slug, name, url, cls, rtype in retailers
        )
        + " ON CONFLICT DO NOTHING"
    )

def downgrade() -> None:
    op.execute("DELETE FROM retailers WHERE plugin_class IN ('SupertailsPlugin','HuftPlugin','AmazonInPlugin','FlipkartPlugin','PetsworldPlugin','ZiglyPlugin','JustdogsPlugin','BlinkitPlugin','ZeptoPlugin','SwiggyInstamartPlugin','BigBasketPlugin')")
```

- [ ] **Step 4: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade ... -> <hash>, seed_retailers`

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add backend/pyproject.toml backend/alembic/versions/
git commit -m "feat: add playwright dep and seed retailers"
```

---

### Task 2: Catalog SQLAlchemy models

**Files:**
- Create: `backend/app/models/product.py`
- Create: `backend/app/models/product_listing.py`
- Create: `backend/app/models/product_price.py`
- Create: `backend/app/models/pending_deal.py`
- Modify: `backend/app/models/dog.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write product.py**

```python
# backend/app/models/product.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="dry")
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    listings: Mapped[list["ProductListing"]] = relationship(back_populates="product", cascade="all, delete-orphan")
```

- [ ] **Step 2: Write product_listing.py**

```python
# backend/app/models/product_listing.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class ProductListing(Base):
    __tablename__ = "product_listings"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"))
    retailer_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("retailers.id"))
    retailer_product_url: Mapped[str] = mapped_column(String, nullable=False)
    retailer_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pack_size_kg: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_catalogued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    product: Mapped["Product"] = relationship(back_populates="listings")
    prices: Mapped[list["ProductPrice"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
```

- [ ] **Step 3: Write product_price.py**

```python
# backend/app/models/product_price.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Float, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class ProductPrice(Base):
    __tablename__ = "product_prices"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_listings.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    seller_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    lead_time_days: Mapped[int | None] = mapped_column(nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    listing: Mapped["ProductListing"] = relationship(back_populates="prices")
```

- [ ] **Step 4: Write pending_deal.py**

```python
# backend/app/models/pending_deal.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class PendingDeal(Base):
    __tablename__ = "pending_deals"
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bin_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bins.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    listing_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_listings.id"))
    price_snapshot_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_prices.id"))
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | acted | expired
    deep_link_url: Mapped[str] = mapped_column(String, nullable=False)
    comparison_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 5: Update dog.py — add product_id**

```python
# backend/app/models/dog.py — add this column after kibble_product_name:
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 6: Update user.py — add pinned_retailer_id + blacklisted_retailer_ids**

```python
# backend/app/models/user.py — add after wallet_type:
    pinned_retailer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("retailers.id", ondelete="SET NULL"), nullable=True
    )
    blacklisted_retailer_ids: Mapped[list] = mapped_column(
        postgresql.ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
```

Also add `from sqlalchemy.dialects import postgresql` to the imports.

- [ ] **Step 7: Update models/__init__.py**

```python
from app.models.user import User
from app.models.dog import Dog
from app.models.bin import Bin
from app.models.sensor_reading import SensorReading
from app.models.retailer import Retailer
from app.models.order import Order
from app.models.lead_time import LeadTime
from app.models.retailer_session import RetailerSession
from app.models.product import Product
from app.models.product_listing import ProductListing
from app.models.product_price import ProductPrice
from app.models.pending_deal import PendingDeal

__all__ = ["User", "Dog", "Bin", "SensorReading", "Retailer", "Order", "LeadTime",
           "RetailerSession", "Product", "ProductListing", "ProductPrice", "PendingDeal"]
```

- [ ] **Step 8: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add backend/app/models/
git commit -m "feat: add catalog SQLAlchemy models"
```

---

### Task 3: Alembic migration for catalog tables + column changes

**Files:**
- Create: `backend/alembic/versions/<hash>_catalog_tables.py`

- [ ] **Step 1: Generate migration**

```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic revision --autogenerate -m "catalog_tables"
```

- [ ] **Step 2: Verify generated migration**

Open the file. Confirm it creates: `products`, `product_listings`, `product_prices`, `pending_deals` tables, adds `product_id` to `dogs`, adds `pinned_retailer_id` + `blacklisted_retailer_ids` to `users`. Fix any issues (autogenerate sometimes misses ARRAY columns — add manually if needed):

```python
# If blacklisted_retailer_ids is missing from autogenerate, add inside upgrade():
op.add_column('users', sa.Column('blacklisted_retailer_ids',
    postgresql.ARRAY(sa.UUID()), nullable=False, server_default='{}'))
op.add_column('users', sa.Column('pinned_retailer_id', sa.UUID(), nullable=True))
op.create_foreign_key(None, 'users', 'retailers', ['pinned_retailer_id'], ['id'], ondelete='SET NULL')
```

- [ ] **Step 3: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade ... -> <hash>, catalog_tables`

- [ ] **Step 4: Add price index manually if not generated**

```python
# Inside upgrade(), after creating product_prices:
op.create_index('ix_product_prices_listing_scraped', 'product_prices',
    ['listing_id', sa.text('scraped_at DESC')])
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/
git commit -m "feat: alembic migration for catalog tables"
```

---

### Task 4: Retailer plugin base + registry

**Files:**
- Create: `backend/app/services/retailer_plugins/__init__.py`
- Create: `backend/app/services/retailer_plugins/base.py`

- [ ] **Step 1: Write base.py**

```python
# backend/app/services/retailer_plugins/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class CatalogListing:
    name: str
    brand: str
    pack_size_kg: float
    url: str
    image_url: str | None
    retailer_product_id: str | None

@dataclass
class PriceResult:
    price: float
    shipping_cost: float
    seller_rating: float | None
    in_stock: bool
    lead_time_days: int | None

class RetailerPlugin(ABC):
    retailer_slug: str
    retailer_type: str  # "standard" | "quick_commerce"

    @abstractmethod
    def catalog_search(self, query: str, page) -> list[CatalogListing]:
        """page is playwright.sync_api.Page"""

    @abstractmethod
    def get_price(self, listing_url: str, pincode: str, page) -> PriceResult:
        """page is playwright.sync_api.Page"""

    def get_deep_link(self, listing_url: str) -> str:
        return listing_url
```

- [ ] **Step 2: Write __init__.py registry**

```python
# backend/app/services/retailer_plugins/__init__.py
from app.services.retailer_plugins.base import RetailerPlugin, CatalogListing, PriceResult
from app.services.retailer_plugins.supertails import SupertailsPlugin
from app.services.retailer_plugins.huft import HuftPlugin
from app.services.retailer_plugins.amazon_in import AmazonInPlugin
from app.services.retailer_plugins.stubs import (
    FlipkartPlugin, PetsworldPlugin, ZiglyPlugin, JustdogsPlugin,
    BlinkitPlugin, ZeptoPlugin, SwiggyInstamartPlugin, BigBasketPlugin,
)

REGISTRY: dict[str, RetailerPlugin] = {
    p.retailer_slug: p()
    for p in [
        SupertailsPlugin, HuftPlugin, AmazonInPlugin,
        FlipkartPlugin, PetsworldPlugin, ZiglyPlugin, JustdogsPlugin,
        BlinkitPlugin, ZeptoPlugin, SwiggyInstamartPlugin, BigBasketPlugin,
    ]
}

__all__ = ["REGISTRY", "RetailerPlugin", "CatalogListing", "PriceResult"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/retailer_plugins/
git commit -m "feat: retailer plugin base class and registry"
```

---

### Task 5: Supertails + HUFT plugins (Shopify JSON API)

**Files:**
- Create: `backend/app/services/retailer_plugins/supertails.py`
- Create: `backend/app/services/retailer_plugins/huft.py`
- Create: `backend/tests/test_supertails_plugin.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_supertails_plugin.py
import json
from unittest.mock import MagicMock, patch
from app.services.retailer_plugins.supertails import SupertailsPlugin, _parse_pack_size_kg, _slugify

SUGGEST_JSON = json.dumps({"resources": {"results": {"products": [
    {"title": "Royal Canin Maxi Adult", "url": "/products/royal-canin-maxi-adult",
     "featured_image": {"url": "https://cdn.supertails.com/img.jpg"}},
]}}})

PRODUCT_JSON = json.dumps({"product": {
    "title": "Royal Canin Maxi Adult", "vendor": "Royal Canin",
    "image": {"src": "https://cdn.supertails.com/img.jpg"},
    "variants": [
        {"id": 111, "title": "3 kg", "price": "1200.00", "available": True},
        {"id": 222, "title": "10 kg", "price": "3500.00", "available": True},
    ]
}})

def test_catalog_search_returns_one_listing_per_variant():
    plugin = SupertailsPlugin()
    page = MagicMock()
    page.inner_text.side_effect = [SUGGEST_JSON, PRODUCT_JSON]
    results = plugin.catalog_search("royal canin dog", page)
    assert len(results) == 2
    assert results[0].pack_size_kg == 3.0
    assert results[1].pack_size_kg == 10.0
    assert results[0].brand == "Royal Canin"
    assert results[0].retailer_product_id == "111"

def test_parse_pack_size_kg():
    assert _parse_pack_size_kg("3 kg") == 3.0
    assert _parse_pack_size_kg("1.5kg") == 1.5
    assert _parse_pack_size_kg("10KG") == 10.0
    assert _parse_pack_size_kg("500g") == 0.5
    assert _parse_pack_size_kg("Default Title") is None

def test_get_price_extracts_price():
    plugin = SupertailsPlugin()
    page = MagicMock()
    page.query_selector.return_value = MagicMock(inner_text=MagicMock(return_value="₹1,200.00"))
    page.title.return_value = "Royal Canin Maxi Adult 3kg"
    result = plugin.get_price("https://www.supertails.com/products/x?variant=111", "400001", page)
    assert result.price == 1200.0
    assert result.in_stock is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_supertails_plugin.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Implement supertails.py**

```python
# backend/app/services/retailer_plugins/supertails.py
import json, re
from app.services.retailer_plugins.base import RetailerPlugin, CatalogListing, PriceResult

def _parse_pack_size_kg(title: str) -> float | None:
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|KG|Kg)', title)
    if m:
        return float(m.group(1))
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|G)\b', title)
    if m:
        return float(m.group(1)) / 1000.0
    return None

def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

class SupertailsPlugin(RetailerPlugin):
    retailer_slug = "supertails"
    retailer_type = "standard"
    BASE = "https://www.supertails.com"

    def catalog_search(self, query: str, page) -> list[CatalogListing]:
        url = f"{self.BASE}/search/suggest.json?q={query}&resources[type]=product&resources[limit]=50"
        page.goto(url)
        data = json.loads(page.inner_text("body"))
        products = data.get("resources", {}).get("results", {}).get("products", [])
        listings = []
        for p in products:
            handle = p["url"].split("/products/")[-1].split("?")[0]
            page.goto(f"{self.BASE}/products/{handle}.json")
            pd = json.loads(page.inner_text("body")).get("product", {})
            brand = pd.get("vendor", "")
            img = (pd.get("image") or {}).get("src")
            for v in pd.get("variants", []):
                sz = _parse_pack_size_kg(v["title"])
                if sz is None:
                    continue
                listings.append(CatalogListing(
                    name=pd["title"], brand=brand, pack_size_kg=sz,
                    url=f"{self.BASE}/products/{handle}?variant={v['id']}",
                    image_url=img, retailer_product_id=str(v["id"]),
                ))
        return listings

    def get_price(self, listing_url: str, pincode: str, page) -> PriceResult:
        page.goto(listing_url)
        el = page.query_selector(".price__sale .price-item--sale") or page.query_selector(".price-item--regular")
        price_text = el.inner_text() if el else "0"
        price = float(re.sub(r'[^\d.]', '', price_text.replace(',', '')))
        sold_out = page.query_selector("[data-sold-out]") is not None
        return PriceResult(price=price, shipping_cost=0.0, seller_rating=None,
                           in_stock=not sold_out, lead_time_days=None)

    def get_deep_link(self, listing_url: str) -> str:
        return listing_url
```

- [ ] **Step 4: Implement huft.py (same Shopify pattern, different base URL + selectors)**

```python
# backend/app/services/retailer_plugins/huft.py
import json, re
from app.services.retailer_plugins.base import RetailerPlugin, CatalogListing, PriceResult
from app.services.retailer_plugins.supertails import _parse_pack_size_kg

class HuftPlugin(RetailerPlugin):
    retailer_slug = "huft"
    retailer_type = "standard"
    BASE = "https://www.headsufortails.com"

    def catalog_search(self, query: str, page) -> list[CatalogListing]:
        url = f"{self.BASE}/search/suggest.json?q={query}&resources[type]=product&resources[limit]=50"
        page.goto(url)
        data = json.loads(page.inner_text("body"))
        products = data.get("resources", {}).get("results", {}).get("products", [])
        listings = []
        for p in products:
            handle = p["url"].split("/products/")[-1].split("?")[0]
            page.goto(f"{self.BASE}/products/{handle}.json")
            pd = json.loads(page.inner_text("body")).get("product", {})
            brand = pd.get("vendor", "")
            img = (pd.get("image") or {}).get("src")
            for v in pd.get("variants", []):
                sz = _parse_pack_size_kg(v["title"])
                if sz is None:
                    continue
                listings.append(CatalogListing(
                    name=pd["title"], brand=brand, pack_size_kg=sz,
                    url=f"{self.BASE}/products/{handle}?variant={v['id']}",
                    image_url=img, retailer_product_id=str(v["id"]),
                ))
        return listings

    def get_price(self, listing_url: str, pincode: str, page) -> PriceResult:
        page.goto(listing_url)
        el = page.query_selector(".price__sale .price-item--sale") or page.query_selector(".price-item--regular")
        price_text = el.inner_text() if el else "0"
        price = float(re.sub(r'[^\d.]', '', price_text.replace(',', '')))
        sold_out = page.query_selector("[data-sold-out]") is not None
        return PriceResult(price=price, shipping_cost=0.0, seller_rating=None,
                           in_stock=not sold_out, lead_time_days=None)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_supertails_plugin.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/retailer_plugins/supertails.py backend/app/services/retailer_plugins/huft.py backend/tests/test_supertails_plugin.py
git commit -m "feat: Supertails and HUFT retailer plugins"
```

---

### Task 6: Amazon.in plugin

**Files:**
- Create: `backend/app/services/retailer_plugins/amazon_in.py`
- Create: `backend/tests/test_amazon_plugin.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_amazon_plugin.py
import json
from unittest.mock import MagicMock
from app.services.retailer_plugins.amazon_in import AmazonInPlugin, _extract_asin

def test_extract_asin():
    assert _extract_asin("https://www.amazon.in/dp/B08XYZ123/ref=sr") == "B08XYZ123"
    assert _extract_asin("https://www.amazon.in/Royal-Canin/dp/B08XYZ123") == "B08XYZ123"
    assert _extract_asin("https://www.amazon.in/s?k=dog+food") is None

def test_get_price_parses_whole_and_decimal():
    plugin = AmazonInPlugin()
    page = MagicMock()
    page.query_selector.side_effect = lambda sel: (
        MagicMock(inner_text=MagicMock(return_value="2")) if "priceSymbol" in sel
        else MagicMock(inner_text=MagicMock(return_value="3,499")) if "price-block-whole" in sel
        else MagicMock(inner_text=MagicMock(return_value="00")) if "price-block-fraction" in sel
        else None
    )
    page.query_selector_all.return_value = []
    result = plugin.get_price("https://www.amazon.in/dp/B08XYZ123?th=1&psc=1", "400001", page)
    assert result.price == 3499.0
    assert result.in_stock is True
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/test_amazon_plugin.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement amazon_in.py**

```python
# backend/app/services/retailer_plugins/amazon_in.py
import re, time
from app.services.retailer_plugins.base import RetailerPlugin, CatalogListing, PriceResult
from app.services.retailer_plugins.supertails import _parse_pack_size_kg

def _extract_asin(url: str) -> str | None:
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    return m.group(1) if m else None

class AmazonInPlugin(RetailerPlugin):
    retailer_slug = "amazon_in"
    retailer_type = "standard"
    BASE = "https://www.amazon.in"

    def catalog_search(self, query: str, page) -> list[CatalogListing]:
        page.goto(f"{self.BASE}/s?k={query.replace(' ', '+')}&i=pet-supplies")
        time.sleep(1.5)
        results = page.query_selector_all('[data-component-type="s-search-result"]')
        listings = []
        for r in results[:20]:
            link_el = r.query_selector("h2 a")
            if not link_el:
                continue
            href = link_el.get_attribute("href") or ""
            asin = _extract_asin(href)
            if not asin:
                continue
            title_el = r.query_selector("h2 span")
            title = title_el.inner_text() if title_el else ""
            sz = _parse_pack_size_kg(title)
            if sz is None:
                continue
            img_el = r.query_selector("img.s-image")
            img = img_el.get_attribute("src") if img_el else None
            brand = self._extract_brand(title)
            listings.append(CatalogListing(
                name=title, brand=brand, pack_size_kg=sz,
                url=f"{self.BASE}/dp/{asin}",
                image_url=img, retailer_product_id=asin,
            ))
        return listings

    def get_price(self, listing_url: str, pincode: str, page) -> PriceResult:
        page.goto(listing_url)
        time.sleep(1.0)
        whole_el = page.query_selector(".a-price-whole")
        frac_el = page.query_selector(".a-price-fraction")
        if whole_el:
            whole = re.sub(r'[^\d]', '', whole_el.inner_text())
            frac = re.sub(r'[^\d]', '', frac_el.inner_text()) if frac_el else "00"
            price = float(f"{whole}.{frac}")
        else:
            price = 0.0
        oos = page.query_selector("#availability .a-color-error") is not None
        rating_el = page.query_selector("#acrPopover span.a-size-base")
        rating = float(rating_el.inner_text().split()[0]) if rating_el else None
        ship_el = page.query_selector("#mir-layout-DELIVERY_BLOCK .a-color-base")
        lead = self._parse_lead_days(ship_el.inner_text() if ship_el else "")
        return PriceResult(price=price, shipping_cost=0.0, seller_rating=rating,
                           in_stock=not oos, lead_time_days=lead)

    def _extract_brand(self, title: str) -> str:
        known = ["Royal Canin", "Drools", "Pedigree", "Farmina", "Hills", "Purina", "Orijen", "Acana"]
        for b in known:
            if b.lower() in title.lower():
                return b
        return title.split()[0] if title else "Unknown"

    def _parse_lead_days(self, text: str) -> int | None:
        m = re.search(r'(\d+)\s*day', text, re.IGNORECASE)
        return int(m.group(1)) if m else None

    def get_deep_link(self, listing_url: str) -> str:
        asin = _extract_asin(listing_url)
        if asin:
            return f"https://www.amazon.in/dp/{asin}"
        return listing_url
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_amazon_plugin.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retailer_plugins/amazon_in.py backend/tests/test_amazon_plugin.py
git commit -m "feat: Amazon.in retailer plugin"
```

---

### Task 7: Stub plugins

**Files:**
- Create: `backend/app/services/retailer_plugins/stubs.py`

- [ ] **Step 1: Write stubs.py**

```python
# backend/app/services/retailer_plugins/stubs.py
from app.services.retailer_plugins.base import RetailerPlugin, CatalogListing, PriceResult

class _StubPlugin(RetailerPlugin):
    def catalog_search(self, query: str, page) -> list[CatalogListing]:
        return []
    def get_price(self, listing_url: str, pincode: str, page) -> PriceResult:
        raise NotImplementedError(f"{self.__class__.__name__} not yet implemented")

class FlipkartPlugin(_StubPlugin):
    retailer_slug = "flipkart"; retailer_type = "standard"
class PetsworldPlugin(_StubPlugin):
    retailer_slug = "petsworld"; retailer_type = "standard"
class ZiglyPlugin(_StubPlugin):
    retailer_slug = "zigly"; retailer_type = "standard"
class JustdogsPlugin(_StubPlugin):
    retailer_slug = "justdogs"; retailer_type = "standard"
class BlinkitPlugin(_StubPlugin):
    retailer_slug = "blinkit"; retailer_type = "quick_commerce"
class ZeptoPlugin(_StubPlugin):
    retailer_slug = "zepto"; retailer_type = "quick_commerce"
class SwiggyInstamartPlugin(_StubPlugin):
    retailer_slug = "swiggy_instamart"; retailer_type = "quick_commerce"
class BigBasketPlugin(_StubPlugin):
    retailer_slug = "bigbasket"; retailer_type = "quick_commerce"
```

- [ ] **Step 2: Verify registry imports cleanly**

```bash
cd /Users/sdagguba/kibble-reorder/backend
python -c "from app.services.retailer_plugins import REGISTRY; print(list(REGISTRY.keys()))"
```

Expected: `['supertails', 'huft', 'amazon_in', 'flipkart', 'petsworld', 'zigly', 'justdogs', 'blinkit', 'zepto', 'swiggy_instamart', 'bigbasket']`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/retailer_plugins/stubs.py
git commit -m "feat: stub plugins for remaining 8 retailers"
```

---

### Task 8: Celery app setup

**Files:**
- Create: `backend/app/celery_app.py`
- Create: `backend/app/tasks/__init__.py`

- [ ] **Step 1: Write celery_app.py**

```python
# backend/app/celery_app.py
from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery("kibble", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-catalog-monthly": {
            "task": "app.tasks.catalog.refresh_catalog",
            "schedule": crontab(day_of_month=1, hour=2, minute=0),
        },
        "refresh-prices-daily": {
            "task": "app.tasks.prices.refresh_prices",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
celery_app.autodiscover_tasks(["app.tasks"])
```

- [ ] **Step 2: Write tasks/__init__.py**

```python
# backend/app/tasks/__init__.py
```

- [ ] **Step 3: Verify Celery starts**

```bash
cd /Users/sdagguba/kibble-reorder/backend
celery -A app.celery_app inspect ping 2>&1 | head -5
```

Expected: no import errors (may show "no nodes" if Redis not running, that's fine)

- [ ] **Step 4: Commit**

```bash
git add backend/app/celery_app.py backend/app/tasks/__init__.py
git commit -m "feat: Celery app setup with beat schedule"
```

---

### Task 9: Catalog scraper task

**Files:**
- Create: `backend/app/tasks/catalog.py`
- Create: `backend/tests/test_catalog_task.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_catalog_task.py
import asyncio, uuid
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.database import Base
from app.models import *  # noqa
from app.config import settings
from app.services.retailer_plugins.base import CatalogListing

async def _setup_db():
    engine = create_async_engine(settings.database_url_test, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)

def test_refresh_catalog_upserts_products():
    fake_listing = CatalogListing(
        name="Royal Canin Maxi Adult", brand="Royal Canin", pack_size_kg=10.0,
        url="https://www.supertails.com/products/x?variant=1",
        image_url=None, retailer_product_id="1",
    )
    with patch("app.tasks.catalog.REGISTRY", {"supertails": MagicMock(
        retailer_type="standard",
        catalog_search=MagicMock(return_value=[fake_listing]),
    )}), patch("app.tasks.catalog.sync_playwright") as mock_pw:
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value.__enter__.return_value.new_page.return_value = MagicMock()
        from app.tasks.catalog import refresh_catalog
        refresh_catalog()
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/test_catalog_task.py -v
```

Expected: `ImportError` (module not yet created)

- [ ] **Step 3: Write catalog.py**

```python
# backend/app/tasks/catalog.py
import asyncio, re, uuid
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.celery_app import celery_app
from app.config import settings
from app.models.product import Product
from app.models.product_listing import ProductListing
from app.models.retailer import Retailer
from app.services.retailer_plugins import REGISTRY
from app.services.retailer_plugins.base import CatalogListing

CATALOG_QUERIES = [
    "dog dry food", "dog wet food", "Royal Canin dog", "Drools dog",
    "Farmina dog", "Pedigree dog", "Purina dog", "Hills dog",
]

def _canonical(brand: str, name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', f"{brand}-{name}".lower()).strip('-')

async def _save_listings(listings_by_retailer: dict, retailer_map: dict):
    engine = create_async_engine(settings.database_url, echo=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        now = datetime.now(timezone.utc)
        for slug, listings in listings_by_retailer.items():
            retailer_id = retailer_map.get(slug)
            if not retailer_id:
                continue
            for cl in listings:
                canon = _canonical(cl.brand, cl.name)
                product = await session.scalar(select(Product).where(Product.canonical_name == canon))
                if not product:
                    product = Product(brand=cl.brand, name=cl.name, canonical_name=canon,
                                      image_url=cl.image_url, category="dry")
                    session.add(product)
                    await session.flush()
                listing = await session.scalar(
                    select(ProductListing).where(
                        ProductListing.product_id == product.id,
                        ProductListing.retailer_id == retailer_id,
                        ProductListing.retailer_product_url == cl.url,
                    )
                )
                if listing:
                    listing.last_catalogued_at = now
                    listing.is_active = True
                else:
                    session.add(ProductListing(
                        product_id=product.id, retailer_id=retailer_id,
                        retailer_product_url=cl.url, retailer_product_id=cl.retailer_product_id,
                        pack_size_kg=cl.pack_size_kg, title=cl.name,
                        image_url=cl.image_url, is_active=True, last_catalogued_at=now,
                    ))
        await session.commit()
    await engine.dispose()

async def _load_retailer_map() -> dict:
    engine = create_async_engine(settings.database_url, echo=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rows = (await session.scalars(select(Retailer).where(Retailer.is_active == True))).all()
        result = {r.plugin_class.replace("Plugin", "").lower(): r.id for r in rows}
        # normalize to slug
        slug_map = {}
        for r in rows:
            slug_map[r.plugin_class.replace("Plugin", "").lower()] = r.id
        # also store by name slug
        for r in rows:
            key = re.sub(r'[^a-z0-9]+', '_', r.name.lower())
            slug_map[key] = r.id
        return slug_map
    await engine.dispose()

@celery_app.task(name="app.tasks.catalog.refresh_catalog")
def refresh_catalog():
    retailer_map = asyncio.run(_load_retailer_map())
    listings_by_slug: dict = {slug: [] for slug in REGISTRY}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for slug, plugin in REGISTRY.items():
            page = browser.new_page()
            for query in CATALOG_QUERIES:
                try:
                    results = plugin.catalog_search(query, page)
                    listings_by_slug[slug].extend(results)
                except NotImplementedError:
                    break
                except Exception:
                    pass
            page.close()
        browser.close()
    asyncio.run(_save_listings(listings_by_slug, retailer_map))
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_catalog_task.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/catalog.py backend/tests/test_catalog_task.py
git commit -m "feat: catalog scraper Celery task"
```

---

### Task 10: Price refresher task

**Files:**
- Create: `backend/app/tasks/prices.py`
- Create: `backend/tests/test_prices_task.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_prices_task.py
from unittest.mock import patch, MagicMock
from app.services.retailer_plugins.base import PriceResult

def test_refresh_prices_inserts_price_rows():
    fake_price = PriceResult(price=2340.0, shipping_cost=0.0, seller_rating=4.5,
                             in_stock=True, lead_time_days=3)
    mock_plugin = MagicMock()
    mock_plugin.retailer_slug = "supertails"
    mock_plugin.get_price.return_value = fake_price

    with patch("app.tasks.prices.REGISTRY", {"supertails": mock_plugin}), \
         patch("app.tasks.prices.sync_playwright") as mock_pw, \
         patch("app.tasks.prices.asyncio.run") as mock_run:
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value.__enter__.return_value.new_page.return_value = MagicMock()
        from app.tasks.prices import refresh_prices
        refresh_prices()
        assert mock_run.called
```

- [ ] **Step 2: Implement prices.py**

```python
# backend/app/tasks/prices.py
import asyncio
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
from app.celery_app import celery_app
from app.config import settings
from app.models.product_listing import ProductListing
from app.models.product_price import ProductPrice
from app.models.retailer import Retailer
from app.services.retailer_plugins import REGISTRY

async def _load_active_listings() -> list[tuple]:
    engine = create_async_engine(settings.database_url, echo=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rows = (await session.scalars(
            select(ProductListing).where(ProductListing.is_active == True)
        )).all()
        retailers = {r.id: r.plugin_class.lower().replace("plugin", "")
                     for r in (await session.scalars(select(Retailer))).all()}
        result = [(str(l.id), l.retailer_product_url, retailers.get(l.retailer_id, "")) for l in rows]
    await engine.dispose()
    return result

async def _save_prices(prices: list[dict]):
    engine = create_async_engine(settings.database_url, echo=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        for p in prices:
            session.add(ProductPrice(**p))
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        await session.execute(delete(ProductPrice).where(ProductPrice.scraped_at < cutoff))
        await session.commit()
    await engine.dispose()

@celery_app.task(name="app.tasks.prices.refresh_prices")
def refresh_prices():
    listings = asyncio.run(_load_active_listings())
    by_slug: dict[str, list] = {}
    for listing_id, url, slug in listings:
        by_slug.setdefault(slug, []).append((listing_id, url))

    prices = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for slug, items in by_slug.items():
            plugin = REGISTRY.get(slug)
            if not plugin:
                continue
            page = browser.new_page()
            for listing_id, url in items:
                try:
                    r = plugin.get_price(url, "", page)
                    prices.append({"listing_id": listing_id, "price": r.price,
                                   "shipping_cost": r.shipping_cost, "seller_rating": r.seller_rating,
                                   "in_stock": r.in_stock, "lead_time_days": r.lead_time_days})
                except Exception:
                    pass
            page.close()
        browser.close()
    asyncio.run(_save_prices(prices))
```

- [ ] **Step 3: Run test**

```bash
pytest tests/test_prices_task.py -v
```

Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add backend/app/tasks/prices.py backend/tests/test_prices_task.py
git commit -m "feat: daily price refresher Celery task"
```

---

### Task 11: Deal selection service (pure Python)

**Files:**
- Create: `backend/app/services/deal_selection.py`
- Create: `backend/tests/test_deal_selection_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_deal_selection_service.py
import uuid
from dataclasses import dataclass
from app.services.deal_selection import select_best_deal, DealCandidate, DealFilters

def _candidate(retailer_type="standard", price=2340.0, shipping=0.0,
               pack_size_kg=10.0, in_stock=True, lead_time_days=3,
               seller_rating=4.5, retailer_id=None):
    return DealCandidate(
        listing_id=uuid.uuid4(), retailer_id=retailer_id or uuid.uuid4(),
        retailer_type=retailer_type, retailer_name="Test",
        listing_url="https://example.com", price=price, shipping_cost=shipping,
        pack_size_kg=pack_size_kg, in_stock=in_stock,
        lead_time_days=lead_time_days, seller_rating=seller_rating,
    )

def test_selects_cheapest_per_kg():
    filters = DealFilters(days_until_runout=10, min_seller_rating=4.0,
                          container_capacity_kg=15.0, blacklisted_ids=[],
                          pinned_retailer_id=None)
    c1 = _candidate(price=3500.0, pack_size_kg=10.0)  # ₹350/kg
    c2 = _candidate(price=2000.0, pack_size_kg=5.0)   # ₹400/kg
    winner, comparison = select_best_deal([c1, c2], filters)
    assert winner.listing_id == c1.listing_id

def test_disqualifies_slow_delivery():
    filters = DealFilters(days_until_runout=5, min_seller_rating=4.0,
                          container_capacity_kg=15.0, blacklisted_ids=[], pinned_retailer_id=None)
    c = _candidate(lead_time_days=7)
    winner, _ = select_best_deal([c], filters)
    assert winner is None

def test_disqualifies_quick_commerce_from_ordering():
    filters = DealFilters(days_until_runout=10, min_seller_rating=4.0,
                          container_capacity_kg=15.0, blacklisted_ids=[], pinned_retailer_id=None)
    c = _candidate(retailer_type="quick_commerce")
    winner, comparison = select_best_deal([c], filters)
    assert winner is None
    assert comparison[0]["disqualified"] is True

def test_pinned_retailer_wins_over_cheaper():
    pinned_id = uuid.uuid4()
    filters = DealFilters(days_until_runout=10, min_seller_rating=4.0,
                          container_capacity_kg=15.0, blacklisted_ids=[], pinned_retailer_id=pinned_id)
    cheap = _candidate(price=1000.0, pack_size_kg=5.0)
    pinned = _candidate(price=3500.0, pack_size_kg=10.0, retailer_id=pinned_id)
    winner, _ = select_best_deal([cheap, pinned], filters)
    assert winner.retailer_id == pinned_id

def test_emergency_fallback_uses_quick_commerce():
    filters = DealFilters(days_until_runout=5, min_seller_rating=4.0,
                          container_capacity_kg=15.0, blacklisted_ids=[], pinned_retailer_id=None)
    qc = _candidate(retailer_type="quick_commerce", lead_time_days=1)
    winner, _ = select_best_deal([qc], filters, emergency=True)
    assert winner is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_deal_selection_service.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement deal_selection.py**

```python
# backend/app/services/deal_selection.py
import uuid
from dataclasses import dataclass

@dataclass
class DealCandidate:
    listing_id: uuid.UUID
    retailer_id: uuid.UUID
    retailer_type: str
    retailer_name: str
    listing_url: str
    price: float
    shipping_cost: float
    pack_size_kg: float
    in_stock: bool
    lead_time_days: int | None
    seller_rating: float | None

@dataclass
class DealFilters:
    days_until_runout: int
    min_seller_rating: float
    container_capacity_kg: float
    blacklisted_ids: list[uuid.UUID]
    pinned_retailer_id: uuid.UUID | None

def _price_per_kg(c: DealCandidate) -> float:
    return (c.price + c.shipping_cost) / c.pack_size_kg

def _disqualify_reason(c: DealCandidate, f: DealFilters, emergency: bool) -> str | None:
    if not c.in_stock:
        return "out_of_stock"
    if c.retailer_type == "quick_commerce" and not emergency:
        return "quick_commerce"
    if c.retailer_id in f.blacklisted_ids:
        return "blacklisted"
    if c.pack_size_kg > f.container_capacity_kg:
        return "too_large"
    if c.seller_rating is not None and c.seller_rating < f.min_seller_rating:
        return "low_rating"
    if c.lead_time_days is not None and c.lead_time_days >= f.days_until_runout:
        return "too_slow"
    return None

def select_best_deal(
    candidates: list[DealCandidate],
    filters: DealFilters,
    emergency: bool = False,
) -> tuple[DealCandidate | None, list[dict]]:
    comparison = []
    eligible = []
    for c in candidates:
        reason = _disqualify_reason(c, filters, emergency)
        comparison.append({
            "listing_id": str(c.listing_id),
            "retailer_name": c.retailer_name,
            "price": c.price,
            "shipping_cost": c.shipping_cost,
            "price_per_kg": round(_price_per_kg(c), 2),
            "pack_size_kg": c.pack_size_kg,
            "in_stock": c.in_stock,
            "lead_time_days": c.lead_time_days,
            "retailer_type": c.retailer_type,
            "disqualified": reason is not None,
            "disqualify_reason": reason,
        })
        if reason is None:
            eligible.append(c)

    if not eligible:
        return None, comparison

    if filters.pinned_retailer_id:
        pinned = [c for c in eligible if c.retailer_id == filters.pinned_retailer_id]
        if pinned:
            return pinned[0], comparison

    winner = min(eligible, key=lambda c: (_price_per_kg(c), c.lead_time_days or 999))
    return winner, comparison
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_deal_selection_service.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/deal_selection.py backend/tests/test_deal_selection_service.py
git commit -m "feat: deal selection service with filter + scoring logic"
```

---

### Task 12: Deal selection Celery task + ingest trigger

**Files:**
- Create: `backend/app/tasks/deal_selection.py`
- Modify: `backend/app/routers/ingest.py`

- [ ] **Step 1: Write deal_selection task**

```python
# backend/app/tasks/deal_selection.py
import asyncio, uuid
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.celery_app import celery_app
from app.config import settings
from app.models.dog import Dog
from app.models.bin import Bin
from app.models.user import User
from app.models.product_listing import ProductListing
from app.models.product_price import ProductPrice
from app.models.pending_deal import PendingDeal
from app.models.retailer import Retailer
from app.models.lead_time import LeadTime
from app.services.deal_selection import DealCandidate, DealFilters, select_best_deal
from app.services.retailer_plugins import REGISTRY
from app.services.lead_time_service import get_avg_lead_time_days

async def _run_deal_selection_async(bin_id: str, user_id: str):
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        bin_ = await session.get(Bin, uuid.UUID(bin_id))
        user = await session.get(User, uuid.UUID(user_id))
        if not bin_ or not user:
            return

        # Check for active pending deal
        existing = await session.scalar(
            select(PendingDeal).where(
                PendingDeal.bin_id == bin_.id,
                PendingDeal.status == "pending",
                PendingDeal.expires_at > datetime.now(timezone.utc),
            )
        )
        if existing:
            return

        # Get dog + product
        dog = await session.scalar(select(Dog).where(Dog.id == bin_.dog_id))
        if not dog or not dog.product_id:
            return

        # Get active listings for this product
        listings_rows = (await session.scalars(
            select(ProductListing).where(
                ProductListing.product_id == dog.product_id,
                ProductListing.is_active == True,
            )
        )).all()
        if not listings_rows:
            return

        # Retailer slug map
        retailers = {r.id: r for r in (await session.scalars(select(Retailer))).all()}
        slug_map = {r.id: r.plugin_class.lower().replace("plugin", "") for r in retailers.values()}

        # Lead time baseline
        lead_rows = (await session.scalars(
            select(LeadTime).where(LeadTime.pincode == user.pincode)
        )).all()
        baseline_days = get_avg_lead_time_days(user.pincode, lead_rows)

        # Forecast days until runout (simplified: use 10 as default, override with real value)
        days_until_runout = 10  # TODO: integrate with forecast endpoint in future plan

    # Scrape fresh prices
    fresh_prices: dict[uuid.UUID, tuple] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for listing in listings_rows:
            slug = slug_map.get(listing.retailer_id, "")
            plugin = REGISTRY.get(slug)
            if not plugin:
                continue
            page = browser.new_page()
            try:
                r = plugin.get_price(listing.retailer_product_url, user.pincode or "", page)
                fresh_prices[listing.id] = r
            except Exception:
                pass
            page.close()
        browser.close()

    # Build candidates
    candidates = []
    for listing in listings_rows:
        r = fresh_prices.get(listing.id)
        if not r:
            continue
        retailer = retailers.get(listing.retailer_id)
        candidates.append(DealCandidate(
            listing_id=listing.id, retailer_id=listing.retailer_id,
            retailer_type=retailer.retailer_type if retailer else "standard",
            retailer_name=retailer.name if retailer else "Unknown",
            listing_url=listing.retailer_product_url,
            price=r.price, shipping_cost=r.shipping_cost,
            pack_size_kg=listing.pack_size_kg, in_stock=r.in_stock,
            lead_time_days=r.lead_time_days or baseline_days,
            seller_rating=r.seller_rating,
        ))

    filters = DealFilters(
        days_until_runout=days_until_runout,
        min_seller_rating=user.min_seller_rating,
        container_capacity_kg=bin_.container_capacity_kg,
        blacklisted_ids=user.blacklisted_retailer_ids or [],
        pinned_retailer_id=user.pinned_retailer_id,
    )
    winner, comparison = select_best_deal(candidates, filters)
    if winner is None:
        winner, comparison = select_best_deal(candidates, filters, emergency=True)

    if winner is None:
        return

    # Save price snapshot + pending deal
    async with factory() as session:
        price_row = ProductPrice(
            listing_id=winner.listing_id, price=winner.price,
            shipping_cost=winner.shipping_cost, seller_rating=winner.seller_rating,
            in_stock=winner.in_stock, lead_time_days=winner.lead_time_days,
        )
        session.add(price_row)
        await session.flush()

        plugin = REGISTRY.get(slug_map.get(winner.retailer_id, ""))
        deep_link = plugin.get_deep_link(winner.listing_url) if plugin else winner.listing_url

        deal = PendingDeal(
            bin_id=bin_.id, user_id=user.id, listing_id=winner.listing_id,
            price_snapshot_id=price_row.id, status="pending",
            deep_link_url=deep_link, comparison_json=comparison,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(deal)
        await session.commit()

    await engine.dispose()

@celery_app.task(name="app.tasks.deal_selection.run_deal_selection")
def run_deal_selection(bin_id: str, user_id: str):
    asyncio.run(_run_deal_selection_async(bin_id, user_id))
```

- [ ] **Step 2: Update ingest.py to trigger deal selection**

Add at the top of `ingest.py`:
```python
from app.tasks.deal_selection import run_deal_selection
from app.services.forecast_state import compute_forecast_state
```

Inside `ingest_reading`, after `reorder_triggered = ...`, add:
```python
    if reorder_triggered and not refill:
        run_deal_selection.delay(str(bin_id), str(current_user.id))
```

- [ ] **Step 3: Verify ingest still passes existing tests**

```bash
pytest tests/test_ingest.py -v 2>/dev/null || pytest tests/ -k "ingest" -v
```

Expected: all ingest tests pass (deal task is fire-and-forget, won't break tests)

- [ ] **Step 4: Commit**

```bash
git add backend/app/tasks/deal_selection.py backend/app/routers/ingest.py
git commit -m "feat: deal selection Celery task + ingest trigger"
```

---

### Task 13: Products router

**Files:**
- Create: `backend/app/routers/products.py`
- Create: `backend/app/schemas/product.py`
- Modify: `backend/app/schemas/user.py` — add `product_id` to DogCreate/DogResponse
- Modify: `backend/app/routers/users.py` — pass `product_id` through dog creation
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_products.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_products.py
import pytest

@pytest.mark.asyncio
async def test_product_search_returns_empty_when_no_catalog(client, user_bin):
    user, bin_, headers = user_bin
    resp = await client.get("/products?q=royal+canin", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_product_search_returns_matching_products(client, user_bin):
    from app.models.product import Product
    from app.database import Base
    # Insert a product directly
    user, bin_, headers = user_bin
    resp = await client.get("/products?q=royal", headers=headers)
    assert resp.status_code == 200
```

- [ ] **Step 2: Write schemas/product.py**

```python
# backend/app/schemas/product.py
import uuid
from pydantic import BaseModel

class ProductResponse(BaseModel):
    id: uuid.UUID
    brand: str
    name: str
    category: str
    canonical_name: str
    image_url: str | None
    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Write routers/products.py**

```python
# backend/app/routers/products.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.auth.deps import get_current_user
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductResponse

router = APIRouter()

@router.get("/products", response_model=list[ProductResponse])
async def search_products(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not q:
        rows = (await db.scalars(select(Product).limit(limit))).all()
        return rows
    pattern = f"%{q}%"
    rows = (await db.scalars(
        select(Product).where(
            or_(Product.name.ilike(pattern), Product.brand.ilike(pattern),
                Product.canonical_name.ilike(pattern))
        ).limit(limit)
    )).all()
    return rows

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    import uuid
    from fastapi import HTTPException
    p = await db.get(Product, uuid.UUID(product_id))
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return p
```

- [ ] **Step 4: Update schemas/user.py — add product_id to DogCreate + DogResponse**

```python
# In DogCreate, add:
    product_id: str | None = None

# In DogResponse, add:
    product_id: str | None
```

- [ ] **Step 5: Update routers/users.py — pass product_id through**

In `create_dog`, change `Dog(user_id=user_id, **payload.model_dump())` to:
```python
    dog = Dog(
        user_id=user_id,
        name=payload.name,
        breed=payload.breed,
        kibble_brand=payload.kibble_brand,
        kibble_product_name=payload.kibble_product_name,
        product_id=uuid.UUID(payload.product_id) if payload.product_id else None,
    )
```
Also add `import uuid` at the top if not already present.

- [ ] **Step 6: Register router in main.py**

```python
from app.routers.products import router as products_router
app.include_router(products_router)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/test_products.py -v
```

Expected: `2 passed`

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/products.py backend/app/schemas/product.py backend/app/schemas/user.py backend/app/routers/users.py backend/app/main.py backend/tests/test_products.py
git commit -m "feat: products router and dog product_id wiring"
```

---

### Task 14: Deals router

**Files:**
- Create: `backend/app/routers/deals.py`
- Create: `backend/app/schemas/deal.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_deals.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_deals.py
import pytest

@pytest.mark.asyncio
async def test_get_deal_returns_404_when_no_pending_deal(client, user_bin):
    user, bin_, headers = user_bin
    resp = await client.get(f"/bins/{bin_['id']}/deal", headers=headers)
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_mark_deal_acted_returns_404_when_no_deal(client, user_bin):
    user, bin_, headers = user_bin
    resp = await client.post(f"/bins/{bin_['id']}/deal/acted", headers=headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Write schemas/deal.py**

```python
# backend/app/schemas/deal.py
import uuid
from datetime import datetime
from pydantic import BaseModel

class DealResponse(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    retailer_name: str
    product_name: str
    pack_size_kg: float
    price: float
    shipping_cost: float
    price_per_kg: float
    deep_link_url: str
    comparison: list[dict]
    expires_at: datetime
    is_emergency: bool = False
    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Write routers/deals.py**

```python
# backend/app/routers/deals.py
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth.deps import get_current_user
from app.models.bin import Bin
from app.models.pending_deal import PendingDeal
from app.models.product_listing import ProductListing
from app.models.product import Product
from app.models.retailer import Retailer
from app.models.user import User
from app.schemas.deal import DealResponse

router = APIRouter()

async def _active_deal(bin_id: uuid.UUID, db: AsyncSession) -> PendingDeal | None:
    return await db.scalar(
        select(PendingDeal).where(
            PendingDeal.bin_id == bin_id,
            PendingDeal.status == "pending",
            PendingDeal.expires_at > datetime.now(timezone.utc),
        ).order_by(PendingDeal.created_at.desc()).limit(1)
    )

@router.get("/bins/{bin_id}/deal", response_model=DealResponse)
async def get_deal(
    bin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bin_ = await db.get(Bin, bin_id)
    if not bin_ or bin_.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Bin not found")
    deal = await _active_deal(bin_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="No active deal")
    listing = await db.get(ProductListing, deal.listing_id)
    product = await db.get(Product, listing.product_id) if listing else None
    retailer = await db.get(Retailer, listing.retailer_id) if listing else None
    price_per_kg = round((deal.comparison_json or [{}])[0].get("price_per_kg", 0), 2)
    qc_comparison = [e for e in (deal.comparison_json or []) if e.get("retailer_type") == "quick_commerce"]
    is_emergency = retailer.retailer_type == "quick_commerce" if retailer else False
    return DealResponse(
        id=deal.id, listing_id=deal.listing_id,
        retailer_name=retailer.name if retailer else "Unknown",
        product_name=product.name if product else "Unknown",
        pack_size_kg=listing.pack_size_kg if listing else 0,
        price=next((e["price"] for e in (deal.comparison_json or []) if e.get("listing_id") == str(deal.listing_id)), 0),
        shipping_cost=next((e["shipping_cost"] for e in (deal.comparison_json or []) if e.get("listing_id") == str(deal.listing_id)), 0),
        price_per_kg=next((e["price_per_kg"] for e in (deal.comparison_json or []) if e.get("listing_id") == str(deal.listing_id)), 0),
        deep_link_url=deal.deep_link_url,
        comparison=deal.comparison_json or [],
        expires_at=deal.expires_at,
        is_emergency=is_emergency,
    )

@router.post("/bins/{bin_id}/deal/acted", status_code=200)
async def mark_deal_acted(
    bin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bin_ = await db.get(Bin, bin_id)
    if not bin_ or bin_.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Bin not found")
    deal = await _active_deal(bin_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="No active deal")
    deal.status = "acted"
    await db.commit()
    return {"status": "ok"}
```

- [ ] **Step 4: Register router in main.py**

```python
from app.routers.deals import router as deals_router
app.include_router(deals_router)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_deals.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/deals.py backend/app/schemas/deal.py backend/app/main.py backend/tests/test_deals.py
git commit -m "feat: deals router — GET /bins/{id}/deal + POST /acted"
```

---

### Task 15: Android — Product + Deal DTOs + KibbleApi

**Files:**
- Create: `android/core/network/src/main/kotlin/com/kibble/core/network/dto/ProductDto.kt`
- Create: `android/core/network/src/main/kotlin/com/kibble/core/network/dto/DealDto.kt`
- Modify: `android/core/network/src/main/kotlin/com/kibble/core/network/dto/DogDto.kt`
- Modify: `android/core/network/src/main/kotlin/com/kibble/core/network/KibbleApi.kt`

- [ ] **Step 1: Write ProductDto.kt**

```kotlin
// android/core/network/src/main/kotlin/com/kibble/core/network/dto/ProductDto.kt
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class ProductDto(
    val id: String,
    val brand: String,
    val name: String,
    val category: String,
    val canonical_name: String,
    val image_url: String? = null,
)
```

- [ ] **Step 2: Write DealDto.kt**

```kotlin
// android/core/network/src/main/kotlin/com/kibble/core/network/dto/DealDto.kt
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class DealDto(
    val id: String,
    val listing_id: String,
    val retailer_name: String,
    val product_name: String,
    val pack_size_kg: Double,
    val price: Double,
    val shipping_cost: Double,
    val price_per_kg: Double,
    val deep_link_url: String,
    val comparison: List<DealComparisonEntry>,
    val expires_at: String,
    val is_emergency: Boolean = false,
)

@Serializable
data class DealComparisonEntry(
    val listing_id: String,
    val retailer_name: String,
    val price: Double,
    val shipping_cost: Double,
    val price_per_kg: Double,
    val pack_size_kg: Double,
    val in_stock: Boolean,
    val lead_time_days: Int? = null,
    val retailer_type: String,
    val disqualified: Boolean,
    val disqualify_reason: String? = null,
)
```

- [ ] **Step 3: Update DogDto.kt — add product_id**

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class DogCreateRequest(
    val name: String,
    val breed: String?,
    val kibble_brand: String,
    val kibble_product_name: String,
    val product_id: String? = null,
)

@Serializable
data class DogDto(
    val id: String,
    val name: String,
    val breed: String?,
    val kibble_brand: String,
    val kibble_product_name: String,
    val product_id: String? = null,
)
```

- [ ] **Step 4: Update KibbleApi.kt — add product + deal endpoints**

Add to the interface:
```kotlin
    @GET("products")
    suspend fun searchProducts(@Query("q") query: String, @Query("limit") limit: Int = 20): List<ProductDto>

    @GET("bins/{id}/deal")
    suspend fun getDeal(@Path("id") binId: String): DealDto

    @POST("bins/{id}/deal/acted")
    suspend fun markDealActed(@Path("id") binId: String)
```

Also add imports at top:
```kotlin
import com.kibble.core.network.dto.DealDto
import com.kibble.core.network.dto.ProductDto
import retrofit2.http.Query
```

- [ ] **Step 5: Verify build compiles**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:network:compileDebugKotlin --quiet
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 6: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/core/network/
git commit -m "feat: product and deal DTOs + KibbleApi additions"
```

---

### Task 16: Android — Product picker in onboarding

**Files:**
- Create: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/product/ProductPickerScreen.kt`
- Create: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/product/ProductPickerViewModel.kt`
- Modify: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/dog/DogScreen.kt`
- Modify: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/dog/DogViewModel.kt`
- Modify: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/OnboardingRepository.kt`

- [ ] **Step 1: Write ProductPickerViewModel.kt**

```kotlin
// android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/product/ProductPickerViewModel.kt
package com.kibble.feature.onboarding.product

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.ProductDto
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ProductPickerState(
    val query: String = "",
    val results: List<ProductDto> = emptyList(),
    val isLoading: Boolean = false,
)

@HiltViewModel
class ProductPickerViewModel @Inject constructor(
    private val api: KibbleApi,
) : ViewModel() {
    private val _state = MutableStateFlow(ProductPickerState())
    val state = _state.asStateFlow()

    private val _queryFlow = MutableStateFlow("")

    init {
        viewModelScope.launch {
            @OptIn(FlowPreview::class)
            _queryFlow.debounce(300).collect { q ->
                if (q.length < 2) {
                    _state.value = _state.value.copy(results = emptyList(), isLoading = false)
                    return@collect
                }
                _state.value = _state.value.copy(isLoading = true)
                try {
                    val results = api.searchProducts(q)
                    _state.value = _state.value.copy(results = results, isLoading = false)
                } catch (e: Exception) {
                    _state.value = _state.value.copy(results = emptyList(), isLoading = false)
                }
            }
        }
    }

    fun onQueryChange(q: String) {
        _state.value = _state.value.copy(query = q)
        _queryFlow.value = q
    }
}
```

- [ ] **Step 2: Write ProductPickerScreen.kt**

```kotlin
// android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/product/ProductPickerScreen.kt
package com.kibble.feature.onboarding.product

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kibble.core.network.dto.ProductDto

@Composable
fun ProductPickerScreen(
    onProductSelected: (ProductDto) -> Unit,
    onSkip: () -> Unit,
    viewModel: ProductPickerViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Find your kibble", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text(
            "We'll track prices across all retailers for your dog's exact food.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
        )
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::onQueryChange,
            label = { Text("Brand or product name") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Spacer(Modifier.height(8.dp))
        if (state.isLoading) {
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
            }
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            items(state.results) { product ->
                ListItem(
                    headlineContent = { Text(product.name) },
                    supportingContent = { Text(product.brand, style = MaterialTheme.typography.bodySmall) },
                    modifier = Modifier.clickable { onProductSelected(product) },
                )
                HorizontalDivider()
            }
            if (state.query.length >= 2 && state.results.isEmpty() && !state.isLoading) {
                item {
                    TextButton(onClick = onSkip, modifier = Modifier.fillMaxWidth()) {
                        Text("Can't find my kibble — skip for now")
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 3: Update DogState + DogIntent**

In `DogState.kt` (or wherever it lives, check path), add:
```kotlin
data class DogState(
    val isLoading: Boolean = false,
    val error: String? = null,
    val dogId: String? = null,
    val selectedProductId: String? = null,   // ← add this
)
```

- [ ] **Step 4: Update DogScreen.kt — show product picker inline**

Replace the brand dropdown and product text field section with:
```kotlin
// Remove: kibbleBrands dropdown and product OutlinedTextField
// Add after breed field:
        Spacer(Modifier.height(16.dp))
        if (state.selectedProductId != null) {
            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer,
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(brand.ifEmpty { "Kibble selected" }, modifier = Modifier.weight(1f))
                    TextButton(onClick = { viewModel.clearProduct() }) { Text("Change") }
                }
            }
        } else {
            var showPicker by remember { mutableStateOf(false) }
            if (showPicker) {
                ProductPickerScreen(
                    onProductSelected = { p ->
                        brand = p.brand
                        product = p.name
                        viewModel.selectProduct(p.id)
                        showPicker = false
                    },
                    onSkip = { showPicker = false },
                )
            } else {
                OutlinedButton(onClick = { showPicker = true }, modifier = Modifier.fillMaxWidth()) {
                    Text("Search for kibble product")
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = brand, onValueChange = { brand = it },
                    label = { Text("Kibble brand") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = product, onValueChange = { product = it },
                    label = { Text("Product name") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            }
        }
```

Also update the Continue button enabled condition:
```kotlin
enabled = dogName.isNotBlank() && (state.selectedProductId != null || (brand.isNotBlank() && product.isNotBlank())) && !state.isLoading,
```

- [ ] **Step 5: Update DogViewModel.kt**

```kotlin
// Add to DogViewModel:
    fun selectProduct(productId: String) {
        _state.value = _state.value.copy(selectedProductId = productId)
    }

    fun clearProduct() {
        _state.value = _state.value.copy(selectedProductId = null)
    }

    fun onContinue(name: String, breed: String?, brand: String, product: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            val user = userDao.first() ?: run {
                _state.value = _state.value.copy(isLoading = false, error = "Not signed in")
                return@launch
            }
            val productId = _state.value.selectedProductId
            when (val result = repo.createDog(user.id, name, breed?.ifBlank { null }, brand, product, productId)) {
                is KibbleResult.Success -> _state.value = _state.value.copy(isLoading = false, dogId = result.data.toString())
                is KibbleResult.Failure -> _state.value = _state.value.copy(isLoading = false, error = result.cause.message)
            }
        }
    }
```

- [ ] **Step 6: Update OnboardingRepository.createDog**

```kotlin
    suspend fun createDog(userId: UUID, name: String, breed: String?, brand: String, product: String, productId: String?): KibbleResult<UUID> = kibbleRunCatching {
        val dog = api.createDog(userId.toString(), DogCreateRequest(
            name = name, breed = breed, kibble_brand = brand,
            kibble_product_name = product, product_id = productId,
        ))
        val dogId = UUID.fromString(dog.id)
        dogDao.upsert(DogEntity(id = dogId, userId = userId, name = name, breed = breed,
            kibbleBrand = brand, kibbleProductName = product))
        dogId
    }
```

- [ ] **Step 7: Build**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :feature:onboarding:compileDebugKotlin --quiet
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 8: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/feature/onboarding/ android/core/network/
git commit -m "feat: product picker in onboarding dog screen"
```

---

### Task 17: Android — Deal card + price comparison components

**Files:**
- Create: `android/feature/orders/src/main/kotlin/com/kibble/feature/orders/DealCard.kt`
- Create: `android/feature/orders/src/main/kotlin/com/kibble/feature/orders/PriceComparisonTable.kt`

- [ ] **Step 1: Write DealCard.kt**

```kotlin
// android/feature/orders/src/main/kotlin/com/kibble/feature/orders/DealCard.kt
package com.kibble.feature.orders

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.kibble.core.network.dto.DealDto

private val ColorStocked = Color(0xFF155243)

@Composable
fun DealCard(deal: DealDto, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(16.dp),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            if (deal.is_emergency) {
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.padding(bottom = 12.dp),
                ) {
                    Text(
                        "⚡ Emergency order — standard retailers unavailable",
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                    )
                }
            }
            Text("Best deal found", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            Spacer(Modifier.height(4.dp))
            Text(deal.retailer_name, style = MaterialTheme.typography.titleMedium, color = ColorStocked)
            Text("${deal.product_name} · ${deal.pack_size_kg}kg",
                style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.Bottom) {
                Text("₹${deal.price.toInt()}", style = MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.width(8.dp))
                Text("₹${String.format("%.0f", deal.price_per_kg)}/kg",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(deal.deep_link_url)))
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = ColorStocked),
            ) { Text("Order Now") }
        }
    }
}
```

- [ ] **Step 2: Write PriceComparisonTable.kt**

```kotlin
// android/feature/orders/src/main/kotlin/com/kibble/feature/orders/PriceComparisonTable.kt
package com.kibble.feature.orders

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.kibble.core.network.dto.DealComparisonEntry

@Composable
fun PriceComparisonTable(entries: List<DealComparisonEntry>, modifier: Modifier = Modifier) {
    val sorted = entries.sortedWith(compareBy({ it.disqualified }, { it.price_per_kg }))
    val maxPrice = sorted.maxOfOrNull { it.price_per_kg } ?: 1.0

    Column(modifier = modifier.fillMaxWidth()) {
        Text("Price comparison", style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            modifier = Modifier.padding(bottom = 8.dp))
        sorted.forEach { entry ->
            val savings = ((maxPrice - entry.price_per_kg) / maxPrice * 100).toInt()
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(entry.retailer_name, style = MaterialTheme.typography.bodyMedium,
                            color = if (entry.disqualified)
                                MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f)
                            else MaterialTheme.colorScheme.onSurface)
                        if (entry.retailer_type == "quick_commerce") {
                            Spacer(Modifier.width(4.dp))
                            Surface(color = Color(0xFFE07B39).copy(alpha = 0.15f),
                                shape = RoundedCornerShape(4.dp)) {
                                Text("⚡", style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                            }
                        }
                    }
                    if (entry.disqualified && entry.disqualify_reason != null) {
                        Text(entry.disqualify_reason.replace('_', ' '),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("₹${String.format("%.0f", entry.price_per_kg)}/kg",
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (entry.disqualified)
                            MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f)
                        else MaterialTheme.colorScheme.onSurface)
                    if (!entry.disqualified && savings > 0) {
                        Text("saves ${savings}%", style = MaterialTheme.typography.labelSmall,
                            color = Color(0xFF155243))
                    }
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        }
    }
}
```

- [ ] **Step 3: Build**

```bash
./gradlew :feature:orders:compileDebugKotlin --quiet
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/feature/orders/src/main/kotlin/com/kibble/feature/orders/DealCard.kt android/feature/orders/src/main/kotlin/com/kibble/feature/orders/PriceComparisonTable.kt
git commit -m "feat: DealCard and PriceComparisonTable components"
```

---

### Task 18: Android — Orders screen rewrite

**Files:**
- Modify: `android/feature/orders/src/main/kotlin/com/kibble/feature/orders/OrdersScreen.kt`
- Modify: `android/feature/orders/src/main/kotlin/com/kibble/feature/orders/OrdersViewModel.kt`

- [ ] **Step 1: Update OrdersViewModel.kt**

```kotlin
package com.kibble.feature.orders

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.UserDao
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.DealDto
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import javax.inject.Inject

data class OrdersState(
    val deal: DealDto? = null,
    val isLoading: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class OrdersViewModel @Inject constructor(
    private val api: KibbleApi,
    private val userDao: UserDao,
    private val binDao: BinDao,
) : ViewModel() {
    private val _state = MutableStateFlow(OrdersState())
    val state = _state.asStateFlow()

    init { loadDeal() }

    fun loadDeal() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val user = userDao.first() ?: return@launch
                val bin = binDao.observeForUser(user.id).firstOrNull()?.firstOrNull()
                    ?: return@launch
                val deal = api.getDeal(bin.id.toString())
                _state.value = _state.value.copy(deal = deal, isLoading = false)
            } catch (e: retrofit2.HttpException) {
                if (e.code() == 404) {
                    _state.value = _state.value.copy(deal = null, isLoading = false)
                } else {
                    _state.value = _state.value.copy(isLoading = false, error = e.message())
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }
}
```

- [ ] **Step 2: Rewrite OrdersScreen.kt**

```kotlin
package com.kibble.feature.orders

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrdersScreen(viewModel: OrdersViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text("Kibble", style = MaterialTheme.typography.titleLarge.copy(fontStyle = FontStyle.Italic)) },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        when {
            state.isLoading -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }

            state.deal != null -> Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(padding)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                DealCard(deal = state.deal!!)
                PriceComparisonTable(entries = state.deal!!.comparison)
            }

            else -> Column(
                modifier = Modifier.fillMaxSize().padding(padding).padding(40.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text("Auto-order activates soon", style = MaterialTheme.typography.headlineSmall)
                Spacer(Modifier.height(16.dp))
                Text(
                    "We're learning your kibble's rhythm. When it's time to reorder, we'll find the best deal automatically.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}
```

- [ ] **Step 3: Build**

```bash
./gradlew :feature:orders:compileDebugKotlin --quiet
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/feature/orders/
git commit -m "feat: Orders screen with deal card and price comparison"
```

---

### Task 19: Android — Connected Retailers UI update

**Files:**
- Modify: `android/feature/settings/src/main/kotlin/com/kibble/feature/settings/retailers/AddRetailerSheet.kt`

- [ ] **Step 1: Update AddRetailerSheet.kt to match the reference design**

Replace the entire file with:

```kotlin
package com.kibble.feature.settings.retailers

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.kibble.feature.onboarding.retailer.LoginType
import com.kibble.feature.onboarding.retailer.Retailer
import com.kibble.feature.onboarding.retailer.RetailerCatalog
import com.kibble.feature.onboarding.retailer.CookieLoginScreen
import com.kibble.feature.onboarding.retailer.CredentialLoginScreen

private val ColorGreen = Color(0xFF155243)

@Composable
private fun RetailerAvatar(name: String, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .size(44.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            name.first().uppercase(),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddRetailerSheet(
    connectedRetailers: Set<String> = emptySet(),
    onDismiss: () -> Unit,
) {
    var selected by remember { mutableStateOf<Retailer?>(null) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val retailer = selected
    if (retailer != null) {
        when (retailer.loginType) {
            LoginType.COOKIE -> CookieLoginScreen(retailer = retailer, onSuccess = onDismiss, onCancel = { selected = null })
            LoginType.CREDENTIALS -> CredentialLoginScreen(retailer = retailer, onSuccess = onDismiss, onCancel = { selected = null })
        }
        return
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            modifier = Modifier.fillMaxWidth().navigationBarsPadding().padding(bottom = 24.dp),
        ) {
            Text(
                "Add a retailer",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 24.dp, vertical = 16.dp),
            )
            Text(
                "Connect your account to auto-sync orders.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                modifier = Modifier.padding(horizontal = 24.dp).padding(bottom = 8.dp),
            )
            HorizontalDivider()
            LazyColumn {
                items(RetailerCatalog.all) { r ->
                    val isConnected = r.slug in connectedRetailers
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        RetailerAvatar(r.displayName)
                        Column(modifier = Modifier.weight(1f)) {
                            Text(r.displayName, style = MaterialTheme.typography.bodyLarge)
                            Text(r.tagline, style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                        }
                        if (isConnected) {
                            Row(verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("Connected", style = MaterialTheme.typography.labelMedium,
                                    color = ColorGreen)
                                Text("✓", style = MaterialTheme.typography.labelMedium, color = ColorGreen)
                            }
                        } else {
                            Button(
                                onClick = { selected = r },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = Color(0xFFB85C38),
                                    contentColor = Color.White,
                                ),
                                shape = RoundedCornerShape(8.dp),
                                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                            ) {
                                Text("+ Add", style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                    HorizontalDivider(modifier = Modifier.padding(start = 72.dp))
                }
            }
        }
    }
}
```

Note: This requires `Retailer` to have a `slug` and `tagline` field. Add them to `RetailerCatalog.kt` / the `Retailer` data class. Check the existing `Retailer` data class at:
`android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/retailer/`

If `slug` and `tagline` are missing, add:
```kotlin
data class Retailer(
    val slug: String,
    val displayName: String,
    val tagline: String,
    val loginType: LoginType,
    val category: String,
)
```
And update `RetailerCatalog.all` entries to include slug + tagline.

- [ ] **Step 2: Update SettingsScreen.kt call site**

Find where `AddRetailerSheet` is called in `SettingsScreen.kt` and pass `connectedRetailers`:
```kotlin
// In SettingsScreen, change:
AddRetailerSheet(onDismiss = { viewModel.handle(SettingsIntent.HideAddRetailer) })
// to:
AddRetailerSheet(
    connectedRetailers = state.connectedRetailers,
    onDismiss = { viewModel.handle(SettingsIntent.HideAddRetailer) },
)
```

In `SettingsState.kt`, add:
```kotlin
val connectedRetailers: Set<String> = emptySet(),
```

In `SettingsViewModel.kt`, populate `connectedRetailers` from the list of retailer sessions (already loaded from `api.listRetailerSessions`).

- [ ] **Step 3: Build**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :feature:settings:compileDebugKotlin --quiet
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: Run full backend test suite one last time**

```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/feature/settings/
git commit -m "feat: Connected Retailers UI matches design reference"
```
