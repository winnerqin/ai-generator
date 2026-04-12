"""
视频生成相关 API
"""

from flask import Blueprint, request, session

import database
from app.decorators import handle_api_error, login_required
from app.services import file_upload_service
from app.utils import ApiResponse

# 创建蓝图
video_bp = Blueprint("video", __name__)


@video_bp.route("/video-generate")
@login_required
def video_generate_page():
    """视频生成页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("video_generate.html", user=user)


@video_bp.route("/video-tasks")
@login_required
def video_tasks_page():
    """视频任务页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("video_tasks.html", user=user)


@video_bp.route("/api/video-generate", methods=["POST"])
@login_required
@handle_api_error
def generate_video():
    """生成视频"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return ApiResponse.bad_request("提示词不能为空")

    # 提取参数
    params = {
        "prompt": prompt,
        "negative_prompt": data.get("negative_prompt", ""),
        "aspect_ratio": data.get("aspect_ratio", "16:9"),
        "duration": data.get("duration", 5),
        "resolution": data.get("resolution"),
        "seed": data.get("seed"),
        "camera_fixed": data.get("camera_fixed", False),
        "watermark": data.get("watermark", False),
        "generate_audio": data.get("generate_audio", False),
        "return_last_frame": data.get("return_last_frame", False),
        "first_frame_url": data.get("first_frame_url", ""),
        "reference_image_urls": data.get("reference_image_urls", []),
    }

    # 生成视频
    result = database.generate_video(user_id, project_id, params)

    return ApiResponse.success(result, "视频生成任务已创建")


@video_bp.route("/api/video-tasks", methods=["GET"])
@login_required
def get_video_tasks():
    """获取视频任务列表"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    status = request.args.get("status")
    limit = request.args.get("limit", 50, type=int)

    tasks = database.get_video_tasks(user_id, project_id, status, limit)

    return ApiResponse.success({"tasks": tasks})


@video_bp.route("/api/video-tasks/<task_id>", methods=["DELETE"])
@login_required
def delete_video_task(task_id: str):
    """删除视频任务"""
    user_id = session.get("user_id")

    # 检查任务是否属于当前用户
    task = database.get_video_task(task_id)
    if not task or task["user_id"] != user_id:
        return ApiResponse.not_found("任务不存在")

    # 删除视频文件
    if task["video_url"]:
        file_upload_service.delete_file(task["video_url"], is_oss="oss" in task["video_url"])

    database.delete_video_task(task_id)

    return ApiResponse.no_content()


@video_bp.route("/api/delete-video-asset", methods=["POST"])
@login_required
def delete_video_asset():
    """删除视频资源"""
    task_id = request.json.get("task_id")
    asset_type = request.json.get("type", "video")  # video, last_frame

    if not task_id:
        return ApiResponse.bad_request("任务ID不能为空")

    # 获取任务
    task = database.get_video_task(task_id)
    if not task:
        return ApiResponse.not_found("任务不存在")

    # 删除指定资源
    if asset_type == "video" and task["video_url"]:
        file_upload_service.delete_file(task["video_url"], is_oss="oss" in task["video_url"])
        database.update_video_task_asset(task_id, "video_url", None)
    elif asset_type == "last_frame" and task["last_frame_image_url"]:
        file_upload_service.delete_file(
            task["last_frame_image_url"], is_oss="oss" in task["last_frame_image_url"]
        )
        database.update_video_task_asset(task_id, "last_frame_image_url", None)

    return ApiResponse.success(None, "资源已删除")
