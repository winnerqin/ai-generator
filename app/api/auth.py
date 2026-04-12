"""
认证相关 API
"""

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_jwt_extended import jwt_required

import database
from app.decorators import login_required
from app.utils import ApiResponse
from app.utils.jwt_auth import JWTAuth

# 创建蓝图
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """用户登录"""
    if request.method == "GET":
        return render_template("login.html")

    username = (
        request.form.get("username", "").strip()
        if not request.is_json
        else request.json.get("username", "").strip()
    )
    password = (
        request.form.get("password", "")
        if not request.is_json
        else request.json.get("password", "")
    )

    if not username or not password:
        return ApiResponse.bad_request("用户名和密码不能为空")

    # 验证用户
    user = database.verify_user(username, password)
    if not user:
        return ApiResponse.unauthorized("用户名或密码错误")

    user_id = user.get("id")

    # 设置会话
    session["user_id"] = user_id
    session["username"] = username
    session.permanent = True

    # 确保用户有项目
    projects = database.get_user_projects(user_id)
    if projects:
        session["current_project_id"] = projects[0].get("id")
        session["current_project_name"] = projects[0].get("name")

    # 返回 JSON 或重定向
    if request.is_json:
        return ApiResponse.success({"user_id": user_id, "username": username}, "登录成功")
    return redirect(url_for("index"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """用户注册（暂时禁用）"""
    return ApiResponse.error("注册功能已禁用，请联系管理员创建账号", 403)


@auth_bp.route("/logout")
@login_required
def logout():
    """用户登出"""
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def get_current_user():
    """获取当前用户信息"""
    user_id = session.get("user_id")
    username = session.get("username")
    project_id = session.get("current_project_id")

    # 获取用户信息
    database.get_user_by_id(user_id)

    return ApiResponse.success(
        {
            "id": user_id,
            "username": username,
            "project_id": project_id,
            "is_system_admin": username == "system_admin",
        }
    )


# ========== JWT 认证端点 ==========


@auth_bp.route("/api/auth/login", methods=["POST"])
def jwt_login():
    """
    JWT 登录接口

    请求体:
        {
            "username": "用户名",
            "password": "密码"
        }

    响应:
        {
            "success": true,
            "data": {
                "access_token": "访问令牌",
                "refresh_token": "刷新令牌",
                "token_type": "bearer",
                "expires_in": 86400,
                "user": {
                    "id": 1,
                    "username": "用户名"
                }
            }
        }
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return ApiResponse.bad_request("用户名和密码不能为空")

    # 验证用户
    user = database.verify_user(username, password)
    if not user:
        return ApiResponse.unauthorized("用户名或密码错误")

    user_id = user.get("id")

    # 生成 JWT tokens
    tokens = JWTAuth.generate_tokens(user_id=user_id, username=username)

    return ApiResponse.success(
        {
            **tokens,
            "user": {"id": user_id, "username": username},
        },
        "登录成功",
    )


@auth_bp.route("/api/auth/refresh", methods=["POST"])
def jwt_refresh():
    """
    刷新 JWT 访问令牌

    请求头:
        Authorization: Bearer <refresh_token>

    响应:
        {
            "success": true,
            "data": {
                "access_token": "新的访问令牌",
                "token_type": "bearer"
            }
        }
    """
    from flask_jwt_extended import get_jwt_identity, create_access_token
    import json

    @jwt_required(refresh=True)
    def do_refresh():
        identity = get_jwt_identity()
        # 如果身份是字符串，尝试解析为 JSON
        if isinstance(identity, str):
            try:
                identity = json.loads(identity)
            except json.JSONDecodeError:
                pass

        access_token = create_access_token(identity=identity)
        return ApiResponse.success(
            {
                "access_token": access_token,
                "token_type": "bearer",
            },
            "令牌刷新成功",
        )

    return do_refresh()


@auth_bp.route("/api/auth/me", methods=["GET"])
@jwt_required()
def jwt_me():
    """
    获取当前 JWT 认证用户信息

    请求头:
        Authorization: Bearer <access_token>

    响应:
        {
            "success": true,
            "data": {
                "id": 1,
                "username": "用户名"
            }
        }
    """
    from flask_jwt_extended import get_jwt_identity
    import json

    current_user = get_jwt_identity()
    # 如果身份是字符串，尝试解析为 JSON
    if isinstance(current_user, str):
        try:
            current_user = json.loads(current_user)
        except json.JSONDecodeError:
            pass
    return ApiResponse.success(current_user)
