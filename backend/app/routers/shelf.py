from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException

from app.database import get_conn
from app.schemas.shelf import ShelfItem, ShelfItemAdd, ShelfItemUpdate
from app.services import shelf as svc
from app.services.auth import decode_token

router = APIRouter(prefix="/shelf", tags=["shelf"])

Conn = Annotated[psycopg.AsyncConnection, Depends(get_conn)]


def _require_user(authorization: str = Header(...)) -> int:
    try:
        token = authorization.removeprefix("Bearer ")
        return decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


CurrentUser = Annotated[int, Depends(_require_user)]


@router.get("", response_model=list[ShelfItem])
async def get_shelf(conn: Conn, user_id: CurrentUser) -> list[ShelfItem]:
    return await svc.get_shelf(conn, user_id)


@router.post("", response_model=ShelfItem, status_code=201)
async def add_to_shelf(payload: ShelfItemAdd, conn: Conn, user_id: CurrentUser) -> ShelfItem:
    return await svc.add_to_shelf(conn, user_id, payload)


@router.patch("/{item_id}", response_model=ShelfItem)
async def update_shelf_item(
    item_id: int, payload: ShelfItemUpdate, conn: Conn, user_id: CurrentUser
) -> ShelfItem:
    item = await svc.update_shelf_item(conn, user_id, item_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail="Shelf item not found")
    return item


@router.delete("/{item_id}", status_code=204)
async def remove_from_shelf(item_id: int, conn: Conn, user_id: CurrentUser) -> None:
    removed = await svc.remove_from_shelf(conn, user_id, item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Shelf item not found")
