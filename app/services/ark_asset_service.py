"""Volcano Ark private asset-library client."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)


class ArkAssetError(RuntimeError):
    """Stable application error raised for Ark asset API failures."""

    def __init__(self, message: str, *, code: str = "ARK_ASSET_ERROR", status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ArkAssetService:
    ACTIONS = {
        "CreateAssetGroup",
        "ListAssetGroups",
        "UpdateAssetGroup",
        "DeleteAssetGroup",
        "CreateAsset",
        "ListAssets",
        "UpdateAsset",
        "DeleteAsset",
    }

    def is_configured(self, account_id: str | None = None) -> bool:
        try:
            account = config.get_ark_account(account_id)
        except ValueError:
            return False
        return bool(account["ak"] and account["sk"])

    def _validate_action(self, action: str, account_id: str | None = None) -> dict[str, str]:
        if action not in self.ACTIONS:
            raise ArkAssetError("不支持的虚拟资产操作", code="INVALID_ACTION", status_code=400)
        try:
            account = config.get_ark_account(account_id)
        except ValueError as exc:
            raise ArkAssetError(str(exc), code="ARK_ACCOUNT_NOT_FOUND", status_code=400) from exc
        if not account["ak"] or not account["sk"]:
            raise ArkAssetError(
                f"火山引擎账号 {account['id']} 的 AK/SK 未配置",
                code="ARK_ASSET_NOT_CONFIGURED",
                status_code=503,
            )
        return account

    def _send(self, action: str, body: str, account_id: str | None = None) -> dict[str, Any]:
        account = self._validate_action(action, account_id)
        try:
            from volcengine.ApiInfo import ApiInfo
            from volcengine.Credentials import Credentials
            from volcengine.ServiceInfo import ServiceInfo
            from volcengine.base.Service import Service
        except ImportError as exc:
            raise ArkAssetError(
                "火山引擎 SDK 未安装",
                code="ARK_ASSET_SDK_MISSING",
                status_code=503,
            ) from exc
        timeout = max(1, int(config.ARK_ASSET_TIMEOUT_SECONDS))
        service_info = ServiceInfo(
            config.ARK_ASSET_HOST,
            {"Accept": "application/json"},
            Credentials(
                account["ak"],
                account["sk"],
                config.ARK_ASSET_SERVICE,
                config.ARK_ASSET_REGION,
            ),
            timeout,
            timeout,
        )
        api_info = {
            action: ApiInfo(
                "POST",
                "/",
                {"Action": action, "Version": config.ARK_ASSET_VERSION},
                {},
                {},
            )
        }
        client = Service(service_info, api_info)
        raw = client.json(action, {}, body)
        return json.loads(raw) if isinstance(raw, str) else raw

    def call(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        body = {key: value for key, value in (payload or {}).items() if value is not None}
        try:
            body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
            response = self._send(action, body_json, account_id) if account_id else self._send(action, body_json)
        except ArkAssetError:
            raise
        except Exception as exc:
            message = self._safe_error_message(exc)
            logger.warning("Ark asset action %s failed: %s", action, message)
            raise ArkAssetError(message) from exc
        if not isinstance(response, dict):
            raise ArkAssetError("火山方舟返回了无效响应")
        metadata = response.get("ResponseMetadata") or response.get("response_metadata") or {}
        error = metadata.get("Error") or metadata.get("error") or response.get("Error")
        if error:
            code = str(error.get("Code") or error.get("code") or "ARK_ASSET_ERROR")
            message = str(error.get("Message") or error.get("message") or "火山方舟请求失败")
            raise ArkAssetError(message, code=code)
        return response

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        text = str(exc)
        secrets = [config.VOLCENGINE_AK, config.VOLCENGINE_SK]
        for account in config.get_ark_accounts():
            secrets.extend((account.get("ak"), account.get("sk"), account.get("api_key")))
        for secret in secrets:
            if secret:
                text = text.replace(secret, "***")
        try:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start : end + 1])
                metadata = data.get("ResponseMetadata") or {}
                error = metadata.get("Error") or data.get("Error") or {}
                return str(error.get("Message") or error.get("Code") or "火山方舟请求失败")
        except Exception:
            pass
        return text[:500] or "火山方舟请求失败"

    @staticmethod
    def result(response: dict[str, Any]) -> dict[str, Any]:
        value = response.get("Result") or response.get("result") or response.get("Data") or response.get("data")
        return value if isinstance(value, dict) else response

    def create_asset_group(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("CreateAssetGroup", payload, account_id))

    def list_asset_groups(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("ListAssetGroups", payload, account_id))

    def update_asset_group(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("UpdateAssetGroup", payload, account_id))

    def delete_asset_group(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("DeleteAssetGroup", payload, account_id))

    def create_asset(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("CreateAsset", payload, account_id))

    def list_assets(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("ListAssets", payload, account_id))

    def update_asset(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("UpdateAsset", payload, account_id))

    def delete_asset(self, payload: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        return self.result(self.call("DeleteAsset", payload, account_id))


ark_asset_service = ArkAssetService()
