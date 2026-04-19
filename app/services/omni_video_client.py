"""HTTP client for the Seedance 2.0 omni video APIs."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.config import config

logger = logging.getLogger(__name__)

# 国际版模型标识
INTL_MODEL_PREFIX = "dreamina-"


def is_intl_model(model: str) -> bool:
    """判断是否是国际版模型"""
    return model.startswith(INTL_MODEL_PREFIX) if model else False


class OmniVideoClient:
    """Thin wrapper around the remote Seedance omni video endpoints."""

    def __init__(self) -> None:
        # 国内版配置
        self.base_url = config.ARK_BASE_URL.rstrip("/")
        self.api_key = config.ARK_API_KEY
        self.model = config.SEEDANCE_OMNI_MODEL
        self.create_path = config.SEEDANCE_OMNI_CREATE_PATH
        self.query_path = config.SEEDANCE_OMNI_QUERY_PATH
        self.list_path = config.SEEDANCE_OMNI_LIST_PATH
        self.cancel_path = config.SEEDANCE_OMNI_CANCEL_PATH

        # 国际版配置
        self.intl_base_url = config.ARK_INTL_BASE_URL.rstrip("/")
        self.intl_api_key = config.ARK_INTL_API_KEY
        self.intl_model = config.SEEDANCE_INTL_MODEL

    def is_configured(self, model: str | None = None) -> bool:
        """检查是否配置了对应版本的API"""
        if model and is_intl_model(model):
            return config.is_seedance_intl_configured()
        return config.is_seedance_omni_configured()

    def _get_config_for_model(self, model: str | None = None) -> tuple[str, str]:
        """根据模型返回对应的base_url和api_key"""
        if model and is_intl_model(model):
            return self.intl_base_url, self.intl_api_key
        return self.base_url, self.api_key

    def _headers(self, model: str | None = None) -> dict[str, str]:
        """根据模型返回对应的headers"""
        _, api_key = self._get_config_for_model(model)
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str, model: str | None = None, **kwargs: Any) -> str:
        """根据模型返回对应的URL"""
        base_url, _ = self._get_config_for_model(model)
        rendered = path.format(**kwargs)
        return f"{base_url}{rendered}"

    def _sanitize_headers(self, headers: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in headers.items():
            sanitized[key] = "***" if key.lower() == "authorization" else value
        return sanitized

    def _format_payload(self, payload: Any) -> str:
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
        logger.info(
            "[omni-video][%s][request] method=%s url=%s headers=%s params=%s payload=%s timeout=%s",
            action,
            method,
            url,
            self._sanitize_headers(headers),
            self._format_payload(params or {}),
            self._format_payload(payload),
            timeout,
        )

    def _log_response(self, action: str, response: requests.Response) -> None:
        logger.info(
            "[omni-video][%s][response] status=%s headers=%s body=%s",
            action,
            response.status_code,
            dict(response.headers),
            response.text,
        )

    def _raise_timeout(self, action: str, exc: requests.Timeout, **context: Any) -> None:
        logger.error(
            "[omni-video][%s][timeout] context=%s",
            action,
            json.dumps(context, ensure_ascii=False),
        )
        raise ValueError(f"Seedance {action} 请求超时，请稍后重试。") from exc

    def _raise_request_error(self, action: str, exc: requests.RequestException, **context: Any) -> None:
        logger.exception(
            "[omni-video][%s][request-error] context=%s error=%s",
            action,
            json.dumps(context, ensure_ascii=False, default=str),
            str(exc),
        )
        raise ValueError(f"Seedance {action} 请求失败，请稍后重试。") from exc

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = payload.get("model")
        url = self._url(self.create_path, model=model)
        headers = self._headers(model=model)
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
            self._raise_timeout("create_task", exc, payload=payload)
        except requests.RequestException as exc:
            self._raise_request_error("create_task", exc, payload=payload, url=url)
        self._log_response("create_task", response)
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

    def get_task(self, task_id: str, model: str | None = None) -> dict[str, Any]:
        url = self._url(self.query_path, model=model, task_id=task_id)
        headers = self._headers(model=model)
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
                "[omni-video][remote-detail][error] status=%s body=%s task_id=%s",
                response.status_code,
                body,
                task_id,
            )
            raise ValueError(
                f"Seedance get_task failed: HTTP {response.status_code}; body={body}"
            ) from exc
        return response.json()

    def list_tasks(self, page: int = 1, page_size: int = 20, model: str | None = None) -> dict[str, Any]:
        url = self._url(self.list_path, model=model)
        headers = self._headers(model=model)
        params = {"page": page, "page_size": page_size}
        timeout = (10, 60)
        self._log_request(
            "list_tasks",
            method="GET",
            url=url,
            headers=headers,
            params=params,
            timeout=timeout,
        )
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            self._raise_timeout("list_tasks", exc, page=page, page_size=page_size)
        except requests.RequestException as exc:
            self._raise_request_error(
                "list_tasks",
                exc,
                page=page,
                page_size=page_size,
                url=url,
                params=params,
            )
        self._log_response("list_tasks", response)
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

    def cancel_task(self, task_id: str, model: str | None = None) -> dict[str, Any]:
        url = self._url(self.cancel_path, model=model, task_id=task_id)
        headers = self._headers(model=model)
        payload = {"action": "cancel"}
        timeout = (10, 60)
        self._log_request(
            "cancel_task",
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
            self._raise_timeout("cancel_task", exc, task_id=task_id)
        except requests.RequestException as exc:
            self._raise_request_error("cancel_task", exc, task_id=task_id, payload=payload, url=url)
        self._log_response("cancel_task", response)
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
