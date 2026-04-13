"""Service layer for video enhance task orchestration."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import requests

import database
from app.config import config
from app.services.oss_service import oss_service
from app.services.video_enhance_client import video_enhance_client, SUPPORTED_ENHANCE_RESOLUTIONS

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"succeeded", "success", "completed", "done", "finished"}
TERMINAL_STATUSES = SUCCESS_STATUSES | {"failed", "cancelled", "canceled", "expired"}


def _generate_output_filename(source_filename: str, resolution: str) -> str:
    """生成输出文件名：原文件名-分辨率.mp4"""
    if not source_filename:
        return f"enhanced-{resolution}.mp4"

    # 移除扩展名
    base_name = source_filename.rsplit(".", 1)[0] if "." in source_filename else source_filename
    return f"{base_name}-{resolution}.mp4"


def _pick_nested(source: Any, *paths: tuple[str, ...]) -> Any:
    """从嵌套字典中提取值。"""
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
    """从远端响应中提取任务ID。"""
    candidates = [
        remote.get("task_id"),
        remote.get("id"),
        _pick_nested(remote, ("data", "task_id")),
        _pick_nested(remote, ("data", "id")),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return f"enhance-{uuid.uuid4().hex[:16]}"


def _extract_status(remote: dict[str, Any], default: str = "queued") -> str:
    """从远端响应中提取状态。"""
    status = remote.get("status")
    if not status:
        status = _pick_nested(remote, ("data", "status"))
    return str(status or default).lower()


def _extract_video_url(remote: dict[str, Any]) -> str | None:
    """从远端响应中提取视频URL。"""
    candidates = [
        remote.get("video_url"),
        remote.get("result_url"),
        remote.get("output_url"),
        _pick_nested(remote, ("result", "video_url")),
        _pick_nested(remote, ("result", "url")),
        _pick_nested(remote, ("data", "video_url")),
        _pick_nested(remote, ("data", "result_url")),
        _pick_nested(remote, ("output", "video_url")),
        _pick_nested(remote, ("output", "url")),
    ]
    for candidate in candidates:
        if candidate and isinstance(candidate, str):
            return candidate
    return None


def _extract_cover_url(remote: dict[str, Any]) -> str | None:
    """从远端响应中提取封面URL。"""
    candidates = [
        remote.get("cover_url"),
        remote.get("thumbnail_url"),
        _pick_nested(remote, ("result", "cover_url")),
        _pick_nested(remote, ("data", "cover_url")),
    ]
    for candidate in candidates:
        if candidate and isinstance(candidate, str):
            return candidate
    return None


def _extract_fail_reason(remote: dict[str, Any]) -> str | None:
    """从远端响应中提取失败原因。"""
    error = remote.get("error")
    if isinstance(error, dict):
        return error.get("message") or str(error)
    if error:
        return str(error)
    return remote.get("fail_reason") or remote.get("message")


def _extract_usage(remote: dict[str, Any]) -> dict[str, Any]:
    """从远端响应中提取用量信息。"""
    raw_usage = _pick_nested(
        remote,
        ("usage",),
        ("data", "usage"),
        ("result", "usage"),
    )
    if not isinstance(raw_usage, dict):
        return {}
    return {
        "total_tokens": raw_usage.get("total_tokens") or raw_usage.get("tokens"),
        "raw": raw_usage,
    }


class VideoEnhanceService:
    """视频画质增强服务层。"""

    def __init__(self) -> None:
        self.client = video_enhance_client

    def create_task(
        self,
        user_id: int,
        project_id: int | None,
        source_video_url: str,
        source_video_id: str | None,
        source_filename: str | None,
        resolution: str,
    ) -> dict[str, Any]:
        """
        创建画质增强任务。

        Args:
            user_id: 用户ID
            project_id: 项目ID（可选）
            source_video_url: 原视频URL
            source_video_id: 原视频在video_library中的ID（可选）
            source_filename: 原文件名（可选）
            resolution: 目标分辨率

        Returns:
            任务信息字典
        """
        if resolution not in SUPPORTED_ENHANCE_RESOLUTIONS:
            raise ValueError(f"不支持的目标分辨率: {resolution}")

        if not source_video_url:
            raise ValueError("原视频URL不能为空")

        # 构建输出文件名
        output_filename = _generate_output_filename(source_filename or "", resolution)

        # 构建输入参数
        input_payload = {
            "video_url": source_video_url,
            "resolution": resolution,
        }

        # 调用远端API
        if self.client.is_configured():
            remote = self.client.create_task(source_video_url, resolution)
        else:
            # 未配置API时使用本地模拟
            remote = {
                "task_id": f"enhance-local-{uuid.uuid4().hex[:16]}",
                "status": "queued",
                "success": True,
            }

        task_id = _extract_task_id(remote)
        status = _extract_status(remote)

        # 保存到数据库
        record = {
            "user_id": user_id,
            "task_id": task_id,
            "project_id": project_id,
            "status": status,
            "source_video_url": source_video_url,
            "source_video_id": source_video_id,
            "source_filename": source_filename,
            "input_payload_json": input_payload,
            "resolution": resolution,
            "output_filename": output_filename,
            "raw_response_json": remote,
        }
        database.save_video_enhance_task(record)

        # 返回任务信息
        return self.get_task(user_id, project_id, task_id)

    def get_task(self, user_id: int, project_id: int | None, task_id: str) -> dict[str, Any] | None:
        """
        获取任务信息。

        Args:
            user_id: 用户ID
            project_id: 项目ID（可选）
            task_id: 任务ID

        Returns:
            任务信息字典或None
        """
        task = database.get_video_enhance_task(task_id, user_id, project_id)
        if not task:
            return None
        return self._decorate_task(task)

    def refresh_task(self, user_id: int, project_id: int | None, task_id: str) -> dict[str, Any]:
        """
        刷新任务状态，从远端同步最新信息。

        Args:
            user_id: 用户ID
            project_id: 项目ID（可选）
            task_id: 任务ID

        Returns:
            更新后的任务信息
        """
        task = database.get_video_enhance_task(task_id, user_id, project_id)
        if not task:
            raise ValueError("任务不存在")

        # 同步远端状态
        updated = self._sync_from_remote(task)

        # 如果任务完成且成功，保存到视频库
        status = str(updated.get("status") or "").lower()
        if status in SUCCESS_STATUSES and updated.get("video_url"):
            self._save_to_video_library(updated)

        return self._decorate_task(updated)

    def list_tasks(
        self,
        user_id: int,
        project_id: int | None,
        status: str | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        分页查询任务列表，自动同步未完成的任务。

        Args:
            user_id: 用户ID
            project_id: 项目ID（可选）
            status: 状态筛选
            search: 搜索关键词
            start_date: 开始日期
            end_date: 结束日期
            page: 页码
            page_size: 每页数量

        Returns:
            (任务列表, 总数)
        """
        offset = (page - 1) * page_size
        items = database.get_video_enhance_tasks(
            user_id,
            project_id,
            status=status,
            search=search,
            start_date=start_date,
            end_date=end_date,
            limit=page_size,
            offset=offset,
        )
        total = database.count_video_enhance_tasks(
            user_id,
            project_id,
            status=status,
            search=search,
            start_date=start_date,
            end_date=end_date,
        )

        # 同步未完成的任务
        synced_items: list[dict[str, Any]] = []
        for item in items:
            normalized = self._decorate_task(item)
            current_status = str(normalized.get("status") or "").lower()
            if current_status and current_status not in TERMINAL_STATUSES:
                try:
                    normalized = self._sync_from_remote(item)
                    normalized = self._decorate_task(normalized)
                except Exception:
                    pass
            synced_items.append(normalized)

        return synced_items, total

    def delete_task(self, user_id: int, project_id: int | None, task_id: str) -> bool:
        """
        删除任务。

        Args:
            user_id: 用户ID
            project_id: 项目ID（可选）
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        deleted = database.delete_video_enhance_task(task_id, user_id, project_id)
        return deleted > 0

    def _sync_from_remote(self, task: dict[str, Any]) -> dict[str, Any]:
        """从远端同步任务状态到本地。"""
        task_id = task.get("task_id")
        if not task_id:
            return task

        if not self.client.is_configured():
            return task

        try:
            remote = self.client.get_task(task_id)
        except Exception:
            return task

        # 提取远端信息
        status = _extract_status(remote)
        video_url = _extract_video_url(remote)
        cover_url = _extract_cover_url(remote)
        fail_reason = _extract_fail_reason(remote)
        usage = _extract_usage(remote)

        # 更新本地记录
        updated = {
            "user_id": task.get("user_id"),
            "task_id": task_id,
            "project_id": task.get("project_id"),
            "status": status,
            "source_video_url": task.get("source_video_url"),
            "source_video_id": task.get("source_video_id"),
            "source_filename": task.get("source_filename"),
            "input_payload_json": task.get("input_payload_json", {}),
            "resolution": task.get("resolution"),
            "output_filename": task.get("output_filename"),
            "raw_response_json": remote,
            "video_url": video_url,
            "cover_url": cover_url,
            "fail_reason": fail_reason,
            "token_usage": usage.get("total_tokens"),
            "usage_json": usage,
        }
        database.save_video_enhance_task(updated)

        return updated

    def _save_to_video_library(self, task: dict[str, Any]) -> None:
        """将增强后的视频保存到视频库，支持下载并上传到OSS。"""
        video_url = task.get("video_url")
        if not video_url:
            return

        user_id = task.get("user_id")
        project_id = task.get("project_id")
        task_id = task.get("task_id")
        output_filename = task.get("output_filename") or f"enhanced-{task.get('resolution')}.mp4"

        # 检查是否已经保存过
        existing = database.get_video_by_task_id(user_id, task_id, project_id=project_id)
        if existing:
            logger.info("[video-enhance] Video already in library: task_id=%s", task_id)
            return

        final_url = video_url

        # 如果OSS可用，下载视频并上传到OSS
        if oss_service.is_available():
            try:
                logger.info("[video-enhance] Downloading video for OSS upload: task_id=%s url=%s", task_id, video_url)
                # 下载视频到临时文件
                response = requests.get(video_url, timeout=120, stream=True)
                response.raise_for_status()

                # 创建临时文件
                temp_dir = tempfile.gettempdir()
                temp_file = os.path.join(temp_dir, output_filename)

                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                logger.info("[video-enhance] Video downloaded to temp: %s", temp_file)

                # 上传到OSS
                oss_url = oss_service.upload_file(
                    temp_file,
                    user_id=user_id,
                    project_id=project_id,
                    file_type="video",
                )

                # 清理临时文件
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

                if oss_url:
                    final_url = oss_url
                    logger.info("[video-enhance] Video uploaded to OSS: %s", oss_url)

                    # 更新任务记录中的video_url
                    task["video_url"] = oss_url
                    database.save_video_enhance_task(task)
            except Exception as e:
                logger.error("[video-enhance] Failed to download/upload video: %s", e)
                # 如果下载/上传失败，继续使用原始URL

        meta = {
            "library_group": "video",
            "source": "video_enhance",
            "source_task_id": task_id,
            "resolution": task.get("resolution"),
            "source_filename": task.get("source_filename"),
            "source_video_id": task.get("source_video_id"),
        }
        if task.get("cover_url"):
            meta["cover_url"] = task.get("cover_url")

        database.save_video_asset(
            user_id=user_id,
            filename=output_filename,
            url=final_url,
            meta=meta,
            project_id=project_id,
        )
        logger.info("[video-enhance] Video saved to library: filename=%s url=%s", output_filename, final_url)

    def _decorate_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """装饰任务信息，添加显示字段。"""
        decorated = dict(task)

        # 确保JSON字段已解码
        for field in ("input_payload_json", "raw_response_json", "result_json", "usage_json"):
            if field not in decorated:
                decorated[field] = {}

        # 添加下载文件名
        if decorated.get("video_url"):
            decorated["download_filename"] = decorated.get("output_filename") or decorated.get("filename")

        return decorated


video_enhance_service = VideoEnhanceService()