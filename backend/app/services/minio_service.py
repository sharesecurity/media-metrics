"""
MinIO object storage service for article text.
Stores large article bodies in MinIO to keep Postgres lean.
Falls back gracefully if MinIO is unavailable.
"""

import asyncio
import io
from typing import Optional
from minio import Minio
from minio.error import S3Error
from app.core.config import settings

_client: Optional[Minio] = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            f"{settings.minio_host}:{settings.minio_port}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _client


async def ensure_bucket() -> bool:
    """Create the articles bucket if it doesn't exist. Returns True on success."""
    try:
        client = _get_client()
        exists = await asyncio.to_thread(client.bucket_exists, settings.minio_bucket)
        if not exists:
            await asyncio.to_thread(client.make_bucket, settings.minio_bucket)
            print(f"[MinIO] Created bucket: {settings.minio_bucket}")
        return True
    except Exception as e:
        print(f"[MinIO] ensure_bucket failed: {e}")
        return False


async def store_article_text(article_id: str, text: str) -> Optional[str]:
    """
    Upload article text to MinIO. Returns the object key on success, None on failure.
    Key format: articles/{article_id}.txt
    """
    try:
        client = _get_client()
        key = f"articles/{article_id}.txt"
        data = text.encode("utf-8")
        stream = io.BytesIO(data)

        await asyncio.to_thread(
            client.put_object,
            settings.minio_bucket,
            key,
            stream,
            len(data),
            content_type="text/plain; charset=utf-8",
        )
        print(f"[MinIO] ✓ Stored article text: {key} ({len(data)} bytes)")
        return key
    except Exception as e:
        print(f"[MinIO] store_article_text failed for {article_id}: {e}")
        return None


async def get_article_text(key: str) -> Optional[str]:
    """Retrieve article text from MinIO by object key. Returns None on failure."""
    try:
        client = _get_client()
        response = await asyncio.to_thread(client.get_object, settings.minio_bucket, key)
        data = await asyncio.to_thread(response.read)
        await asyncio.to_thread(response.close)
        await asyncio.to_thread(response.release_conn)
        return data.decode("utf-8")
    except S3Error as e:
        if e.code == "NoSuchKey":
            print(f"[MinIO] Key not found: {key}")
        else:
            print(f"[MinIO] get_article_text S3Error: {e}")
        return None
    except Exception as e:
        print(f"[MinIO] get_article_text failed for {key}: {e}")
        return None


async def delete_article_text(key: str) -> bool:
    """Delete an article text object from MinIO."""
    try:
        client = _get_client()
        await asyncio.to_thread(client.remove_object, settings.minio_bucket, key)
        return True
    except Exception as e:
        print(f"[MinIO] delete failed for {key}: {e}")
        return False


async def migrate_article_to_minio(article_id: str, text: str) -> Optional[str]:
    """
    Store text in MinIO and return the key.
    Used for batch migration of existing Postgres raw_text to MinIO.
    """
    await ensure_bucket()
    return await store_article_text(article_id, text)


async def get_text_for_article(article) -> str:
    """
    Get the full text for an article, checking MinIO first then falling back to raw_text.
    Pass any Article ORM object.
    """
    if article.minio_key:
        text = await get_article_text(article.minio_key)
        if text:
            return text
    return article.raw_text or ""
