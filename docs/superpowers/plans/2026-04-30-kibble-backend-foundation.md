# Kibble Auto-Reorder — Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the new `kibble-reorder` repo, stand up the Python/FastAPI backend with PostgreSQL, all database models, sensor ingest API, bin calibration logic, and run-out forecasting — the foundation every other component builds on.

**Architecture:** Async FastAPI app using SQLAlchemy 2.0 (async) with PostgreSQL, Alembic for migrations, Celery+Redis stubs for background jobs. Sensor readings arrive via REST, are stored, and the forecasting service computes consumption rate and predicted run-out date. When the forecast crosses the user's reorder threshold, a Celery task will be dispatched (wired in Plan 3).

**Tech Stack:** Python 3.11, FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg, Alembic, PostgreSQL 16, Redis 7, Celery 5, pydantic-settings 2, pytest 8, pytest-asyncio 0.24, httpx

---

## File Map

```
/Users/sdagguba/kibble-reorder/
├── .gitignore
├── docker-compose.yml
└── backend/
    ├── pyproject.toml
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py
    │   └── versions/
    │       └── <hash>_initial_schema.py   (auto-generated)
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── config.py
    │   ├── database.py
    │   ├── models/
    │   │   ├── __init__.py
    │   │   ├── user.py
    │   │   ├── dog.py
    │   │   ├── bin.py
    │   │   ├── sensor_reading.py
    │   │   ├── order.py
    │   │   ├── retailer.py
    │   │   └── lead_time.py
    │   ├── schemas/
    │   │   ├── __init__.py
    │   │   ├── user.py
    │   │   ├── bin.py
    │   │   └── sensor.py
    │   ├── routers/
    │   │   ├── __init__.py
    │   │   ├── users.py
    │   │   └── ingest.py
    │   └── services/
    │       ├── __init__.py
    │       ├── calibration.py
    │       └── forecasting.py
    └── tests/
        ├── __init__.py
        ├── conftest.py
        ├── test_users.py
        ├── test_ingest.py
        └── test_forecasting.py
```

---

### Task 1: Repo scaffold + Docker Compose

**Files:**
- Create: `/Users/sdagguba/kibble-reorder/.gitignore`
- Create: `/Users/sdagguba/kibble-reorder/docker-compose.yml`
- Create: `/Users/sdagguba/kibble-reorder/backend/pyproject.toml`

- [ ] **Step 1: Create repo directory and git init**

```bash
mkdir -p /Users/sdagguba/kibble-reorder/backend
cd /Users/sdagguba/kibble-reorder
git init
```

Expected: `Initialized empty Git repository in /Users/sdagguba/kibble-reorder/.git/`

- [ ] **Step 2: Create .gitignore**

Create `/Users/sdagguba/kibble-reorder/.gitignore`:
```
__pycache__/
*.pyc
.env
.venv/
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
```

- [ ] **Step 3: Create docker-compose.yml**

Create `/Users/sdagguba/kibble-reorder/docker-compose.yml`:
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: kibble
      POSTGRES_USER: kibble
      POSTGRES_PASSWORD: kibble
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  postgres_test:
    image: postgres:16
    environment:
      POSTGRES_DB: kibble_test
      POSTGRES_USER: kibble
      POSTGRES_PASSWORD: kibble
    ports:
      - "5433:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

- [ ] **Step 4: Create pyproject.toml**

Create `/Users/sdagguba/kibble-reorder/backend/pyproject.toml`:
```toml
[project]
name = "kibble-reorder-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.6",
    "sqlalchemy[asyncio]==2.0.36",
    "asyncpg==0.29.0",
    "alembic==1.13.3",
    "pydantic-settings==2.5.2",
    "celery[redis]==5.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.3",
    "pytest-asyncio==0.24.0",
    "httpx==0.27.2",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 5: Create virtual environment and install**

```bash
cd /Users/sdagguba/kibble-reorder/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: all packages install with no errors. Run `python -c "import fastapi; print(fastapi.__version__)"` — should print `0.115.0`.

- [ ] **Step 6: Start Docker services**

```bash
cd /Users/sdagguba/kibble-reorder
docker compose up -d
```

Expected: `docker compose ps` shows `postgres`, `postgres_test`, and `redis` as running.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add .gitignore docker-compose.yml backend/pyproject.toml
git commit -m "chore: repo scaffold with docker compose and pyproject.toml"
```

---

### Task 2: App config and database setup

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Create app/__init__.py**

```bash
mkdir -p /Users/sdagguba/kibble-reorder/backend/app
touch /Users/sdagguba/kibble-reorder/backend/app/__init__.py
```

- [ ] **Step 2: Create config.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://kibble:kibble@localhost:5432/kibble"
    database_url_test: str = "postgresql+asyncpg://kibble:kibble@localhost:5433/kibble_test"
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
```

- [ ] **Step 3: Create database.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/database.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 4: Create main.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="Kibble Reorder API")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Verify app starts**

```bash
cd /Users/sdagguba/kibble-reorder/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Expected: `Uvicorn running on http://127.0.0.1:8000`. Open `http://localhost:8000/health` in browser — should return `{"status":"ok"}`. Press Ctrl+C to stop.

- [ ] **Step 6: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/
git commit -m "chore: FastAPI app skeleton with config and async database setup"
```

---

### Task 3: Database models

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/dog.py`
- Create: `backend/app/models/bin.py`
- Create: `backend/app/models/sensor_reading.py`
- Create: `backend/app/models/order.py`
- Create: `backend/app/models/retailer.py`
- Create: `backend/app/models/lead_time.py`

- [ ] **Step 1: Create models/user.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/user.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Float, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    pincode: Mapped[str] = mapped_column(String(10))
    auto_order_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_mode: Mapped[str] = mapped_column(String, default="90pct")
    min_seller_rating: Mapped[float] = mapped_column(Float, default=4.0)
    pack_size_preference: Mapped[str] = mapped_column(String, default="best_value")
    reorder_threshold_pct: Mapped[int] = mapped_column(Integer, default=20)
    wallet_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    dogs: Mapped[list["Dog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    bins: Mapped[list["Bin"]] = relationship(back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 2: Create models/dog.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/dog.py`:
```python
import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Dog(Base):
    __tablename__ = "dogs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    breed: Mapped[str | None] = mapped_column(String, nullable=True)
    kibble_brand: Mapped[str] = mapped_column(String)
    kibble_product_name: Mapped[str] = mapped_column(String)

    user: Mapped["User"] = relationship(back_populates="dogs")
    bins: Mapped[list["Bin"]] = relationship(back_populates="dog")
```

- [ ] **Step 3: Create models/bin.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/bin.py`:
```python
import uuid
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Bin(Base):
    __tablename__ = "bins"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    dog_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("dogs.id"))
    sensor_device_id: Mapped[str] = mapped_column(String)
    container_capacity_kg: Mapped[float] = mapped_column(Float)
    empty_calibration_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    full_calibration_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_state: Mapped[str] = mapped_column(String, default="uncalibrated")

    user: Mapped["User"] = relationship(back_populates="bins")
    dog: Mapped["Dog"] = relationship(back_populates="bins")
    readings: Mapped[list["SensorReading"]] = relationship(back_populates="bin", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="bin")
```

- [ ] **Step 4: Create models/sensor_reading.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/sensor_reading.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import Float, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bin_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bins.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    distance_mm: Mapped[float] = mapped_column(Float)
    kibble_level_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    kibble_kg_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_refill_event: Mapped[bool] = mapped_column(Boolean, default=False)

    bin: Mapped["Bin"] = relationship(back_populates="readings")
```

- [ ] **Step 5: Create models/retailer.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/retailer.py`:
```python
import uuid
from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Retailer(Base):
    __tablename__ = "retailers"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    base_url: Mapped[str] = mapped_column(String)
    plugin_class: Mapped[str] = mapped_column(String)
    retailer_type: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 6: Create models/order.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/order.py`:
```python
import uuid
from datetime import datetime, date
from sqlalchemy import String, Float, Integer, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    bin_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bins.id"))
    retailer_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("retailers.id"))
    product_name: Mapped[str] = mapped_column(String)
    pack_size_kg: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total_price: Mapped[float] = mapped_column(Float)
    shipping_cost: Mapped[float] = mapped_column(Float, default=0.0)
    price_per_kg: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="pending")
    placed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    estimated_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retailer_order_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    triggered_at_level_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    bin: Mapped["Bin"] = relationship(back_populates="orders")
```

- [ ] **Step 7: Create models/lead_time.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/lead_time.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class LeadTime(Base):
    __tablename__ = "lead_times"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("retailers.id"))
    pincode: Mapped[str] = mapped_column(String(10))
    estimated_days: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String)
    recorded_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    retailer: Mapped["Retailer"] = relationship()
```

- [ ] **Step 8: Create models/__init__.py**

Create `/Users/sdagguba/kibble-reorder/backend/app/models/__init__.py`:
```python
from app.models.user import User
from app.models.dog import Dog
from app.models.bin import Bin
from app.models.sensor_reading import SensorReading
from app.models.retailer import Retailer
from app.models.order import Order
from app.models.lead_time import LeadTime

__all__ = ["User", "Dog", "Bin", "SensorReading", "Retailer", "Order", "LeadTime"]
```

- [ ] **Step 9: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/models/
git commit -m "feat: SQLAlchemy models for all database tables"
```

---

### Task 4: Alembic migrations

**Files:**
- Create: `backend/alembic.ini`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/<hash>_initial_schema.py` (auto-generated)

- [ ] **Step 1: Initialise Alembic**

```bash
cd /Users/sdagguba/kibble-reorder/backend
source .venv/bin/activate
alembic init alembic
```

Expected: `alembic/` directory and `alembic.ini` created.

- [ ] **Step 2: Update sqlalchemy.url in alembic.ini**

In `backend/alembic.ini`, find the line `sqlalchemy.url = ...` and replace it with:
```ini
sqlalchemy.url = postgresql+asyncpg://kibble:kibble@localhost:5432/kibble
```

- [ ] **Step 3: Replace alembic/env.py**

Replace the full contents of `backend/alembic/env.py` with:
```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.database import Base
import app.models  # noqa: F401 — registers all models with Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Generate initial migration**

```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic revision --autogenerate -m "initial schema"
```

Expected: file created in `alembic/versions/` like `xxxx_initial_schema.py`. Open it and verify it contains `op.create_table` calls for `users`, `dogs`, `bins`, `sensor_readings`, `retailers`, `orders`, `lead_times`.

- [ ] **Step 5: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade -> xxxx, initial schema` with no errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add alembic/ alembic.ini
git commit -m "feat: Alembic migration for initial schema"
```

---

### Task 5: User, Dog, and Bin registration API

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/schemas/bin.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/users.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_users.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/__init__.py` (empty).

Create `backend/tests/conftest.py`:
```python
import pytest
import app.models  # noqa: F401 — registers all models with Base.metadata
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.database import Base, get_db
from app.config import settings

test_engine = create_async_engine(settings.database_url_test, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

@pytest.fixture
async def db_session():
    async with test_engine.connect() as conn:
        await conn.begin_nested()
        async with AsyncSession(bind=conn) as session:
            yield session
        await conn.rollback()

@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

Create `backend/tests/test_users.py`:
```python
async def test_create_user(client):
    response = await client.post("/users", json={
        "email": "test@example.com",
        "name": "Test User",
        "pincode": "560001",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert data["reorder_threshold_pct"] == 20

async def test_create_user_duplicate_email_returns_409(client):
    payload = {"email": "dup@example.com", "name": "A", "pincode": "560001"}
    await client.post("/users", json=payload)
    response = await client.post("/users", json=payload)
    assert response.status_code == 409

async def test_create_dog(client):
    user = (await client.post("/users", json={
        "email": "dogowner@example.com", "name": "Owner", "pincode": "560001"
    })).json()
    response = await client.post(f"/users/{user['id']}/dogs", json={
        "name": "Bruno",
        "breed": "Labrador",
        "kibble_brand": "Royal Canin",
        "kibble_product_name": "Royal Canin Labrador Adult 12kg",
    })
    assert response.status_code == 201
    assert response.json()["name"] == "Bruno"

async def test_create_bin(client):
    user = (await client.post("/users", json={
        "email": "binowner@example.com", "name": "Owner", "pincode": "560001"
    })).json()
    dog = (await client.post(f"/users/{user['id']}/dogs", json={
        "name": "Rex", "breed": "GSD",
        "kibble_brand": "Drools", "kibble_product_name": "Drools Adult 10kg",
    })).json()
    response = await client.post(f"/users/{user['id']}/bins", json={
        "dog_id": dog["id"],
        "sensor_device_id": "AA:BB:CC:DD:EE:FF",
        "container_capacity_kg": 15.0,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["calibration_state"] == "uncalibrated"
    assert data["container_capacity_kg"] == 15.0

async def test_update_user_settings(client):
    user = (await client.post("/users", json={
        "email": "settings@example.com", "name": "S", "pincode": "560001"
    })).json()
    response = await client.patch(f"/users/{user['id']}", json={"reorder_threshold_pct": 30})
    assert response.status_code == 200
    assert response.json()["reorder_threshold_pct"] == 30
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sdagguba/kibble-reorder/backend
source .venv/bin/activate
pytest tests/test_users.py -v
```

Expected: FAIL with `404 Not Found` — routes don't exist yet.

- [ ] **Step 3: Create schemas**

Create `backend/app/schemas/__init__.py` (empty).

Create `backend/app/schemas/user.py`:
```python
import uuid
from pydantic import BaseModel

class UserCreate(BaseModel):
    email: str
    name: str
    pincode: str

class UserUpdate(BaseModel):
    reorder_threshold_pct: int | None = None
    payment_mode: str | None = None
    min_seller_rating: float | None = None
    pack_size_preference: str | None = None
    wallet_type: str | None = None

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    pincode: str
    reorder_threshold_pct: int
    payment_mode: str
    min_seller_rating: float
    pack_size_preference: str

    model_config = {"from_attributes": True}

class DogCreate(BaseModel):
    name: str
    breed: str | None = None
    kibble_brand: str
    kibble_product_name: str

class DogResponse(BaseModel):
    id: uuid.UUID
    name: str
    breed: str | None
    kibble_brand: str
    kibble_product_name: str

    model_config = {"from_attributes": True}
```

Create `backend/app/schemas/bin.py`:
```python
import uuid
from pydantic import BaseModel

class BinCreate(BaseModel):
    dog_id: uuid.UUID
    sensor_device_id: str
    container_capacity_kg: float

class BinResponse(BaseModel):
    id: uuid.UUID
    dog_id: uuid.UUID
    sensor_device_id: str
    container_capacity_kg: float
    calibration_state: str
    empty_calibration_mm: float | None
    full_calibration_mm: float | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create routers/users.py**

Create `backend/app/routers/__init__.py` (empty).

Create `backend/app/routers/users.py`:
```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.dog import Dog
from app.models.bin import Bin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, DogCreate, DogResponse
from app.schemas.bin import BinCreate, BinResponse

router = APIRouter()

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(**payload.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: uuid.UUID, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/users/{user_id}/dogs", response_model=DogResponse, status_code=status.HTTP_201_CREATED)
async def create_dog(user_id: uuid.UUID, payload: DogCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    dog = Dog(user_id=user_id, **payload.model_dump())
    db.add(dog)
    await db.commit()
    await db.refresh(dog)
    return dog

@router.post("/users/{user_id}/bins", response_model=BinResponse, status_code=status.HTTP_201_CREATED)
async def create_bin(user_id: uuid.UUID, payload: BinCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    bin_ = Bin(user_id=user_id, **payload.model_dump())
    db.add(bin_)
    await db.commit()
    await db.refresh(bin_)
    return bin_
```

- [ ] **Step 5: Register router in main.py**

Replace `backend/app/main.py` with:
```python
from fastapi import FastAPI
from app.routers.users import router as users_router

app = FastAPI(title="Kibble Reorder API")
app.include_router(users_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_users.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/schemas/ app/routers/ app/main.py tests/
git commit -m "feat: user, dog, and bin registration API with settings update"
```

---

### Task 6: Calibration service + sensor ingest API

**Files:**
- Create: `backend/app/schemas/sensor.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/calibration.py`
- Create: `backend/app/routers/ingest.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_ingest.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_ingest.py`:
```python
import pytest

@pytest.fixture
async def user_bin(client):
    user = (await client.post("/users", json={
        "email": "ingest@example.com", "name": "T", "pincode": "560001"
    })).json()
    dog = (await client.post(f"/users/{user['id']}/dogs", json={
        "name": "D", "breed": None,
        "kibble_brand": "Drools", "kibble_product_name": "Drools 10kg",
    })).json()
    bin_ = (await client.post(f"/users/{user['id']}/bins", json={
        "dog_id": dog["id"],
        "sensor_device_id": "AA:BB:CC:DD:EE:FF",
        "container_capacity_kg": 15.0,
    })).json()
    return user, bin_

async def test_calibrate_empty(client, user_bin):
    _, bin_ = user_bin
    response = await client.post(f"/bins/{bin_['id']}/calibrate/empty", json={"distance_mm": 400.0})
    assert response.status_code == 200
    data = response.json()
    assert data["calibration_state"] == "empty_only"
    assert data["empty_calibration_mm"] == 400.0

async def test_calibrate_full_requires_empty_first(client, user_bin):
    _, bin_ = user_bin
    response = await client.post(f"/bins/{bin_['id']}/calibrate/full", json={"distance_mm": 50.0, "weight_kg": 10.0})
    assert response.status_code == 400

async def test_ingest_reading_before_calibration(client, user_bin):
    _, bin_ = user_bin
    response = await client.post(f"/bins/{bin_['id']}/readings", json={"distance_mm": 200.0})
    assert response.status_code == 201
    data = response.json()
    assert data["kibble_level_pct"] is None

async def test_ingest_reading_after_full_calibration(client, user_bin):
    _, bin_ = user_bin
    await client.post(f"/bins/{bin_['id']}/calibrate/empty", json={"distance_mm": 400.0})
    await client.post(f"/bins/{bin_['id']}/calibrate/full", json={"distance_mm": 50.0, "weight_kg": 10.0})
    # distance=225mm → kibble_depth = 400-225 = 175mm, max_depth = 400-50 = 350mm → 50%
    response = await client.post(f"/bins/{bin_['id']}/readings", json={"distance_mm": 225.0})
    assert response.status_code == 201
    data = response.json()
    assert abs(data["kibble_level_pct"] - 50.0) < 0.1
    # kg_remaining = 50% * 15kg = 7.5kg
    assert abs(data["kibble_kg_remaining"] - 7.5) < 0.1

async def test_ingest_detects_refill_event(client, user_bin):
    _, bin_ = user_bin
    await client.post(f"/bins/{bin_['id']}/readings", json={"distance_mm": 380.0})  # near empty
    response = await client.post(f"/bins/{bin_['id']}/readings", json={"distance_mm": 80.0})  # refilled
    assert response.status_code == 201
    assert response.json()["is_refill_event"] is True

async def test_ingest_reorder_triggered_below_threshold(client, user_bin):
    user, bin_ = user_bin
    await client.patch(f"/users/{user['id']}", json={"reorder_threshold_pct": 50})
    await client.post(f"/bins/{bin_['id']}/calibrate/empty", json={"distance_mm": 400.0})
    await client.post(f"/bins/{bin_['id']}/calibrate/full", json={"distance_mm": 50.0, "weight_kg": 10.0})
    # 15% level → depth=52.5mm → distance=400-52.5=347.5mm
    response = await client.post(f"/bins/{bin_['id']}/readings", json={"distance_mm": 347.5})
    assert response.status_code == 201
    data = response.json()
    assert abs(data["kibble_level_pct"] - 15.0) < 0.5
    assert data["reorder_triggered"] is True

async def test_ingest_no_reorder_above_threshold(client, user_bin):
    _, bin_ = user_bin
    await client.post(f"/bins/{bin_['id']}/calibrate/empty", json={"distance_mm": 400.0})
    await client.post(f"/bins/{bin_['id']}/calibrate/full", json={"distance_mm": 50.0, "weight_kg": 10.0})
    # 75% level → depth=262.5mm → distance=400-262.5=137.5mm
    response = await client.post(f"/bins/{bin_['id']}/readings", json={"distance_mm": 137.5})
    assert response.status_code == 201
    assert response.json()["reorder_triggered"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ingest.py -v
```

Expected: FAIL — routes don't exist yet.

- [ ] **Step 3: Create services skeleton**

Create `backend/app/services/__init__.py` (empty).

Create `backend/app/services/forecasting.py` (stub — Task 7 adds the full implementation):
```python
def should_trigger_reorder(level_pct: float, reorder_threshold_pct: int) -> bool:
    return level_pct <= reorder_threshold_pct
```

Create `backend/app/services/calibration.py`:
```python
from app.models.bin import Bin

def compute_level(bin_: Bin, distance_mm: float) -> tuple[float | None, float | None]:
    """Returns (kibble_level_pct, kibble_kg_remaining). Returns (None, None) if not fully calibrated."""
    if bin_.calibration_state != "fully_calibrated":
        return None, None
    max_depth = bin_.empty_calibration_mm - bin_.full_calibration_mm
    current_depth = bin_.empty_calibration_mm - distance_mm
    current_depth = max(0.0, min(current_depth, max_depth))
    level_pct = (current_depth / max_depth) * 100.0
    kg_remaining = (level_pct / 100.0) * bin_.container_capacity_kg
    return round(level_pct, 2), round(kg_remaining, 3)

def is_refill_event(previous_distance_mm: float | None, current_distance_mm: float, threshold_mm: float = 50.0) -> bool:
    """Refill detected when distance drops by more than threshold_mm in one reading."""
    if previous_distance_mm is None:
        return False
    return (previous_distance_mm - current_distance_mm) > threshold_mm
```

- [ ] **Step 4: Create sensor schemas**

Create `backend/app/schemas/sensor.py`:
```python
import uuid
from datetime import datetime
from pydantic import BaseModel

class CalibrateEmptyRequest(BaseModel):
    distance_mm: float

class CalibrateFullRequest(BaseModel):
    distance_mm: float
    weight_kg: float

class BinCalibrationResponse(BaseModel):
    id: uuid.UUID
    calibration_state: str
    empty_calibration_mm: float | None
    full_calibration_mm: float | None

    model_config = {"from_attributes": True}

class ReadingCreate(BaseModel):
    distance_mm: float

class ReadingResponse(BaseModel):
    id: uuid.UUID
    bin_id: uuid.UUID
    timestamp: datetime
    distance_mm: float
    kibble_level_pct: float | None
    kibble_kg_remaining: float | None
    is_refill_event: bool
    reorder_triggered: bool
```

- [ ] **Step 5: Create routers/ingest.py**

Create `backend/app/routers/ingest.py`:
```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.bin import Bin
from app.models.sensor_reading import SensorReading
from app.models.user import User
from app.schemas.sensor import (
    CalibrateEmptyRequest, CalibrateFullRequest,
    BinCalibrationResponse, ReadingCreate, ReadingResponse,
)
from app.services.calibration import compute_level, is_refill_event
from app.services.forecasting import should_trigger_reorder

router = APIRouter()

@router.post("/bins/{bin_id}/calibrate/empty", response_model=BinCalibrationResponse)
async def calibrate_empty(bin_id: uuid.UUID, payload: CalibrateEmptyRequest, db: AsyncSession = Depends(get_db)):
    bin_ = await db.get(Bin, bin_id)
    if not bin_:
        raise HTTPException(status_code=404, detail="Bin not found")
    bin_.empty_calibration_mm = payload.distance_mm
    bin_.calibration_state = "empty_only"
    await db.commit()
    await db.refresh(bin_)
    return bin_

@router.post("/bins/{bin_id}/calibrate/full", response_model=BinCalibrationResponse)
async def calibrate_full(bin_id: uuid.UUID, payload: CalibrateFullRequest, db: AsyncSession = Depends(get_db)):
    bin_ = await db.get(Bin, bin_id)
    if not bin_:
        raise HTTPException(status_code=404, detail="Bin not found")
    if bin_.empty_calibration_mm is None:
        raise HTTPException(status_code=400, detail="Empty calibration must be set first")
    bin_.full_calibration_mm = payload.distance_mm
    bin_.calibration_state = "fully_calibrated"
    await db.commit()
    await db.refresh(bin_)
    return bin_

@router.post("/bins/{bin_id}/readings", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
async def ingest_reading(bin_id: uuid.UUID, payload: ReadingCreate, db: AsyncSession = Depends(get_db)):
    bin_ = await db.get(Bin, bin_id)
    if not bin_:
        raise HTTPException(status_code=404, detail="Bin not found")

    last = await db.scalar(
        select(SensorReading)
        .where(SensorReading.bin_id == bin_id)
        .order_by(SensorReading.timestamp.desc())
        .limit(1)
    )

    level_pct, kg_remaining = compute_level(bin_, payload.distance_mm)
    refill = is_refill_event(last.distance_mm if last else None, payload.distance_mm)

    reading = SensorReading(
        bin_id=bin_id,
        distance_mm=payload.distance_mm,
        kibble_level_pct=level_pct,
        kibble_kg_remaining=kg_remaining,
        is_refill_event=refill,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)

    reorder_triggered = False
    if level_pct is not None:
        user = await db.get(User, bin_.user_id)
        reorder_triggered = should_trigger_reorder(level_pct, user.reorder_threshold_pct)

    return ReadingResponse(
        id=reading.id,
        bin_id=reading.bin_id,
        timestamp=reading.timestamp,
        distance_mm=reading.distance_mm,
        kibble_level_pct=reading.kibble_level_pct,
        kibble_kg_remaining=reading.kibble_kg_remaining,
        is_refill_event=reading.is_refill_event,
        reorder_triggered=reorder_triggered,
    )
```

- [ ] **Step 6: Register ingest router in main.py**

Replace `backend/app/main.py` with:
```python
from fastapi import FastAPI
from app.routers.users import router as users_router
from app.routers.ingest import router as ingest_router

app = FastAPI(title="Kibble Reorder API")
app.include_router(users_router)
app.include_router(ingest_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/test_ingest.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/schemas/sensor.py app/services/ app/routers/ingest.py app/main.py tests/test_ingest.py
git commit -m "feat: sensor ingest API with calibration and refill detection"
```

---

### Task 7: Forecasting service

**Files:**
- Create: `backend/app/services/forecasting.py`
- Create: `backend/tests/test_forecasting.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_forecasting.py`:
```python
from datetime import datetime, timedelta
from app.services.forecasting import (
    compute_consumption_rate_mm_per_day,
    forecast_runout_date,
    should_trigger_reorder,
)

def make_readings(distances: list[float], hours_apart: int = 6) -> list[tuple[datetime, float]]:
    """distances is oldest-to-newest. Returns list sorted oldest-first."""
    start = datetime(2024, 1, 8, 12, 0)
    return [(start + timedelta(hours=i * hours_apart), d) for i, d in enumerate(distances)]

def test_consumption_rate_steady():
    # distance increases 10mm every 6h = 40mm/day consumed
    readings = make_readings([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0])
    rate = compute_consumption_rate_mm_per_day(readings)
    assert abs(rate - 40.0) < 1.0

def test_consumption_rate_uses_only_post_refill_segment():
    # refill at index 3 (prev=120, curr=50: drop of 70mm > 50mm threshold)
    readings = make_readings([100.0, 110.0, 120.0, 50.0, 60.0, 70.0])
    rate = compute_consumption_rate_mm_per_day(readings)
    # segment after refill: 50→70 over 12h = 0.5d → 40mm/day
    assert abs(rate - 40.0) < 1.0

def test_consumption_rate_single_reading_returns_zero():
    readings = make_readings([200.0])
    assert compute_consumption_rate_mm_per_day(readings) == 0.0

def test_forecast_runout_date():
    now = datetime(2024, 1, 10, 12, 0)
    # 400mm empty, 50mm full, current=200mm → depth=200mm, rate=40mm/day → 5 days
    runout = forecast_runout_date(
        current_distance_mm=200.0,
        empty_calibration_mm=400.0,
        full_calibration_mm=50.0,
        consumption_rate_mm_per_day=40.0,
        now=now,
    )
    assert abs((runout - now).total_seconds() / 86400 - 5.0) < 0.1

def test_forecast_runout_zero_rate_returns_far_future():
    now = datetime(2024, 1, 10, 12, 0)
    runout = forecast_runout_date(200.0, 400.0, 50.0, 0.0, now)
    assert (runout - now).days >= 365

def test_should_trigger_reorder_below_threshold():
    assert should_trigger_reorder(level_pct=15.0, reorder_threshold_pct=20) is True

def test_should_trigger_reorder_at_threshold():
    assert should_trigger_reorder(level_pct=20.0, reorder_threshold_pct=20) is True

def test_should_trigger_reorder_above_threshold():
    assert should_trigger_reorder(level_pct=25.0, reorder_threshold_pct=20) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_forecasting.py -v
```

Expected: FAIL — `forecasting` module not found.

- [ ] **Step 3: Replace stub with full forecasting service**

Replace the contents of `backend/app/services/forecasting.py` with:
```python
from datetime import datetime, timedelta

def compute_consumption_rate_mm_per_day(
    readings: list[tuple[datetime, float]],
    refill_threshold_mm: float = 50.0,
) -> float:
    """
    readings: list of (timestamp, distance_mm) sorted oldest-first.
    Finds the last refill event (sudden distance decrease), uses only the
    most recent continuous segment to compute consumption rate in mm/day.
    """
    if len(readings) < 2:
        return 0.0

    last_refill_idx = 0
    for i in range(1, len(readings)):
        prev_dist = readings[i - 1][1]
        curr_dist = readings[i][1]
        if (prev_dist - curr_dist) > refill_threshold_mm:
            last_refill_idx = i

    segment = readings[last_refill_idx:]
    if len(segment) < 2:
        return 0.0

    start_time, start_dist = segment[0]
    end_time, end_dist = segment[-1]
    elapsed_days = (end_time - start_time).total_seconds() / 86400.0
    if elapsed_days < 0.01:
        return 0.0

    distance_consumed = end_dist - start_dist  # positive when kibble level drops
    return max(0.0, distance_consumed / elapsed_days)

def forecast_runout_date(
    current_distance_mm: float,
    empty_calibration_mm: float,
    full_calibration_mm: float,
    consumption_rate_mm_per_day: float,
    now: datetime,
) -> datetime:
    """Returns predicted datetime when bin reaches empty."""
    kibble_depth_mm = empty_calibration_mm - current_distance_mm
    if consumption_rate_mm_per_day <= 0:
        return now + timedelta(days=365)
    days_remaining = kibble_depth_mm / consumption_rate_mm_per_day
    return now + timedelta(days=days_remaining)

def should_trigger_reorder(level_pct: float, reorder_threshold_pct: int) -> bool:
    return level_pct <= reorder_threshold_pct
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_forecasting.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests across all files PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/services/forecasting.py tests/test_forecasting.py
git commit -m "feat: forecasting service — consumption rate and run-out prediction"
```

---

## What comes next

- **Plan 2 — Android App:** BLE foreground service (MokoSmart SDK), all screens, FCM notifications, sends readings to `/bins/{id}/readings`
- **Plan 3 — Retailer Scrapers & Deal Selection:** Playwright plugins per retailer, deal scoring, price comparison API
- **Plan 4 — Checkout Automation & Full Loop:** 90%/100% payment modes, Celery job wiring, end-to-end order flow
