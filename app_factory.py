"""
Flask application factory with blueprint integration.

This module is the preferred entry point for the modularized app layout.
Legacy UI compatibility is now provided from modules under ``app/`` instead of
direct imports from the old monolithic entry file.
"""

from __future__ import annotations

import logging
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import database
from dotenv import load_dotenv
from flask import Flask, abort, g, render_template, request, send_file, session

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from app.api import (
        admin_bp,
        auth_bp,
        batch_bp,
        content_bp,
        image_bp,
        omni_video_bp,
        projects_bp,
        script_bp,
        storyboard_bp,
        tools_bp,
        video_bp,
        video_enhance_bp,
    )
    from app.config import config
    from app.decorators import login_required
    from app.utils import ApiResponse
    from app.utils.jwt_auth import JWTAuth
    from app.utils.sanitizer import (
        extract_response_summary,
        sanitize_request_params,
        should_skip_logging,
    )

    NEW_MODULES_AVAILABLE = True
    MODULE_IMPORT_ERROR: Exception | None = None
except ImportError as exc:
    NEW_MODULES_AVAILABLE = False
    MODULE_IMPORT_ERROR = exc
    logger.warning("Failed to import modular app package: %s", exc)


def _sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive header values before logging them."""
    redacted_keys = {"authorization", "cookie", "x-api-key"}
    sanitized: dict[str, Any] = {}
    for key, value in headers.items():
        sanitized[key] = "***" if key.lower() in redacted_keys else value
    return sanitized


def _safe_response_body(response) -> str:
    """Return a loggable response body preview for text-like responses."""
    if getattr(response, "direct_passthrough", False):
        return "<direct_passthrough>"
    content_type = (response.headers.get("Content-Type") or "").lower()
    if not any(
        token in content_type
        for token in ("application/json", "text/", "application/javascript", "application/xml")
    ):
        return f"<binary content-type={content_type or 'unknown'}>"
    try:
        body = response.get_data(as_text=True)
    except Exception as exc:  # pragma: no cover - defensive logging fallback
        return f"<unavailable: {exc}>"
    max_len = 8000
    if len(body) > max_len:
        return f"{body[:max_len]}...<truncated {len(body) - max_len} chars>"
    return body


def setup_request_logging(app: Flask) -> None:
    """Register lightweight request logging handlers."""

    @app.before_request
    def log_request_info() -> None:
        if request.path.startswith("/static/"):
            return

        g.start_time = time.time()
        app.logger.info(
            "[REQUEST] method=%s path=%s full_path=%s remote=%s headers=%s",
            request.method,
            request.path,
            request.full_path,
            request.remote_addr,
            _sanitize_headers(dict(request.headers)),
        )

        if request.is_json:
            payload = request.get_json(silent=True)
            if payload is not None:
                app.logger.info("[REQUEST JSON] %s", payload)
        elif request.form:
            app.logger.info("[REQUEST FORM] %s", dict(request.form))
        elif request.args:
            app.logger.info("[REQUEST ARGS] %s", dict(request.args))

    @app.after_request
    def log_response_info(response):
        if request.path.startswith("/static/"):
            return response

        duration = time.time() - getattr(g, "start_time", time.time())
        app.logger.info(
            "[RESPONSE] method=%s path=%s status=%s duration=%.3fs headers=%s body=%s",
            request.method,
            request.path,
            response.status_code,
            duration,
            dict(response.headers),
            _safe_response_body(response),
        )
        return response


def setup_operation_logging(app: Flask) -> None:
    """注册操作日志记录钩子，记录用户API请求和详细响应。"""

    # 创建操作日志目录
    log_dir = Path(config.OPERATION_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    def write_log_to_file(log_data: dict) -> None:
        """将日志写入按天分隔的文件。"""
        try:
            # 按天生成文件名
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = log_dir / f"operation_{today}.log"

            # 添加毫秒级时间戳，确保放在第一列
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            ordered_log_data = {"timestamp": timestamp}
            for key, value in log_data.items():
                ordered_log_data[key] = value

            # 写入JSON格式的日志（每行一条记录）
            log_line = json.dumps(ordered_log_data, ensure_ascii=False)

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception as e:
            logger.warning("[operation_log] file write failed: %s", e)

    def extract_response_data(response) -> dict:
        """提取完整的响应数据"""
        try:
            content_type = (response.headers.get("Content-Type") or "").lower()

            # 非JSON响应，返回基本信息
            if "application/json" not in content_type:
                return {
                    "content_type": content_type,
                    "summary": extract_response_summary(response),
                }

            # 解析JSON响应
            body = response.get_data(as_text=True)
            data = json.loads(body)

            # 截断过大的响应数据
            max_len = 2000
            if isinstance(data, dict):
                # 对于包含大量数据的响应，只保留关键信息
                truncated_data = {}
                for key, value in data.items():
                    if isinstance(value, str) and len(value) > max_len:
                        truncated_data[key] = value[:max_len] + "...<truncated>"
                    elif isinstance(value, list) and len(value) > 20:
                        truncated_data[key] = value[:20] + [f"...<truncated {len(value) - 20} items>"]
                    elif isinstance(value, dict) and len(str(value)) > max_len:
                        truncated_data[key] = f"<dict size={len(str(value))}>"
                    else:
                        truncated_data[key] = value
                return truncated_data

            return {"data": str(data)[:max_len] if len(str(data)) > max_len else data}

        except Exception as e:
            return {"error": str(e), "summary": "<unavailable>"}

    @app.after_request
    def log_operation(response):
        # 跳过静态资源和不需要记录的路径
        if should_skip_logging(request.path):
            return response

        # 仅记录 API 请求
        if not request.path.startswith("/api/"):
            return response

        # 收集用户信息
        user_id = session.get("user_id")
        username = session.get("username")
        project_id = session.get("current_project_id")

        # 收集请求参数
        params = {}
        if request.is_json:
            params = request.get_json(silent=True) or {}
        elif request.form:
            params = dict(request.form)
        elif request.args:
            params = dict(request.args)

        # 脱敏处理
        sanitized_params = sanitize_request_params(params)

        # 计算耗时
        duration_ms = int((time.time() - getattr(g, "start_time", time.time())) * 1000)

        # 提取完整响应数据
        response_data = extract_response_data(response)

        # 构建日志数据
        log_data = {
            "log_type": "api_response",
            "user_id": user_id,
            "username": username,
            "project_id": project_id,
            "request_path": request.path,
            "request_method": request.method,
            "request_params": sanitized_params,
            "response_status": response.status_code,
            "response_data": response_data,
            "ip_address": request.remote_addr,
            "duration_ms": duration_ms,
        }

        # 异步写入数据库和文件（避免阻塞响应）
        threading.Thread(
            target=_write_log_async,
            args=(log_data,),
            daemon=True,
        ).start()

        return response

    def _write_log_async(log_data: dict) -> None:
        """异步写入日志到数据库和文件。"""
        # 写入数据库
        database.save_operation_log(log_data)
        # 写入文件
        write_log_to_file(log_data)


def create_app(config_name: str | None = None) -> Flask:
    """
    Create and configure the Flask app.

    ``config_name`` is reserved for future multi-environment config support.
    """
    del config_name

    if not NEW_MODULES_AVAILABLE:
        raise RuntimeError(
            "Modular app package failed to import; app_factory requires the modular app package."
        ) from MODULE_IMPORT_ERROR

    database.init_database()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", config.SECRET_KEY),
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", config.UPLOAD_FOLDER),
        OUTPUT_FOLDER=os.environ.get("OUTPUT_FOLDER", config.OUTPUT_FOLDER),
        MAX_CONTENT_LENGTH=int(
            os.environ.get("MAX_CONTENT_LENGTH", str(config.MAX_VIDEO_SIZE))
        ),
    )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["OUTPUT_FOLDER"], exist_ok=True)

    setup_request_logging(app)
    setup_operation_logging(app)
    JWTAuth.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(omni_video_bp)
    app.register_blueprint(video_enhance_bp)
    app.register_blueprint(batch_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(script_bp)
    app.register_blueprint(storyboard_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(content_bp)

    register_error_handlers(app)
    register_context_processors(app)
    register_remaining_routes(app)
    return app


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers."""

    @app.errorhandler(404)
    def not_found(error):
        del error
        if request.is_json or request.path.startswith("/api/"):
            return ApiResponse.not_found("\u8d44\u6e90\u4e0d\u5b58\u5728")
        return "\u9875\u9762\u4e0d\u5b58\u5728", 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Unhandled server error: %s", error)
        if request.is_json or request.path.startswith("/api/"):
            return ApiResponse.server_error("\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef")
        return "\u670d\u52a1\u5668\u9519\u8bef", 500


def register_context_processors(app: Flask) -> None:
    """Register template context processors."""

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        from datetime import datetime

        return {
            "now": datetime.now(),
            "NEW_MODULES_AVAILABLE": NEW_MODULES_AVAILABLE,
            "MODULE_IMPORT_ERROR": str(MODULE_IMPORT_ERROR) if MODULE_IMPORT_ERROR else None,
        }


def register_remaining_routes(app: Flask) -> None:
    """Register routes that have not been migrated to blueprints yet."""

    @app.route("/")
    @login_required
    def index():
        user = {"username": session.get("username", ""), "id": session.get("user_id")}
        return render_template("index.html", user=user)

    @app.route("/uploads/<path:relative_path>")
    @login_required
    def uploaded_file(relative_path: str):
        upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
        file_path = (upload_root / relative_path).resolve()
        try:
            file_path.relative_to(upload_root)
        except ValueError:
            abort(403)

        user_id = session.get("user_id")
        username = session.get("username")
        normalized = relative_path.replace("\\", "/")
        if username != "system_admin" and f"user_{user_id}/" not in normalized and f"user_{user_id}\\" not in relative_path:
            abort(403)
        if not file_path.exists():
            abort(404)
        return send_file(file_path)

    @app.route("/favicon.ico")
    def favicon():
        return send_file(Path(app.root_path) / "static" / "favicon.ico")

    page_routes = [
        ("/batch", "batch.html", "\u6279\u91cf\u751f\u6210"),
        ("/content-management", "content_management.html", "\u5185\u5bb9\u7ba1\u7406"),
        ("/manage-samples", "manage_samples.html", "\u793a\u4f8b\u56fe\u7ba1\u7406"),
        ("/records", "records.html", "\u751f\u6210\u8bb0\u5f55"),
        ("/script-analysis", "script_analysis.html", "\u5267\u672c\u5206\u6790"),
        ("/script-generate", "script_generate.html", "\u5267\u672c\u751f\u6210"),
        ("/stats", "stats.html", "\u7edf\u8ba1"),
        ("/storyboard", "storyboard_generate.html", "\u5206\u955c\u751f\u6210"),
        ("/storyboard-studio", "storyboard_studio.html", "\u5206\u955c\u5de5\u4f5c\u5ba4"),
        ("/txt2csv", "txt2csv.html", "\u6587\u672c\u8f6cCSV"),
        ("/video-generate", "video_generate.html", "\u89c6\u9891\u751f\u6210"),
        ("/video-tasks", "video_tasks.html", "\u89c6\u9891\u4efb\u52a1"),
    ]

    def make_route(template_name: str, page_title: str):
        @login_required
        def route():
            user = {"username": session.get("username", ""), "id": session.get("user_id")}
            return render_template(template_name, title=page_title, user=user)

        return route

    for path, template, title in page_routes:
        endpoint = f"page_{path.strip('/').replace('-', '_')}"
        app.add_url_rule(path, endpoint=endpoint, view_func=make_route(template, title))



app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("FLASK_PORT", 8090))
    host = os.environ.get("FLASK_HOST", "0.0.0.0")

    logger.info(
        "Starting Flask server on %s:%s debug=%s new_modules_available=%s",
        host,
        port,
        debug,
        NEW_MODULES_AVAILABLE,
    )
    app.run(host=host, port=port, debug=debug)
