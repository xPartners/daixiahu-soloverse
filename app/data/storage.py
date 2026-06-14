"""MinIO 文件存储封装。"""
from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO
from typing import Optional

from minio import Minio

from app.config import settings
from app.core.exceptions import YbA2AError

logger = logging.getLogger(__name__)


class FileStorage:
    """MinIO 文件存储客户端（连接容错）。"""

    def __init__(self) -> None:
        self.client: Optional[Minio] = None
        try:
            self.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            # 确保 bucket 存在
            if not self.client.bucket_exists(settings.MINIO_BUCKET):
                self.client.make_bucket(settings.MINIO_BUCKET)
        except Exception as exc:  # noqa: BLE001
            logger.warning("无法连接 MinIO: %s", exc)
            self.client = None

    def upload(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """上传文件，返回可访问 URL。"""
        if self.client is None:
            raise YbA2AError("MinIO 未连接，无法上传文件")
        try:
            self.client.put_object(
                settings.MINIO_BUCKET,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return self.get_url(object_name)
        except Exception as exc:  # noqa: BLE001
            raise YbA2AError(f"文件上传失败: {exc}") from exc

    def download(self, object_name: str) -> bytes:
        """下载文件，返回字节内容。"""
        if self.client is None:
            raise YbA2AError("MinIO 未连接，无法下载文件")
        try:
            response = self.client.get_object(settings.MINIO_BUCKET, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:  # noqa: BLE001
            raise YbA2AError(f"文件下载失败: {exc}") from exc

    def get_url(self, object_name: str) -> str:
        """生成文件可访问的预签名 URL。"""
        if self.client is None:
            raise YbA2AError("MinIO 未连接，无法生成 URL")
        return self.client.presigned_get_object(
            settings.MINIO_BUCKET, object_name, expires=timedelta(days=7)
        )
