"""
Cloudflare R2 file storage (S3-compatible), used for profile pictures.

Files are uploaded by the backend and served from the bucket's public URL
(R2_PUBLIC_URL: a custom domain connected to the bucket, or its r2.dev URL
while developing).
"""

import aioboto3

from src.core.config import settings


class StorageError(Exception):
    """R2 is not configured or the request failed."""


class R2Storage:
    @property
    def configured(self) -> bool:
        return all(
            (
                settings.R2_ACCOUNT_ID,
                settings.R2_ACCESS_KEY_ID,
                settings.R2_SECRET_ACCESS_KEY,
                settings.R2_BUCKET,
                settings.R2_PUBLIC_URL,
            )
        )

    def _client(self):
        if not self.configured:
            raise StorageError("File storage is not configured")
        return aioboto3.Session().client(
            "s3",
            endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        )

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=settings.R2_BUCKET,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                    # Every upload gets a new key, so it can be cached forever.
                    CacheControl="public, max-age=31536000, immutable",
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Upload failed") from exc

    async def delete(self, key: str) -> None:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=settings.R2_BUCKET, Key=key)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("Delete failed") from exc


def public_url(key: str | None) -> str | None:
    """Where a stored file can be viewed."""
    if not key or not settings.R2_PUBLIC_URL:
        return None
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"
