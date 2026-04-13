"""
API 路由模块

集中管理所有 API 蓝图
"""

from flask import Blueprint

# 管理员
from app.api.admin import admin_bp

# 认证相关
from app.api.auth import auth_bp

# 批量生成
from app.api.batch import batch_bp

# 内容管理
from app.api.content import content_bp

# 图片生成
from app.api.image import image_bp

# 全能视频
from app.api.omni_video import omni_video_bp

# 项目管理
from app.api.projects import projects_bp

# 剧本相关
from app.api.script import script_bp

# 分镜相关
from app.api.storyboard import storyboard_bp

# 工具类
from app.api.tools import tools_bp

# 视频生成
from app.api.video import video_bp

# 视频画质增强
from app.api.video_enhance import video_enhance_bp

__all__ = [
    "auth_bp",
    "projects_bp",
    "admin_bp",
    "image_bp",
    "omni_video_bp",
    "batch_bp",
    "video_bp",
    "script_bp",
    "storyboard_bp",
    "tools_bp",
    "content_bp",
    "video_enhance_bp",
]
