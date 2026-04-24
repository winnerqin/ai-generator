"""Service layer for omni video task orchestration."""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import requests

import database
from app.config import config
from app.services.omni_video_client import omni_video_client, is_intl_model
from app.services.operation_log_service import (
    log_external_api_call,
    log_task_operation,
    log_video_download,
)
from app.services.oss_service import oss_service

logger = logging.getLogger(__name__)

SUPPORTED_OMNI_MODELS = {
    "doubao-seedance-2-0-260128",
    "doubao-seedance-2-0-fast-260128",
    "dreamina-seedance-2-0-260128",  # 国际版模型
}
SUPPORTED_OMNI_RESOLUTIONS = {"480p", "720p"}
SUPPORTED_OMNI_ASPECT_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4"}
SUCCESS_STATUSES = {"succeeded", "success", "completed", "done", "finished"}
TERMINAL_STATUSES = SUCCESS_STATUSES | {"failed", "cancelled", "canceled", "expired"}

# URL类型判断
OSS_URL_PATTERNS = ["oss-cn", "aliyuncs.com"]
TOS_URL_PATTERNS = ["tos-cn-beijing.volces.com", "tos-cn"]


def is_oss_url(url: str) -> bool:
    """判断是否是阿里云OSS永久URL"""
    if not url:
        return False
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in OSS_URL_PATTERNS)


def is_tos_temp_url(url: str) -> bool:
    """判断是否是火山引擎TOS临时URL"""
    if not url:
        return False
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in TOS_URL_PATTERNS)


def _normalize_reference_urls(reference_urls: list[str] | None) -> list[str]:
    if not reference_urls:
        return []
    return [url.strip() for url in reference_urls if isinstance(url, str) and url.strip()]


def _normalize_filename(value: Any) -> str | None:
    if value in (None, ""):
        return None
    filename = str(value).strip()
    if not filename:
        return None

    invalid_chars = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in invalid_chars else ch for ch in filename).strip().strip(".")
    if not cleaned:
        return None
    if not cleaned.lower().endswith(".mp4"):
        cleaned = f"{cleaned}.mp4"
    return cleaned


def _infer_upload_file_type(url: str) -> str:
    lower = urlparse(url).path.lower() if url.startswith(("http://", "https://")) else url.lower()
    if any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
        return "image"
    if any(lower.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".avi", ".mkv")):
        return "video"
    if any(lower.endswith(ext) for ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")):
        return "document"
    return "document"


def _encode_public_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    encoded_path = quote(parsed.path, safe="/%._-~()")
    encoded_query = quote(parsed.query, safe="=&%._-~")
    return urlunparse(parsed._replace(path=encoded_path, query=encoded_query))


def _resolve_reference_url(
    url: str,
    *,
    user_id: int | None,
    project_id: int | None,
    public_origin: str | None,
) -> str:
    value = (url or "").strip()
    if not value:
        return value

    # 虚拟人像URL格式 asset://asset-xxx 直接返回，无需转换
    if value.startswith("asset://"):
        return value

    local_path: Path | None = None
    public_path: str | None = None
    parsed_url = urlparse(value) if value.startswith(("http://", "https://")) else None
    if parsed_url and parsed_url.path.startswith("/uploads/"):
        relative_path = parsed_url.path.removeprefix("/uploads/").lstrip("/\\")
        local_path = Path(config.UPLOAD_FOLDER) / relative_path
        public_path = parsed_url.path
    elif value.startswith("/uploads/"):
        relative_path = value.removeprefix("/uploads/").lstrip("/\\")
        local_path = Path(config.UPLOAD_FOLDER) / relative_path
        public_path = value
    else:
        candidate = Path(value)
        if candidate.exists():
            local_path = candidate
            try:
                public_path = f"/uploads/{candidate.resolve().relative_to(Path(config.UPLOAD_FOLDER).resolve()).as_posix()}"
            except ValueError:
                public_path = None

    if local_path and local_path.exists() and oss_service.is_available():
        oss_url = oss_service.upload_file(
            str(local_path),
            user_id=user_id,
            project_id=project_id,
            file_type=_infer_upload_file_type(value),
        )
        if oss_url:
            return _encode_public_url(oss_url)

    if parsed_url and parsed_url.scheme and parsed_url.netloc:
        return _encode_public_url(value)

    if public_path and public_origin:
        return _encode_public_url(f"{public_origin.rstrip('/')}{public_path}")

    raise ValueError("参考素材必须使用可公开访问的 URL，或提供可拼接本地上传地址的服务域名。")


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no"}
    return bool(value)


def _content_item_for_url(url: str) -> dict[str, Any]:
    # 虚拟人像URL格式: asset://asset-xxx
    if url.startswith("asset://"):
        return {"type": "image_url", "role": "reference_image", "image_url": {"url": url}}
    lower = url.lower()
    if any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
        return {"type": "image_url", "role": "reference_image", "image_url": {"url": url}}
    if any(lower.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".avi", ".mkv")):
        return {"type": "video_url", "role": "reference_video", "video_url": {"url": url}}
    if any(lower.endswith(ext) for ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")):
        return {"type": "audio_url", "role": "reference_audio", "audio_url": {"url": url}}
    return {"type": "file_url", "role": "reference_file", "file_url": {"url": url}}


def build_omni_video_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Map local form fields into an omni-reference request payload."""

    reference_urls = [
        _resolve_reference_url(
            url,
            user_id=data.get("_user_id"),
            project_id=data.get("_project_id"),
            public_origin=(data.get("_public_origin") or "").strip() or None,
        )
        for url in _normalize_reference_urls(data.get("reference_urls"))
    ]
    model = (data.get("model") or config.SEEDANCE_OMNI_MODEL or "").strip()
    resolution = str(data.get("resolution") or "720p").strip().lower()
    aspect_ratio = str(data.get("aspect_ratio") or data.get("ratio") or "16:9").strip()
    raw_duration = data.get("duration", -1)
    raw_frame_count = data.get("frame_count")

    if model not in SUPPORTED_OMNI_MODELS:
        raise ValueError("不支持的全能视频模型")
    if resolution not in SUPPORTED_OMNI_RESOLUTIONS:
        raise ValueError("全能视频仅支持 480P 和 720P")
    if aspect_ratio not in SUPPORTED_OMNI_ASPECT_RATIOS:
        raise ValueError("不支持的视频比例")

    frame_count: int | None = None
    if raw_frame_count not in (None, "", "null"):
        try:
            frame_count = int(raw_frame_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("帧数必须是整数") from exc
        if not 29 <= frame_count <= 289:
            raise ValueError("帧数取值范围为 29-289")

    duration: int | None = None
    if frame_count is None:
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError) as exc:
            raise ValueError("时长必须是 4-15 或 -1") from exc
        if duration != -1 and not 4 <= duration <= 15:
            raise ValueError("时长取值范围为 4-15 秒，或使用 -1")

    payload: dict[str, Any] = {
        "model": model,
        "mode": "omni_reference",
        "prompt": (data.get("prompt") or "").strip(),
        "duration": duration,
        "frame_count": frame_count,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "ratio": aspect_ratio,
        "seed": data.get("seed"),
        "generate_audio": _coerce_bool(data.get("generate_audio"), default=True),
        "reference_urls": reference_urls,
        "filename": _normalize_filename(data.get("filename")),
    }

    content: list[dict[str, Any]] = []
    if payload["prompt"]:
        content.append({"type": "text", "text": payload["prompt"]})
    for url in reference_urls:
        content.append(_content_item_for_url(url))
    payload["content"] = content
    return payload


def _pick_nested(source: Any, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current = source
        found = True
        for key in path:
            if not isinstance(current, dict) or key not in current:
                found = False
                break
            current = current[key]
        if found and current not in (None, ""):
            return current
    return None


def _extract_task_id(remote: dict[str, Any]) -> str:
    candidates = [
        remote.get("task_id"),
        remote.get("id"),
        _pick_nested(remote, ("data", "task_id")),
        _pick_nested(remote, ("data", "id")),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return f"local-{uuid.uuid4().hex[:16]}"


def _extract_status(remote: dict[str, Any], default: str = "queued") -> str:
    status = remote.get("status")
    if not status:
        status = _pick_nested(remote, ("data", "status"))
    return str(status or default)


def _extract_result_blob(remote: dict[str, Any]) -> dict[str, Any]:
    for key in ("result", "output", "data", "content"):
        value = remote.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _extract_usage(remote: dict[str, Any]) -> dict[str, Any]:
    raw_usage = _pick_nested(
        remote,
        ("usage",),
        ("data", "usage"),
        ("result", "usage"),
        ("output", "usage"),
        ("content", "usage"),
    )
    if not isinstance(raw_usage, dict):
        return {}
    return {
        "total_tokens": raw_usage.get("total_tokens") or raw_usage.get("tokens") or raw_usage.get("total"),
        "input_tokens": raw_usage.get("prompt_tokens") or raw_usage.get("input_tokens"),
        "output_tokens": raw_usage.get("completion_tokens") or raw_usage.get("output_tokens"),
        "raw": raw_usage,
    }


def _normalize_token_usage(remote: dict[str, Any]) -> int | None:
    usage = _extract_usage(remote)
    total_tokens = usage.get("total_tokens")
    if total_tokens in (None, ""):
        return None
    try:
        return int(total_tokens)
    except (TypeError, ValueError):
        return None


def _normalize_duration(local_payload: dict[str, Any], remote: dict[str, Any], result: dict[str, Any]) -> int | None:
    value = _pick_nested(
        remote,
        ("duration",),
        ("data", "duration"),
        ("result", "duration"),
        ("output", "duration"),
        ("content", "duration"),
    )
    if value in (None, ""):
        value = result.get("duration")
    if value in (None, ""):
        value = local_payload.get("duration")
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _normalize_frame_count(local_payload: dict[str, Any], remote: dict[str, Any], result: dict[str, Any]) -> int | None:
    value = _pick_nested(
        remote,
        ("frames",),
        ("frame_count",),
        ("framespersecond",),
        ("data", "frames"),
        ("data", "frame_count"),
        ("data", "framespersecond"),
        ("result", "frames"),
        ("result", "frame_count"),
        ("result", "framespersecond"),
        ("output", "frames"),
        ("output", "frame_count"),
        ("output", "framespersecond"),
        ("content", "frames"),
        ("content", "frame_count"),
        ("content", "framespersecond"),
    )
    if value in (None, ""):
        value = result.get("frames") or result.get("frame_count")
    if value in (None, ""):
        value = local_payload.get("frame_count")
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _normalize_seed(local_payload: dict[str, Any], remote: dict[str, Any], result: dict[str, Any]) -> int | None:
    value = _pick_nested(
        remote,
        ("seed",),
        ("data", "seed"),
        ("result", "seed"),
        ("output", "seed"),
        ("content", "seed"),
    )
    if value in (None, ""):
        value = result.get("seed")
    if value in (None, ""):
        value = local_payload.get("seed")
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _normalize_text_field(local_payload: dict[str, Any], remote: dict[str, Any], result: dict[str, Any], *keys: str) -> str | None:
    nested_paths = (
        [(key,) for key in keys]
        + [("data", key) for key in keys]
        + [("result", key) for key in keys]
        + [("output", key) for key in keys]
        + [("content", key) for key in keys]
    )
    value = _pick_nested(remote, *nested_paths)
    if value in (None, ""):
        for key in keys:
            value = result.get(key)
            if value not in (None, ""):
                break
    if value in (None, ""):
        for key in keys:
            value = local_payload.get(key)
            if value not in (None, ""):
                break
    return str(value) if value not in (None, "") else None


def _guess_video_filename(task_id: str, video_url: str) -> str:
    parsed = urlparse(video_url)
    suffix = Path(parsed.path).suffix or ".mp4"
    return f"{task_id}{suffix}"


def _task_record_from_remote(
    *,
    user_id: int,
    project_id: int | None,
    local_payload: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any]:
    result = _extract_result_blob(remote)
    usage = _extract_usage(remote)
    return {
        "user_id": user_id,
        "project_id": project_id,
        "task_id": _extract_task_id(remote),
        "status": _extract_status(remote),
        "model": _normalize_text_field(local_payload, remote, result, "model") or local_payload.get("model"),
        "mode": local_payload.get("mode"),
        "prompt": _normalize_text_field(local_payload, remote, result, "prompt") or local_payload.get("prompt"),
        "input_payload_json": local_payload,
        "raw_response_json": remote,
        "result_json": result,
        "fail_reason": _normalize_text_field({}, remote, result, "error", "message", "reason"),
        "video_url": _normalize_text_field({}, remote, result, "video_url", "url"),
        "cover_url": _normalize_text_field({}, remote, result, "cover_url", "poster_url", "cover"),
        "first_frame_url": _normalize_text_field({}, remote, result, "first_frame_url"),
        "last_frame_url": _normalize_text_field({}, remote, result, "last_frame_url"),
        "reference_urls_json": local_payload.get("reference_urls", []),
        "duration": _normalize_duration(local_payload, remote, result),
        "frame_count": _normalize_frame_count(local_payload, remote, result),
        "resolution": _normalize_text_field(local_payload, remote, result, "resolution"),
        "aspect_ratio": _normalize_text_field(local_payload, remote, result, "aspect_ratio", "ratio"),
        "filename": _normalize_filename(local_payload.get("filename")),
        "seed": _normalize_seed(local_payload, remote, result),
        "token_usage": _normalize_token_usage(remote),
        "usage_json": usage,
    }


def _decorate_task(task: dict[str, Any]) -> dict[str, Any]:
    local_payload = task.get("input_payload_json") or {}
    raw_response = task.get("raw_response_json") or {}
    result = task.get("result_json") or {}
    usage = task.get("usage_json") or _extract_usage(raw_response)

    if task.get("resolution") in (None, ""):
        task["resolution"] = _normalize_text_field(local_payload, raw_response, result, "resolution")
    if task.get("aspect_ratio") in (None, ""):
        task["aspect_ratio"] = _normalize_text_field(local_payload, raw_response, result, "aspect_ratio", "ratio")
    if task.get("duration") in (None, ""):
        task["duration"] = _normalize_duration(local_payload, raw_response, result)
    if task.get("frame_count") in (None, ""):
        task["frame_count"] = _normalize_frame_count(local_payload, raw_response, result)
    if task.get("seed") in (None, ""):
        task["seed"] = _normalize_seed(local_payload, raw_response, result)
    if task.get("model") in (None, ""):
        task["model"] = _normalize_text_field(local_payload, raw_response, result, "model")
    if task.get("video_url") in (None, ""):
        task["video_url"] = _normalize_text_field({}, raw_response, result, "video_url", "url")
    if task.get("cover_url") in (None, ""):
        task["cover_url"] = _normalize_text_field({}, raw_response, result, "cover_url", "poster_url", "cover")
    task["filename"] = _normalize_filename(task.get("filename") or local_payload.get("filename"))
    task["download_filename"] = task["filename"] or (
        _guess_video_filename(task.get("task_id") or "video", task.get("video_url") or "")
        if task.get("task_id")
        else None
    )

    token_usage = task.get("token_usage")
    if token_usage in (None, ""):
        token_usage = _normalize_token_usage(raw_response)
    task["token_usage"] = token_usage
    task["usage_json"] = usage if isinstance(usage, dict) else {}
    return task


def _download_and_upload_to_oss(
    video_url: str,
    filename: str,
    user_id: int,
    project_id: int | None,
    username: str | None = None,
) -> tuple[str | None, bool]:
    """
    从远程URL下载视频并上传到OSS，返回(OSS永久URL, 是否过期)。

    如果OSS不可用或下载失败，返回(None, False)。
    如果下载返回403（URL过期），返回(None, True)。
    """
    start_time = time.time()

    if not oss_service.is_available():
        log_video_download(
            user_id=user_id,
            username=username,
            project_id=project_id,
            source_url=video_url,
            success=False,
            error="OSS不可用",
            duration_ms=int((time.time() - start_time) * 1000),
        )
        return None, False

    try:
        logger.info("[omni-video] Downloading video for OSS upload: url=%s", video_url)
        response = requests.get(video_url, timeout=120, stream=True)
        response.raise_for_status()

        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, filename)

        file_size = 0
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    file_size += len(chunk)

        logger.info("[omni-video] Video downloaded to temp: %s, size=%d", temp_file, file_size)

        oss_url = oss_service.upload_file(
            temp_file,
            user_id=user_id,
            project_id=project_id,
            file_type="video",
            username=username,
        )

        # 清理临时文件
        try:
            os.unlink(temp_file)
        except Exception:
            pass

        duration_ms = int((time.time() - start_time) * 1000)

        if oss_url:
            logger.info("[omni-video] Video uploaded to OSS: %s", oss_url)
            log_video_download(
                user_id=user_id,
                username=username,
                project_id=project_id,
                source_url=video_url,
                target_path=temp_file,
                oss_url=oss_url,
                file_size=file_size,
                success=True,
                duration_ms=duration_ms,
            )
            return oss_url, False

        log_video_download(
            user_id=user_id,
            username=username,
            project_id=project_id,
            source_url=video_url,
            target_path=temp_file,
            file_size=file_size,
            success=False,
            error="OSS上传失败",
            duration_ms=duration_ms,
        )
        return None, False

    except requests.HTTPError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        is_expired = e.response is not None and e.response.status_code == 403
        if is_expired:
            logger.warning("[omni-video] Video URL expired (403): %s", video_url)
            log_video_download(
                user_id=user_id,
                username=username,
                project_id=project_id,
                source_url=video_url,
                success=False,
                is_expired=True,
                duration_ms=duration_ms,
                error="URL过期(403)",
            )
            return None, True
        error_str = str(e)
        logger.error("[omni-video] Failed to download/upload video: %s", e)
        log_video_download(
            user_id=user_id,
            username=username,
            project_id=project_id,
            source_url=video_url,
            success=False,
            duration_ms=duration_ms,
            error=error_str,
        )
        return None, False
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_str = str(e)
        logger.error("[omni-video] Failed to download/upload video: %s", e)
        log_video_download(
            user_id=user_id,
            username=username,
            project_id=project_id,
            source_url=video_url,
            success=False,
            duration_ms=duration_ms,
            error=error_str,
        )
        return None, False


class OmniVideoService:
    def __init__(self) -> None:
        self.client = omni_video_client

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def _ensure_video_library_entry(self, task: dict[str, Any]) -> None:
        status = str(task.get("status") or "").lower()
        video_url = task.get("video_url")
        username = task.get("username")
        if status not in SUCCESS_STATUSES or not video_url:
            return

        if database.is_video_task_deleted_from_library(
            task["user_id"],
            task["task_id"],
            project_id=task.get("project_id"),
        ):
            return

        existing = database.get_video_by_task_id(
            task["user_id"],
            task["task_id"],
            project_id=task.get("project_id"),
        )
        if existing:
            # 已存在记录，检查是否需要更新URL（如果原URL是临时URL且OSS可用）
            existing_url = existing.get("url") or ""
            existing_meta = existing.get("meta") or {}
            # 如果已有OSS URL或原始URL不可用，无需更新
            if is_oss_url(existing_url) or not oss_service.is_available():
                return
            # 如果已标记URL过期，不再重复尝试
            if existing_meta.get("url_expired"):
                return
            # 如果原始URL仍是临时URL，尝试迁移到OSS
            if is_tos_temp_url(existing_url):
                filename = existing.get("filename") or _guess_video_filename(task["task_id"], existing_url)
                oss_url, is_expired = _download_and_upload_to_oss(
                    existing_url,
                    filename,
                    task["user_id"],
                    task.get("project_id"),
                    username=username,
                )
                if oss_url:
                    # 更新数据库中的URL
                    database.update_video_asset_url(existing["id"], oss_url)
                    # 更新任务记录
                    task["video_url"] = oss_url
                    database.save_omni_video_task(task)
                elif is_expired:
                    # 标记URL过期，不再重复尝试
                    database.update_video_asset_meta(existing["id"], {"url_expired": True})
                    logger.info("[omni-video] Marked video URL as expired: task_id=%s", task["task_id"])
            return

        filename = task.get("download_filename") or _guess_video_filename(task["task_id"], video_url)

        # 先保存到视频库（使用原始URL），作为占位防止并发重复
        database.save_video_asset(
            user_id=task["user_id"],
            project_id=task.get("project_id"),
            filename=filename,
            url=video_url,
            meta={
                "library_group": "video",
                "task_id": task["task_id"],
                "source": "omni_video",
                "model": task.get("model"),
                "prompt": task.get("prompt"),
                "resolution": task.get("resolution"),
                "duration": task.get("duration"),
                "frame_count": task.get("frame_count"),
                "aspect_ratio": task.get("aspect_ratio"),
                "seed": task.get("seed"),
                "token_usage": task.get("token_usage"),
                "cover_url": task.get("cover_url"),
                "filename": task.get("filename"),
            },
        )

        # 然后尝试下载并上传到OSS，获取永久URL
        if oss_service.is_available() and is_tos_temp_url(video_url):
            oss_url, is_expired = _download_and_upload_to_oss(
                video_url,
                filename,
                task["user_id"],
                task.get("project_id"),
                username=username,
            )
            if oss_url:
                # 更新视频库中的URL
                database.update_video_asset_url_by_task_id(
                    task["user_id"],
                    task["task_id"],
                    oss_url,
                    project_id=task.get("project_id"),
                )
                # 更新任务记录中的video_url为OSS URL
                task["video_url"] = oss_url
                database.save_omni_video_task(task)
            elif is_expired:
                # 标记URL过期
                existing_video = database.get_video_by_task_id(
                    task["user_id"],
                    task["task_id"],
                    project_id=task.get("project_id"),
                )
                if existing_video:
                    database.update_video_asset_meta(existing_video["id"], {"url_expired": True})
                    logger.info("[omni-video] Marked new video URL as expired: task_id=%s", task["task_id"])

    def _persist_and_load(self, record: dict[str, Any]) -> dict[str, Any]:
        database.save_omni_video_task(record)
        task = (
            database.get_omni_video_task(
                record["task_id"],
                user_id=record["user_id"],
                project_id=record.get("project_id"),
            )
            or record
        )
        task = _decorate_task(task)
        self._ensure_video_library_entry(task)
        return task

    def _sync_task_from_remote(self, task: dict[str, Any]) -> dict[str, Any]:
        local_payload = task.get("input_payload_json", {})
        model = local_payload.get("model") or task.get("model")

        if not self.client.is_configured(model=model):
            task = _decorate_task(task)
            self._ensure_video_library_entry(task)
            return task

        task_id = task.get("task_id")
        if not task_id:
            task = _decorate_task(task)
            self._ensure_video_library_entry(task)
            return task

        remote = self.client.get_task(task_id, model=model)
        record = _task_record_from_remote(
            user_id=task["user_id"],
            project_id=task.get("project_id"),
            local_payload=local_payload,
            remote=remote,
        )
        return self._persist_and_load(record)

    def create_task(self, user_id: int, project_id: int | None, data: dict[str, Any]) -> dict[str, Any]:
        start_time = time.time()
        username = data.get("_username")
        payload = build_omni_video_payload(data)
        if not payload["prompt"]:
            error_msg = "提示词不能为空"
            log_task_operation(
                user_id=user_id,
                username=username,
                project_id=project_id,
                task_type="omni_video",
                operation="create",
                success=False,
                error=error_msg,
            )
            raise ValueError(error_msg)

        model = payload.get("model")
        is_configured = self.client.is_configured(model=model)
        api_endpoint = self.client._url(self.client.create_path, model=model) if is_configured else "local"

        if is_configured:
            remote = self.client.create_task(payload)
            log_external_api_call(
                user_id=user_id,
                username=username,
                project_id=project_id,
                service_name="seedance",
                api_endpoint=api_endpoint,
                request_method="POST",
                request_payload=payload,
                response_status=200 if remote else None,
                response_data=remote,
                task_id=remote.get("task_id") if remote else None,
                duration_ms=int((time.time() - start_time) * 1000),
                success=bool(remote),
            )
        else:
            remote = {
                "task_id": f"local-{uuid.uuid4().hex[:16]}",
                "status": "queued",
                "message": "Seedance 2.0 尚未完成远端配置，当前为本地占位任务。",
            }
            log_task_operation(
                user_id=user_id,
                username=username,
                project_id=project_id,
                task_type="omni_video",
                task_id=remote["task_id"],
                operation="create",
                task_status="queued",
                success=True,
                error="远端未配置，创建本地占位任务",
            )

        record = _task_record_from_remote(
            user_id=user_id,
            project_id=project_id,
            local_payload=payload,
            remote=remote,
        )
        # 传递 username 以便后续操作记录
        record["username"] = username
        result = self._persist_and_load(record)

        log_task_operation(
            user_id=user_id,
            username=username,
            project_id=project_id,
            task_type="omni_video",
            task_id=result.get("task_id"),
            operation="create",
            task_status=result.get("status"),
            task_data={
                "model": result.get("model"),
                "resolution": result.get("resolution"),
                "aspect_ratio": result.get("aspect_ratio"),
                "duration": result.get("duration"),
                "frame_count": result.get("frame_count"),
            },
            duration_ms=int((time.time() - start_time) * 1000),
            success=True,
        )

        return result

    def list_tasks(
        self,
        user_id: int,
        project_id: int | None,
        *,
        status: str | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        offset = max(page - 1, 0) * page_size
        items = database.get_omni_video_tasks(
            user_id,
            project_id,
            status=status,
            search=search,
            start_date=start_date,
            end_date=end_date,
            limit=page_size,
            offset=offset,
        )
        total = database.count_omni_video_tasks(
            user_id,
            project_id,
            status=status,
            search=search,
            start_date=start_date,
            end_date=end_date,
        )

        synced_items: list[dict[str, Any]] = []
        for item in items:
            normalized = _decorate_task(item)
            current_status = str(normalized.get("status") or "").lower()
            if current_status and current_status not in TERMINAL_STATUSES:
                try:
                    normalized = self._sync_task_from_remote(normalized)
                except Exception:
                    pass
            else:
                self._ensure_video_library_entry(normalized)
            synced_items.append(_decorate_task(normalized))
        return synced_items, total

    def get_task(self, user_id: int, project_id: int | None, task_id: str) -> dict[str, Any] | None:
        existing = database.get_omni_video_task(task_id, user_id=user_id, project_id=project_id)
        if not existing:
            return None
        normalized = _decorate_task(existing)
        current_status = str(normalized.get("status") or "").lower()
        if current_status and current_status in TERMINAL_STATUSES:
            self._ensure_video_library_entry(normalized)
            return normalized
        return self._sync_task_from_remote(existing)

    def refresh_task(self, user_id: int, project_id: int | None, task_id: str) -> dict[str, Any]:
        existing = database.get_omni_video_task(task_id, user_id=user_id, project_id=project_id)
        if not existing:
            raise ValueError("任务不存在")
        normalized = _decorate_task(existing)
        current_status = str(normalized.get("status") or "").lower()
        if current_status and current_status in TERMINAL_STATUSES:
            self._ensure_video_library_entry(normalized)
            return normalized
        return self._sync_task_from_remote(existing)

    def cancel_task(self, user_id: int, project_id: int | None, task_id: str) -> dict[str, Any]:
        existing = database.get_omni_video_task(task_id, user_id=user_id, project_id=project_id)
        if not existing:
            raise ValueError("任务不存在")

        local_payload = existing.get("input_payload_json", {})
        model = local_payload.get("model") or existing.get("model")

        if self.client.is_configured(model=model):
            remote = self.client.cancel_task(task_id, model=model)
            status = _extract_status(remote, "cancelled")
        else:
            remote = {"task_id": task_id, "status": "cancelled", "message": "本地占位任务已取消。"}
            status = "cancelled"

        record = {
            **existing,
            "status": status,
            "raw_response_json": remote,
            "fail_reason": None if status != "failed" else remote.get("message"),
        }
        return self._persist_and_load(record)

    def delete_task(self, user_id: int, project_id: int | None, task_id: str) -> int:
        return database.delete_omni_video_task(task_id, user_id=user_id, project_id=project_id)


omni_video_service = OmniVideoService()
