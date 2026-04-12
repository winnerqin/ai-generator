"""
装饰器模块

提供常用的装饰器函数
"""

from functools import wraps

from flask import redirect, session, url_for

from app.utils import ApiResponse


def login_required(f):
    """
    登录验证装饰器

    如果用户未登录，重定向到登录页面（用于页面路由）
    或返回未授权响应（用于API路由）
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            # 检查是否是 API 请求
            from flask import request

            is_api = request.path.startswith("/api/")

            if is_api:
                return ApiResponse.unauthorized("请先登录")
            else:
                return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    管理员权限验证装饰器

    要求用户已登录且是系统管理员（username == 'system_admin'）
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return ApiResponse.unauthorized("请先登录")

        if session.get("username") != "system_admin":
            return ApiResponse.forbidden("需要管理员权限")

        return f(*args, **kwargs)

    return decorated_function


def project_access_required(f):
    """
    项目访问权限验证装饰器

    确保用户可以访问指定的项目
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return ApiResponse.unauthorized("请先登录")

        user_id = session.get("user_id")
        current_project_id = session.get("current_project_id")

        # 检查用户是否有权访问当前项目
        if current_project_id:
            import database

            if not database.has_project_access(user_id, current_project_id):
                return ApiResponse.forbidden("无权访问该项目")

        return f(*args, **kwargs)

    return decorated_function


def json_required(f):
    """
    JSON 请求装饰器

    确保请求包含有效的 JSON 数据
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request

        if not request.is_json:
            return ApiResponse.bad_request("请求必须是 JSON 格式")
        return f(*args, **kwargs)

    return decorated_function


def with_current_project(f):
    """
    自动注入当前项目 ID 装饰器

    从 session 中获取 current_project_id 并注入到函数参数中
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_project_id = session.get("current_project_id")
        kwargs["current_project_id"] = current_project_id
        return f(*args, **kwargs)

    return decorated_function


def handle_api_error(f):
    """
    API 错误处理装饰器

    捕获异常并返回统一的错误响应
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return ApiResponse.bad_request(str(e))
        except PermissionError as e:
            return ApiResponse.forbidden(str(e))
        except FileNotFoundError as e:
            return ApiResponse.not_found(str(e))
        except Exception as e:
            import traceback

            traceback.print_exc()
            return ApiResponse.server_error(f"服务器错误: {str(e)}")

    return decorated_function
