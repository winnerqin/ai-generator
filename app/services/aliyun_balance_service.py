"""Cached Alibaba Cloud account balance lookup."""

from __future__ import annotations

import threading
import time
from typing import Any

from app.config import config


class AliyunBalanceService:
    CACHE_SECONDS = 60

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0

    def is_configured(self) -> bool:
        return bool(
            config.ALIBABA_CLOUD_ACCESS_KEY_ID
            and config.ALIBABA_CLOUD_ACCESS_KEY_SECRET
            and config.ALIBABA_BSS_ENDPOINT
        )

    def query(self, *, force: bool = False) -> dict[str, Any]:
        if not self.is_configured():
            raise ValueError("阿里云账户余额查询尚未配置 AK/SK。")
        now = time.monotonic()
        with self._lock:
            if not force and self._cached and now - self._cached_at < self.CACHE_SECONDS:
                return dict(self._cached)

            try:
                from alibabacloud_bssopenapi20171214.client import (
                    Client as BssOpenApi20171214Client,
                )
                from alibabacloud_tea_openapi import models as open_api_models
                from alibabacloud_tea_util import models as util_models
            except ImportError as exc:
                raise RuntimeError("缺少阿里云 BSS OpenAPI SDK，请安装项目依赖。") from exc

            sdk_config = open_api_models.Config(
                access_key_id=config.ALIBABA_CLOUD_ACCESS_KEY_ID,
                access_key_secret=config.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
            )
            sdk_config.endpoint = config.ALIBABA_BSS_ENDPOINT
            client = BssOpenApi20171214Client(sdk_config)
            response = client.query_account_balance_with_options(util_models.RuntimeOptions())
            body = response.body
            if not getattr(body, "success", False):
                raise ValueError(getattr(body, "message", None) or "阿里云余额查询失败。")
            data = getattr(body, "data", None)
            if data is None:
                raise ValueError("阿里云余额响应缺少 Data。")
            result = {
                "available_amount": str(getattr(data, "available_amount", "0.00") or "0.00"),
                "available_cash_amount": str(
                    getattr(data, "available_cash_amount", "0.00") or "0.00"
                ),
                "currency": str(getattr(data, "currency", "CNY") or "CNY"),
            }
            self._cached = result
            self._cached_at = time.monotonic()
            return dict(result)


aliyun_balance_service = AliyunBalanceService()
