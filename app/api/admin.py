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

    if period == "day":
        start = today  # 今日：当天数据
        end = today
    elif period == "last7days":
        start = today - timedelta(days=6)  # 近7天：包含今天
        end = today
    elif period == "month":
        start = today - timedelta(days=29)  # 近30天：包含今天
        end = today
    else:  # custom
        # start_date 和 end_date 已经是字符串格式
        return start_date or today.strftime("%Y-%m-%d"), end_date or today.strftime("%Y-%m-%d")

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@admin_bp.route("/admin")
@login_required
@admin_required
def admin_page():
    """管理员页面"""
    from flask import render_template

    user = {
        "username": session.get("username", ""),
        "id": session.get("user_id"),
        "role_code": session.get("role_code"),
    }
    return render_template("admin.html", user=user)


@admin_bp.route("/stats")
@login_required
@admin_required
def stats_page():
    """统计页面"""
    from flask import render_template

    user = {
        "username": session.get("username", ""),
        "id": session.get("user_id"),
        "role_code": session.get("role_code"),
    }
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
    role_code = request.json.get("role_code", database.ROLE_EXTERNAL_USER)

    if not username or not password:
        return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400

    if len(username) < 3:
        return jsonify({"success": False, "error": "用户名至少3个字符"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少6个字符"}), 400

    if role_code not in set(database.get_available_role_codes()):
        return jsonify({"success": False, "error": "不支持的角色"}), 400

    user_id = database.create_user(username, password, role_code=role_code)

    return jsonify(
        {
            "success": True,
            "id": user_id,
            "username": username,
            "role_code": role_code,
            "message": "用户创建成功",
        }
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


@admin_bp.route("/api/admin/users/<int:user_id>/pricing-multiplier", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def update_pricing_multiplier(user_id: int):
    multiplier = request.json.get("pricing_multiplier")
    if multiplier in (None, ""):
        return jsonify({"success": False, "error": "倍率不能为空"}), 400
    try:
        multiplier = float(multiplier)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "倍率格式错误"}), 400
    if multiplier <= 0:
        return jsonify({"success": False, "error": "倍率必须大于0"}), 400
    affected = database.update_user_pricing_multiplier(user_id, multiplier)
    if not affected:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    return jsonify({"success": True, "message": "倍率更新成功"})


@admin_bp.route("/api/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def update_user_role(user_id: int):
    role_code = request.json.get("role_code")
    if role_code not in set(database.get_available_role_codes()):
        return jsonify({"success": False, "error": "不支持的角色"}), 400
    if session.get("user_id") == user_id and role_code != database.ROLE_SYSTEM_ADMIN:
        return jsonify({"success": False, "error": "不能将自己降级为非管理员"}), 400
    affected = database.update_user_role(user_id, role_code)
    if not affected:
        return jsonify({"success": False, "error": "用户不存在或当前数据库未启用角色字段"}), 404
    return jsonify({"success": True, "message": "角色更新成功"})


@admin_bp.route("/api/admin/users/<int:user_id>/recharge", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def recharge_user(user_id: int):
    amount_cent = request.json.get("amount_cent")
    if amount_cent in (None, ""):
        return jsonify({"success": False, "error": "调整金额不能为空"}), 400
    try:
        amount_cent = int(amount_cent)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "调整金额格式错误"}), 400
    if amount_cent == 0:
        return jsonify({"success": False, "error": "调整金额不能为0"}), 400

    user = database.get_user_by_id(user_id)
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    if user.get("role_code") != database.ROLE_EXTERNAL_USER:
        return jsonify({"success": False, "error": "仅支持为外部用户调整余额"}), 400

    is_credit = amount_cent > 0

    result = database.create_account_ledger_entry(
        user_id=user_id,
        entry_type="credit" if is_credit else "debit",
        amount_cent=abs(amount_cent),
        biz_type="manual_recharge" if is_credit else "manual_adjust",
        biz_id=f"manual-balance-adjust-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        operator_user_id=session.get("user_id"),
        snapshot_json={"source": "admin_api"},
    )
    return jsonify(
        {
            "success": True,
            "message": "余额调整成功",
            "balance_cent": result["after"],
        }
    )


@admin_bp.route("/api/admin/model-pricing", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_model_pricing():
    items = database.get_model_pricing_list()
    return jsonify({"success": True, "items": items})


@admin_bp.route("/api/admin/model-pricing", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def create_or_update_model_pricing():
    model_code = (request.json.get("model_code") or "").strip()
    model_name = (request.json.get("model_name") or "").strip()
    currency_code = (
        (request.json.get("currency_code") or database.MODEL_CURRENCY_CNY).strip().upper()
    )
    resolution_code = (request.json.get("resolution_code") or "").strip().lower()
    reference_video_mode = (
        (request.json.get("reference_video_mode") or database.REFERENCE_VIDEO_MODE_ANY)
        .strip()
        .lower()
    )
    price_per_million_token_cent = request.json.get("price_per_million_token_cent")
    enabled = bool(request.json.get("enabled", True))
    if not model_code or not model_name:
        return jsonify({"success": False, "error": "模型编码和名称不能为空"}), 400
    if currency_code not in {database.MODEL_CURRENCY_CNY, database.MODEL_CURRENCY_USD}:
        return jsonify({"success": False, "error": "币种仅支持 CNY 或 USD"}), 400
    if reference_video_mode not in {
        database.REFERENCE_VIDEO_MODE_ANY,
        database.REFERENCE_VIDEO_MODE_WITH,
        database.REFERENCE_VIDEO_MODE_WITHOUT,
    }:
        return jsonify({"success": False, "error": "参考素材类型不合法"}), 400
    if price_per_million_token_cent in (None, ""):
        return jsonify({"success": False, "error": "价格不能为空"}), 400
    try:
        price_per_million_token_cent = int(price_per_million_token_cent)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "价格格式错误"}), 400
    if price_per_million_token_cent <= 0:
        return jsonify({"success": False, "error": "价格必须大于0"}), 400
    pricing_id = database.upsert_model_pricing(
        model_code=model_code,
        model_name=model_name,
        currency_code=currency_code,
        resolution_code=resolution_code,
        reference_video_mode=reference_video_mode,
        price_per_million_token_cent=price_per_million_token_cent,
        enabled=enabled,
    )
    return jsonify({"success": True, "id": pricing_id, "message": "模型价格已保存"})


@admin_bp.route("/api/admin/model-pricing/<int:pricing_id>", methods=["PUT"])
@login_required
@admin_required
@handle_api_error
def update_model_pricing(pricing_id: int):
    model_name = (request.json.get("model_name") or "").strip()
    currency_code = (
        (request.json.get("currency_code") or database.MODEL_CURRENCY_CNY).strip().upper()
    )
    resolution_code = (request.json.get("resolution_code") or "").strip().lower()
    reference_video_mode = (
        (request.json.get("reference_video_mode") or database.REFERENCE_VIDEO_MODE_ANY)
        .strip()
        .lower()
    )
    price_per_million_token_cent = request.json.get("price_per_million_token_cent")
    enabled = bool(request.json.get("enabled", True))
    if not model_name:
        return jsonify({"success": False, "error": "模型名称不能为空"}), 400
    if currency_code not in {database.MODEL_CURRENCY_CNY, database.MODEL_CURRENCY_USD}:
        return jsonify({"success": False, "error": "币种仅支持 CNY 或 USD"}), 400
    if reference_video_mode not in {
        database.REFERENCE_VIDEO_MODE_ANY,
        database.REFERENCE_VIDEO_MODE_WITH,
        database.REFERENCE_VIDEO_MODE_WITHOUT,
    }:
        return jsonify({"success": False, "error": "参考素材类型不合法"}), 400
    if price_per_million_token_cent in (None, ""):
        return jsonify({"success": False, "error": "价格不能为空"}), 400
    try:
        price_per_million_token_cent = int(price_per_million_token_cent)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "价格格式错误"}), 400
    if price_per_million_token_cent <= 0:
        return jsonify({"success": False, "error": "价格必须大于0"}), 400
    affected = database.update_model_pricing_by_id(
        pricing_id=pricing_id,
        model_name=model_name,
        currency_code=currency_code,
        resolution_code=resolution_code,
        reference_video_mode=reference_video_mode,
        price_per_million_token_cent=price_per_million_token_cent,
        enabled=enabled,
    )
    if not affected:
        return jsonify({"success": False, "error": "模型价格记录不存在"}), 404
    return jsonify({"success": True, "message": "模型价格更新成功"})


@admin_bp.route("/api/admin/billing-ledger", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_billing_ledger():
    user_id = request.args.get("user_id", type=int)
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 200)
    offset = (page - 1) * page_size
    items = database.get_account_ledger(user_id=user_id, limit=page_size, offset=offset)
    total = database.count_account_ledger(user_id=user_id)
    return jsonify(
        {
            "success": True,
            "data": {
                "items": items,
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size,
                },
            },
        }
    )


@admin_bp.route("/api/admin/role-menu-permissions", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_role_menu_permissions():
    roles = database.get_role_definitions()
    permissions = {r["code"]: r.get("menu_keys", []) for r in roles}
    return jsonify(
        {
            "success": True,
            "data": {
                "menus": database.MENU_DEFINITIONS,
                "roles": [r["code"] for r in roles],
                "role_defs": roles,
                "permissions": permissions,
            },
        }
    )


@admin_bp.route("/api/admin/role-menu-permissions", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def update_role_menu_permissions():
    permissions = request.json.get("permissions") if request.is_json else None
    if not isinstance(permissions, dict):
        return jsonify({"success": False, "error": "permissions 参数格式错误"}), 400
    role_defs = database.get_role_definitions()
    for role in role_defs:
        role["menu_keys"] = permissions.get(role["code"], role.get("menu_keys", []))
    saved = database.save_role_definitions(role_defs)
    return jsonify({"success": True, "message": "菜单权限已保存", "role_defs": saved})


@admin_bp.route("/api/admin/roles", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_roles():
    return jsonify({"success": True, "roles": database.get_role_definitions()})


@admin_bp.route("/api/admin/roles", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def create_role():
    data = request.get_json(silent=True) or {}
    role_code = (data.get("code") or "").strip()
    role_name = (data.get("name") or "").strip()
    menu_keys = data.get("menu_keys") or []
    pricing_multiplier = data.get("pricing_multiplier", 1.0)
    if not role_code or not role_name:
        return jsonify({"success": False, "error": "角色编码和名称不能为空"}), 400
    try:
        pricing_multiplier = float(pricing_multiplier)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "角色倍率格式错误"}), 400
    if pricing_multiplier <= 0:
        return jsonify({"success": False, "error": "角色倍率必须大于0"}), 400
    pricing_multiplier = round(pricing_multiplier, 1)
    roles = database.get_role_definitions()
    if any(r["code"] == role_code for r in roles):
        return jsonify({"success": False, "error": "角色编码已存在"}), 409
    roles.append(
        {
            "code": role_code,
            "name": role_name,
            "menu_keys": menu_keys if isinstance(menu_keys, list) else [],
            "pricing_multiplier": pricing_multiplier,
            "built_in": False,
        }
    )
    saved = database.save_role_definitions(roles)
    return jsonify({"success": True, "roles": saved, "message": "角色创建成功"})


@admin_bp.route("/api/admin/roles/<role_code>", methods=["PUT"])
@login_required
@admin_required
@handle_api_error
def update_role(role_code: str):
    data = request.get_json(silent=True) or {}
    role_name = (data.get("name") or "").strip()
    menu_keys = data.get("menu_keys")
    pricing_multiplier = data.get("pricing_multiplier")
    roles = database.get_role_definitions()
    target = next((r for r in roles if r["code"] == role_code), None)
    if not target:
        return jsonify({"success": False, "error": "角色不存在"}), 404
    if role_name:
        target["name"] = role_name
    if isinstance(menu_keys, list):
        target["menu_keys"] = menu_keys
    if pricing_multiplier is not None:
        try:
            parsed = float(pricing_multiplier)
            if parsed <= 0:
                return jsonify({"success": False, "error": "角色倍率必须大于0"}), 400
            target["pricing_multiplier"] = round(parsed, 1)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "角色倍率格式错误"}), 400
    saved = database.save_role_definitions(roles)
    return jsonify({"success": True, "roles": saved, "message": "角色更新成功"})


@admin_bp.route("/api/admin/roles/<role_code>", methods=["DELETE"])
@login_required
@admin_required
@handle_api_error
def delete_role(role_code: str):
    roles = database.get_role_definitions()
    target = next((r for r in roles if r["code"] == role_code), None)
    if not target:
        return jsonify({"success": False, "error": "角色不存在"}), 404
    if target.get("built_in"):
        return jsonify({"success": False, "error": "内置角色不可删除"}), 400
    # ensure no users are using this role
    users = database.get_all_users()
    if any((u.get("role_code") or "") == role_code for u in users):
        return jsonify({"success": False, "error": "该角色仍有用户绑定，无法删除"}), 400
    roles = [r for r in roles if r["code"] != role_code]
    saved = database.save_role_definitions(roles)
    return jsonify({"success": True, "roles": saved, "message": "角色删除成功"})


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
    period = request.args.get("period", "last7days")  # day/last7days/month/custom
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    username_filter = request.args.get("username")  # 用户名筛选

    # 计算日期范围
    start_date, end_date = calculate_date_range(period, start_date, end_date)

    # 获取报表概览统计
    overview = database.get_report_overview(start_date, end_date)

    # 获取用户统计（支持用户名筛选）
    user_stats = database.get_user_report(start_date, end_date, username_filter)

    # 获取每日统计
    daily_stats = database.get_daily_report(start_date, end_date)

    # 获取任务状态统计
    status_report = database.get_task_status_report(start_date, end_date)

    # 获取Token消耗统计
    token_report = database.get_token_usage_report(start_date, end_date)

    return jsonify(
        {
            "success": True,
            "data": {
                "period": {"start": start_date, "end": end_date},
                "overview": overview,
                "user_stats": user_stats,
                "daily_stats": daily_stats,
                "status_report": status_report,
                "token_report": token_report,
            },
        }
    )


@admin_bp.route("/api/admin/operation-logs", methods=["GET"])
@login_required
@admin_required
@handle_api_error
def get_operation_logs():
    """查询操作日志"""
    user_id = request.args.get("user_id", type=int)
    project_id = request.args.get("project_id", type=int)
    path_prefix = request.args.get("path")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    logs = database.get_operation_logs(
        user_id=user_id,
        project_id=project_id,
        path_prefix=path_prefix,
        limit=min(limit, 500),
        offset=offset,
    )

    total = database.count_operation_logs(
        user_id=user_id,
        project_id=project_id,
        path_prefix=path_prefix,
    )

    return jsonify(
        {
            "success": True,
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@admin_bp.route("/api/admin/operation-logs/cleanup", methods=["POST"])
@login_required
@admin_required
@handle_api_error
def cleanup_operation_logs():
    """清理旧操作日志"""
    days = request.json.get("days", 30, type=int)

    if days < 7:
        return jsonify({"success": False, "error": "至少保留7天的日志"}), 400

    deleted = database.delete_old_operation_logs(days)

    return jsonify(
        {
            "success": True,
            "deleted": deleted,
            "message": f"已删除 {deleted} 条超过 {days} 天的日志",
        }
    )
