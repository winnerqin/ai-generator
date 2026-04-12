"""
分镜生成相关 API
"""

from flask import Blueprint, request, session

import database
from app.decorators import handle_api_error, login_required
from app.utils import ApiResponse

# 创建蓝图
storyboard_bp = Blueprint("storyboard", __name__)


@storyboard_bp.route("/storyboard")
@login_required
def storyboard_page():
    """分镜页面（旧版）"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("storyboard_generate.html", user=user)


@storyboard_bp.route("/storyboard-studio")
@login_required
def storyboard_studio_page():
    """分镜工作室"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("storyboard_studio.html", user=user)


@storyboard_bp.route("/api/storyboard-generate", methods=["POST"])
@login_required
@handle_api_error
def generate_storyboard():
    """生成分镜"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    script_text = data.get("script_text", "").strip()
    prompt_file = data.get("prompt_file", "storyboard.md")

    if not script_text:
        return ApiResponse.bad_request("剧本文本不能为空")

    # 提取参数
    params = {
        "script_text": script_text,
        "prompt_file": prompt_file,
        "output": data.get("output", "csv"),  # csv, markdown
    }

    result = database.generate_storyboard(user_id, project_id, params)

    return ApiResponse.success(result, "分镜生成成功")


@storyboard_bp.route("/api/storyboard-generate-async", methods=["POST"])
@login_required
@handle_api_error
def generate_storyboard_async():
    """异步生成分镜"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    script_text = data.get("script_text", "").strip()

    if not script_text:
        return ApiResponse.bad_request("剧本文本不能为空")

    # 创建异步任务
    task_id = database.create_storyboard_generation_task(user_id, project_id, data)

    return ApiResponse.created({"task_id": task_id, "status": "pending"}, "任务已创建")


@storyboard_bp.route("/api/storyboard-saves", methods=["GET"])
@login_required
def get_storyboard_saves():
    """获取保存的分镜"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    saves = database.get_storyboard_saves(user_id, project_id)

    return ApiResponse.success(saves)


@storyboard_bp.route("/api/storyboard-saves", methods=["POST"])
@login_required
@handle_api_error
def save_storyboard():
    """保存分镜"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    title = data.get("title", "").strip()
    script_text = data.get("script_text", "")
    storyboard_text = data.get("storyboard_text", "")
    storyboard_json = data.get("storyboard_json")

    if not title:
        return ApiResponse.bad_request("标题不能为空")

    save_id = database.save_storyboard(
        user_id,
        project_id,
        {
            "title": title,
            "script_text": script_text,
            "storyboard_text": storyboard_text,
            "storyboard_json": storyboard_json,
        },
    )

    return ApiResponse.created({"id": save_id}, "分镜已保存")


@storyboard_bp.route("/api/storyboard-series", methods=["GET"])
@login_required
def get_storyboard_series():
    """获取分镜系列"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    series = database.get_storyboard_series(user_id, project_id)

    return ApiResponse.success(series)


@storyboard_bp.route("/api/storyboard-series/<int:series_id>/versions", methods=["GET"])
@login_required
def get_storyboard_versions(series_id: int):
    """获取分镜版本"""
    user_id = session.get("user_id")

    versions = database.get_storyboard_versions(user_id, series_id)

    return ApiResponse.success(versions)


@storyboard_bp.route("/api/storyboard-sample-images", methods=["POST"])
@login_required
@handle_api_error
def upload_storyboard_sample_images():
    """上传分镜示例图片"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    images = request.json.get("images", [])

    if not images:
        return ApiResponse.bad_request("图片列表不能为空")

    saved_count = database.save_storyboard_sample_images(user_id, project_id, images)

    return ApiResponse.success({"saved_count": saved_count}, f"已保存 {saved_count} 张图片")


@storyboard_bp.route("/api/storyboard-episodes", methods=["GET"])
@login_required
def get_storyboard_episodes():
    """获取分镜分集"""
    user_id = session.get("user_id")
    series_id = request.args.get("series_id", type=int)

    if not series_id:
        return ApiResponse.bad_request("系列ID不能为空")

    episodes = database.get_storyboard_episodes(user_id, series_id)

    return ApiResponse.success(episodes)


@storyboard_bp.route("/api/storyboard-episodes", methods=["POST"])
@login_required
@handle_api_error
def create_storyboard_episode():
    """创建分镜分集"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    script_episode_id = data.get("script_episode_id")
    storyboard_json = data.get("storyboard_json")
    storyboard_text = data.get("storyboard_text", "")

    if not script_episode_id:
        return ApiResponse.bad_request("剧本分集ID不能为空")

    episode_id = database.create_storyboard_episode(
        user_id,
        project_id,
        {
            "script_episode_id": script_episode_id,
            "storyboard_json": storyboard_json,
            "storyboard_text": storyboard_text,
        },
    )

    return ApiResponse.created({"id": episode_id}, "分镜分集已创建")


@storyboard_bp.route("/api/storyboard-from-script", methods=["POST"])
@login_required
@handle_api_error
def storyboard_from_script():
    """从剧本生成分镜"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    text = data.get("text", "").strip()
    markdown = data.get("markdown", "")
    prompt_file = data.get("prompt_file", "storyboard.md")
    output = data.get("output", "markdown")  # markdown, csv

    if not text and not markdown:
        return ApiResponse.bad_request("文本或 Markdown 不能为空")

    result = database.generate_storyboard_from_script(
        user_id,
        project_id,
        {"text": text, "markdown": markdown, "prompt_file": prompt_file, "output": output},
    )

    return ApiResponse.success(result)


@storyboard_bp.route("/api/storyboard-queue", methods=["GET"])
@login_required
def get_storyboard_queue():
    """获取分镜队列"""
    user_id = session.get("user_id")

    tasks = database.get_storyboard_queue_tasks(user_id)

    return ApiResponse.success({"tasks": tasks})


@storyboard_bp.route("/api/storyboard-queue/upload", methods=["POST"])
@login_required
@handle_api_error
def upload_to_storyboard_queue():
    """上传文件到分镜队列"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    files = request.files.getlist("files[]")
    prompt_file = request.form.get("prompt_file", "storyboard.md")

    if not files:
        return ApiResponse.bad_request("未选择文件")

    tasks = database.upload_storyboard_queue(user_id, project_id, files, prompt_file)

    return ApiResponse.created({"tasks": tasks}, f"已添加 {len(tasks)} 个任务")


@storyboard_bp.route("/api/storyboard-queue/<task_id>", methods=["DELETE"])
@login_required
def delete_storyboard_queue_task(task_id: str):
    """删除分镜队列任务"""
    user_id = session.get("user_id")

    database.delete_storyboard_queue_task(user_id, task_id)

    return ApiResponse.no_content()


@storyboard_bp.route("/api/storyboard-queue/process-one", methods=["POST"])
@login_required
@handle_api_error
def process_one_storyboard_task():
    """处理一个分镜队列任务"""
    user_id = session.get("user_id")

    result = database.process_one_storyboard_queue_task(user_id)

    if result.get("error"):
        return ApiResponse.bad_request(result["error"])

    return ApiResponse.success(result)
