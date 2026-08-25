"""Wan 3.0 pages and APIs."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, render_template, request, session

import database
from app.config import config
from app.decorators import handle_api_error, login_required
from app.services.wan_video_service import SOURCE, _default_model, _models, wan_video_service
from app.services.aliyun_balance_service import aliyun_balance_service
from app.services.operation_log_service import log_balance_query

wan_video_bp = Blueprint("wan_video", __name__)


def _task(task_id: str, user_id: int, project_id: int | None = None):
    task = database.get_omni_video_task(task_id, user_id=user_id, project_id=project_id)
    if not task or task.get("source") != SOURCE:
        raise ValueError("Wan 视频任务不存在。")
    return task


@wan_video_bp.route("/wan-video")
@login_required
def page():
    return render_template("wan_video.html", active_page="wan_video", user={
        "id": session.get("user_id"), "username": session.get("username", ""),
        "role_code": session.get("role_code", ""),
    })


@wan_video_bp.route("/api/wan-video/config")
@login_required
def get_config():
    return jsonify({
        "success": True,
        "configured": bool(
            config.DASHSCOPE_API_KEY or config.DASHSCOPE_API_KEY_POOL
            or config.DASHSCOPE_INTL_API_KEY or config.DASHSCOPE_INTL_API_KEY_POOL
        ),
        "models": _models(), "default_model": _default_model(),
        "model_aliases": {
            model: ("WAN3.0-video国际版" if model == config.WAN_VIDEO_INTL_MODEL
                    else "WAN3.0-video国内版")
            for model in _models()
        },
        "modes": ["text_to_video", "image_to_video_first", "image_to_video_first_last", "reference_to_video"],
    })


@wan_video_bp.route("/api/wan-video/balance")
@login_required
def get_aliyun_balance():
    user_id = session.get("user_id")
    username = session.get("username")
    role_code = session.get("role_code")
    if role_code == database.ROLE_EXTERNAL_USER:
        user = database.get_user_by_id(user_id) or {}
        balance_cent = int(user.get("balance_cent") or 0)
        balance_yuan = f"{balance_cent / 100:.2f}"
        return jsonify({
            "success": True,
            "role_code": role_code,
            "balance_type": "user",
            "available_amount": balance_yuan,
            "available_cash_amount": balance_yuan,
            "currency": database.MODEL_CURRENCY_CNY,
        })
    try:
        result = aliyun_balance_service.query(
            force=(request.args.get("refresh") or "").lower() == "true"
        )
        log_balance_query(
            user_id=user_id, username=username, service_name="aliyun_bss",
            available_balance=float(result["available_amount"]), success=True,
        )
        return jsonify({
            "success": True, "role_code": role_code,
            "balance_type": "system", **result,
        })
    except Exception as exc:
        log_balance_query(
            user_id=user_id, username=username, service_name="aliyun_bss",
            success=False, error=str(exc),
        )
        return jsonify({"success": False, "error": str(exc)}), 400


@wan_video_bp.route("/api/wan-video/tasks", methods=["POST"])
@login_required
@handle_api_error
def create_task():
    data = request.get_json(silent=True) or {}
    user_id = int(session["user_id"])
    project_id = session.get("current_project_id")
    client_request_id = str(data.get("client_request_id") or "").strip()
    if client_request_id:
        existing = database.get_omni_video_task_by_client_request_id(user_id, client_request_id, SOURCE)
        if existing:
            return jsonify({"success": True, "task": existing, "idempotent": True})
    task = wan_video_service.create_task(data, user_id=user_id, project_id=project_id)
    return jsonify({"success": True, "task": task}), 201


@wan_video_bp.route("/api/wan-video/tasks/<task_id>")
@login_required
@handle_api_error
def get_task(task_id):
    return jsonify({"success": True, "task": _task(task_id, int(session["user_id"]))})


@wan_video_bp.route("/api/wan-video/tasks/<task_id>/refresh", methods=["POST"])
@login_required
@handle_api_error
def refresh_task(task_id):
    task = _task(task_id, int(session["user_id"]))
    return jsonify({"success": True, "task": wan_video_service.refresh_task(task)})


@wan_video_bp.route("/api/wan-video/tasks/<task_id>/cancel", methods=["POST"])
@login_required
@handle_api_error
def cancel_task(task_id):
    task = _task(task_id, int(session["user_id"]))
    return jsonify({"success": True, "task": wan_video_service.cancel_task(task)})


def _external_context(data):
    # Reuse the established JWT/API-key and project access contract.
    from app.api.omni_video import _external_auth_context, _resolve_external_project_id
    auth, error = _external_auth_context()
    if error:
        return None, None, error
    try:
        project_id = _resolve_external_project_id(auth, data)
    except Exception as exc:
        return None, None, (jsonify({"success": False, "error": str(exc)}), 403)
    return auth, project_id, None


@wan_video_bp.route("/api/external/wan-video/tasks", methods=["POST"])
def external_create_task():
    data = request.get_json(silent=True) or {}
    auth, project_id, error = _external_context(data)
    if error:
        return error
    try:
        client_request_id = str(data.get("client_request_id") or "").strip()
        if client_request_id:
            existing = database.get_omni_video_task_by_client_request_id(int(auth["user_id"]), client_request_id, SOURCE)
            if existing:
                return jsonify({"success": True, "task": existing, "idempotent": True})
        task = wan_video_service.create_task(data, user_id=int(auth["user_id"]), project_id=project_id)
        return jsonify({"success": True, "task": task}), 201
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@wan_video_bp.route("/api/external/wan-video/tasks/batch", methods=["POST"])
def external_create_batch():
    body = request.get_json(silent=True) or {}
    auth, project_id, error = _external_context(body)
    if error:
        return error
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"success": False, "error": "items 不能为空"}), 400
    batch_id = str(body.get("batch_id") or f"wan-{uuid.uuid4().hex}")
    created, errors = [], []
    for index, item in enumerate(items):
        try:
            payload = {**item, "batch_id": batch_id, "callback_url": body.get("callback_url")}
            created.append(wan_video_service.create_task(payload, user_id=int(auth["user_id"]), project_id=project_id))
        except Exception as exc:
            errors.append({"index": index, "error": str(exc)})
    return jsonify({"success": not errors, "batch_id": batch_id, "tasks": created, "errors": errors}), (201 if created else 400)


@wan_video_bp.route("/api/external/wan-video/tasks/<task_id>")
def external_get_task(task_id):
    auth, project_id, error = _external_context(request.args.to_dict())
    if error:
        return error
    try:
        return jsonify({"success": True, "task": _task(task_id, int(auth["user_id"]), project_id)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


@wan_video_bp.route("/api/external/wan-video/tasks/<task_id>/cancel", methods=["POST"])
def external_cancel_task(task_id):
    auth, project_id, error = _external_context(request.get_json(silent=True) or {})
    if error:
        return error
    try:
        task = _task(task_id, int(auth["user_id"]), project_id)
        return jsonify({"success": True, "task": wan_video_service.cancel_task(task)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@wan_video_bp.route("/api/external/wan-video/batches/<batch_id>")
def external_get_batch(batch_id):
    auth, project_id, error = _external_context(request.args.to_dict())
    if error:
        return error
    tasks = database.get_omni_video_tasks(int(auth["user_id"]), project_id=project_id, batch_id=batch_id, limit=1000)
    tasks = [task for task in tasks if task.get("source") == SOURCE]
    return jsonify({"success": True, "batch_id": batch_id, "tasks": tasks})
