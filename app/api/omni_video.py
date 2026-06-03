"""Omni video module APIs and pages."""

from __future__ import annotations

import logging
from io import BytesIO

import requests
import volcenginesdkbilling
import volcenginesdkcore
from flask import Blueprint, jsonify, render_template, request, send_file, session
from volcenginesdkcore.rest import ApiException

import database
from app.config import config
from app.decorators import handle_api_error, login_required
from app.services.omni_video_service import get_models_for_role, omni_video_service
from app.services.operation_log_service import log_balance_query

logger = logging.getLogger(__name__)
omni_video_bp = Blueprint("omni_video", __name__)


def _current_user_context() -> dict[str, object]:
    return {
        "username": session.get("username", ""),
        "id": session.get("user_id"),
        "role_code": session.get("role_code"),
    }


def _safe_log_payload(payload):
    return payload if isinstance(payload, dict) else {"value": payload}


@omni_video_bp.route("/omni-video")
@login_required
def omni_video_page():
    return render_template("omni_video.html", user=_current_user_context())


@omni_video_bp.route("/omni-video-tasks")
@login_required
def omni_video_tasks_page():
    return render_template("omni_video_tasks.html", user=_current_user_context())


@omni_video_bp.route("/api/omni-video/tasks", methods=["POST"])
@login_required
@handle_api_error
def create_omni_video_task():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    username = session.get("username")
    data = request.get_json(silent=True) or {}
    data["_user_id"] = user_id
    data["_project_id"] = project_id
    data["_public_origin"] = request.host_url.rstrip("/")
    data["_username"] = username
    logger.info(
        "[omni-video][create][request] user_id=%s project_id=%s model=%s payload=%s",
        user_id,
        project_id,
        data.get("model"),
        _safe_log_payload(data),
    )

    task = omni_video_service.create_task(user_id, project_id, data)
    logger.info(
        "[omni-video][create][response] task_id=%s status=%s task=%s",
        task.get("task_id"),
        task.get("status"),
        _safe_log_payload(task),
    )
    return (
        jsonify(
            {
                "success": True,
                "task": task,
                "task_id": task.get("task_id"),
                "message": "全能视频任务已创建",
            }
        ),
        201,
    )


@omni_video_bp.route("/api/omni-video/tasks", methods=["GET"])
@login_required
def list_omni_video_tasks():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 10, type=int)
    status = request.args.get("status") or None
    search = request.args.get("search") or None
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None
    sync_running = (request.args.get("sync_running", "false") or "false").lower() == "true"
    logger.info(
        "[omni-video][list][request] user_id=%s project_id=%s page=%s page_size=%s status=%s search=%s start_date=%s end_date=%s sync_running=%s",
        user_id,
        project_id,
        page,
        page_size,
        status,
        search,
        start_date,
        end_date,
        sync_running,
    )

    items, total = omni_video_service.list_tasks(
        user_id,
        project_id,
        status=status,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sync_running=sync_running,
    )
    logger.info(
        "[omni-video][list][response] total=%s items=%s", total, _safe_log_payload({"items": items})
    )
    return jsonify(
        {
            "success": True,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@omni_video_bp.route("/api/omni-video/tasks/<task_id>", methods=["GET"])
@login_required
def get_omni_video_task(task_id: str):
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    logger.info(
        "[omni-video][detail][request] user_id=%s project_id=%s task_id=%s",
        user_id,
        project_id,
        task_id,
    )

    task = omni_video_service.get_task(user_id, project_id, task_id)
    if not task:
        logger.warning("[omni-video][detail][response] task_id=%s not_found=true", task_id)
        return jsonify({"success": False, "error": "任务不存在"}), 404
    logger.info("[omni-video][detail][response] task=%s", _safe_log_payload(task))
    return jsonify({"success": True, "task": task})


@omni_video_bp.route("/api/omni-video/tasks/<task_id>/download", methods=["GET"])
@login_required
@handle_api_error
def download_omni_video_task(task_id: str):
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    logger.info(
        "[omni-video][download][request] user_id=%s project_id=%s task_id=%s",
        user_id,
        project_id,
        task_id,
    )

    task = omni_video_service.get_task(user_id, project_id, task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    video_url = task.get("video_url")
    if not video_url:
        return jsonify({"success": False, "error": "当前任务暂无可下载视频"}), 400

    filename = task.get("download_filename") or f"{task_id}.mp4"
    try:
        response = requests.get(video_url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception(
            "[omni-video][download][error] task_id=%s video_url=%s error=%s",
            task_id,
            video_url,
            exc,
        )
        raise ValueError("视频下载失败，请稍后重试") from exc

    mimetype = response.headers.get("Content-Type") or "video/mp4"
    logger.info(
        "[omni-video][download][response] task_id=%s status=%s content_type=%s content_length=%s filename=%s",
        task_id,
        response.status_code,
        mimetype,
        response.headers.get("Content-Length"),
        filename,
    )
    return send_file(
        BytesIO(response.content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@omni_video_bp.route("/api/omni-video/tasks/<task_id>/refresh", methods=["POST"])
@login_required
@handle_api_error
def refresh_omni_video_task(task_id: str):
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    logger.info(
        "[omni-video][refresh][request] user_id=%s project_id=%s task_id=%s",
        user_id,
        project_id,
        task_id,
    )

    task = omni_video_service.refresh_task(user_id, project_id, task_id)
    logger.info("[omni-video][refresh][response] task=%s", _safe_log_payload(task))
    return jsonify({"success": True, "task": task, "message": "任务状态已刷新"})


@omni_video_bp.route("/api/omni-video/tasks/<task_id>/cancel", methods=["POST"])
@login_required
@handle_api_error
def cancel_omni_video_task(task_id: str):
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    logger.info(
        "[omni-video][cancel][request] user_id=%s project_id=%s task_id=%s",
        user_id,
        project_id,
        task_id,
    )

    task = omni_video_service.cancel_task(user_id, project_id, task_id)
    logger.info("[omni-video][cancel][response] task=%s", _safe_log_payload(task))
    return jsonify({"success": True, "task": task, "message": "任务已取消"})


@omni_video_bp.route("/api/omni-video/tasks/batch-delete", methods=["POST"])
@login_required
@handle_api_error
def batch_delete_omni_video_tasks():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}
    task_ids = data.get("task_ids") or []
    if not isinstance(task_ids, list):
        return jsonify({"success": False, "error": "task_ids 参数格式错误"}), 400

    cleaned_task_ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
    if not cleaned_task_ids:
        return jsonify({"success": False, "error": "请选择要删除的任务"}), 400

    deleted = 0
    failed: list[str] = []
    for task_id in cleaned_task_ids:
        try:
            if omni_video_service.delete_task(user_id, project_id, task_id):
                deleted += 1
            else:
                failed.append(task_id)
        except Exception:
            logger.exception("[omni-video][batch-delete][error] task_id=%s", task_id)
            failed.append(task_id)

    return jsonify(
        {
            "success": True,
            "deleted": deleted,
            "failed": failed,
            "message": f"已删除 {deleted} 个任务",
        }
    )


@omni_video_bp.route("/api/omni-video/tasks/<task_id>", methods=["DELETE"])
@login_required
def delete_omni_video_task(task_id: str):
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    logger.info(
        "[omni-video][delete][request] user_id=%s project_id=%s task_id=%s",
        user_id,
        project_id,
        task_id,
    )

    deleted = omni_video_service.delete_task(user_id, project_id, task_id)
    logger.info("[omni-video][delete][response] task_id=%s deleted=%s", task_id, deleted)
    if not deleted:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    return jsonify({"success": True, "message": "任务已删除"})


@omni_video_bp.route("/api/omni-video/config", methods=["GET"])
@login_required
def get_omni_video_config():
    configured = omni_video_service.is_configured()
    role_code = session.get("role_code")
    models = get_models_for_role(role_code)
    default_model = models[0] if models else None
    logger.info("[omni-video][config] configured=%s", configured)
    return jsonify(
        {
            "success": True,
            "configured": configured,
            "models": models,
            "default_model": default_model,
            "model_aliases": config.get_omni_model_alias_map(),
            "role_code": role_code,
        }
    )


@omni_video_bp.route("/api/omni-video/balance", methods=["GET"])
@login_required
def get_volcengine_balance():
    """查询火山引擎账户余额"""
    import time

    start_time = time.time()
    user_id = session.get("user_id")
    username = session.get("username")
    role_code = session.get("role_code")

    if role_code == database.ROLE_EXTERNAL_USER:
        user = database.get_user_by_id(user_id)
        user_balance_cent = user.get("balance_cent", 0) if user else 0
        return jsonify(
            {
                "success": True,
                "role_code": role_code,
                "balance_type": "user",
                "available_balance": float(user_balance_cent or 0) / 100.0,
            }
        )

    if not config.is_volcengine_configured():
        log_balance_query(
            user_id=user_id,
            username=username,
            service_name="volcengine",
            success=False,
            error="火山引擎配置缺失",
        )
        return jsonify({"success": False, "error": "火山引擎配置缺失"}), 400

    try:
        configuration = volcenginesdkcore.Configuration()
        configuration.ak = config.VOLCENGINE_AK
        configuration.sk = config.VOLCENGINE_SK
        configuration.region = "cn-beijing"
        volcenginesdkcore.Configuration.set_default(configuration)

        api_instance = volcenginesdkbilling.BILLINGApi()
        request_body = volcenginesdkbilling.QueryBalanceAcctRequest()
        result = api_instance.query_balance_acct(request_body)

        # 解析返回结果
        balance = 0
        if hasattr(result, "available_balance"):
            balance = float(result.available_balance) if result.available_balance else 0
        elif hasattr(result, "balance_amount"):
            balance = float(result.balance_amount) if result.balance_amount else 0
        elif hasattr(result, "result") and hasattr(result.result, "available_balance"):
            balance = (
                float(result.result.available_balance) if result.result.available_balance else 0
            )

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info("[omni-video][balance] balance=%s", balance)

        log_balance_query(
            user_id=user_id,
            username=username,
            service_name="volcengine",
            available_balance=balance,
            success=True,
            duration_ms=duration_ms,
        )

        return jsonify(
            {
                "success": True,
                "role_code": role_code,
                "balance_type": "system",
                "available_balance": balance,
            }
        )
    except ApiException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_str = str(e)
        logger.error("[omni-video][balance] API error: %s", e)
        log_balance_query(
            user_id=user_id,
            username=username,
            service_name="volcengine",
            success=False,
            duration_ms=duration_ms,
            error=f"API错误: {error_str}",
        )
        return jsonify({"success": False, "error": f"API错误: {e}"}), 500
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_str = str(e)
        logger.error("[omni-video][balance] error: %s", e)
        log_balance_query(
            user_id=user_id,
            username=username,
            service_name="volcengine",
            success=False,
            duration_ms=duration_ms,
            error=f"查询失败: {error_str}",
        )
        return jsonify({"success": False, "error": f"查询失败: {e}"}), 500
