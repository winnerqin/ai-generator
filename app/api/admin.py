"""
管理员 API
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, session

import database
from app.decorators import admin_required, handle_api_error, login_required

# 创建蓝图
admin_bp = Blueprint("admin", __name__)


def calculate_date_range(period, start_date=None, end_date=None):
    """计算日期范围"""
    today = datetime.now().date()

    if period == 'day':
        start = today
        end = today
    elif period == 'week':
        start = today - timedelta(days=6)
        end = today
    elif period == 'month':
        start = today - timedelta(days=29)
        end = today
    else:  # custom
        # start_date 和 end_date 已经是字符串格式
        return start_date or today.strftime('%Y-%m-%d'), end_date or today.strftime('%Y-%m-%d')

    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


@admin_bp.route("/admin")
@login_required
@admin_required
def admin_page():
    """管理员页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("admin.html", user=user)


@admin_bp.route("/stats")
@login_required
@admin_required
def stats_page():
    """统计页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("stats.html", user=user)


@admin_bp.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_users():
    """获取所有用户"""
    users = database.get_all_users()
    return jsonify({"success": True, "users": users})


@admin_bp.route("/api/admin/users", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def create_user():
    """创建用户"""
    username = request.json.get("username", "").strip()
    password = request.json.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400

    if len(username) < 3:
        return jsonify({"success": False, "error": "用户名至少3个字符"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少6个字符"}), 400

    user_id = database.create_user(username, password)

    return jsonify(
        {"success": True, "id": user_id, "username": username, "message": "用户创建成功"}
    )


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
@handle_api_error
def delete_user(user_id: int):
    """删除用户"""
    # 不允许删除自己
    if session.get("user_id") == user_id:
        return jsonify({"success": False, "error": "不能删除自己"}), 400

    database.delete_user(user_id)
    return jsonify({"success": True, "message": "用户删除成功"})


@admin_bp.route("/api/admin/users/<int:user_id>/password", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def reset_password(user_id: int):
    """重置用户密码"""
    password = request.json.get("password", "")

    if not password:
        return jsonify({"success": False, "error": "密码不能为空"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少6个字符"}), 400

    database.update_user_password(user_id, password)

    return jsonify({"success": True, "message": "密码修改成功"})


@admin_bp.route("/api/admin/projects", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_projects():
    """获取所有项目"""
    projects = database.get_all_projects()
    # 为每个项目获取用户列表
    for project in projects:
        project["users"] = database.get_project_users(project["id"])
    return jsonify({"success": True, "projects": projects})


@admin_bp.route("/api/admin/projects", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def create_project():
    """创建项目"""
    name = request.json.get("name", "").strip()

    if not name:
        return jsonify({"success": False, "error": "项目名称不能为空"}), 400

    project_id = database.create_project(name, None)  # 不指定所有者

    return jsonify({"success": True, "id": project_id, "name": name, "message": "项目创建成功"})


@admin_bp.route("/api/admin/projects/<int:project_id>/assign", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def assign_user_to_project(project_id: int):
    """授权用户访问项目"""
    user_id = request.json.get("user_id")

    if not user_id:
        return jsonify({"success": False, "error": "用户ID不能为空"}), 400

    database.assign_user_to_project(user_id, project_id)

    return jsonify({"success": True, "message": "授权成功"})


@admin_bp.route("/api/admin/projects/<int:project_id>/revoke", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def revoke_user_from_project(project_id: int):
    """移除用户对项目的访问权限"""
    user_id = request.json.get("user_id")

    if not user_id:
        return jsonify({"success": False, "error": "用户ID不能为空"}), 400

    database.revoke_user_from_project(user_id, project_id)

    return jsonify({"success": True, "message": "权限已移除"})


@admin_bp.route("/api/stats", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_stats():
    """获取系统统计信息"""
    period = request.args.get("period", "week")  # day/week/month/custom
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # 计算日期范围
    start_date, end_date = calculate_date_range(period, start_date, end_date)

    # 获取报表概览统计
    overview = database.get_report_overview(start_date, end_date)

    # 获取用户统计
    user_stats = database.get_user_report(start_date, end_date)

    # 获取每日统计
    daily_stats = database.get_daily_report(start_date, end_date)

    return jsonify({
        "success": True,
        "data": {
            "period": {"start": start_date, "end": end_date},
            "overview": overview,
            "user_stats": user_stats,
            "daily_stats": daily_stats,
        }
    })
