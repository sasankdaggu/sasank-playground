from __future__ import annotations

from collections.abc import AsyncGenerator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        _pool = AsyncConnectionPool(
            dsn,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        await _pool.open()
    return _pool


async def get_conn() -> AsyncGenerator[psycopg.AsyncConnection, None]:  # type: ignore[misc]
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
