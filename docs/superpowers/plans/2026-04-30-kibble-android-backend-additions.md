# Plan 2a — Backend Additions for Android Client

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Plan 1 backend with Firebase Authentication, retailer session storage (cookies + credentials), and notification quiet hours — the prerequisites for the Android client (Plan 2b) to begin.

**Architecture:** Add a Firebase ID token verification layer (`app/auth/`), require auth on existing endpoints, and add three new resource families (`/auth/firebase`, `/users/{id}/retailer-sessions`, `/users/{id}/quiet-hours`). Encrypted retailer blobs use AES-256-GCM with a server-held key.

**Tech Stack:** Python 3.14, FastAPI 0.115, SQLAlchemy 2.0.49, asyncpg 0.30, Alembic 1.13, `firebase-admin>=6.5`, `cryptography>=43`. Existing test patterns reused — pytest-asyncio with `client` fixture, NullPool engine, autouse `truncate_tables`.

**Repo:** `/Users/sdagguba/kibble-reorder/backend/`

**Spec:** `/Users/sdagguba/sasank-playground/docs/superpowers/specs/2026-04-30-kibble-android-app-design.md` (Section 13)

---

## File Structure

**New files:**
- `app/auth/__init__.py`
- `app/auth/firebase.py` — Firebase Admin SDK init + `verify_firebase_token()`
- `app/auth/deps.py` — `get_current_user` FastAPI dependency
- `app/services/encryption.py` — AES-256-GCM encrypt/decrypt
- `app/models/retailer_session.py` — `RetailerSession` SQLAlchemy model
- `app/schemas/auth.py` — Pydantic schemas for `/auth/firebase`
- `app/schemas/retailer_session.py` — schemas for retailer sessions
- `app/schemas/quiet_hours.py` — schemas for quiet hours
- `app/routers/auth.py` — `POST /auth/firebase`
- `app/routers/retailer_sessions.py` — POST/GET/DELETE retailer sessions
- `tests/test_auth_firebase.py`
- `tests/test_encryption.py`
- `tests/test_retailer_sessions.py`
- `tests/test_quiet_hours.py`
- `alembic/versions/<rev>_add_firebase_uid_and_quiet_hours.py` — User schema additions
- `alembic/versions/<rev>_add_retailer_sessions.py` — RetailerSession table

**Modified files:**
- `pyproject.toml` — add `firebase-admin`, `cryptography`
- `app/config.py` — add `firebase_project_id`, `firebase_credentials_path`, `retailer_secret_key_b64`
- `app/models/__init__.py` — register `RetailerSession`
- `app/models/user.py` — add `firebase_uid`, make `name`/`pincode`/`email` nullable, add `quiet_hours_*`
- `app/routers/users.py` — require auth, add `PATCH /users/{user_id}/quiet-hours`
- `app/routers/ingest.py` — require auth + ownership
- `app/routers/forecast.py` — require auth + ownership
- `app/main.py` — include `auth` and `retailer_sessions` routers
- `app/schemas/user.py` — make name/pincode optional in `UserUpdate`
- `tests/conftest.py` — add `auth_headers` fixture + Firebase verifier override
- `tests/test_users.py` — update existing tests to use auth headers
- `tests/test_ingest.py` — update to use auth headers
- `tests/test_forecast.py` — update to use auth headers

---

## Task 1: Add dependencies and config

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/config.py`
- Create: `.env.example` (if missing)

- [ ] **Step 1: Add the new dependencies**

Edit `pyproject.toml`:

```toml
[project]
name = "kibble-reorder-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.6",
    "sqlalchemy[asyncio]==2.0.49",
    "asyncpg==0.30.0",
    "alembic==1.13.3",
    "pydantic-settings==2.5.2",
    "celery[redis]==5.4.0",
    "prophet==1.1.5",
    "pandas>=1.4,<3",
    "firebase-admin>=6.5,<7",
    "cryptography>=43",
]
```

- [ ] **Step 2: Install**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pip install -e ".[dev]"
```
Expected: installs `firebase-admin` and `cryptography` plus their transitive deps.

- [ ] **Step 3: Extend config**

Replace `app/config.py` contents:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://kibble:kibble@localhost:5432/kibble"
    database_url_test: str = "postgresql+asyncpg://kibble:kibble@localhost:5433/kibble_test"
    redis_url: str = "redis://localhost:6379/0"

    # Firebase Auth
    firebase_project_id: str = "kibble-reorder-dev"
    firebase_credentials_path: str | None = None  # path to service-account JSON; None in test mode

    # Retailer credential encryption: 32 raw bytes encoded as base64 (urlsafe)
    retailer_secret_key_b64: str = "dGVzdC1rZXktMzItYnl0ZXMtbG9uZy1mb3ItYWVzMjU2LWdjbS0xMjM0NTY="  # test default; override in prod

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
```

- [ ] **Step 4: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add pyproject.toml app/config.py
git commit -m "chore: add firebase-admin and cryptography deps; extend config for Firebase + retailer encryption"
```

---

## Task 2: Firebase token verifier with test override

**Files:**
- Create: `app/auth/__init__.py`
- Create: `app/auth/firebase.py`
- Create: `tests/test_auth_firebase.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_firebase.py`:

```python
import pytest
from app.auth.firebase import verify_firebase_token, FirebaseAuthError, set_test_verifier, clear_test_verifier


def test_verify_with_test_override_returns_claims():
    set_test_verifier(lambda token: {"uid": "fb-abc", "email": "user@example.com"} if token == "valid" else None)
    try:
        claims = verify_firebase_token("valid")
        assert claims["uid"] == "fb-abc"
        assert claims["email"] == "user@example.com"
    finally:
        clear_test_verifier()


def test_verify_invalid_token_raises():
    set_test_verifier(lambda token: None)
    try:
        with pytest.raises(FirebaseAuthError):
            verify_firebase_token("bad")
    finally:
        clear_test_verifier()


def test_verify_empty_token_raises():
    with pytest.raises(FirebaseAuthError):
        verify_firebase_token("")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_auth_firebase.py -v
```
Expected: ImportError or ModuleNotFoundError — `app.auth` doesn't exist.

- [ ] **Step 3: Create the auth package**

Create `app/auth/__init__.py`:

```python
```

(empty file)

Create `app/auth/firebase.py`:

```python
from typing import Callable, Optional
import firebase_admin
from firebase_admin import auth as fb_auth, credentials
from app.config import settings


class FirebaseAuthError(Exception):
    """Raised when a Firebase ID token cannot be verified."""


_test_verifier: Optional[Callable[[str], Optional[dict]]] = None
_app_initialized = False


def set_test_verifier(fn: Callable[[str], Optional[dict]]) -> None:
    """Install a verifier override for tests. The function takes a token and returns
    a claims dict (uid, email, etc.) or None to indicate invalid."""
    global _test_verifier
    _test_verifier = fn


def clear_test_verifier() -> None:
    global _test_verifier
    _test_verifier = None


def _ensure_initialized() -> None:
    global _app_initialized
    if _app_initialized:
        return
    if settings.firebase_credentials_path:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
    else:
        firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id})
    _app_initialized = True


def verify_firebase_token(token: str) -> dict:
    """Verify a Firebase ID token and return its claims dict.

    Raises FirebaseAuthError if the token is missing or invalid. In tests,
    set_test_verifier() bypasses the real Firebase Admin SDK call.
    """
    if not token:
        raise FirebaseAuthError("Empty token")
    if _test_verifier is not None:
        claims = _test_verifier(token)
        if claims is None:
            raise FirebaseAuthError("Invalid test token")
        return claims
    _ensure_initialized()
    try:
        return fb_auth.verify_id_token(token)
    except Exception as e:
        raise FirebaseAuthError(str(e)) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_auth_firebase.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/auth/ tests/test_auth_firebase.py
git commit -m "feat(auth): Firebase ID token verifier with test override"
```

---

## Task 3: User schema migration — firebase_uid, nullable name/pincode/email, quiet hours

**Files:**
- Modify: `app/models/user.py`
- Create: `alembic/versions/<rev>_add_firebase_uid_and_quiet_hours.py`
- Modify: `app/schemas/user.py`

- [ ] **Step 1: Update the User model**

Replace `app/models/user.py`:

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    auto_order_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_mode: Mapped[str] = mapped_column(String, default="90pct")
    min_seller_rating: Mapped[float] = mapped_column(Float, default=4.0)
    pack_size_preference: Mapped[str] = mapped_column(String, default="best_value")
    reorder_threshold_pct: Mapped[int] = mapped_column(Integer, default=20)
    wallet_type: Mapped[str | None] = mapped_column(String, nullable=True)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "22:00"
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), nullable=True)    # "08:00"
    quiet_hours_tz: Mapped[str | None] = mapped_column(String(64), nullable=True)    # "Asia/Kolkata"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    dogs: Mapped[list["Dog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    bins: Mapped[list["Bin"]] = relationship(back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 2: Generate the migration**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic revision --autogenerate -m "add firebase_uid and quiet_hours to users"
```
Expected: a new file in `alembic/versions/` named like `<rev>_add_firebase_uid_and_quiet_hours.py`.

- [ ] **Step 3: Review and edit the migration**

Open the generated migration. Confirm `upgrade()` adds:
- `firebase_uid` column (String, nullable, unique index)
- `quiet_hours_start`, `quiet_hours_end`, `quiet_hours_tz` columns (nullable)
- Alters `email`, `name`, `pincode` to nullable

If autogenerate missed any of those, add the missing `op.add_column` / `op.alter_column` calls manually. Confirm `downgrade()` reverses them.

- [ ] **Step 4: Apply the migration**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic upgrade head
```
Expected: prints "Running upgrade" line; exit 0.

- [ ] **Step 5: Update UserUpdate schema**

Replace `app/schemas/user.py` `UserUpdate` class to include `name` and `pincode`:

```python
class UserUpdate(BaseModel):
    name: str | None = None
    pincode: str | None = None
    reorder_threshold_pct: int | None = None
    payment_mode: str | None = None
    min_seller_rating: float | None = None
    pack_size_preference: str | None = None
    wallet_type: str | None = None
```

(Leave `UserCreate` alone for now — Task 5 will remove it.)

- [ ] **Step 6: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/models/user.py app/schemas/user.py alembic/versions/
git commit -m "feat(db): User firebase_uid, nullable profile fields, quiet hours columns"
```

---

## Task 4: Encryption service (AES-256-GCM)

**Files:**
- Create: `app/services/encryption.py`
- Create: `tests/test_encryption.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_encryption.py`:

```python
import pytest
from app.services.encryption import encrypt_blob, decrypt_blob, EncryptionError


def test_round_trip_returns_original_plaintext():
    plaintext = "session_cookie=abc123; expires=tomorrow"
    ciphertext = encrypt_blob(plaintext)
    assert ciphertext != plaintext
    assert decrypt_blob(ciphertext) == plaintext


def test_round_trip_with_unicode():
    plaintext = "user@example.com / पासवर्ड123"
    assert decrypt_blob(encrypt_blob(plaintext)) == plaintext


def test_decrypt_tampered_ciphertext_raises():
    ciphertext = encrypt_blob("hello")
    tampered = ciphertext[:-4] + "AAAA"
    with pytest.raises(EncryptionError):
        decrypt_blob(tampered)


def test_decrypt_garbage_raises():
    with pytest.raises(EncryptionError):
        decrypt_blob("not-base64-or-anything!")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_encryption.py -v
```
Expected: ImportError — `app.services.encryption` does not exist.

- [ ] **Step 3: Implement the encryption service**

Create `app/services/encryption.py`:

```python
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings


class EncryptionError(Exception):
    pass


def _key() -> bytes:
    raw = base64.b64decode(settings.retailer_secret_key_b64)
    if len(raw) != 32:
        raise EncryptionError(f"Retailer key must decode to exactly 32 bytes; got {len(raw)}")
    return raw


def encrypt_blob(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Returns urlsafe-base64(nonce || ciphertext || tag)."""
    aesgcm = AESGCM(_key())
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_blob(ciphertext_b64: str) -> str:
    """Reverse of encrypt_blob. Raises EncryptionError on any failure."""
    try:
        raw = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
    except Exception as e:
        raise EncryptionError(f"Invalid base64: {e}") from e
    if len(raw) < 13:
        raise EncryptionError("Ciphertext too short")
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(_key())
    try:
        return aesgcm.decrypt(nonce, ct, associated_data=None).decode("utf-8")
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_encryption.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/services/encryption.py tests/test_encryption.py
git commit -m "feat(crypto): AES-256-GCM encryption service for retailer credentials"
```

---

## Task 5: get_current_user FastAPI dependency + auth_headers test fixture

**Files:**
- Create: `app/auth/deps.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Implement the dependency**

Create `app/auth/deps.py`:

```python
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.firebase import verify_firebase_token, FirebaseAuthError
from app.database import get_db
from app.models.user import User


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the Authorization: Bearer <token> header.

    - 401 if no header / malformed
    - 401 if token verification fails
    - 401 if no user is provisioned for the firebase_uid (caller must POST /auth/firebase first)
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[7:].strip()
    try:
        claims = verify_firebase_token(token)
    except FirebaseAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    uid = claims.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing uid")
    user = await db.scalar(select(User).where(User.firebase_uid == uid))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not provisioned")
    return user


def require_user_id_match(current_user: User, path_user_id) -> None:
    """Raise 403 if the path user_id does not match the authenticated user."""
    if str(current_user.id) != str(path_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
```

- [ ] **Step 2: Add the test auth fixture**

Replace `tests/conftest.py`:

```python
import pytest
import app.models  # noqa: F401 — registers all models with Base.metadata
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.main import app
from app.database import Base, get_db
from app.config import settings
from app.auth.firebase import set_test_verifier, clear_test_verifier
from app.models.user import User

_engine = create_async_engine(settings.database_url_test, echo=False, poolclass=NullPool)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()

@pytest.fixture(autouse=True)
async def truncate_tables():
    yield
    async with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))

@pytest.fixture(autouse=True)
def firebase_test_verifier():
    """Map test tokens to firebase claims. Tokens of the form "fb:<uid>:<email>" are valid."""
    def verifier(token: str):
        if not token.startswith("fb:"):
            return None
        parts = token.split(":")
        if len(parts) < 2:
            return None
        uid = parts[1]
        email = parts[2] if len(parts) >= 3 else f"{uid}@example.com"
        return {"uid": uid, "email": email}
    set_test_verifier(verifier)
    yield
    clear_test_verifier()

@pytest.fixture
async def client():
    async def override_get_db():
        async with _session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
async def provisioned_user(client):
    """Create a user via POST /auth/firebase and return (user_dict, headers)."""
    token = "fb:test-uid-1:test@example.com"
    resp = await client.post("/auth/firebase", json={"firebase_id_token": token})
    assert resp.status_code == 200, resp.text
    user = resp.json()
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers
```

(The `provisioned_user` fixture depends on `POST /auth/firebase`, which is built in Task 6. The fixture won't be exercised until later tasks.)

- [ ] **Step 3: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/auth/deps.py tests/conftest.py
git commit -m "feat(auth): get_current_user dependency + test verifier fixture"
```

---

## Task 6: POST /auth/firebase endpoint

**Files:**
- Create: `app/schemas/auth.py`
- Create: `app/routers/auth.py`
- Modify: `app/main.py`
- Create: `tests/test_auth_endpoint.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth_endpoint.py`:

```python
async def test_firebase_login_provisions_new_user(client):
    resp = await client.post("/auth/firebase", json={"firebase_id_token": "fb:abc:abc@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert "user_id" in body
    assert body["is_new_user"] is True
    assert body["email"] == "abc@example.com"


async def test_firebase_login_returns_existing_user(client):
    # First call provisions
    r1 = await client.post("/auth/firebase", json={"firebase_id_token": "fb:abc:abc@example.com"})
    user_id = r1.json()["user_id"]
    # Second call for same uid returns same id
    r2 = await client.post("/auth/firebase", json={"firebase_id_token": "fb:abc:abc@example.com"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["user_id"] == user_id
    assert body["is_new_user"] is False


async def test_firebase_login_rejects_invalid_token(client):
    resp = await client.post("/auth/firebase", json={"firebase_id_token": "garbage"})
    assert resp.status_code == 401


async def test_firebase_login_rejects_empty_token(client):
    resp = await client.post("/auth/firebase", json={"firebase_id_token": ""})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_auth_endpoint.py -v
```
Expected: 404 Not Found on `/auth/firebase` (route doesn't exist yet).

- [ ] **Step 3: Create the schema**

Create `app/schemas/auth.py`:

```python
import uuid
from pydantic import BaseModel


class FirebaseLoginRequest(BaseModel):
    firebase_id_token: str


class FirebaseLoginResponse(BaseModel):
    user_id: uuid.UUID
    is_new_user: bool
    email: str | None
```

- [ ] **Step 4: Create the router**

Create `app/routers/auth.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.firebase import verify_firebase_token, FirebaseAuthError
from app.database import get_db
from app.models.user import User
from app.schemas.auth import FirebaseLoginRequest, FirebaseLoginResponse

router = APIRouter()


@router.post("/auth/firebase", response_model=FirebaseLoginResponse)
async def firebase_login(payload: FirebaseLoginRequest, db: AsyncSession = Depends(get_db)) -> FirebaseLoginResponse:
    try:
        claims = verify_firebase_token(payload.firebase_id_token)
    except FirebaseAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    uid = claims.get("uid")
    email = claims.get("email")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing uid")

    user = await db.scalar(select(User).where(User.firebase_uid == uid))
    if user:
        return FirebaseLoginResponse(user_id=user.id, is_new_user=False, email=user.email)

    user = User(firebase_uid=uid, email=email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return FirebaseLoginResponse(user_id=user.id, is_new_user=True, email=user.email)
```

- [ ] **Step 5: Wire the router into main**

Replace `app/main.py`:

```python
from fastapi import FastAPI
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.ingest import router as ingest_router
from app.routers.forecast import router as forecast_router

app = FastAPI(title="Kibble Reorder API")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ingest_router)
app.include_router(forecast_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_auth_endpoint.py -v
```
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/schemas/auth.py app/routers/auth.py app/main.py tests/test_auth_endpoint.py
git commit -m "feat(auth): POST /auth/firebase — verify token + provision or fetch user"
```

---

## Task 7: Require auth on existing endpoints + update existing tests

**Files:**
- Modify: `app/routers/users.py`
- Modify: `app/routers/ingest.py`
- Modify: `app/routers/forecast.py`
- Modify: `tests/test_users.py`
- Modify: `tests/test_ingest.py`
- Modify: `tests/test_forecast.py`

- [ ] **Step 1: Replace users router**

Replace `app/routers/users.py`:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth.deps import get_current_user, require_user_id_match
from app.models.user import User
from app.models.dog import Dog
from app.models.bin import Bin
from app.schemas.user import UserUpdate, UserResponse, DogCreate, DogResponse
from app.schemas.bin import BinCreate, BinResponse

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_user_id_match(current_user, user_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/users/{user_id}/dogs", response_model=DogResponse, status_code=status.HTTP_201_CREATED)
async def create_dog(
    user_id: uuid.UUID,
    payload: DogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_user_id_match(current_user, user_id)
    dog = Dog(user_id=user_id, **payload.model_dump())
    db.add(dog)
    await db.commit()
    await db.refresh(dog)
    return dog


@router.post("/users/{user_id}/bins", response_model=BinResponse, status_code=status.HTTP_201_CREATED)
async def create_bin(
    user_id: uuid.UUID,
    payload: BinCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_user_id_match(current_user, user_id)
    dog = await db.get(Dog, payload.dog_id)
    if not dog or dog.user_id != user_id:
        raise HTTPException(status_code=404, detail="Dog not found for this user")
    bin_ = Bin(user_id=user_id, **payload.model_dump())
    db.add(bin_)
    await db.commit()
    await db.refresh(bin_)
    return bin_
```

(Note: `POST /users` is removed — `POST /auth/firebase` provisions instead. `UserResponse` now needs to handle nullable name/pincode/email.)

- [ ] **Step 2: Update UserResponse to allow nullable fields**

Edit `app/schemas/user.py` `UserResponse` to accept `None` for name/pincode/email:

```python
class UserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    name: str | None
    pincode: str | None
    reorder_threshold_pct: int
    payment_mode: str
    min_seller_rating: float
    pack_size_preference: str

    model_config = {"from_attributes": True}
```

(Remove the `UserCreate` class — no longer used.)

- [ ] **Step 3: Add auth to ingest router**

Read `app/routers/ingest.py` first to see existing structure. Add `current_user: User = Depends(get_current_user)` to each endpoint that takes a `bin_id` and add an ownership check: load the bin, then `if bin_.user_id != current_user.id: raise HTTPException(403)`.

The exact code edit depends on the current ingest.py contents. The pattern to apply per endpoint:

```python
from app.auth.deps import get_current_user
from app.models.user import User
# ...

@router.post("/bins/{bin_id}/...")
async def some_endpoint(
    bin_id: uuid.UUID,
    payload: ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bin_ = await db.get(Bin, bin_id)
    if not bin_:
        raise HTTPException(status_code=404, detail="Bin not found")
    if bin_.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    # ... existing logic
```

Apply the same change to every endpoint in `app/routers/ingest.py` that takes `bin_id`.

- [ ] **Step 4: Add auth to forecast router**

Read `app/routers/forecast.py`. Apply the same pattern as Step 3 — add `current_user: User = Depends(get_current_user)` and ownership check on the `bin_id` for the forecast endpoint.

- [ ] **Step 5: Replace test_users.py to use auth**

Replace `tests/test_users.py`:

```python
async def test_update_user_settings(client):
    token = "fb:settings-uid:settings@example.com"
    user = (await client.post("/auth/firebase", json={"firebase_id_token": token})).json()
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.patch(
        f"/users/{user['user_id']}",
        json={"reorder_threshold_pct": 30, "name": "Sasank", "pincode": "560001"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reorder_threshold_pct"] == 30
    assert body["name"] == "Sasank"
    assert body["pincode"] == "560001"


async def test_update_other_user_returns_403(client):
    t1 = "fb:u1:u1@example.com"
    t2 = "fb:u2:u2@example.com"
    user1 = (await client.post("/auth/firebase", json={"firebase_id_token": t1})).json()
    await client.post("/auth/firebase", json={"firebase_id_token": t2})
    headers2 = {"Authorization": f"Bearer {t2}"}
    resp = await client.patch(
        f"/users/{user1['user_id']}",
        json={"reorder_threshold_pct": 99},
        headers=headers2,
    )
    assert resp.status_code == 403


async def test_create_dog_requires_auth(client):
    user = (await client.post("/auth/firebase", json={"firebase_id_token": "fb:dog-owner:dog@example.com"})).json()
    headers = {"Authorization": "Bearer fb:dog-owner:dog@example.com"}
    resp = await client.post(
        f"/users/{user['user_id']}/dogs",
        json={
            "name": "Bruno",
            "breed": "Labrador",
            "kibble_brand": "Royal Canin",
            "kibble_product_name": "Royal Canin Labrador Adult 12kg",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Bruno"


async def test_create_bin(client):
    token = "fb:bin-owner:bin@example.com"
    user = (await client.post("/auth/firebase", json={"firebase_id_token": token})).json()
    headers = {"Authorization": f"Bearer {token}"}
    dog = (await client.post(
        f"/users/{user['user_id']}/dogs",
        json={
            "name": "Rex", "breed": "GSD",
            "kibble_brand": "Drools", "kibble_product_name": "Drools Adult 10kg",
        },
        headers=headers,
    )).json()
    resp = await client.post(
        f"/users/{user['user_id']}/bins",
        json={
            "dog_id": dog["id"],
            "sensor_device_id": "AA:BB:CC:DD:EE:FF",
            "container_capacity_kg": 15.0,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["calibration_state"] == "uncalibrated"
    assert body["container_capacity_kg"] == 15.0


async def test_create_bin_cross_user_dog_returns_404(client):
    t1 = "fb:cross-1:cross1@example.com"
    t2 = "fb:cross-2:cross2@example.com"
    u1 = (await client.post("/auth/firebase", json={"firebase_id_token": t1})).json()
    u2 = (await client.post("/auth/firebase", json={"firebase_id_token": t2})).json()
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}
    dog = (await client.post(
        f"/users/{u1['user_id']}/dogs",
        json={"name": "Buddy", "breed": None,
              "kibble_brand": "Pedigree", "kibble_product_name": "Pedigree Adult 10kg"},
        headers=h1,
    )).json()
    resp = await client.post(
        f"/users/{u2['user_id']}/bins",
        json={
            "dog_id": dog["id"],
            "sensor_device_id": "AA:BB:CC:DD:EE:FF",
            "container_capacity_kg": 10.0,
        },
        headers=h2,
    )
    assert resp.status_code == 404


async def test_unauthenticated_request_returns_401(client):
    resp = await client.patch(
        "/users/00000000-0000-0000-0000-000000000000",
        json={"reorder_threshold_pct": 30},
    )
    assert resp.status_code == 401


async def test_get_me_returns_current_user(client):
    token = "fb:me-uid:me@example.com"
    user = (await client.post("/auth/firebase", json={"firebase_id_token": token})).json()
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == user["user_id"]
```

- [ ] **Step 6: Update test_ingest.py and test_forecast.py to send auth**

Read `tests/test_ingest.py` and `tests/test_forecast.py`. For each test that creates a user/bin and then calls a `/bins/{id}/...` endpoint, prepend a `POST /auth/firebase` call to provision a user, capture `user_id` and a `headers = {"Authorization": "Bearer fb:..."}` dict, and pass `headers=headers` to every subsequent request that requires auth. Replace `POST /users` paths with the auth flow.

Apply the pattern below to every test:

```python
async def test_X(client):
    token = "fb:test-X:x@example.com"
    user = (await client.post("/auth/firebase", json={"firebase_id_token": token})).json()
    headers = {"Authorization": f"Bearer {token}"}
    # ... existing test body, but with headers=headers on every call
```

- [ ] **Step 7: Run the full suite**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest -v
```
Expected: all existing tests pass + new auth tests pass.

- [ ] **Step 8: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/routers/ app/schemas/user.py tests/
git commit -m "feat(auth): require Firebase auth on all endpoints; ownership checks; updated tests"
```

---

## Task 8: RetailerSession model + migration

**Files:**
- Create: `app/models/retailer_session.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<rev>_add_retailer_sessions.py`

- [ ] **Step 1: Create the model**

Create `app/models/retailer_session.py`:

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RetailerSession(Base):
    __tablename__ = "retailer_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    retailer: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "amazon", "supertails"
    type: Mapped[str] = mapped_column(String, nullable=False)  # "cookie" | "credentials"
    encrypted_blob: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String, default="ONBOARDING")  # ONBOARDING | CHECKOUT_PROMPT | SETTINGS_ADD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 2: Register the model**

Edit `app/models/__init__.py`:

```python
from app.models.user import User
from app.models.dog import Dog
from app.models.bin import Bin
from app.models.sensor_reading import SensorReading
from app.models.retailer import Retailer
from app.models.order import Order
from app.models.lead_time import LeadTime
from app.models.retailer_session import RetailerSession

__all__ = ["User", "Dog", "Bin", "SensorReading", "Retailer", "Order", "LeadTime", "RetailerSession"]
```

- [ ] **Step 3: Generate the migration**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic revision --autogenerate -m "add retailer_sessions table"
```
Expected: migration file created with `op.create_table('retailer_sessions', ...)`.

- [ ] **Step 4: Verify and apply the migration**

Open the migration. Confirm:
- `op.create_table('retailer_sessions', ...)` with all columns
- Foreign key to `users.id` with `ondelete="CASCADE"`
- Index on `user_id`

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
alembic upgrade head
```
Expected: migration applied; exit 0.

- [ ] **Step 5: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/models/retailer_session.py app/models/__init__.py alembic/versions/
git commit -m "feat(db): RetailerSession model + migration"
```

---

## Task 9: Retailer-sessions CRUD endpoints

**Files:**
- Create: `app/schemas/retailer_session.py`
- Create: `app/routers/retailer_sessions.py`
- Modify: `app/main.py`
- Create: `tests/test_retailer_sessions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retailer_sessions.py`:

```python
async def _provision(client, uid: str = "rs-uid", email: str = "rs@example.com"):
    token = f"fb:{uid}:{email}"
    user = (await client.post("/auth/firebase", json={"firebase_id_token": token})).json()
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


async def test_post_cookie_session(client):
    user, headers = await _provision(client)
    resp = await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={
            "retailer": "supertails",
            "type": "cookie",
            "session_blob": "session=xyz; expires=tomorrow",
            "expires_at": "2026-12-31T23:59:59Z",
            "source": "ONBOARDING",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["retailer"] == "supertails"
    assert body["type"] == "cookie"
    assert body["expires_at"] is not None
    assert "encrypted_blob" not in body
    assert "session_blob" not in body


async def test_post_credentials_session(client):
    user, headers = await _provision(client)
    resp = await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={
            "retailer": "amazon",
            "type": "credentials",
            "credentials_blob": "{\"email\":\"foo@example.com\",\"password\":\"hunter2\"}",
            "source": "ONBOARDING",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["retailer"] == "amazon"
    assert body["type"] == "credentials"
    assert body.get("expires_at") is None


async def test_post_session_other_user_returns_403(client):
    u1, _ = await _provision(client, "rs-1", "rs1@example.com")
    _, h2 = await _provision(client, "rs-2", "rs2@example.com")
    resp = await client.post(
        f"/users/{u1['user_id']}/retailer-sessions",
        json={"retailer": "amazon", "type": "credentials", "credentials_blob": "x"},
        headers=h2,
    )
    assert resp.status_code == 403


async def test_get_sessions_lists_all_for_user(client):
    user, headers = await _provision(client)
    await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={"retailer": "supertails", "type": "cookie", "session_blob": "a", "expires_at": "2027-01-01T00:00:00Z"},
        headers=headers,
    )
    await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={"retailer": "amazon", "type": "credentials", "credentials_blob": "b"},
        headers=headers,
    )
    resp = await client.get(f"/users/{user['user_id']}/retailer-sessions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    retailers = {r["retailer"] for r in data}
    assert retailers == {"supertails", "amazon"}
    for r in data:
        assert "encrypted_blob" not in r


async def test_post_same_retailer_twice_replaces(client):
    user, headers = await _provision(client)
    body = {"retailer": "supertails", "type": "cookie", "session_blob": "first"}
    await client.post(f"/users/{user['user_id']}/retailer-sessions", json=body, headers=headers)
    body["session_blob"] = "second"
    resp = await client.post(f"/users/{user['user_id']}/retailer-sessions", json=body, headers=headers)
    assert resp.status_code == 201
    listing = (await client.get(f"/users/{user['user_id']}/retailer-sessions", headers=headers)).json()
    assert len([r for r in listing if r["retailer"] == "supertails"]) == 1


async def test_delete_session(client):
    user, headers = await _provision(client)
    await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={"retailer": "huft", "type": "cookie", "session_blob": "x"},
        headers=headers,
    )
    resp = await client.delete(f"/users/{user['user_id']}/retailer-sessions/huft", headers=headers)
    assert resp.status_code == 204
    listing = (await client.get(f"/users/{user['user_id']}/retailer-sessions", headers=headers)).json()
    assert all(r["retailer"] != "huft" for r in listing)


async def test_blob_is_actually_encrypted_at_rest(client):
    """The persisted blob must not equal the plaintext sent by the client."""
    from app.services.encryption import decrypt_blob
    from sqlalchemy import select
    from app.models.retailer_session import RetailerSession
    from tests.conftest import _session_factory  # type: ignore

    user, headers = await _provision(client)
    plaintext = "session=ABC123_PLAINTEXT_SENTINEL"
    await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={"retailer": "supertails", "type": "cookie", "session_blob": plaintext},
        headers=headers,
    )
    async with _session_factory() as session:
        row = await session.scalar(select(RetailerSession).where(RetailerSession.retailer == "supertails"))
        assert row is not None
        assert row.encrypted_blob != plaintext
        assert decrypt_blob(row.encrypted_blob) == plaintext


async def test_invalid_type_rejected(client):
    user, headers = await _provision(client)
    resp = await client.post(
        f"/users/{user['user_id']}/retailer-sessions",
        json={"retailer": "amazon", "type": "magic", "credentials_blob": "x"},
        headers=headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_retailer_sessions.py -v
```
Expected: 404 Not Found on every test (no router registered yet).

- [ ] **Step 3: Create the schemas**

Create `app/schemas/retailer_session.py`:

```python
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, model_validator


class RetailerSessionCreate(BaseModel):
    retailer: str
    type: Literal["cookie", "credentials"]
    session_blob: str | None = None
    credentials_blob: str | None = None
    expires_at: datetime | None = None
    source: Literal["ONBOARDING", "CHECKOUT_PROMPT", "SETTINGS_ADD"] = "ONBOARDING"

    @model_validator(mode="after")
    def _exactly_one_blob(self):
        if self.type == "cookie" and not self.session_blob:
            raise ValueError("session_blob required when type=cookie")
        if self.type == "credentials" and not self.credentials_blob:
            raise ValueError("credentials_blob required when type=credentials")
        return self


class RetailerSessionResponse(BaseModel):
    id: uuid.UUID
    retailer: str
    type: str
    expires_at: datetime | None
    source: str

    model_config = {"from_attributes": True}


class RetailerSessionListItem(BaseModel):
    retailer: str
    type: str
    expires_at: datetime | None
    is_expired: bool
    source: str
```

- [ ] **Step 4: Create the router**

Create `app/routers/retailer_sessions.py`:

```python
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user, require_user_id_match
from app.database import get_db
from app.models.user import User
from app.models.retailer_session import RetailerSession
from app.schemas.retailer_session import (
    RetailerSessionCreate,
    RetailerSessionResponse,
    RetailerSessionListItem,
)
from app.services.encryption import encrypt_blob

router = APIRouter()


@router.post(
    "/users/{user_id}/retailer-sessions",
    response_model=RetailerSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_retailer_session(
    user_id: uuid.UUID,
    payload: RetailerSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RetailerSession:
    require_user_id_match(current_user, user_id)
    plaintext = payload.session_blob if payload.type == "cookie" else payload.credentials_blob
    encrypted = encrypt_blob(plaintext)

    existing = await db.scalar(
        select(RetailerSession).where(
            RetailerSession.user_id == user_id,
            RetailerSession.retailer == payload.retailer,
        )
    )
    if existing:
        existing.type = payload.type
        existing.encrypted_blob = encrypted
        existing.expires_at = payload.expires_at
        existing.source = payload.source
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    row = RetailerSession(
        user_id=user_id,
        retailer=payload.retailer,
        type=payload.type,
        encrypted_blob=encrypted,
        expires_at=payload.expires_at,
        source=payload.source,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/users/{user_id}/retailer-sessions", response_model=list[RetailerSessionListItem])
async def list_retailer_sessions(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RetailerSessionListItem]:
    require_user_id_match(current_user, user_id)
    rows = (await db.scalars(select(RetailerSession).where(RetailerSession.user_id == user_id))).all()
    now = datetime.now(timezone.utc)
    return [
        RetailerSessionListItem(
            retailer=r.retailer,
            type=r.type,
            expires_at=r.expires_at,
            is_expired=bool(r.expires_at and r.expires_at <= now),
            source=r.source,
        )
        for r in rows
    ]


@router.delete("/users/{user_id}/retailer-sessions/{retailer}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_retailer_session(
    user_id: uuid.UUID,
    retailer: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    require_user_id_match(current_user, user_id)
    await db.execute(
        delete(RetailerSession).where(
            RetailerSession.user_id == user_id,
            RetailerSession.retailer == retailer,
        )
    )
    await db.commit()
```

- [ ] **Step 5: Wire router into main**

Edit `app/main.py` — add to imports and `include_router`:

```python
from app.routers.retailer_sessions import router as retailer_sessions_router
# ...
app.include_router(retailer_sessions_router)
```

Final `app/main.py`:

```python
from fastapi import FastAPI
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.ingest import router as ingest_router
from app.routers.forecast import router as forecast_router
from app.routers.retailer_sessions import router as retailer_sessions_router

app = FastAPI(title="Kibble Reorder API")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ingest_router)
app.include_router(forecast_router)
app.include_router(retailer_sessions_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_retailer_sessions.py -v
```
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/schemas/retailer_session.py app/routers/retailer_sessions.py app/main.py tests/test_retailer_sessions.py
git commit -m "feat(retailer): POST/GET/DELETE /users/{id}/retailer-sessions with AES-GCM encryption"
```

---

## Task 10: PATCH /users/{user_id}/quiet-hours endpoint

**Files:**
- Create: `app/schemas/quiet_hours.py`
- Modify: `app/routers/users.py`
- Create: `tests/test_quiet_hours.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quiet_hours.py`:

```python
async def _provision(client, uid: str = "qh-uid", email: str = "qh@example.com"):
    token = f"fb:{uid}:{email}"
    user = (await client.post("/auth/firebase", json={"firebase_id_token": token})).json()
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


async def test_set_quiet_hours(client):
    user, headers = await _provision(client)
    resp = await client.patch(
        f"/users/{user['user_id']}/quiet-hours",
        json={"start": "22:00", "end": "08:00", "timezone": "Asia/Kolkata"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["quiet_hours_start"] == "22:00"
    assert body["quiet_hours_end"] == "08:00"
    assert body["quiet_hours_tz"] == "Asia/Kolkata"


async def test_quiet_hours_invalid_format_rejected(client):
    user, headers = await _provision(client)
    resp = await client.patch(
        f"/users/{user['user_id']}/quiet-hours",
        json={"start": "10pm", "end": "8am", "timezone": "Asia/Kolkata"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_quiet_hours_other_user_returns_403(client):
    u1, _ = await _provision(client, "qh-1", "qh1@example.com")
    _, h2 = await _provision(client, "qh-2", "qh2@example.com")
    resp = await client.patch(
        f"/users/{u1['user_id']}/quiet-hours",
        json={"start": "22:00", "end": "08:00", "timezone": "Asia/Kolkata"},
        headers=h2,
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_quiet_hours.py -v
```
Expected: 404 on the patch route (doesn't exist).

- [ ] **Step 3: Create the schema**

Create `app/schemas/quiet_hours.py`:

```python
import re
import uuid
from pydantic import BaseModel, field_validator

_HHMM = re.compile(r"^[0-2]\d:[0-5]\d$")


class QuietHoursUpdate(BaseModel):
    start: str
    end: str
    timezone: str

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("Must be HH:MM (24-hour)")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("timezone required")
        return v


class QuietHoursResponse(BaseModel):
    id: uuid.UUID
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    quiet_hours_tz: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Add the endpoint to users router**

Edit `app/routers/users.py`. Add the import and a new endpoint at the bottom of the router:

```python
from app.schemas.quiet_hours import QuietHoursUpdate, QuietHoursResponse


@router.patch("/users/{user_id}/quiet-hours", response_model=QuietHoursResponse)
async def update_quiet_hours(
    user_id: uuid.UUID,
    payload: QuietHoursUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_user_id_match(current_user, user_id)
    current_user.quiet_hours_start = payload.start
    current_user.quiet_hours_end = payload.end
    current_user.quiet_hours_tz = payload.timezone
    await db.commit()
    await db.refresh(current_user)
    return current_user
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest tests/test_quiet_hours.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Run the entire suite to confirm nothing regressed**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
pytest -v
```
Expected: all tests pass (Task 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10).

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add app/schemas/quiet_hours.py app/routers/users.py tests/test_quiet_hours.py
git commit -m "feat(notify): PATCH /users/{id}/quiet-hours endpoint"
```

---

## Task 11: Final integration check + README

**Files:**
- Create: `README.md` (or update existing)

- [ ] **Step 1: Verify backend boots**

Run:
```bash
cd /Users/sdagguba/kibble-reorder/backend
uvicorn app.main:app --reload --port 8000 &
sleep 3
curl -s http://localhost:8000/health
curl -s http://localhost:8000/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print('\\n'.join(sorted(d['paths'].keys())))"
kill %1 2>/dev/null || true
```

Expected output for the second curl includes:
```
/auth/firebase
/bins/{bin_id}/...
/health
/users/me
/users/{user_id}
/users/{user_id}/bins
/users/{user_id}/dogs
/users/{user_id}/quiet-hours
/users/{user_id}/retailer-sessions
/users/{user_id}/retailer-sessions/{retailer}
```

- [ ] **Step 2: Update or create README with new env vars**

Add or update `README.md` (only if user asks for one — otherwise skip this step). New env vars to document:
- `FIREBASE_PROJECT_ID`
- `FIREBASE_CREDENTIALS_PATH`
- `RETAILER_SECRET_KEY_B64` (base64-encoded 32-byte key)

To generate a production key:
```bash
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
```

- [ ] **Step 3: Final commit (if README was created/updated)**

```bash
cd /Users/sdagguba/kibble-reorder/backend
git add README.md
git commit -m "docs: env vars for Firebase Auth and retailer encryption"
```

---

## Definition of Done

- [ ] `pytest -v` passes (all existing tests + ~25 new tests across auth, encryption, retailer-sessions, quiet-hours)
- [ ] `alembic upgrade head` applies cleanly on a fresh database
- [ ] `uvicorn app.main:app` boots without error
- [ ] `/openapi.json` lists `/auth/firebase`, `/users/{id}/retailer-sessions` (POST/GET/DELETE), `/users/{id}/quiet-hours`
- [ ] All endpoints except `/health` and `/auth/firebase` reject unauthenticated requests with 401
- [ ] All path-`user_id` endpoints reject other users with 403
- [ ] Retailer session blobs are AES-256-GCM encrypted at rest (verified by `test_blob_is_actually_encrypted_at_rest`)
- [ ] Pre-existing endpoints (`POST /users/{id}/dogs`, `POST /users/{id}/bins`, `POST /bins/{id}/readings`, `GET /bins/{id}/forecast`, `POST /bins/{id}/calibrate-empty` etc.) still work, now requiring auth
- [ ] No reference to the old `POST /users` endpoint remains in code or tests

---

## Notes for the Implementer

- **Always run tests from the backend directory:** `cd /Users/sdagguba/kibble-reorder/backend && pytest`. The repo root has no test config.
- **Database before testing:** `docker compose up -d` from the kibble-reorder repo root brings up Postgres on 5432 (dev) and 5433 (test).
- **Migrations are sequential:** if you generate two migrations from a single conceptual change, that's fine — Alembic chains them.
- **Test fixtures are autouse:** the `firebase_test_verifier` fixture in conftest.py rewires the verifier for every test. Tokens of the form `fb:<uid>:<email>` are valid; anything else raises.
- **Existing test patterns:** all tests use `async def test_X(client):` and `await client.post(...)`. Don't introduce sync clients.
- **Don't edit existing migrations:** if a migration was already applied, generate a new one to fix issues.
- **`provisioned_user` fixture:** available in conftest.py for tests that just need an authenticated user — depend on it via parameter name.
