"""
工具类 API（txt2csv 等）
"""

import json
from pathlib import Path

from flask import Blueprint, Response, request, session, stream_with_context

import database
from app.decorators import handle_api_error, login_required
from app.utils import ApiResponse

# 创建蓝图
tools_bp = Blueprint("tools", __name__)


@tools_bp.route("/txt2csv")
@login_required
def txt2csv_page():
    """文本转 CSV 页面"""
    from flask import render_template

    user = {"username": session.get("username", ""), "id": session.get("user_id")}
    return render_template("txt2csv.html", user=user)


@tools_bp.route("/api/txt2csv-stream", methods=["POST"])
@login_required
def txt2csv_stream():
    """流式文本转 CSV"""
    _ = session.get("user_id")  # 保留供未来使用
    _ = session.get("current_project_id")  # 保留供未来使用

    data = request.json
    text = data.get("text", "").strip()

    if not text:
        return ApiResponse.bad_request("文本不能为空")

    def generate():
        try:
            for chunk in database.txt2csv_stream(text):
                yield f"data: {json.dumps(chunk)}\n\n"
        except GeneratorExit:
            pass

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@tools_bp.route("/api/config-prompts", methods=["GET"])
@login_required
def get_config_prompts():
    """获取配置提示词文件列表"""
    config_dir = Path("config")
    files = []

    if config_dir.exists():
        for file in config_dir.glob("*.md"):
            files.append(file.name)

    files.sort()

    return ApiResponse.success({"files": files})


@tools_bp.route("/api/config-prompts/<path:filename>", methods=["GET"])
@login_required
def get_config_prompt(filename: str):
    """获取配置提示词文件内容"""
    config_dir = Path("config")
    file_path = config_dir / filename

    if not file_path.exists():
        return ApiResponse.not_found("文件不存在")

    content = file_path.read_text(encoding="utf-8")

    return ApiResponse.success({"filename": filename, "content": content})


@tools_bp.route("/api/config-prompts", methods=["POST"])
@login_required
@handle_api_error
def save_config_prompt():
    """保存配置提示词文件"""
    data = request.json
    filename = data.get("filename", "").strip()
    content = data.get("content", "")

    if not filename:
        return ApiResponse.bad_request("文件名不能为空")

    if not filename.endswith(".md"):
        return ApiResponse.bad_request("文件名必须以 .md 结尾")

    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    file_path = config_dir / filename
    file_path.write_text(content, encoding="utf-8")

    return ApiResponse.success(None, "文件已保存")


@tools_bp.route("/api/config-prompts/<path:filename>", methods=["DELETE"])
@login_required
def delete_config_prompt(filename: str):
    """删除配置提示词文件"""
    config_dir = Path("config")
    file_path = config_dir / filename

    if not file_path.exists():
        return ApiResponse.not_found("文件不存在")

    file_path.unlink()

    return ApiResponse.success(None, "文件已删除")


@tools_bp.route("/api/analyze-script", methods=["POST"])
@login_required
@handle_api_error
def analyze_script():
    """分析剧本"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    data = request.json
    script_text = data.get("script_text", "").strip()

    if not script_text:
        return ApiResponse.bad_request("剧本文本不能为空")

    result = database.analyze_script(user_id, project_id, script_text)

    return ApiResponse.success(result, "分析完成")
