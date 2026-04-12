"""HTTP client for the Seedance 2.0 omni video APIs."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.config import config

logger = logging.getLogger(__name__)


class OmniVideoClient:
    """Thin wrapper around the remote Seedance omni video endpoints."""

    def __init__(self) -> None:
        self.base_url = config.ARK_BASE_URL.rstrip("/")
        self.api_key = config.ARK_API_KEY
        self.model = config.SEEDANCE_OMNI_MODEL
        self.create_path = config.SEEDANCE_OMNI_CREATE_PATH
        self.query_path = config.SEEDANCE_OMNI_QUERY_PATH
        self.list_path = config.SEEDANCE_OMNI_LIST_PATH
        self.cancel_path = config.SEEDANCE_OMNI_CANCEL_PATH

    def is_configured(self) -> bool:
        return config.is_seedance_omni_configured()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str, **kwargs: Any) -> str:
        rendered = path.format(**kwargs)
        return f"{self.base_url}{rendered}"

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            self._url(self.create_path),
            headers=self._headers(),
            json=payload,
            timeout=60,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text
            logger.error(
                "[omni-video][remote-create][error] status=%s body=%s payload=%s",
                response.status_code,
                body,
                json.dumps(payload, ensure_ascii=False),
            )
            raise ValueError(
                f"Seedance create_task failed: HTTP {response.status_code}; body={body}"
            ) from exc
        return response.json()

    def get_task(self, task_id: str) -> dict[str, Any]:
        response = requests.get(
            self._url(self.query_path, task_id=task_id),
            headers=self._headers(),
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text
            logger.error(
                "[omni-video][remote-detail][error] status=%s body=%s task_id=%s",
                response.status_code,
                body,
                task_id,
            )
            raise ValueError(
                f"Seedance get_task failed: HTTP {response.status_code}; body={body}"
            ) from exc
        return response.json()

    def list_tasks(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        response = requests.get(
            self._url(self.list_path),
            headers=self._headers(),
            params={"page": page, "page_size": page_size},
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text
            logger.error(
                "[omni-video][remote-list][error] status=%s body=%s page=%s page_size=%s",
                response.status_code,
                body,
                page,
                page_size,
            )
            raise ValueError(
                f"Seedance list_tasks failed: HTTP {response.status_code}; body={body}"
            ) from exc
        return response.json()

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        response = requests.post(
            self._url(self.cancel_path, task_id=task_id),
            headers=self._headers(),
            json={"action": "cancel"},
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text
            logger.error(
                "[omni-video][remote-cancel][error] status=%s body=%s task_id=%s",
                response.status_code,
                body,
                task_id,
            )
            raise ValueError(
                f"Seedance cancel_task failed: HTTP {response.status_code}; body={body}"
            ) from exc
        return response.json()


omni_video_client = OmniVideoClient()
