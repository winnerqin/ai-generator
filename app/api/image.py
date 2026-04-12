"""
图片生成相关 API
"""

import json
import time

from flask import Blueprint, Response, jsonify, request, session, stream_with_context

import database
from app.decorators import handle_api_error, login_required
from app.services import (
    file_upload_service,
    generate_legacy_request,
    oss_service,
    resume_legacy_generation_stream,
)
from app.utils import ApiResponse

# 创建蓝图
image_bp = Blueprint("image", __name__)


@image_bp.route("/api/image-styles", methods=["GET"])
@login_required
def get_image_styles():
    """获取图片风格列表"""
    import os

    try:
        styles_file = os.path.join("static", "styles.json")
        if os.path.exists(styles_file):
            with open(styles_file, "r", encoding="utf-8") as f:
                import json

                data = json.load(f)
                styles = data.get("styles", [])
                return jsonify(
                    {
                        "success": True,
                        "styles": styles,
                        "data": {"styles": styles},
                    }
                )
        else:
            return ApiResponse.not_found("风格文件不存在")
    except Exception as e:
        return ApiResponse.server_error(str(e))


@image_bp.route("/api/recent-images", methods=["GET"])
@login_required
def get_recent_images():
    """获取最近生成的图片"""
    user_id = session.get("user_id")
    limit = request.args.get("limit", 20, type=int)
    project_id = session.get("current_project_id")

    # 使用 image_library 表获取最近的图片
    images = database.get_image_assets(user_id, project_id, limit)

    return jsonify(
        {
            "success": True,
            "images": images,
            "data": {"images": images},
        }
    )


@image_bp.route("/api/sample-images", methods=["GET"])
@login_required
def get_sample_images():
    """获取示例图片"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    category = request.args.get("category")  # person, scene, all

    # 尝试从 OSS 获取
    if oss_service.is_available():
        images = oss_service.list_sample_images(user_id, project_id, category)
        return jsonify(
            {
                "success": True,
                "images": images,
                "data": {"images": images},
            }
        )

    # 从数据库获取 person 和 scene 资源
    images = []
    if category in ("person", "all"):
        person_assets = database.get_person_assets(user_id, project_id)
        for a in person_assets:
            images.append(
                {
                    "url": a.get("url"),
                    "filename": a.get("filename"),
                    "category": "person",
                }
            )

    if category in ("scene", "all"):
        scene_assets = database.get_scene_assets(user_id, project_id)
        for a in scene_assets:
            images.append(
                {
                    "url": a.get("url"),
                    "filename": a.get("filename"),
                    "category": "scene",
                }
            )

    return jsonify(
        {
            "success": True,
            "images": images,
            "data": {"images": images},
        }
    )


@image_bp.route("/api/upload-sample-image", methods=["POST"])
@login_required
@handle_api_error
def upload_sample_image():
    """上传示例图片"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    category = request.form.get("category", "person")  # person or scene

    file = request.files.get("file")
    if not file:
        return ApiResponse.bad_request("未选择文件")

    # 保存文件
    success, path_or_url, error = file_upload_service.save_uploaded_file(
        file=file,
        user_id=user_id,
        project_id=project_id,
        subfolder=category,
        file_type="image",
        upload_to_oss=True,
    )

    if not success:
        return ApiResponse.bad_request(error)

    # 保存到数据库
    if category == "person":
        database.save_person_asset(
            user_id=user_id,
            filename=file.filename,
            url=path_or_url,
            project_id=project_id,
        )
    else:
        database.save_scene_asset(
            user_id=user_id,
            filename=file.filename,
            url=path_or_url,
            project_id=project_id,
        )

    record = {"url": path_or_url, "filename": file.filename, "category": category}
    return ApiResponse.success(record, "上传成功")


@image_bp.route("/api/delete-sample-image", methods=["POST"])
@login_required
def delete_sample_image():
    """删除示例图片"""
    # 支持 JSON 和 FormData 两种格式
    if request.is_json:
        data = request.json
    else:
        data = request.form.to_dict()

    # 前端使用 'key' 或 'id' 作为参数名
    image_id = data.get("id") or data.get("key")
    category = data.get("category", "person")
    if not image_id:
        return ApiResponse.bad_request("图片ID不能为空")

    # 删除文件（这里简化处理，实际应该从数据库获取URL）
    # 根据类别删除
    if category == "person":
        database.delete_person_asset(image_id)
    else:
        database.delete_scene_asset(image_id)

    return ApiResponse.success(None, "删除成功")


@image_bp.route("/api/generate-task", methods=["POST"])
@login_required
@handle_api_error
def generate_image():
    """生成图片"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    # 支持 JSON 和 FormData 两种格式
    if request.is_json:
        data = request.json
    else:
        data = request.form.to_dict()

    prompt = data.get("prompt", "").strip()

    if not prompt:
        return ApiResponse.bad_request("提示词不能为空")

    # 解析 reference_images (如果是 JSON 字符串)
    reference_images = data.get("reference_images", "[]")
    if isinstance(reference_images, str):
        try:
            import json

            reference_images = json.loads(reference_images)
        except (json.JSONDecodeError, TypeError):
            reference_images = []

    # 创建生成任务
    task_id = database.create_generation_task(
        user_id=user_id,
        project_id=project_id,
        task_type="image_generation",
        payload={
            "prompt": prompt,
            "negative_prompt": data.get("negative_prompt", ""),
            "aspect_ratio": data.get("aspect_ratio", "1:1"),
            "resolution": data.get("resolution"),
            "num_images": int(data.get("num_images", 1)) if data.get("num_images") else 1,
            "seed": int(data.get("seed")) if data.get("seed") else None,
            "steps": int(data.get("steps")) if data.get("steps") else None,
            "reference_images": reference_images,
            "style": data.get("style"),
        },
    )

    return ApiResponse.success(
        {"task_id": task_id, "status": "running"},
        "图片生成任务已创建",
    )


@image_bp.route("/api/generate-task/stream", methods=["GET"])
@login_required
def generate_image_stream():
    """获取图片生成流"""
    user_id = session.get("user_id")
    task_id = request.args.get("task_id")

    if not task_id:
        return ApiResponse.bad_request("任务ID不能为空")

    def generate():
        # 生成 SSE 事件流
        try:
            while True:
                # 获取任务状态
                task = database.get_generation_task(user_id, None, task_id)
                if not task:
                    yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'})}\n\n"
                    break

                progress = {
                    "task_id": task_id,
                    "status": task.get("status"),
                    "progress": task.get("progress"),
                    "result": task.get("result_json"),
                }
                yield f"data: {json.dumps(progress)}\n\n"

                if task.get("status") in ["completed", "failed"]:
                    break

                time.sleep(0.5)
        except GeneratorExit:
            pass

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@image_bp.route("/generate", methods=["POST"])
@login_required
def generate_legacy_image():
    """Compatibility route for the legacy generator UI."""

    return generate_legacy_request()


@image_bp.route("/generate/stream", methods=["GET"])
@login_required
def generate_legacy_image_stream():
    """Resume the legacy generator SSE stream."""

    return resume_legacy_generation_stream()


@image_bp.route("/generate/resume", methods=["GET"])
@login_required
def generate_legacy_image_resume():
    """Alias kept for clients that explicitly call /generate/resume."""

    return resume_legacy_generation_stream()


@image_bp.route("/api/delete-image-asset", methods=["POST"])
@login_required
def delete_image_asset():
    """删除生成的图片"""
    # 支持 JSON 和 FormData 两种格式
    if request.is_json:
        data = request.json
    else:
        data = request.form.to_dict()

    # 前端使用 'key' 或 'id' 作为参数名
    record_id = data.get("id") or data.get("key")
    if not record_id:
        return ApiResponse.bad_request("记录ID不能为空")

    # 获取记录
    record = database.get_record_by_id(record_id)
    if not record:
        return ApiResponse.not_found("记录不存在")

    # 删除文件
    if record.get("image_path"):
        file_upload_service.delete_file(record["image_path"], is_oss="oss" in record["image_path"])

    # 从数据库删除
    database.delete_record(record_id)

    return ApiResponse.success(None, "删除成功")
