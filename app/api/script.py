"""
剧本生成相关 API
"""

import json

from flask import Blueprint, Response, request, session, stream_with_context

import database
from app.decorators import handle_api_error, login_required
from app.utils import ApiResponse

# 创建蓝图
script_bp = Blueprint("script", __name__)


@script_bp.route("/script-generate")
@login_required
def script_generate_page():
    """剧本生成页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("script_generate.html", user=user)


@script_bp.route("/script-analysis")
@login_required
def script_analysis_page():
    """剧本分析页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("script_analysis.html", user=user)


@script_bp.route("/api/script-generate", methods=["POST"])
@login_required
@handle_api_error
def generate_script():
    """生成剧本"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    novel_text = data.get("novel_text", "").strip()

    if not novel_text:
        return ApiResponse.bad_request("小说文本不能为空")

    # 提取参数
    params = {
        "novel_text": novel_text,
        "title": data.get("title", ""),
        "min_seconds": data.get("min_seconds", 60),
        "max_seconds": data.get("max_seconds", 120),
        "prompt_template": data.get("prompt_template"),
    }

    # 生成剧本
    result = database.generate_script(user_id, project_id, params)

    return ApiResponse.success(result, "剧本生成成功")


@script_bp.route("/api/script-generate-stream", methods=["POST"])
@login_required
def generate_script_stream():
    """流式生成剧本"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    novel_text = data.get("novel_text", "").strip()

    if not novel_text:
        return ApiResponse.bad_request("小说文本不能为空")

    def generate():
        try:
            for chunk in database.generate_script_stream(user_id, project_id, data):
                yield f"data: {json.dumps(chunk)}\n\n"
        except GeneratorExit:
            pass

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@script_bp.route("/api/script-generate-async", methods=["POST"])
@login_required
@handle_api_error
def generate_script_async():
    """异步生成剧本"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    novel_text = data.get("novel_text", "").strip()

    if not novel_text:
        return ApiResponse.bad_request("小说文本不能为空")

    # 创建异步任务
    task_id = database.create_script_generation_task(user_id, project_id, data)

    return ApiResponse.created({"task_id": task_id, "status": "pending"}, "任务已创建")


@script_bp.route("/api/tasks/<int:task_id>", methods=["GET"])
@login_required
def get_task_status(task_id: int):
    """获取任务状态"""
    user_id = session.get("user_id")

    task = database.get_generation_task(user_id, task_id)

    if not task:
        return ApiResponse.not_found("任务不存在")

    return ApiResponse.success(task)


@script_bp.route("/api/script-saves", methods=["GET"])
@login_required
def get_script_saves():
    """获取保存的剧本"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    saves = database.get_script_saves(user_id, project_id)

    return ApiResponse.success(saves)


@script_bp.route("/api/script-saves", methods=["POST"])
@login_required
@handle_api_error
def save_script():
    """保存剧本"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    title = data.get("title", "").strip()
    novel_text = data.get("novel_text", "")
    script_text = data.get("script_text", "")
    episodes_json = data.get("episodes_json")

    if not title:
        return ApiResponse.bad_request("标题不能为空")

    save_id = database.save_script(
        user_id,
        project_id,
        {
            "title": title,
            "novel_text": novel_text,
            "script_text": script_text,
            "episodes_json": episodes_json,
        },
    )

    return ApiResponse.created({"id": save_id}, "剧本已保存")


@script_bp.route("/api/script-episodes", methods=["GET"])
@login_required
def get_script_episodes():
    """获取剧本分集"""
    user_id = session.get("user_id")
    script_id = request.args.get("script_id", type=int)

    if not script_id:
        return ApiResponse.bad_request("剧本ID不能为空")

    episodes = database.get_script_episodes(user_id, script_id)

    return ApiResponse.success(episodes)


@script_bp.route("/api/script-episodes", methods=["POST"])
@login_required
@handle_api_error
def create_episode():
    """创建剧本分集"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    script_id = data.get("script_id")
    episode_index = data.get("episode_index")
    title = data.get("title", "")
    content_url = data.get("content_url", "")

    if not script_id:
        return ApiResponse.bad_request("剧本ID不能为空")

    episode_id = database.create_script_episode(
        user_id,
        project_id,
        {
            "script_id": script_id,
            "episode_index": episode_index,
            "title": title,
            "content_url": content_url,
        },
    )

    return ApiResponse.created({"id": episode_id}, "分集已创建")


@script_bp.route("/api/script-episodes/<int:episode_id>", methods=["GET"])
@login_required
def get_episode_content(episode_id: int):
    """获取分集内容"""
    user_id = session.get("user_id")

    episode = database.get_script_episode(user_id, episode_id)

    if not episode:
        return ApiResponse.not_found("分集不存在")

    return ApiResponse.success(episode)


@script_bp.route("/api/script-episodes/<int:episode_id>", methods=["POST"])
@login_required
@handle_api_error
def update_episode(episode_id: int):
    """更新分集"""
    user_id = session.get("user_id")

    # 检查分集是否存在
    episode = database.get_script_episode(user_id, episode_id)
    if not episode:
        return ApiResponse.not_found("分集不存在")

    data = request.json
    database.update_script_episode(episode_id, data)

    return ApiResponse.success(None, "分集已更新")


@script_bp.route("/api/script-episodes/<int:episode_id>", methods=["DELETE"])
@login_required
def delete_episode(episode_id: int):
    """删除分集"""
    user_id = session.get("user_id")

    # 检查分集是否存在
    episode = database.get_script_episode(user_id, episode_id)
    if not episode:
        return ApiResponse.not_found("分集不存在")

    database.delete_script_episode(episode_id)

    return ApiResponse.no_content()


@script_bp.route("/api/script-episodes/import", methods=["POST"])
@login_required
@handle_api_error
def import_episodes():
    """导入分集"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    script_id = data.get("script_id")
    episodes = data.get("episodes", [])

    if not script_id:
        return ApiResponse.bad_request("剧本ID不能为空")

    imported_count = database.import_script_episodes(user_id, project_id, script_id, episodes)

    return ApiResponse.success(
        {"imported_count": imported_count}, f"已导入 {imported_count} 集内容"
    )


@script_bp.route("/api/script-templates", methods=["GET"])
@login_required
def get_script_templates():
    """获取剧本模板"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    templates = database.get_script_templates(user_id, project_id)

    return ApiResponse.success(templates)


@script_bp.route("/api/script-templates", methods=["POST"])
@login_required
@handle_api_error
def save_script_template():
    """保存剧本模板"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    name = data.get("name", "").strip()
    prompt = data.get("prompt", "")

    if not name or not prompt:
        return ApiResponse.bad_request("名称和提示词不能为空")

    template_id = database.save_script_template(
        user_id, project_id, {"name": name, "prompt": prompt}
    )

    return ApiResponse.created({"id": template_id}, "模板已保存")


@script_bp.route("/api/script-templates/<int:template_id>", methods=["DELETE"])
@login_required
def delete_script_template(template_id: int):
    """删除剧本模板"""
    user_id = session.get("user_id")

    database.delete_script_template(user_id, template_id)

    return ApiResponse.no_content()
