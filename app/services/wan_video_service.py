"""Wan 3.0 payload validation and shared-task orchestration."""

from __future__ import annotations

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import database
from app.config import config
from app.services.omni_video_service import _download_and_upload_to_oss
from app.services.oss_service import oss_service
from app.services.wan_video_client import wan_video_client

SOURCE = "wan_video"
MODES = {"text_to_video", "image_to_video_first", "image_to_video_first_last", "reference_to_video"}
MEDIA_ROLES = {"first_frame", "last_frame", "reference_image", "reference_video", "reference_audio"}
STATUS_MAP = {
    "PENDING": "queued", "QUEUED": "queued", "RUNNING": "running",
    "SUCCEEDED": "succeeded", "SUCCESS": "succeeded",
    "FAILED": "failed", "CANCELED": "cancelled", "CANCELLED": "cancelled",
}
TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
SUPPORTED_RESOLUTIONS = {"480p", "720p", "1080p"}
logger = logging.getLogger(__name__)


def _models() -> list[str]:
    return [item.strip() for item in config.WAN_VIDEO_MODELS.split(",") if item.strip()]


def _price_cent_per_second(resolution: Any) -> int:
    normalized = str(resolution or "720p").strip().lower()
    if normalized not in SUPPORTED_RESOLUTIONS:
        raise ValueError("Wan 3.0 分辨率必须是 480P、720P 或 1080P。")
    setting = f"WAN_VIDEO_PRICE_{normalized.upper()}_CENT_PER_SECOND"
    price = int(getattr(config, setting, 0) or 0)
    if price <= 0:
        raise ValueError(f"Wan 3.0 尚未配置 {normalized.upper()} 按秒计费单价。")
    return price


def _duration(value: Any) -> int:
    try:
        duration = int(value if value not in (None, "") else 5)
    except (TypeError, ValueError) as exc:
        raise ValueError("Wan 3.0 时长必须是 -1 或 2 到 30 秒的整数。") from exc
    if duration != -1 and not 2 <= duration <= 30:
        raise ValueError("Wan 3.0 时长必须是 -1（智能时长）或 2 到 30 秒。")
    return duration


def _billable_seconds(task: dict[str, Any]) -> int | None:
    usage = task.get("usage_json") or {}
    for key in ("duration", "video_duration"):
        value = usage.get(key)
        if value not in (None, ""):
            try:
                seconds = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            except (ValueError, TypeError, ArithmeticError):
                continue
            if seconds > 0:
                return seconds
    input_seconds = usage.get("input_video_duration")
    output_seconds = usage.get("output_video_duration")
    if input_seconds not in (None, "") and output_seconds not in (None, ""):
        try:
            total = Decimal(str(input_seconds)) + Decimal(str(output_seconds))
            seconds = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (ValueError, TypeError, ArithmeticError):
            return None
        return seconds if seconds > 0 else None
    requested = task.get("duration")
    if requested not in (None, "", -1, "-1"):
        return _duration(requested)
    return None


def build_wan_video_payload(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    mode = str(data.get("mode") or "text_to_video").strip()
    if mode not in MODES:
        raise ValueError("不支持的 Wan 视频生成模式。")
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("提示词不能为空。")
    model = str(data.get("model") or config.WAN_VIDEO_MODEL).strip()
    if model not in _models():
        raise ValueError("不支持的 Wan 模型。")
    resolution = str(data.get("resolution") or "720P").strip().upper()
    if resolution.lower() not in SUPPORTED_RESOLUTIONS:
        raise ValueError("Wan 3.0 分辨率必须是 480P、720P 或 1080P。")
    duration = _duration(data.get("duration"))

    media = data.get("media") or []
    if not isinstance(media, list):
        raise ValueError("media 必须是数组。")
    normalized: list[dict[str, str]] = []
    for item in media:
        role = str((item or {}).get("role") or "").strip()
        url = str((item or {}).get("url") or "").strip()
        if role not in MEDIA_ROLES or not url:
            raise ValueError("参考素材必须包含有效的 role 和 url。")
        normalized.append({"role": role, "url": url})

    counts = {role: sum(1 for item in normalized if item["role"] == role) for role in MEDIA_ROLES}
    if counts["first_frame"] > 1 or counts["last_frame"] > 1:
        raise ValueError("首帧和尾帧最多各一张。")
    if mode == "text_to_video" and normalized:
        raise ValueError("文生视频不能传入参考素材。")
    if mode == "image_to_video_first" and (counts["first_frame"] != 1 or len(normalized) != 1):
        raise ValueError("首帧图生视频必须且只能传入一张首帧图。")
    if mode == "image_to_video_first_last" and (
        counts["first_frame"] != 1 or counts["last_frame"] != 1 or len(normalized) != 2
    ):
        raise ValueError("首尾帧图生视频必须各传入一张图片。")
    if mode == "reference_to_video" and not any(
        item["role"].startswith("reference_") for item in normalized
    ):
        raise ValueError("参考生视频至少需要一个参考素材。")

    role_to_type = {
        "first_frame": "first_frame", "last_frame": "last_frame",
        "reference_image": "reference_image", "reference_video": "reference_video",
        "reference_audio": "reference_audio",
    }
    parameters: dict[str, Any] = {}
    for key in ("resolution", "ratio", "duration", "seed", "prompt_extend", "watermark"):
        if data.get(key) not in (None, ""):
            parameters[key] = data[key]
    upstream_input: dict[str, Any] = {"prompt": prompt}
    if normalized:
        upstream_input["media"] = [
            {"type": role_to_type[item["role"]], "url": item["url"]} for item in normalized
        ]
    upstream = {"model": model, "input": upstream_input, "parameters": parameters}
    parameters["resolution"] = resolution
    parameters["duration"] = duration
    canonical = {**data, "mode": mode, "model": model, "prompt": prompt,
                 "media": normalized, "resolution": resolution, "duration": duration}
    return upstream, canonical


class WanVideoService:
    @staticmethod
    def _multiplier(user: dict[str, Any]) -> Decimal:
        role_multiplier = Decimal(str(database.get_role_pricing_multiplier(
            user.get("role_code") or database.ROLE_EXTERNAL_USER
        ) or 1))
        user_multiplier = Decimal(str(user.get("pricing_multiplier") or 1))
        return user_multiplier if user_multiplier > 0 else role_multiplier

    def _ensure_balance(self, user_id: int, duration: Any, resolution: Any) -> None:
        user = database.get_user_by_id(user_id) or {}
        if user.get("role_code") != database.ROLE_EXTERNAL_USER:
            return
        unit_price = _price_cent_per_second(resolution)
        requested_seconds = _duration(duration)
        seconds = (int(config.WAN_VIDEO_SMART_DURATION_MAX_SECONDS or 30)
                   if requested_seconds == -1 else requested_seconds)
        if seconds <= 0:
            raise ValueError("Wan 3.0 智能时长余额预检上限必须大于 0 秒。")
        fee = int((Decimal(unit_price * seconds) * self._multiplier(user)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))
        if int(user.get("balance_cent") or 0) < fee:
            raise ValueError("账号余额不足，请联系管理员充值。")

    def _settle(self, task: dict[str, Any]) -> str:
        if task.get("status") != "succeeded" or not task.get("user_id"):
            return "skipped"
        if database.has_ledger_entry(task["user_id"], "debit", SOURCE, task["task_id"]):
            return "settled"
        user = database.get_user_by_id(task["user_id"]) or {}
        if user.get("role_code") != database.ROLE_EXTERNAL_USER:
            return "skipped"
        try:
            unit_price = _price_cent_per_second(task.get("resolution"))
        except ValueError:
            return "pending"
        seconds = _billable_seconds(task)
        if seconds is None:
            return "pending"
        multiplier = self._multiplier(user)
        fee = int((Decimal(unit_price * seconds) * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        database.create_account_ledger_entry(
            user_id=task["user_id"], entry_type="debit", amount_cent=fee,
            biz_type=SOURCE, biz_id=task["task_id"], model_code=task.get("model"),
            tokens_raw=seconds, tokens_billed=seconds,
            unit_price_cent_per_ktoken=unit_price * 1000, multiplier=float(multiplier),
            snapshot_json={"billing_unit": "video_second", "billable_seconds": seconds,
                           "resolution": str(task.get("resolution") or "720P").upper(),
                           "price_cent_per_second": unit_price, "pricing_multiplier": float(multiplier)},
        )
        return "settled"

    @staticmethod
    def _ensure_library(task: dict[str, Any]) -> None:
        if task.get("status") != "succeeded" or not task.get("video_url"):
            return
        if database.is_video_task_deleted_from_library(
            task["user_id"], task["task_id"], project_id=task.get("project_id")
        ):
            return
        if database.get_video_by_task_id(
            task["user_id"], task["task_id"], project_id=task.get("project_id")
        ):
            return
        filename = str(task.get("filename") or f"wan_{task['task_id']}.mp4")
        if not filename.lower().endswith(".mp4"):
            filename += ".mp4"
        video_url = task["video_url"]
        asset_id = database.save_video_asset(
            user_id=task["user_id"], project_id=task.get("project_id"),
            filename=filename, url=video_url,
            meta={"library_group": "video", "task_id": task["task_id"],
                  "source": SOURCE, "model": task.get("model"), "mode": task.get("mode"),
                  "prompt": task.get("prompt"), "resolution": task.get("resolution"),
                  "duration": task.get("duration")},
        )
        if oss_service.is_available():
            try:
                oss_url, _ = _download_and_upload_to_oss(
                    video_url, filename, task["user_id"], task.get("project_id")
                )
                if oss_url:
                    task["video_url"] = oss_url
                    database.save_omni_video_task(task)
                    database.update_video_asset_url(asset_id, oss_url)
            except Exception as exc:
                logger.warning(
                    "[wan-video][library] OSS backfill failed; upstream URL retained: "
                    "task_id=%s error=%s", task.get("task_id"), exc,
                )

    def create_task(self, data: dict[str, Any], *, user_id: int, project_id: int | None) -> dict[str, Any]:
        if not wan_video_client.is_configured():
            raise ValueError("Wan 3.0 服务尚未配置。")
        upstream, canonical = build_wan_video_payload(data)
        self._ensure_balance(user_id, canonical.get("duration"), canonical.get("resolution"))
        route_key = str(data.get("client_request_id") or uuid.uuid4().hex)
        response, slot = wan_video_client.create_task(upstream, route_key=route_key)
        output = response.get("output") or {}
        task_id = output.get("task_id") or response.get("task_id")
        if not task_id:
            raise ValueError("Wan 上游未返回 task_id。")
        task = {
            "user_id": user_id, "project_id": project_id, "task_id": task_id,
            "status": "queued", "source": SOURCE, "mode": canonical["mode"],
            "model": canonical["model"], "prompt": canonical["prompt"],
            "input_payload_json": canonical, "raw_response_json": response,
            "reference_urls_json": [item["url"] for item in canonical["media"]],
            "first_frame_url": next((i["url"] for i in canonical["media"] if i["role"] == "first_frame"), None),
            "last_frame_url": next((i["url"] for i in canonical["media"] if i["role"] == "last_frame"), None),
            "duration": canonical.get("duration"), "resolution": canonical.get("resolution"),
            "aspect_ratio": canonical.get("ratio"), "seed": canonical.get("seed"),
            "filename": canonical.get("filename"), "client_request_id": data.get("client_request_id"),
            "batch_id": data.get("batch_id"), "callback_url": data.get("callback_url"),
            "external_meta_json": {"upstream_slot": slot},
        }
        database.save_omni_video_task(task)
        return database.get_omni_video_task(task_id, user_id=user_id)

    def refresh_task(self, task: dict[str, Any]) -> dict[str, Any]:
        slot = int((task.get("external_meta_json") or {}).get("upstream_slot") or 0)
        response = wan_video_client.get_task(task["task_id"], slot=slot)
        output = response.get("output") or {}
        status = STATUS_MAP.get(str(output.get("task_status") or response.get("status") or "").upper(), "running")
        results = output.get("results") or []
        first_result = results[0] if results and isinstance(results[0], dict) else {}
        video_url = output.get("video_url") or first_result.get("url") or first_result.get("video_url")
        updated = {**task, "status": status, "raw_response_json": response,
                   "result_json": output, "video_url": video_url or task.get("video_url"),
                   "fail_reason": output.get("message") or response.get("message")}
        usage = response.get("usage") or output.get("usage") or {}
        updated["usage_json"] = usage
        updated["token_usage"] = (_billable_seconds(updated)
                                  if status == "succeeded" else None)
        database.save_omni_video_task(updated)
        saved = database.get_omni_video_task(task["task_id"], user_id=task.get("user_id"))
        billing_status = self._settle(saved)
        if saved.get("status") == "succeeded":
            meta = dict(saved.get("external_meta_json") or {})
            meta["billing_status"] = billing_status
            saved["external_meta_json"] = meta
            database.save_omni_video_task(saved)
            saved = database.get_omni_video_task(task["task_id"], user_id=task.get("user_id"))
        self._ensure_library(saved)
        return saved

    def refresh_pending_tasks(self, limit: int = 200) -> dict[str, int]:
        tasks = database.get_omni_video_tasks_by_statuses(["queued", "running"], limit=limit)
        tasks = [task for task in tasks if task.get("source") == SOURCE]
        result = {"checked": len(tasks), "updated": 0, "failed": 0}
        for task in tasks:
            try:
                self.refresh_task(task)
                result["updated"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def cancel_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") in TERMINAL:
            return task
        slot = int((task.get("external_meta_json") or {}).get("upstream_slot") or 0)
        response = wan_video_client.cancel_task(task["task_id"], slot=slot)
        updated = {**task, "status": "cancelled", "raw_response_json": response}
        database.save_omni_video_task(updated)
        return database.get_omni_video_task(task["task_id"], user_id=task.get("user_id"))


wan_video_service = WanVideoService()
