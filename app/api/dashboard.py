"""Role-aware dashboard page and API."""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, session

import database
from app.decorators import login_required


dashboard_bp = Blueprint("dashboard", __name__)


def _is_admin() -> bool:
    return session.get("role_code") == database.ROLE_SYSTEM_ADMIN or session.get("username") == "system_admin"


def _date_range() -> tuple[datetime, datetime, str]:
    now = datetime.now()
    period = (request.args.get("period") or "7d").lower()
    if period == "custom":
        try:
            start = datetime.strptime(request.args.get("start_date", ""), "%Y-%m-%d")
            end = datetime.strptime(request.args.get("end_date", ""), "%Y-%m-%d") + timedelta(days=1)
        except ValueError as exc:
            raise ValueError("自定义日期必须使用 YYYY-MM-DD 格式") from exc
        if start >= end or (end - start).days > 366:
            raise ValueError("日期范围无效或超过 366 天")
        return start, end, period
    days = 30 if period == "30d" else 7
    return now - timedelta(days=days - 1), now + timedelta(days=1), f"{days}d"


@dashboard_bp.route("/dashboard")
@login_required
def dashboard_page():
    user = {
        "username": session.get("username", ""),
        "id": session.get("user_id"),
        "role_code": session.get("role_code", ""),
    }
    return render_template("dashboard.html", user=user)


@dashboard_bp.route("/api/dashboard")
@login_required
def dashboard_data():
    try:
        start, end, period = _date_range()
        admin = _is_admin()
        requested_project = request.args.get("project_id")
        project_id = session.get("current_project_id")
        if requested_project not in (None, ""):
            project_id = int(requested_project)
            if not admin and not database.has_project_access(session["user_id"], project_id):
                return jsonify({"success": False, "error": "无权访问该项目"}), 403
        global_scope = admin and request.args.get("scope") == "global"
        data = database.get_dashboard_data(
            user_id=None if admin else session["user_id"],
            project_id=None if global_scope else project_id,
            start_at=start,
            end_at=end,
            include_admin=admin,
            stale_minutes=30,
        )
        data["context"] = {
            "role_code": session.get("role_code"),
            "is_admin": admin,
            "project_id": project_id,
            "scope": "global" if global_scope else "project",
            "period": period,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return jsonify({"success": True, **data})
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
