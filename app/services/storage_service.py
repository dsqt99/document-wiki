"""MinIO object storage wrapper (clients are created lazily)."""

import asyncio
import hashlib
import io
import logging
from datetime import timedelta
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self):
        self._client = None
        self._presign_client = None

    @property
    def bucket(self) -> str:
        return settings.minio_bucket

    @property
    def client(self):
        if self._client is None:
            from minio import Minio

            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        return self._client

    @property
    def presign_client(self):
        if self._presign_client is None:
            from minio import Minio

            endpoint = settings.minio_public_endpoint or settings.minio_endpoint
            secure = settings.minio_secure
            for scheme in ("https://", "http://"):
                if endpoint.startswith(scheme):
                    secure = scheme == "https://"
                    endpoint = endpoint[len(scheme):]
            self._presign_client = Minio(
                endpoint.rstrip("/"),
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=secure,
                region="us-east-1",
            )
        return self._presign_client

    def _ensure_bucket_sync(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info("Created MinIO bucket %s", self.bucket)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    def upload_file(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(self.bucket, object_name, io.BytesIO(data), length=len(data), content_type=content_type)
        return object_name

    def download_file(self, object_name: str) -> bytes:
        resp = self.client.get_object(self.bucket, object_name)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def upload_stream(self, object_name: str, stream, length: int, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(self.bucket, object_name, stream, length=length, content_type=content_type)
        return object_name

    async def upload_stream_async(self, object_name: str, stream, length: int, content_type: str = "application/octet-stream") -> str:
        return await asyncio.to_thread(self.upload_stream, object_name, stream, length, content_type)

    def get_presigned_url(self, object_name: str, expiry_hours: Optional[int] = None) -> str:
        hours = expiry_hours if expiry_hours is not None else settings.minio_presign_expiry_hours
        return self.presign_client.presigned_get_object(self.bucket, object_name, expires=timedelta(hours=hours))

    def delete_object(self, object_name: str) -> None:
        self.client.remove_object(self.bucket, object_name)

    def list_objects(self, prefix: str, recursive: bool = True):
        return list(self.client.list_objects(self.bucket, prefix=prefix, recursive=recursive))

    def delete_prefix(self, prefix: str) -> int:
        count = 0
        for obj in self.list_objects(prefix, recursive=True):
            self.client.remove_object(self.bucket, obj.object_name)
            count += 1
        return count

    def copy_object(self, src: str, dest: str) -> None:
        from minio.commonconfig import CopySource

        self.client.copy_object(self.bucket, dest, CopySource(self.bucket, src))

    def copy_prefix(self, src_prefix: str, dest_prefix: str) -> int:
        count = 0
        for obj in self.list_objects(src_prefix, recursive=True):
            rel = obj.object_name[len(src_prefix):]
            self.copy_object(obj.object_name, dest_prefix + rel)
            count += 1
        return count

    def move_prefix(self, src_prefix: str, dest_prefix: str) -> int:
        count = self.copy_prefix(src_prefix, dest_prefix)
        self.delete_prefix(src_prefix)
        return count

    def calculate_prefix_hash(self, prefix: str) -> str:
        pairs = sorted(
            (obj.object_name[len(prefix):], (obj.etag or "").strip('"'))
            for obj in self.list_objects(prefix, recursive=True)
        )
        digest = hashlib.sha256()
        for rel, etag in pairs:
            digest.update(f"{rel}:{etag}\n".encode())
        return digest.hexdigest()


storage_service = StorageService()
