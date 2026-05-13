from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr


class GoogleAuthRequest(BaseModel):
    credential: str  # Google ID token from frontend GSI


class EmailOTPSendRequest(BaseModel):
    email: EmailStr


class EmailOTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    is_new_user: bool


class UserProfile(BaseModel):
    id: int
    phone: str | None
    name: str | None
    theme_slug: str
    selected_agent_slugs: list[str]
    profile: dict
    onboarding_step: str | None
    goals: dict
    skin_profile: dict


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    theme_slug: str | None = None
    selected_agent_slugs: list[str] | None = None
    goals: dict[str, Any] | None = None
    skin_profile: dict[str, Any] | None = None
    onboarding_step: str | None = None


class AnalyzeSkinRequest(BaseModel):
    image_base64: str  # base64-encoded JPEG/PNG
    media_type: str = "image/jpeg"


class AnalyzeSkinResponse(BaseModel):
    skin_type: str | None = None
    visible_concerns: list[str] = []
    texture: str | None = None
    oiliness: str | None = None
    skin_tone: str | None = None
    notes: str | None = None
    raw: dict = {}
