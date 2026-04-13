"""HTTP client for the video enhance APIs."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.config import config

logger = logging.getLogger(__name__)

SUPPORTED_ENHANCE_RESOLUTIONS = {"720p", "1080p", "2k", "4k"}


class VideoEnhanceClient:
    """Thin wrapper around the video enhance endpoints."""

    def __init__(self) -> None:
        self.base_url = config.VIDEO_ENHANCE_BASE_URL.rstrip("/")
        self.api_key = config.VIDEO_ENHANCE_API_KEY
        self.create_path = config.VIDEO_ENHANCE_CREATE_PATH
        self.query_path = config.VIDEO_ENHANCE_QUERY_PATH

    def is_configured(self) -> bool:
        """检查是否配置了画质增强API。"""
        return config.is_video_enhance_configured()

    def _headers(self) -> dict[str, str]:
        """构建请求头。"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str, **kwargs: Any) -> str:
        """构建完整URL。"""
        rendered = path.format(**kwargs)
        return f"{self.base_url}{rendered}"

    def _sanitize_headers(self, headers: dict[str, Any]) -> dict[str, Any]:
        """隐藏敏感头信息用于日志。"""
        sanitized: dict[str, Any] = {}
        for key, value in headers.items():
            sanitized[key] = "***" if key.lower() == "authorization" else value
        return sanitized

    def _format_payload(self, payload: Any) -> str:
        """格式化payload用于日志。"""
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return str(payload)

    def _log_request(
        self,
        action: str,
        *,
        method: str,
        url: str,
        headers: dict[str, Any],
        payload: Any = None,
        params: dict[str, Any] | None = None,
        timeout: Any = None,
    ) -> None:
        """记录请求日志。"""
        logger.info(
            "[video-enhance][%s][request] method=%s url=%s headers=%s params=%s payload=%s timeout=%s",
            action,
            method,
            url,
            self._sanitize_headers(headers),
            self._format_payload(params or {}),
            self._format_payload(payload),
            timeout,
        )

    def _log_response(self, action: str, response: requests.Response) -> None:
        """记录响应日志。"""
        logger.info(
            "[video-enhance][%s][response] status=%s headers=%s body=%s",
            action,
            response.status_code,
            dict(response.headers),
            response.text,
        )

    def _raise_timeout(self, action: str, exc: requests.Timeout, **context: Any) -> None:
        """处理超时异常。"""
        logger.error(
            "[video-enhance][%s][timeout] context=%s",
            action,
            json.dumps(context, ensure_ascii=False),
        )
        raise ValueError(f"画质增强 {action} 请求超时，请稍后重试。") from exc

    def _raise_request_error(self, action: str, exc: requests.RequestException, **context: Any) -> None:
        """处理请求异常。"""
        logger.exception(
            "[video-enhance][%s][request-error] context=%s error=%s",
            action,
            json.dumps(context, ensure_ascii=False, default=str),
            str(exc),
        )
        raise ValueError(f"画质增强 {action} 请求失败，请稍后重试。") from exc

    def create_task(self, video_url: str, resolution: str) -> dict[str, Any]:
        """
        提交画质增强任务。

        Args:
            video_url: 原视频URL
            resolution: 目标分辨率 (720p, 1080p, 2k, 4k)

        Returns:
            API响应数据，包含task_id
        """
        if resolution not in SUPPORTED_ENHANCE_RESOLUTIONS:
            raise ValueError(f"不支持的目标分辨率: {resolution}，仅支持 720p, 1080p, 2k, 4k")

        url = self._url(self.create_path)
        headers = self._headers()
        payload = {
            "video_url": video_url,
            "resolution": resolution,
        }
        timeout = (15, 180)

        self._log_request(
            "create_task",
            method="POST",
            url=url,
            headers=headers,
            payload=payload,
            timeout=timeout,
        )

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            self._raise_timeout("create_task", exc, video_url=video_url, resolution=resolution)
        except requests.RequestException as exc:
            self._raise_request_error("create_task", exc, video_url=video_url, resolution=resolution, url=url)

        self._log_response("create_task", response)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text
            logger.error(
                "[video-enhance][create][error] status=%s body=%s video_url=%s resolution=%s",
                response.status_code,
                body,
                video_url,
                resolution,
            )
            raise ValueError(
                f"画质增强任务创建失败: HTTP {response.status_code}; body={body}"
            ) from exc

        return response.json()

    def get_task(self, task_id: str) -> dict[str, Any]:
        """
        查询画质增强任务状态。

        Args:
            task_id: 任务ID

        Returns:
            API响应数据，包含任务状态和结果
        """
        url = self._url(self.query_path, task_id=task_id)
        headers = self._headers()
        timeout = (10, 60)

        self._log_request(
            "get_task",
            method="GET",
            url=url,
            headers=headers,
            params={"task_id": task_id},
            timeout=timeout,
        )

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            self._raise_timeout("get_task", exc, task_id=task_id)
        except requests.RequestException as exc:
            self._raise_request_error("get_task", exc, task_id=task_id, url=url)

        self._log_response("get_task", response)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text
            logger.error(
                "[video-enhance][get][error] status=%s body=%s task_id=%s",
                response.status_code,
                body,
                task_id,
            )
            raise ValueError(
                f"画质增强任务查询失败: HTTP {response.status_code}; body={body}"
            ) from exc

        return response.json()


video_enhance_client = VideoEnhanceClient()