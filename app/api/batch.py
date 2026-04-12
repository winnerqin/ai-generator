"""Batch generation and records APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

import database
from app.decorators import handle_api_error, login_required
from app.utils import ApiResponse

batch_bp = Blueprint("batch", __name__)


@batch_bp.route("/batch")
@login_required
def batch_page():
    from flask import render_template

    user = {"username": session.get("username", "")}
    return render_template("batch.html", user=user)


@batch_bp.route("/records")
@login_required
def records_page():
    from flask import render_template

    user = {"username": session.get("username", "")}
    return render_template("records.html", user=user)


@batch_bp.route("/api/batch-generate", methods=["POST"])
@login_required
@handle_api_error
def batch_generate():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}
    tasks = data.get("tasks", [])

    if not tasks:
        return ApiResponse.bad_request("\u4efb\u52a1\u5217\u8868\u4e0d\u80fd\u4e3a\u7a7a")

    batch_id = database.create_batch_task(user_id, project_id, tasks)
    return ApiResponse.created(
        {"batch_id": batch_id, "task_count": len(tasks)},
        "\u6279\u91cf\u4efb\u52a1\u5df2\u521b\u5efa",
    )


@batch_bp.route("/api/batch-generate-all", methods=["POST"])
@login_required
@handle_api_error
def batch_generate_all():
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id")

    if not batch_id:
        return ApiResponse.bad_request("\u6279\u91cf\u4efb\u52a1ID\u4e0d\u80fd\u4e3a\u7a7a")

    database.execute_batch_tasks(user_id, batch_id)
    return ApiResponse.success(None, "\u6279\u91cf\u751f\u6210\u5df2\u5f00\u59cb")


@batch_bp.route("/api/batch-progress/<batch_id>", methods=["GET"])
@login_required
def get_batch_progress(batch_id: str):
    user_id = session.get("user_id")
    progress = database.get_batch_progress(user_id, batch_id)
    return ApiResponse.success(progress)


@batch_bp.route("/api/records", methods=["GET"])
@login_required
def get_records():
    """Return generation records in the legacy flat payload expected by the UI."""

    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    search = (request.args.get("search") or "").strip().lower()

    if limit is None:
        limit = page_size
    if offset is None:
        offset = max(page - 1, 0) * limit

    records = database.get_all_records(user_id, project_id, limit=limit, offset=offset)
    total = database.get_total_count(user_id, project_id)

    if search:
        filtered = []
        for record in records:
            prompt = (record.get("prompt") or "").lower()
            filename = (record.get("filename") or "").lower()
            if search in prompt or search in filename:
                filtered.append(record)
        records = filtered

    response_payload = {
        "success": True,
        "records": records,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": {
            "records": records,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }
    return jsonify(response_payload)


@batch_bp.route("/api/records/<int:record_id>", methods=["DELETE"])
@login_required
def delete_record(record_id: int):
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    record = database.get_record_by_id(record_id)
    if not record or record.get("user_id") != user_id:
        return ApiResponse.not_found("\u8bb0\u5f55\u4e0d\u5b58\u5728")

    database.delete_record(record_id, user_id=user_id, project_id=project_id)
    return jsonify({"success": True, "message": "\u5220\u9664\u6210\u529f"})


@batch_bp.route("/api/batch-delete", methods=["POST"])
@login_required
def batch_delete():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}
    record_ids = data.get("ids", [])

    if not record_ids:
        return ApiResponse.bad_request("\u8bb0\u5f55ID\u5217\u8868\u4e0d\u80fd\u4e3a\u7a7a")

    deleted_count = 0
    for record_id in record_ids:
        try:
            rid = int(record_id)
        except (TypeError, ValueError):
            continue

        record = database.get_record_by_id(rid)
        if not record or record.get("user_id") != user_id:
            continue
        database.delete_record(rid, user_id=user_id, project_id=project_id)
        deleted_count += 1

    return ApiResponse.success(
        {"deleted_count": deleted_count},
        f"\u5df2\u5220\u9664 {deleted_count} \u6761\u8bb0\u5f55",
    )


@batch_bp.route("/api/download-file", methods=["GET"])
@login_required
def download_file():
    import os
    from flask import send_file

    file_path = request.args.get("path")
    if not file_path:
        return ApiResponse.bad_request("\u6587\u4ef6\u8def\u5f84\u4e0d\u80fd\u4e3a\u7a7a")

    if not os.path.exists(file_path):
        return ApiResponse.not_found("\u6587\u4ef6\u4e0d\u5b58\u5728")

    return send_file(file_path, as_attachment=True)
