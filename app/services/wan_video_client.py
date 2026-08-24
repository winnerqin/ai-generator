"""HTTP adapter for Alibaba Cloud Model Studio Wan video tasks."""

from __future__ import annotations

import hashlib
from typing import Any

import requests

from app.config import config


class WanVideoClient:
    def _pool(self, region: str = "cn") -> list[str]:
        if region == "intl":
            raw = config.DASHSCOPE_INTL_API_KEY_POOL or config.DASHSCOPE_INTL_API_KEY
        else:
            raw = config.DASHSCOPE_API_KEY_POOL or config.DASHSCOPE_API_KEY
        return [item.strip() for item in raw.split(",") if item.strip()]

    def select_slot(self, route_key: str | None = None, slot: int | None = None,
                    region: str = "cn") -> int:
        pool = self._pool(region)
        if not pool:
            return 0
        if slot is not None:
            return int(slot) % len(pool)
        if route_key:
            digest = hashlib.sha256(route_key.encode("utf-8")).hexdigest()
            return int(digest[:8], 16) % len(pool)
        return 0

    def is_configured(self, region: str = "cn") -> bool:
        base_url = config.WAN_INTL_BASE_URL if region == "intl" else config.WAN_BASE_URL
        return bool(self._pool(region) and base_url and config.WAN_VIDEO_UPSTREAM_MODEL)

    def _headers(self, slot: int, *, region: str = "cn",
                 asynchronous: bool = False) -> dict[str, str]:
        pool = self._pool(region)
        key = pool[slot % len(pool)] if pool else ""
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if asynchronous:
            headers["X-DashScope-Async"] = "enable"
        return headers

    @staticmethod
    def _url(path: str, region: str) -> str:
        base_url = config.WAN_INTL_BASE_URL if region == "intl" else config.WAN_BASE_URL
        normalized_path = path
        if region == "intl" and base_url.rstrip("/").endswith("/api/v1"):
            normalized_path = path.removeprefix("/api/v1")
        return f"{base_url.rstrip('/')}/{normalized_path.lstrip('/')}"

    @staticmethod
    def _body(response: requests.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ValueError("Wan 上游返回了无法解析的响应。") from exc
        if not response.ok:
            message = body.get("message") or body.get("code") or response.text
            raise ValueError(f"Wan 上游请求失败：{message}")
        return body

    def create_task(self, payload: dict[str, Any], *, route_key: str,
                    region: str = "cn") -> tuple[dict[str, Any], int]:
        slot = self.select_slot(route_key, region=region)
        response = requests.post(
            self._url(config.WAN_VIDEO_CREATE_PATH, region),
            headers=self._headers(slot, region=region, asynchronous=True),
            json=payload, timeout=(10, 60),
        )
        return self._body(response), slot

    def get_task(self, task_id: str, *, slot: int = 0, region: str = "cn") -> dict[str, Any]:
        response = requests.get(
            self._url(config.WAN_VIDEO_QUERY_PATH.format(task_id=task_id), region),
            headers=self._headers(slot, region=region), timeout=(10, 30),
        )
        return self._body(response)

    def cancel_task(self, task_id: str, *, slot: int = 0,
                    region: str = "cn") -> dict[str, Any]:
        response = requests.post(
            self._url(config.WAN_VIDEO_CANCEL_PATH.format(task_id=task_id), region),
            headers=self._headers(slot, region=region), timeout=(10, 30),
        )
        return self._body(response)


wan_video_client = WanVideoClient()
