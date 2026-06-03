"""Omni video module APIs and pages."""

from __future__ import annotations

import logging
import os
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
from app.utils.jwt_auth import JWTAuth

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


def _first_project_id(user_id: int | None) -> int | None:
    if not user_id:
        return None
    try:
        projects = database.get_user_projects(user_id)
    except Exception:
        return None
    return projects[0].get("id") if projects else None


def _env_api_key_context(api_key: str) -> dict[str, object] | None:
    raw = os.environ.get("EXTERNAL_OMNI_API_KEYS", "")
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        parts = item.split(":")
        if len(parts) < 2 or parts[0] != api_key:
            continue
        try:
            user_id = int(parts[1])
        except (TypeError, ValueError):
            return None
        project_id = None
        if len(parts) >= 3 and parts[2].strip():
            try:
                project_id = int(parts[2])
            except (TypeError, ValueError):
                project_id = None
        user = database.get_user_by_id(user_id) or {}
        return {
            "auth_type": "api_key",
            "user_id": user_id,
            "username": user.get("username") or f"api_user_{user_id}",
            "project_id": project_id,
        }
    return None


def _external_auth_context() -> tuple[dict[str, object] | None, tuple[object, int] | None]:
    user = JWTAuth.get_current_user()
    if user:
        try:
            user_id = int(user.get("user_id"))
        except (TypeError, ValueError):
            return None, (jsonify({"success": False, "error": "无效的认证用户"}), 401)
        db_user = database.get_user_by_id(user_id) or {}
        return (
            {
                "auth_type": "jwt",
                "user_id": user_id,
                "username": db_user.get("username") or user.get("username"),
                "project_id": None,
            },
            None,
        )

    api_key = request.headers.get("X-API-Key") or ""
    auth_header = request.headers.get("Authorization") or ""
    if not api_key and auth_header.lower().startswith("apikey "):
        api_key = auth_header.split(" ", 1)[1].strip()
    if not api_key and auth_header.lower().startswith("bearer "):
        api_key = auth_header.split(" ", 1)[1].strip()
    if not api_key:
        return None, (jsonify({"success": False, "error": "缺少认证凭据"}), 401)

    key_record = database.get_external_api_key(api_key)
    if key_record:
        return (
            {
                "auth_type": "api_key",
                "user_id": int(key_record.get("user_id")),
                "username": key_record.get("username"),
                "project_id": key_record.get("project_id"),
            },
            None,
        )

    env_context = _env_api_key_context(api_key)
    if env_context:
        return env_context, None
    return None, (jsonify({"success": False, "error": "无效的 API Key"}), 401)


def _resolve_external_project_id(
    auth_context: dict[str, object], payload: dict[str, object]
) -> int | None:
    user_id = int(auth_context["user_id"])
    auth_project_id = auth_context.get("project_id")
    requested_project_id = payload.get("project_id")
    project_id = requested_project_id if requested_project_id not in (None, "") else auth_project_id
    if project_id in (None, ""):
        return _first_project_id(user_id)
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise PermissionError("project_id 参数无效") from exc
    if not database.has_project_access(user_id, project_id):
        raise PermissionError("无权访问指定项目")
    return project_id


def _status_code_for_error(exc: Exception) -> int:
    if isinstance(exc, PermissionError):
        return 403
    if "余额不足" in str(exc):
        return 402
    if isinstance(exc, ValueError):
        return 400
    return 500


def _external_task_payload(task: dict[str, object] | None) -> dict[str, object] | None:
    if not task:
        return None
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "batch_id": task.get("batch_id"),
        "client_request_id": task.get("client_request_id"),
        "prompt": task.get("prompt"),
        "model": task.get("model"),
        "resolution": task.get("resolution"),
        "aspect_ratio": task.get("aspect_ratio"),
        "duration": task.get("duration"),
        "frame_count": task.get("frame_count"),
        "seed": task.get("seed"),
        "video_url": task.get("video_url"),
        "cover_url": task.get("cover_url"),
        "first_frame_url": task.get("first_frame_url"),
        "last_frame_url": task.get("last_frame_url"),
        "fail_reason": task.get("fail_reason"),
        "token_usage": task.get("token_usage"),
        "amount_yuan": task.get("amount_yuan"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


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
    batch_id = request.args.get("batch_id") or None
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
        batch_id=batch_id,
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


@omni_video_bp.route("/api/external/omni-video/tasks/batch", methods=["POST"])
@handle_api_error
def external_batch_create_omni_video_tasks():
    auth_context, auth_error = _external_auth_context()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    tasks = payload.get("tasks") or []
    if not isinstance(tasks, list) or not tasks:
        return jsonify({"success": False, "error": "tasks 参数必须是非空数组"}), 400
    if len(tasks) > 50:
        return jsonify({"success": False, "error": "单次最多提交 50 个任务"}), 400

    user_id = int(auth_context["user_id"])
    username = auth_context.get("username")
    project_id = _resolve_external_project_id(auth_context, payload)
    batch_id = str(payload.get("batch_id") or "").strip() or None
    callback_url = str(payload.get("callback_url") or "").strip() or None
    public_origin = request.host_url.rstrip("/")

    items = []
    created = 0
    reused = 0
    failed = 0
    for index, raw_task in enumerate(tasks):
        client_request_id = ""
        try:
            if not isinstance(raw_task, dict):
                raise ValueError("任务参数必须是对象")
            task_data = dict(raw_task)
            client_request_id = str(task_data.get("client_request_id") or "").strip()
            if client_request_id:
                existing = database.get_omni_video_task_by_client_request_id(
                    user_id, client_request_id, source="external_api"
                )
                if existing:
                    reused += 1
                    items.append(
                        {
                            "index": index,
                            "client_request_id": client_request_id,
                            "task_id": existing.get("task_id"),
                            "status": existing.get("status"),
                            "status_code": 200,
                            "idempotent": True,
                            "message": "任务已存在",
                        }
                    )
                    continue

            task_data["batch_id"] = batch_id
            task_data["client_request_id"] = client_request_id or None
            task_data["source"] = "external_api"
            task_data["callback_url"] = task_data.get("callback_url") or callback_url
            task_data["_user_id"] = user_id
            task_data["_project_id"] = project_id
            task_data["_public_origin"] = public_origin
            task_data["_username"] = username

            task = omni_video_service.create_task(user_id, project_id, task_data)
            created += 1
            items.append(
                {
                    "index": index,
                    "client_request_id": client_request_id or None,
                    "task_id": task.get("task_id"),
                    "status": task.get("status"),
                    "status_code": 201,
                    "idempotent": False,
                    "message": "任务创建成功",
                }
            )
        except Exception as exc:
            failed += 1
            status_code = _status_code_for_error(exc)
            logger.exception(
                "[omni-video][external-batch][item-error] user_id=%s batch_id=%s index=%s",
                user_id,
                batch_id,
                index,
            )
            items.append(
                {
                    "index": index,
                    "client_request_id": client_request_id or None,
                    "task_id": None,
                    "status": "failed",
                    "status_code": status_code,
                    "idempotent": False,
                    "error": str(exc),
                }
            )

    response_status = 201 if failed == 0 else 207
    return (
        jsonify(
            {
                "success": failed == 0,
                "batch_id": batch_id,
                "created": created,
                "reused": reused,
                "failed": failed,
                "items": items,
            }
        ),
        response_status,
    )


@omni_video_bp.route("/api/external/omni-video/tasks/<task_id>", methods=["GET"])
@handle_api_error
def external_get_omni_video_task(task_id: str):
    auth_context, auth_error = _external_auth_context()
    if auth_error:
        return auth_error

    user_id = int(auth_context["user_id"])
    project_id = _resolve_external_project_id(auth_context, request.args)
    sync = (request.args.get("sync", "true") or "true").lower() in {"1", "true", "yes", "on"}
    task = (
        omni_video_service.get_task(user_id, project_id, task_id)
        if sync
        else database.get_omni_video_task(task_id, user_id=user_id, project_id=project_id)
    )
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    return jsonify({"success": True, "task": _external_task_payload(task)})


@omni_video_bp.route("/api/external/omni-video/batches/<batch_id>", methods=["GET"])
@handle_api_error
def external_list_omni_video_batch_tasks(batch_id: str):
    auth_context, auth_error = _external_auth_context()
    if auth_error:
        return auth_error

    user_id = int(auth_context["user_id"])
    project_id = _resolve_external_project_id(auth_context, request.args)
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 100)
    status = request.args.get("status") or None
    sync_running = (request.args.get("sync_running", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    items, total = omni_video_service.list_tasks(
        user_id,
        project_id,
        status=status,
        batch_id=batch_id,
        page=page,
        page_size=page_size,
        sync_running=sync_running,
    )
    return jsonify(
        {
            "success": True,
            "batch_id": batch_id,
            "items": [_external_task_payload(item) for item in items],
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
