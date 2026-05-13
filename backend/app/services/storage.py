from __future__ import annotations

import hashlib
import io
from collections import deque
from urllib.parse import urlparse

import boto3
import httpx
import numpy as np
import structlog
from PIL import Image

from app.config import settings

log = structlog.get_logger()

BRAND_BG_COLOR = (253, 248, 245)  # warm cream #FDF8F5
THUMB_SIZE = (800, 800)
SHELF_SIZE = (800, 800)
BG_THRESHOLD = 35  # color distance tolerance for background detection

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
    return _s3


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _r2_upload(key: str, data: bytes, content_type: str) -> str:
    _client().put_object(
        Bucket=settings.r2_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"{settings.r2_public_url}/{key}"


async def _fetch_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def _remove_background_local(image_bytes: bytes) -> bytes:
    """
    Flood-fill background removal from image edges.
    Works well for e-commerce product photos on white/light backgrounds.
    Returns PNG bytes with transparency.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    data = np.array(img, dtype=np.int32)
    h, w = data.shape[:2]

    # Sample background color from image edges (top row, bottom row, sides)
    edge_pixels = np.concatenate([
        data[0, :, :3],
        data[-1, :, :3],
        data[:, 0, :3],
        data[:, -1, :3],
    ])
    # Use median to be robust against product touching edges
    bg_color = np.median(edge_pixels, axis=0)

    # BFS flood fill from all 4 corners to identify background
    visited = np.zeros((h, w), dtype=bool)
    queue = deque()

    # Seed from corners
    for y, x in [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]:
        if not visited[y, x]:
            dist = np.sqrt(np.sum((data[y, x, :3] - bg_color) ** 2))
            if dist < BG_THRESHOLD * 2:
                queue.append((y, x))
                visited[y, x] = True

    # Also seed from edges where pixel is close to bg color
    for x in range(w):
        for y in [0, h - 1]:
            if not visited[y, x]:
                dist = np.sqrt(np.sum((data[y, x, :3] - bg_color) ** 2))
                if dist < BG_THRESHOLD:
                    queue.append((y, x))
                    visited[y, x] = True
    for y in range(h):
        for x in [0, w - 1]:
            if not visited[y, x]:
                dist = np.sqrt(np.sum((data[y, x, :3] - bg_color) ** 2))
                if dist < BG_THRESHOLD:
                    queue.append((y, x))
                    visited[y, x] = True

    while queue:
        y, x = queue.popleft()
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                dist = np.sqrt(np.sum((data[ny, nx, :3] - bg_color) ** 2))
                if dist < BG_THRESHOLD:
                    visited[ny, nx] = True
                    queue.append((ny, nx))

    # Set background pixels to transparent
    result = data.copy()
    result[visited, 3] = 0

    # Soften edges: semi-transparent border pixels
    from scipy.ndimage import binary_dilation
    dilated = binary_dilation(visited, iterations=2)
    border = dilated & ~visited
    result[border, 3] = 128

    out_img = Image.fromarray(result.astype(np.uint8), "RGBA")
    buf = io.BytesIO()
    out_img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _make_shelf_png(transparent_png: bytes) -> bytes:
    img = Image.open(io.BytesIO(transparent_png)).convert("RGBA")
    img.thumbnail(SHELF_SIZE, Image.LANCZOS)
    canvas = Image.new("RGBA", SHELF_SIZE, (0, 0, 0, 0))
    offset = ((SHELF_SIZE[0] - img.width) // 2, (SHELF_SIZE[1] - img.height) // 2)
    canvas.paste(img, offset, img)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _make_thumb_jpg(transparent_png: bytes) -> bytes:
    img = Image.open(io.BytesIO(transparent_png)).convert("RGBA")
    img.thumbnail(THUMB_SIZE, Image.LANCZOS)
    bg = Image.new("RGBA", THUMB_SIZE, (*BRAND_BG_COLOR, 255))
    offset = ((THUMB_SIZE[0] - img.width) // 2, (THUMB_SIZE[1] - img.height) // 2)
    bg.paste(img, offset, img)
    buf = io.BytesIO()
    bg.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


async def process_and_upload(source_url: str) -> dict[str, str]:
    """
    Download image, remove background, upload 3 variants to R2.
    Returns dict: original, shelf (transparent PNG), thumb (brand bg JPEG).
    """
    if not settings.r2_account_id:
        return {"original": source_url, "shelf": source_url, "thumb": source_url}

    h = _hash(source_url)
    original_key = f"products/{h}_original.jpg"
    shelf_key = f"products/{h}_shelf.png"
    thumb_key = f"products/{h}_thumb.jpg"

    try:
        image_bytes = await _fetch_bytes(source_url)
    except Exception as e:
        log.warning("fetch_failed", url=source_url, error=str(e))
        return {"original": source_url, "shelf": source_url, "thumb": source_url}

    original_url = _r2_upload(original_key, image_bytes, "image/jpeg")

    try:
        transparent_bytes = _remove_background_local(image_bytes)
        shelf_url = _r2_upload(shelf_key, _make_shelf_png(transparent_bytes), "image/png")
        thumb_url = _r2_upload(thumb_key, _make_thumb_jpg(transparent_bytes), "image/jpeg")
        log.info("image_processed", hash=h)
    except Exception as e:
        log.warning("bg_removal_failed", url=source_url, error=str(e))
        shelf_url = original_url
        thumb_url = original_url

    return {"original": original_url, "shelf": shelf_url, "thumb": thumb_url}


async def upload_images(urls: list[str]) -> list[str]:
    results = []
    for url in urls:
        try:
            r = await process_and_upload(url)
            results.append(r["original"])
        except Exception as e:
            log.warning("upload_failed", url=url, error=str(e))
            results.append(url)
    return results
