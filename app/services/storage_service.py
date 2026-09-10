"""AWS S3 storage through the ai-video-backend HTTP API."""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, unquote, urlparse

import requests

from app.config import config

logger = logging.getLogger(__name__)


class StorageBackendError(RuntimeError):
    """Raised when ai-video-backend rejects or cannot complete an operation."""


class InvalidStorageReferenceError(StorageBackendError):
    """Raised when an application storage URL is malformed or was tampered with."""


class AIVideoBackendStorageService:
    """Synchronous client for the FileController documented by the backend."""

    MAX_FILE_BYTES = 500 * 1024 * 1024

    def __init__(self) -> None:
        self._preview_cache: dict[int, tuple[float, str]] = {}
        self._cache_lock = threading.Lock()
        self._health_checked_at = 0.0
        self._health_available = False

    def is_available(self) -> bool:
        """Return whether mandatory backend configuration is present and authenticates."""
        if not config.is_ai_video_storage_enabled():
            return False
        now = time.monotonic()
        if now - self._health_checked_at < 30:
            return self._health_available
        try:
            self._request("/user/v1/auth", timeout=(5, 15))
            self._health_available = True
        except Exception as exc:
            self._health_available = False
            logger.warning("[storage][ai-video-backend] health check failed: %s", exc)
        self._health_checked_at = now
        return self._health_available

    @staticmethod
    def _project_id(project_id: Optional[int]) -> int:
        value = (
            config.AI_VIDEO_BACKEND_PROJECT_ID
            or project_id
            or config.AI_VIDEO_BACKEND_DEFAULT_PROJECT_ID
        )
        if not value:
            raise StorageBackendError("当前内容没有项目ID，且未配置默认存储项目")
        return int(value)

    def _request(
        self,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        timeout: Optional[tuple[int, int]] = None,
    ) -> Any:
        base_url = str(config.AI_VIDEO_BACKEND_BASE_URL or "").strip().rstrip("/")
        app_key = str(config.AI_VIDEO_BACKEND_APP_KEY or "").strip()
        if not base_url or not app_key:
            raise StorageBackendError("AI Video Backend 存储地址或 AppKey 未配置")
        try:
            response = requests.post(
                f"{base_url}{path}",
                headers={"appkey": app_key},
                json=json,
                data=data,
                files=files,
                timeout=timeout
                or (
                    int(config.AI_VIDEO_BACKEND_CONNECT_TIMEOUT_SECONDS),
                    int(config.AI_VIDEO_BACKEND_READ_TIMEOUT_SECONDS),
                ),
            )
        except requests.RequestException as exc:
            raise StorageBackendError(f"AI Video Backend 连接失败: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise StorageBackendError(
                f"AI Video Backend 返回非 JSON 响应，HTTP {response.status_code}"
            ) from exc
        if not isinstance(payload, dict):
            raise StorageBackendError("AI Video Backend 返回的 JSON 格式不正确")
        if response.status_code >= 400 or payload.get("success") is not True:
            message = payload.get("message") or f"HTTP {response.status_code}"
            code = payload.get("code") or response.status_code
            raise StorageBackendError(f"AI Video Backend 请求失败 [{code}]: {message}")
        return payload.get("data")

    def _remember_preview(self, file_id: int, preview_url: str) -> None:
        if preview_url:
            with self._cache_lock:
                self._preview_cache[int(file_id)] = (time.monotonic() + 50 * 60, preview_url)

    def _sign(self, file_id: int, project_id: int, filename: str) -> str:
        secret = str(config.AI_VIDEO_BACKEND_PROXY_SECRET or config.SECRET_KEY).encode("utf-8")
        message = f"{file_id}:{project_id}:{filename}".encode("utf-8")
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def build_access_url(self, item: dict[str, Any]) -> str:
        """Build a stable signed application URL for an S3-backed file record."""
        file_id = int(item["id"])
        project_id = int(item["projectId"])
        filename = str(item.get("originalFileName") or f"file-{file_id}")
        preview_url = str(item.get("previewUrl") or "")
        self._remember_preview(file_id, preview_url)
        signature = self._sign(file_id, project_id, filename)
        path = (
            f"/api/storage/files/{file_id}/{project_id}/{signature}/" f"{quote(filename, safe='')}"
        )
        public_base = str(config.AI_VIDEO_BACKEND_PUBLIC_BASE_URL or config.PUBLIC_BASE_URL).rstrip(
            "/"
        )
        return f"{public_base}{path}" if public_base else path

    def parse_access_url(self, reference: str) -> Optional[tuple[int, int, str, str]]:
        path = urlparse(str(reference or "")).path
        marker = "/api/storage/files/"
        if marker not in path:
            return None
        parts = path.split(marker, 1)[1].split("/", 3)
        if len(parts) != 4:
            return None
        try:
            file_id, project_id = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        signature, filename = parts[2], unquote(parts[3])
        if not hmac.compare_digest(signature, self._sign(file_id, project_id, filename)):
            return None
        return file_id, project_id, signature, filename

    def upload_file_record(
        self,
        file_path: str,
        *,
        project_id: Optional[int],
    ) -> dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise StorageBackendError(f"待上传文件不存在: {file_path}")
        size = path.stat().st_size
        if size > self.MAX_FILE_BYTES:
            raise StorageBackendError("文件大小超过 AI Video Backend 的 500MB 限制")
        with path.open("rb") as stream:
            item = self._request(
                "/file/v1/upload",
                data={"projectId": str(self._project_id(project_id))},
                files={"file": (path.name, stream, "application/octet-stream")},
                timeout=(
                    int(config.AI_VIDEO_BACKEND_CONNECT_TIMEOUT_SECONDS),
                    int(config.AI_VIDEO_BACKEND_UPLOAD_TIMEOUT_SECONDS),
                ),
            )
        if not isinstance(item, dict) or not item.get("id") or not item.get("previewUrl"):
            raise StorageBackendError("AI Video Backend 上传响应缺少文件ID或预览地址")
        return item

    def upload_file(
        self,
        file_path: str,
        user_id: Optional[int] = None,
        project_id: Optional[int] = None,
        file_type: str = "image",
        username: Optional[str] = None,
    ) -> Optional[str]:
        del user_id, file_type, username
        try:
            return self.build_access_url(self.upload_file_record(file_path, project_id=project_id))
        except Exception:
            logger.exception(
                "[storage] file upload failed: path=%s project_id=%s", file_path, project_id
            )
            return None

    def upload_bytes(
        self,
        content: bytes,
        filename: str,
        *,
        project_id: Optional[int],
    ) -> str:
        """Upload in-memory request content without writing a persistent local copy."""
        if len(content) > self.MAX_FILE_BYTES:
            raise StorageBackendError("文件大小超过 AI Video Backend 的 500MB 限制")
        safe_name = str(filename or "upload.bin").replace("\\", "/").rsplit("/", 1)[-1]
        item = self._request(
            "/file/v1/upload",
            data={"projectId": str(self._project_id(project_id))},
            files={"file": (safe_name, io.BytesIO(content), "application/octet-stream")},
            timeout=(
                int(config.AI_VIDEO_BACKEND_CONNECT_TIMEOUT_SECONDS),
                int(config.AI_VIDEO_BACKEND_UPLOAD_TIMEOUT_SECONDS),
            ),
        )
        if not isinstance(item, dict) or not item.get("id") or not item.get("previewUrl"):
            raise StorageBackendError("AI Video Backend 上传响应缺少文件ID或预览地址")
        return self.build_access_url(item)

    def upload_from_url_record(
        self,
        source_url: str,
        *,
        filename: str,
        project_id: Optional[int],
    ) -> dict[str, Any]:
        if urlparse(source_url).scheme not in {"http", "https"}:
            raise StorageBackendError("URL 上传仅支持 HTTP 或 HTTPS 地址")
        safe_name = str(filename or "download.bin").replace("\\", "/").rsplit("/", 1)[-1]
        item = self._request(
            "/file/v1/upload/url",
            json={
                "projectId": self._project_id(project_id),
                "fileUrl": source_url,
                "originalFileName": safe_name,
            },
            timeout=(
                int(config.AI_VIDEO_BACKEND_CONNECT_TIMEOUT_SECONDS),
                int(config.AI_VIDEO_BACKEND_UPLOAD_TIMEOUT_SECONDS),
            ),
        )
        if not isinstance(item, dict) or not item.get("id") or not item.get("previewUrl"):
            raise StorageBackendError("AI Video Backend URL上传响应缺少文件ID或预览地址")
        return item

    def import_from_url(
        self,
        source_url: str,
        filename: str,
        user_id: Optional[int],
        project_id: Optional[int],
        **_: Any,
    ) -> tuple[Optional[str], bool]:
        del user_id
        try:
            item = self.upload_from_url_record(source_url, filename=filename, project_id=project_id)
            return self.build_access_url(item), False
        except StorageBackendError as exc:
            message = str(exc).lower()
            expired = "过期" in message or "expired" in message
            logger.error("[storage] URL upload failed: %s", exc)
            return None, expired

    def _page(self, project_id: int, filename: str, page_no: int) -> dict[str, Any]:
        result = self._request(
            "/file/v1/page",
            json={
                "projectId": project_id,
                "originalFileName": filename,
                "status": 1,
                "pageNo": page_no,
                "pageSize": 100,
            },
        )
        return result if isinstance(result, dict) else {}

    def get_fresh_preview_url(self, file_id: int, project_id: int, filename: str) -> str:
        with self._cache_lock:
            cached = self._preview_cache.get(int(file_id))
            if cached and cached[0] > time.monotonic():
                return cached[1]
        page_no = 1
        while page_no <= 100:
            page = self._page(project_id, filename, page_no)
            for item in page.get("items") or []:
                if int(item.get("id") or 0) == int(file_id):
                    preview_url = str(item.get("previewUrl") or "")
                    if not preview_url:
                        raise StorageBackendError("文件记录没有可用的预览地址")
                    self._remember_preview(file_id, preview_url)
                    return preview_url
            page_param = page.get("pageParam") or {}
            next_page = int(page_param.get("nextPage") or 0)
            if not next_page:
                break
            page_no = next_page
        raise StorageBackendError("未找到对应的 AWS S3 文件记录")

    def resolve_access_url(self, reference: str) -> str:
        parsed = self.parse_access_url(reference)
        if not parsed:
            raise InvalidStorageReferenceError("无效的存储文件地址或签名")
        file_id, project_id, _, filename = parsed
        return self.get_fresh_preview_url(file_id, project_id, filename)

    def resolve_download_url(self, reference: str) -> str:
        """Return a fresh S3 URL for managed references and pass other URLs through."""
        return self.resolve_access_url(reference) if self.is_managed_url(reference) else reference

    def delete_file(self, reference: str, **_: Any) -> bool:
        parsed = self.parse_access_url(reference)
        if not parsed:
            return False
        file_id = parsed[0]
        try:
            self._request("/file/v1/update", json={"id": file_id, "status": 0})
            with self._cache_lock:
                self._preview_cache.pop(file_id, None)
            return True
        except Exception:
            logger.exception("[storage] failed to disable backend file: id=%s", file_id)
            return False

    def is_managed_url(self, reference: str) -> bool:
        return self.parse_access_url(reference) is not None

    def list_sample_images(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        # Person/scene category is application metadata and is read from local DB.
        return []


storage_service = AIVideoBackendStorageService()
