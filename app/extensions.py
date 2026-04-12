"""
Flask 扩展初始化

集中管理所有 Flask 扩展的初始化
"""

import logging
from pathlib import Path

from flask import Flask

from app.config import config


def init_logging(app: Flask):
    """初始化日志系统"""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(config.LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )
    return logging.getLogger(__name__)


def init_directories(app: Flask):
    """初始化必要的目录"""
    directories = [
        config.UPLOAD_FOLDER,
        config.OUTPUT_FOLDER,
        str(Path(config.OUTPUT_FOLDER) / "generated_images"),
        str(Path(config.OUTPUT_FOLDER) / "videos"),
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)


def init_error_handlers(app: Flask):
    """初始化错误处理器"""
    from flask import request

    from app.utils import ApiResponse

    @app.errorhandler(404)
    def not_found(error):
        # API 请求返回 JSON，页面请求返回 HTML
        if request.path.startswith("/api/"):
            return ApiResponse.not_found("请求的资源不存在")
        return "Not Found", 404

    @app.errorhandler(403)
    def forbidden(error):
        if request.path.startswith("/api/"):
            return ApiResponse.forbidden("无权限访问")
        return "Forbidden", 403

    @app.errorhandler(500)
    def internal_error(error):
        if request.path.startswith("/api/"):
            return ApiResponse.server_error("服务器内部错误")
        return "Internal Server Error", 500

    @app.errorhandler(413)
    def request_entity_too_large(error):
        if request.path.startswith("/api/"):
            return ApiResponse.bad_request("请求体过大")
        return "Request Entity Too Large", 413


def create_app(config_obj=None) -> Flask:
    """
    应用工厂函数

    创建并配置 Flask 应用实例

    Args:
        config_obj: 配置对象（可选）

    Returns:
        Flask 应用实例
    """
    app = Flask(__name__)

    # 配置
    if config_obj:
        app.config.from_object(config_obj)
    else:
        from app.config import config

        app.config["SECRET_KEY"] = config.SECRET_KEY
        app.config["DEBUG"] = config.DEBUG
        app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
        from datetime import timedelta

        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=config.SESSION_LIFETIME_DAYS)

    # 初始化扩展
    init_logging(app)
    init_directories(app)
    init_error_handlers(app)

    # 注册蓝图
    register_blueprints(app)

    return app


def register_blueprints(app: Flask):
    """
    注册所有蓝图

    Args:
        app: Flask 应用实例
    """
    from app.api import (
        admin_bp,
        auth_bp,
        batch_bp,
        content_bp,
        image_bp,
        projects_bp,
        script_bp,
        storyboard_bp,
        tools_bp,
        video_bp,
    )

    # 认证相关
    app.register_blueprint(auth_bp)

    # 项目管理
    app.register_blueprint(projects_bp)

    # 管理员
    app.register_blueprint(admin_bp)

    # 图片生成
    app.register_blueprint(image_bp)

    # 批量生成
    app.register_blueprint(batch_bp)

    # 视频生成
    app.register_blueprint(video_bp)

    # 剧本相关
    app.register_blueprint(script_bp)

    # 分镜相关
    app.register_blueprint(storyboard_bp)

    # 工具
    app.register_blueprint(tools_bp)

    # 内容管理
    app.register_blueprint(content_bp)
