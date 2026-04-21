"""Video enhance APIs and pages."""

from __future__ import annotations

from io import BytesIO
import logging
import mimetypes

import requests
from flask import Blueprint, jsonify, render_template, request, send_file, session

from app.decorators import handle_api_error, login_required
from app.services.video_enhance_service import video_enhance_service

logger = logging.getLogger(__name__)
video_enhance_bp = Blueprint("video_enhance", __name__)


def _current_user_context() -> dict[str, object]:
    return {"username": session.get("username", ""), "id": session.get("user_id")}


def _safe_log_payload(payload):
    return payload if isinstance(payload, dict) else {"value": payload}


@video_enhance_bp.route("/enhance-tasks")
@login_required
def enhance_tasks_page():
    """增强任务列表页面。"""
    return render_template("enhance_tasks.html", user=_current_user_context())


@video_enhance_bp.route("/api/video-enhance/tasks", methods=["POST"])
@login_required
@handle_api_error
def create_enhance_task():
    """创建画质增强任务。"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}

    source_video_url = (data.get("source_video_url") or "").strip()
    source_video_id = data.get("source_video_id")
    source_filename = (data.get("source_filename") or "").strip()
    tool_version = (data.get("tool_version") or "standard").strip().lower()
    resolution = (data.get("resolution") or "1080p").strip().lower()

    logger.info(
        "[video-enhance][create][request] user_id=%s project_id=%s source_video_url=%s tool_version=%s resolution=%s source_filename=%s",
        user_id,
        project_id,
        source_video_url,
        tool_version,
        resolution,
        source_filename,
    )

    task = video_enhance_service.create_task(
        user_id=user_id,
        project_id=project_id,
        source_video_url=source_video_url,
        source_video_id=source_video_id,
        source_filename=source_filename,
        tool_version=tool_version,
        resolution=resolution,
    )

    logger.info(
        "[video-enhance][create][response] task_id=%s status=%s",
        task.get("task_id"),
        task.get("status"),
    )

    return jsonify({
        "success": True,
        "task": task,
        "task_id": task.get("task_id"),
        "message": "画质增强任务已创建",
    }), 201


@video_enhance_bp.route("/api/video-enhance/tasks", methods=["GET"])
@login_required
@handle_api_error
def list_enhance_tasks():
    """查询增强任务列表。"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 10, type=int)
    status = request.args.get("status") or None
    search = request.args.get("search") or None
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None

    logger.info(
        "[video-enhance][list][request] user_id=%s project_id=%s page=%s page_size=%s status=%s search=%s",
        user_id,
        project_id,
        page,
        page_size,
        status,
        search,
    )

    items, total = video_enhance_service.list_tasks(
        user_id,
        project_id,
        status=status,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    return jsonify({
        "success": True,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@video_enhance_bp.route("/api/video-enhance/tasks/<task_id>", methods=["GET"])
@login_required
@handle_api_error
def get_enhance_task(task_id: str):
    """获取增强任务详情。"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    task = video_enhance_service.get_task(user_id, project_id, task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    return jsonify({"success": True, "task": task})


@video_enhance_bp.route("/api/video-enhance/tasks/<task_id>/refresh", methods=["POST"])
@login_required
@handle_api_error
def refresh_enhance_task(task_id: str):
    """刷新增强任务状态。"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    task = video_enhance_service.refresh_task(user_id, project_id, task_id)

    return jsonify({
        "success": True,
        "task": task,
        "message": "任务状态已刷新",
    })


@video_enhance_bp.route("/api/video-enhance/tasks/<task_id>", methods=["DELETE"])
@login_required
@handle_api_error
def delete_enhance_task(task_id: str):
    """删除增强任务。"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    deleted = video_enhance_service.delete_task(user_id, project_id, task_id)
    if not deleted:
        return jsonify({"success": False, "error": "任务不存在或无权删除"}), 404

    return jsonify({"success": True, "message": "任务已删除"})


@video_enhance_bp.route("/api/video-enhance/tasks/<task_id>/download", methods=["GET"])
@login_required
@handle_api_error
def download_enhance_task(task_id: str):
    """下载增强后的视频。"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    task = video_enhance_service.get_task(user_id, project_id, task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    video_url = task.get("video_url")
    if not video_url:
        return jsonify({"success": False, "error": "视频尚未生成完成"}), 400

    filename = task.get("download_filename") or task.get("output_filename") or f"{task_id}.mp4"

    try:
        response = requests.get(video_url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("[video-enhance][download][error] task_id=%s video_url=%s error=%s", task_id, video_url, exc)
        return jsonify({"success": False, "error": f"下载失败: {exc}"}), 502

    mimetype = response.headers.get("Content-Type") or mimetypes.guess_type(filename)[0] or "video/mp4"
    return send_file(
        BytesIO(response.content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )