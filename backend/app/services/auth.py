from __future__ import annotations

import json
import random
import re
import string
from datetime import datetime, timedelta, timezone

import psycopg
import resend
import structlog
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import jwt

from app.config import settings
from app.schemas.auth import AnalyzeSkinResponse, TokenResponse, UpdateProfileRequest, UserProfile

log = structlog.get_logger()

# In-memory OTP store — replace with Redis in production
_otp_store: dict[str, tuple[str, datetime]] = {}
OTP_TTL_MINUTES = 10


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


# ── Google OAuth ──────────────────────────────────────────────────────────────

async def verify_google_token(
    conn: psycopg.AsyncConnection, credential: str
) -> TokenResponse:
    """Verify Google ID token, upsert user, return our JWT."""
    try:
        info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as e:
        raise ValueError(f"Invalid Google token: {e}")

    email = info.get("email")
    name = info.get("name")
    if not email:
        raise ValueError("Google token missing email")

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO users.users (email, name)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET name = COALESCE(EXCLUDED.name, users.users.name)
            RETURNING id, created_at
            """,
            (email, name),
        )
        row = await cur.fetchone()
        await conn.commit()

    user_id = row["id"]
    is_new = (datetime.now(timezone.utc) - row["created_at"]).total_seconds() < 5
    token = _create_token(user_id)
    log.info("google_auth", user_id=user_id, email=email, is_new=is_new)
    return TokenResponse(access_token=token, user_id=user_id, is_new_user=is_new)


# ── Email OTP ─────────────────────────────────────────────────────────────────

async def send_email_otp(email: str) -> str:
    """Send 6-digit OTP to email. Returns request_id. Dev mode if no Resend key."""
    otp = _generate_otp()
    _otp_store[email] = (otp, datetime.now(timezone.utc))

    if not settings.resend_api_key:
        log.info("dev_email_otp", email=email, otp=otp)
        return f"dev-{email}"

    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from": settings.otp_from_email,
        "to": email,
        "subject": "Your Wand sign-in code",
        "html": f"""
        <div style="font-family:sans-serif;max-width:400px;margin:40px auto">
          <h2 style="color:#e85d9b">Your sign-in code</h2>
          <p style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#1a1a1a">{otp}</p>
          <p style="color:#666;font-size:14px">Valid for {OTP_TTL_MINUTES} minutes. Don't share this with anyone.</p>
        </div>
        """,
    })
    return f"email-{email}"


async def verify_email_otp(
    conn: psycopg.AsyncConnection, email: str, otp: str
) -> TokenResponse:
    entry = _otp_store.get(email)
    if not entry:
        raise ValueError("No OTP found for this email")

    stored_otp, sent_at = entry
    if (datetime.now(timezone.utc) - sent_at).total_seconds() > OTP_TTL_MINUTES * 60:
        del _otp_store[email]
        raise ValueError("OTP expired")

    if stored_otp != otp:
        raise ValueError("Invalid OTP")

    del _otp_store[email]

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO users.users (email)
            VALUES (%s)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id, created_at
            """,
            (email,),
        )
        row = await cur.fetchone()
        await conn.commit()

    user_id = row["id"]
    is_new = (datetime.now(timezone.utc) - row["created_at"]).total_seconds() < 5
    token = _create_token(user_id)
    log.info("email_otp_verified", user_id=user_id, email=email)
    return TokenResponse(access_token=token, user_id=user_id, is_new_user=is_new)


# ── Profile update ────────────────────────────────────────────────────────────

async def update_user_profile(
    conn: psycopg.AsyncConnection, user_id: int, req: UpdateProfileRequest
) -> UserProfile | None:
    """Patch any subset of user profile fields."""
    updates: list[str] = []
    params: list = []

    if req.name is not None:
        updates.append("name = %s")
        params.append(req.name)
    if req.theme_slug is not None:
        updates.append("theme_slug = %s")
        params.append(req.theme_slug)
    if req.selected_agent_slugs is not None:
        updates.append("selected_agent_slugs = %s")
        params.append(req.selected_agent_slugs)
    if req.goals is not None:
        updates.append("goals = %s")
        params.append(json.dumps(req.goals))
    if req.skin_profile is not None:
        updates.append("skin_profile = %s")
        params.append(json.dumps(req.skin_profile))
    if req.onboarding_step is not None:
        updates.append("onboarding_step = %s")
        params.append(req.onboarding_step)

    if not updates:
        return await get_user_profile(conn, user_id)

    params.append(user_id)
    async with conn.cursor() as cur:
        await cur.execute(
            f"UPDATE users.users SET {', '.join(updates)} WHERE id = %s",
            params,
        )
        await conn.commit()

    return await get_user_profile(conn, user_id)


# ── Skin photo analysis ───────────────────────────────────────────────────────

_SKIN_ANALYSIS_PROMPT = """Analyze this skin/face photo and return a JSON object with these fields:
- skin_type: one of "oily", "dry", "combination", "normal", "sensitive"
- visible_concerns: array of strings describing visible skin concerns (e.g. "acne", "dark spots", "redness", "hyperpigmentation", "dryness", "fine lines", "large pores", "dark circles", "uneven texture")
- texture: one of "smooth", "rough", "uneven", "bumpy"
- oiliness: one of "very oily", "moderately oily", "balanced", "dry"
- skin_tone: one of "fair", "light", "medium", "tan", "deep"
- notes: brief additional observations (1-2 sentences max)

Return ONLY the JSON object, no explanation, no markdown fences."""


_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_SKIN_MODEL = "claude-haiku-4-5-20251001"


async def analyze_skin_photo(image_base64: str, media_type: str = "image/jpeg") -> AnalyzeSkinResponse:
    """Call Claude Haiku vision to extract skin profile from a photo."""
    if not settings.anthropic_api_key:
        raise ValueError("Anthropic API key not configured")

    payload = {
        "model": _SKIN_MODEL,
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {"type": "text", "text": _SKIN_ANALYSIS_PROMPT},
                ],
            }
        ],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(_ANTHROPIC_API_URL, json=payload, headers=headers)
        if r.status_code != 200:
            raise ValueError(f"Claude API error {r.status_code}: {r.text[:200]}")
        resp = r.json()

    raw_text = resp["content"][0]["text"].strip()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw_text, re.S)
        data = json.loads(m.group()) if m else {}

    return AnalyzeSkinResponse(
        skin_type=data.get("skin_type"),
        visible_concerns=data.get("visible_concerns") or [],
        texture=data.get("texture"),
        oiliness=data.get("oiliness"),
        skin_tone=data.get("skin_tone"),
        notes=data.get("notes"),
        raw=data,
    )


# ── Shared ────────────────────────────────────────────────────────────────────

def _create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def decode_token(token: str) -> int:
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    return int(payload["sub"])


async def get_user_profile(conn: psycopg.AsyncConnection, user_id: int) -> UserProfile | None:
    async with conn.cursor() as cur:
        await cur.execute(
            """SELECT id, phone, email, name, theme_slug, selected_agent_slugs,
                      profile, onboarding_step, goals, skin_profile
               FROM users.users WHERE id = %s""",
            (user_id,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return UserProfile(
        id=row["id"],
        phone=row["phone"],
        name=row["name"],
        theme_slug=row["theme_slug"],
        selected_agent_slugs=row["selected_agent_slugs"] or [],
        profile=row["profile"] or {},
        onboarding_step=row["onboarding_step"],
        goals=row["goals"] or {},
        skin_profile=row["skin_profile"] or {},
    )
