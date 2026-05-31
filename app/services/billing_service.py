from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import database
from app.config import config

BIZ_OMNI_VIDEO = "omni_video"


def _to_cent(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _effective_multiplier(user: dict) -> Decimal:
    role_code = user.get("role_code") or database.ROLE_EXTERNAL_USER
    role_multiplier = Decimal(str(database.get_role_pricing_multiplier(role_code) or 1))
    user_multiplier = Decimal(str(user.get("pricing_multiplier") or 1))
    return role_multiplier if role_multiplier > 0 else user_multiplier


def _price_per_million_cny_cent(pricing: dict) -> Decimal:
    price = Decimal(str(pricing.get("price_per_million_token_cent") or 0))
    currency_code = str(pricing.get("currency_code") or database.MODEL_CURRENCY_CNY).upper()
    if currency_code == database.MODEL_CURRENCY_USD:
        return price * Decimal(str(database.USD_TO_CNY_RATE))
    return price


def _has_video_reference(task: dict) -> bool:
    urls = task.get("reference_urls_json") or []
    if isinstance(urls, str):
        try:
            import json

            urls = json.loads(urls)
        except Exception:
            urls = []
    if not isinstance(urls, list):
        return False
    video_exts = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
    for url in urls:
        try:
            suffix = Path(str(url)).suffix.lower()
        except Exception:
            suffix = ""
        if suffix in video_exts:
            return True
    return False


def _pricing_model_candidates(model_code_or_alias: str | None) -> list[str]:
    value = (model_code_or_alias or "").strip()
    if not value:
        return []
    alias_map = config.get_omni_model_alias_map()
    reverse_map = {
        str(alias).strip(): code for code, alias in alias_map.items() if str(alias).strip()
    }
    candidates = [value]
    alias_value = (alias_map.get(value) or "").strip()
    reverse_value = (reverse_map.get(value) or "").strip()
    if alias_value and alias_value not in candidates:
        candidates.append(alias_value)
    if reverse_value and reverse_value not in candidates:
        candidates.append(reverse_value)
    return candidates


def ensure_min_balance_for_omni_video(user: dict, model_code: str | None = None) -> None:
    role_code = user.get("role_code")
    if role_code != database.ROLE_EXTERNAL_USER:
        return

    candidates = _pricing_model_candidates(model_code)
    if candidates:
        pricings = [
            item
            for item in database.get_model_pricing_list(enabled=True)
            if (item.get("model_code") or "") in candidates
            or (item.get("model_name") or "") in candidates
        ]
        if not pricings:
            raise ValueError("当前模型未配置计费规则，请联系管理员。")
        model_price_cent_per_million = min(int(_price_per_million_cny_cent(p)) for p in pricings)
    else:
        min_price = database.get_min_enabled_model_price_per_million_cent()
        if min_price is None:
            return
        model_price_cent_per_million = int(min_price)

    multiplier = _effective_multiplier(user)
    unit_price_cent_per_ktoken = Decimal(model_price_cent_per_million) / Decimal(1000)
    min_fee_cent = _to_cent(unit_price_cent_per_ktoken * multiplier)
    balance_cent = int(user.get("balance_cent") or 0)
    if balance_cent < min_fee_cent:
        raise ValueError("账号余额不足，请联系管理员充值。")


def settle_omni_video_charge(task: dict) -> None:
    task_id = task.get("task_id")
    user_id = task.get("user_id")
    token_usage = task.get("token_usage")
    model_code = task.get("model")
    if not task_id or not user_id or token_usage in (None, ""):
        return

    if database.has_ledger_entry(user_id, "debit", BIZ_OMNI_VIDEO, task_id):
        return

    user = database.get_user_by_id(user_id)
    if not user:
        return

    pricing = None
    for candidate in _pricing_model_candidates(model_code):
        pricing = database.resolve_model_pricing(
            model_code=candidate,
            resolution=task.get("resolution"),
            has_video_reference=_has_video_reference(task),
        )
        if pricing:
            break
    if not pricing or not pricing.get("enabled"):
        return

    tokens_raw = int(token_usage)
    tokens_billed = database.compute_tokens_billed(tokens_raw)
    price_per_million_cent = _price_per_million_cny_cent(pricing)
    unit_price_cent_per_ktoken = price_per_million_cent / Decimal(1000)
    multiplier = _effective_multiplier(user)
    fee_cent = _to_cent(
        (Decimal(tokens_billed) / Decimal(1000)) * unit_price_cent_per_ktoken * multiplier
    )

    database.create_account_ledger_entry(
        user_id=user_id,
        entry_type="debit",
        amount_cent=fee_cent,
        biz_type=BIZ_OMNI_VIDEO,
        biz_id=task_id,
        model_code=model_code,
        tokens_raw=tokens_raw,
        tokens_billed=tokens_billed,
        unit_price_cent_per_ktoken=int(_to_cent(unit_price_cent_per_ktoken)),
        multiplier=float(multiplier),
        snapshot_json={
            "currency_code": pricing.get("currency_code") or database.MODEL_CURRENCY_CNY,
            "price_per_million_token_cent": int(pricing["price_per_million_token_cent"]),
            "price_per_million_token_cny_cent": int(price_per_million_cent),
            "usd_to_cny_rate": database.USD_TO_CNY_RATE,
            "pricing_multiplier": float(multiplier),
        },
    )
