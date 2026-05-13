from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException

from app.database import get_conn
from app.schemas.auth import (
    AnalyzeSkinRequest,
    AnalyzeSkinResponse,
    EmailOTPSendRequest,
    EmailOTPVerifyRequest,
    GoogleAuthRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserProfile,
)
from app.services import auth as svc
from app.services.auth import decode_token

router = APIRouter(prefix="/auth", tags=["auth"])

Conn = Annotated[psycopg.AsyncConnection, Depends(get_conn)]


def _get_user_id(authorization: str) -> int:
    try:
        return decode_token(authorization.removeprefix("Bearer "))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/google", response_model=TokenResponse)
async def google_auth(payload: GoogleAuthRequest, conn: Conn) -> TokenResponse:
    try:
        return await svc.verify_google_token(conn, payload.credential)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/email/send")
async def send_email_otp(payload: EmailOTPSendRequest) -> dict:
    try:
        await svc.send_email_otp(payload.email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {e}")
    return {"message": "OTP sent"}


@router.post("/email/verify", response_model=TokenResponse)
async def verify_email_otp(payload: EmailOTPVerifyRequest, conn: Conn) -> TokenResponse:
    try:
        return await svc.verify_email_otp(conn, payload.email, payload.otp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=UserProfile)
async def get_me(conn: Conn, authorization: str = Header(...)) -> UserProfile:
    user_id = _get_user_id(authorization)
    profile = await svc.get_user_profile(conn, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.patch("/me", response_model=UserProfile)
async def update_me(
    payload: UpdateProfileRequest,
    conn: Conn,
    authorization: str = Header(...),
) -> UserProfile:
    user_id = _get_user_id(authorization)
    profile = await svc.update_user_profile(conn, user_id, payload)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.post("/analyze-skin", response_model=AnalyzeSkinResponse)
async def analyze_skin(
    payload: AnalyzeSkinRequest,
    authorization: str = Header(...),
) -> AnalyzeSkinResponse:
    _get_user_id(authorization)  # require auth
    try:
        return await svc.analyze_skin_photo(payload.image_base64, payload.media_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
