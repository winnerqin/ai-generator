"""Project management API."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

import database
from app.decorators import login_required

projects_bp = Blueprint("projects", __name__)


def user_has_project(user_id, project_id) -> bool:
    """Return whether the user can access the given project."""
    projects = database.get_user_projects(user_id)
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        return False
    return any(project.get("id") == pid for project in projects)


@projects_bp.route("/api/projects", methods=["GET"])
@login_required
def get_projects():
    user_id = session.get("user_id")
    projects = database.get_user_projects(user_id)
    current_project_id = session.get("current_project_id")
    return jsonify(
        {
            "success": True,
            "projects": projects,
            "current_project_id": current_project_id,
        }
    )


@projects_bp.route("/api/projects/switch", methods=["POST"])
@login_required
def switch_project():
    user_id = session.get("user_id")
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")

    if project_id in (None, ""):
        return jsonify({"success": False, "error": "\u9879\u76eeID\u4e0d\u80fd\u4e3a\u7a7a"}), 400

    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "\u9879\u76eeID\u683c\u5f0f\u9519\u8bef"}), 400

    if not user_has_project(user_id, pid):
        return jsonify({"success": False, "error": "\u65e0\u6743\u8bbf\u95ee\u8be5\u9879\u76ee"}), 403

    session["current_project_id"] = pid
    project = database.get_project_by_id(pid) or {}
    session["current_project_name"] = project.get("name")

    return jsonify(
        {
            "success": True,
            "project_id": pid,
            "message": "\u9879\u76ee\u5207\u6362\u6210\u529f",
        }
    )


@projects_bp.route("/api/projects", methods=["POST"])
@login_required
def create_project():
    user_id = session.get("user_id")
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()

    if not name:
        return jsonify({"success": False, "error": "\u9879\u76ee\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a"}), 400

    project_id = database.create_project(name, user_id)
    database.assign_user_to_project(user_id, project_id)

    return jsonify(
        {
            "success": True,
            "id": project_id,
            "name": name,
            "message": "\u9879\u76ee\u521b\u5efa\u6210\u529f",
        }
    )


@projects_bp.route("/api/projects/<int:project_id>", methods=["DELETE"])
@login_required
def delete_project(project_id: int):
    user_id = session.get("user_id")
    project = database.get_project_by_id(project_id)

    if not project:
        return jsonify({"success": False, "error": "\u9879\u76ee\u4e0d\u5b58\u5728"}), 404

    is_owner = (
        project.get("owner_id") == user_id
        or project.get("owner") == user_id
        or project.get("created_by") == user_id
    )
    is_admin = session.get("username") == "system_admin"
    if not is_owner and not is_admin:
        return jsonify({"success": False, "error": "\u65e0\u6743\u5220\u9664\u8be5\u9879\u76ee"}), 403

    database.delete_project(project_id)

    current_project_id = session.get("current_project_id")
    if current_project_id is not None and int(current_project_id) == project_id:
        session.pop("current_project_id", None)
        session.pop("current_project_name", None)

    return jsonify({"success": True, "message": "\u9879\u76ee\u5220\u9664\u6210\u529f"})
