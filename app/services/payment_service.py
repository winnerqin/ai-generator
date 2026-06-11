from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import requests

from app.config import config


class PaymentService:
    def is_configured(self) -> bool:
        return config.is_payment_center_configured()

    def get_recharge_options(self) -> dict[str, Any]:
        return {
            "enabled": self.is_configured(),
            "preset_amounts_cent": config.get_payment_center_allowed_amounts_cent(),
            "min_amount_cent": config.PAYMENT_CENTER_MIN_RECHARGE_CENT,
            "max_amount_cent": config.PAYMENT_CENTER_MAX_RECHARGE_CENT,
            "currency_code": "CNY",
            "payment_channel": "wechat_native",
        }

    def normalize_amount_cent(self, amount_yuan: Any = None, amount_cent: Any = None) -> int:
        if amount_cent not in (None, ""):
            try:
                normalized = int(amount_cent)
            except (TypeError, ValueError) as exc:
                raise ValueError("充值金额格式不正确") from exc
        else:
            try:
                normalized = int(
                    (Decimal(str(amount_yuan or 0)) * Decimal("100")).quantize(Decimal("1"))
                )
            except Exception as exc:
                raise ValueError("充值金额格式不正确") from exc
        if normalized < config.PAYMENT_CENTER_MIN_RECHARGE_CENT:
            raise ValueError(
                f"充值金额不能低于 {config.PAYMENT_CENTER_MIN_RECHARGE_CENT / 100:.0f} 元"
            )
        if normalized > config.PAYMENT_CENTER_MAX_RECHARGE_CENT:
            raise ValueError(
                f"充值金额不能高于 {config.PAYMENT_CENTER_MAX_RECHARGE_CENT / 100:.0f} 元"
            )
        return normalized

    @staticmethod
    def _canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def sign_payload(self, payload: dict[str, Any], timestamp: str, nonce: str) -> str:
        message = f"{timestamp}\n{nonce}\n{self._canonical_json(payload)}"
        return hmac.new(
            config.PAYMENT_CENTER_SIGN_SECRET.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(
        self, payload: dict[str, Any], timestamp: str, nonce: str, signature: str
    ) -> bool:
        expected = self.sign_payload(payload, timestamp, nonce)
        return hmac.compare_digest(expected, str(signature or "").strip())

    def build_callback_url(self, request_origin: str | None = None) -> str:
        base = (config.PUBLIC_BASE_URL or request_origin or "").rstrip("/")
        if not base:
            raise ValueError("未配置 PUBLIC_BASE_URL，无法生成支付回调地址")
        return f"{base}{config.PAYMENT_CENTER_NOTIFY_PATH}"

    def create_recharge_order(
        self,
        *,
        order_no: str,
        user_id: int,
        username: str,
        amount_cent: int,
        callback_url: str,
        return_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise ValueError("支付中心未配置")

        payload = {
            "merchant_id": config.PAYMENT_CENTER_MERCHANT_ID,
            "app_id": config.PAYMENT_CENTER_APP_ID,
            "merchant_order_no": order_no,
            "user_id": user_id,
            "username": username,
            "amount_cent": amount_cent,
            "currency": "CNY",
            "product_name": "账户充值",
            "product_desc": "AI创作工具余额充值",
            "pay_channel": "wechat_native",
            "client_type": "web",
            "callback_url": callback_url,
            "return_url": return_url or "",
            "attach": metadata or {},
            "expire_minutes": 15,
        }
        timestamp = str(int(datetime.now().timestamp()))
        nonce = secrets.token_hex(8)
        signature = self.sign_payload(payload, timestamp, nonce)
        headers = {
            "Content-Type": "application/json",
            "X-Merchant-Id": config.PAYMENT_CENTER_MERCHANT_ID,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
        }
        response = requests.post(
            f"{config.PAYMENT_CENTER_BASE_URL.rstrip('/')}{config.PAYMENT_CENTER_CREATE_ORDER_PATH}",
            headers=headers,
            json=payload,
            timeout=(10, config.PAYMENT_CENTER_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success", True):
            raise ValueError(data.get("error") or data.get("message") or "支付中心创建订单失败")
        return {
            "request_payload": payload,
            "response_payload": data,
            "payment_center_order_no": data.get("payment_center_order_no")
            or data.get("order_no")
            or "",
            "pay_status": data.get("pay_status") or data.get("status") or "pending",
            "qr_code_url": data.get("qr_code_url") or "",
            "qr_code_img_url": data.get("qr_code_img_url") or "",
            "expire_at": data.get("expire_at")
            or (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
        }


payment_service = PaymentService()
