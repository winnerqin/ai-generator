"""
图片生成相关 API
"""

import json
import base64
import io
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, session, stream_with_context
from openai import OpenAI
import requests

import database
from app.decorators import handle_api_error, login_required
from app.services import (
    file_upload_service,
    generate_legacy_request,
    oss_service,
    resume_legacy_generation_stream,
)
from app.services.generation_storage import save_generated_image
from app.utils import ApiResponse

# 创建蓝图
image_bp = Blueprint("image", __name__)
logger = logging.getLogger(__name__)

IMAGE2_MODEL = "gpt-image-2"
IMAGE2_FORMAT = "jpeg"
IMAGE2_QUALITIES = {"standard", "hd", "low", "medium", "high", "auto"}
IMAGE2_PRESET_SIZES = {"1024x1024", "1024x1536", "1536x1024"}
IMAGE2_MAX_WIDTH = 3840
IMAGE2_MAX_HEIGHT = 2160
IMAGE2_MAX_IMAGES = 10
IMAGE2_MAX_REFERENCE_IMAGES = 16
IMAGE2_REFERENCE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}


def _pagination_args(default_page_size: int = 20, max_page_size: int = 200) -> tuple[int, int, int]:
    page = request.args.get("page", 1, type=int) or 1
    page_size = request.args.get("page_size", default_page_size, type=int) or default_page_size
    page = max(1, page)
    page_size = max(1, min(max_page_size, page_size))
    return page, page_size, (page - 1) * page_size


def _paginate_items(items: list[dict], page: int, page_size: int) -> tuple[list[dict], int]:
    total = len(items)
    start = (page - 1) * page_size
    return items[start : start + page_size], total


def _parse_image2_size(data: dict[str, Any]) -> tuple[str, int, int]:
    size_mode = data.get("size", "1024x1024")
    if size_mode == "custom":
        width = int(data.get("custom_width") or 0)
        height = int(data.get("custom_height") or 0)
        size = f"{width}x{height}"
    else:
        size = str(size_mode)
        try:
            width_text, height_text = size.split("x", 1)
            width = int(width_text)
            height = int(height_text)
        except (ValueError, TypeError):
            raise ValueError("图片尺寸格式不正确")

    if size_mode != "custom" and size not in IMAGE2_PRESET_SIZES:
        raise ValueError("不支持的图片尺寸")
    if width <= 0 or height <= 0:
        raise ValueError("自定义分辨率必须大于 0")
    if width % 16 != 0 or height % 16 != 0:
        raise ValueError("自定义分辨率宽高必须都能被 16 整除")
    if width > IMAGE2_MAX_WIDTH or height > IMAGE2_MAX_HEIGHT:
        raise ValueError("自定义分辨率最大为 3840x2160")
    return size, width, height


def _create_openai_image_client() -> OpenAI:
    api_key = os.environ.get("IMAGE2_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("IMAGE2_OPENAI_API_KEY is not configured")
    base_url = os.environ.get("IMAGE2_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _image2_item_to_bytes(item: Any) -> bytes:
    b64_json = getattr(item, "b64_json", None)
    if b64_json:
        return base64.b64decode(b64_json)

    image_url = getattr(item, "url", None)
    if image_url:
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        return response.content

    raise ValueError("API returned no image content")


def _image2_reference_files() -> list[io.BytesIO]:
    files = request.files.getlist("reference_images")
    reference_urls = request.form.getlist("reference_image_urls")
    if len(files) + len(reference_urls) > IMAGE2_MAX_REFERENCE_IMAGES:
        raise ValueError(f"参考图最多 {IMAGE2_MAX_REFERENCE_IMAGES} 张")

    references: list[io.BytesIO] = []
    for file in files:
        if not file or not file.filename:
            continue
        extension = os.path.splitext(file.filename)[1].lower()
        if extension not in IMAGE2_REFERENCE_EXTENSIONS:
            raise ValueError("参考图仅支持 png、webp、jpg")
        content = file.read()
        if not content:
            continue
        reference_file = io.BytesIO(content)
        reference_file.name = file.filename
        references.append(reference_file)

    for index, image_url in enumerate(reference_urls):
        image_url = (image_url or "").strip()
        if not image_url:
            continue
        content = _load_reference_url_bytes(image_url)
        reference_file = io.BytesIO(content)
        reference_file.name = f"reference_{index + 1}.jpg"
        references.append(reference_file)
    return references


def _load_reference_url_bytes(image_url: str) -> bytes:
    if image_url.startswith("/output/"):
        parts = image_url.strip("/").split("/")
        if len(parts) == 3:
            _, user_id, filename = parts
            file_path = Path(current_app.config["OUTPUT_FOLDER"]) / user_id / filename
        elif len(parts) == 4:
            _, user_id, project_id, filename = parts
            file_path = Path(current_app.config["OUTPUT_FOLDER"]) / user_id / f"project_{project_id}" / filename
            if not file_path.exists():
                file_path = Path(current_app.config["OUTPUT_FOLDER"]) / user_id / project_id / filename
        else:
            raise ValueError("参考图 URL 格式不正确")
        if not file_path.exists():
            raise ValueError("参考图文件不存在")
        return file_path.read_bytes()

    response = requests.get(image_url, timeout=60)
    response.raise_for_status()
    return response.content


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
    project_id = session.get("current_project_id")
    page_requested = "page" in request.args or "page_size" in request.args

    if page_requested:
        page, page_size, offset = _pagination_args()
        images = database.get_image_assets(user_id, project_id, page_size, offset=offset)
        total = database.count_image_assets(user_id, project_id)
    else:
        limit = max(1, min(500, request.args.get("limit", 20, type=int) or 20))
        page, page_size = 1, limit
        images = database.get_image_assets(user_id, project_id, limit)
        total = len(images)

    return jsonify(
        {
            "success": True,
            "images": images,
            "data": {"images": images},
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    )


@image_bp.route("/api/sample-images", methods=["GET"])
@login_required
def get_sample_images():
    """获取示例图片"""
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    category = request.args.get("category")  # person, scene, all
    page, page_size, _ = _pagination_args()

    # 尝试从 OSS 获取
    if oss_service.is_available():
        all_images = oss_service.list_sample_images(user_id, project_id, category)
        images, total = _paginate_items(all_images, page, page_size)
        return jsonify(
            {
                "success": True,
                "images": images,
                "data": {"images": images},
                "page": page,
                "page_size": page_size,
                "total": total,
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

    images, total = _paginate_items(images, page, page_size)

    return jsonify(
        {
            "success": True,
            "images": images,
            "data": {"images": images},
            "page": page,
            "page_size": page_size,
            "total": total,
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


@image_bp.route("/api/image2/generate", methods=["POST"])
@login_required
@handle_api_error
def generate_image2():
    """Generate images with OpenAI gpt-image-2."""
    user_id = session.get("user_id")
    username = session.get("username")
    project_id = session.get("current_project_id")
    data = request.json if request.is_json else request.form.to_dict()

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return ApiResponse.bad_request("提示词不能为空")

    quality = data.get("quality", "auto")
    if quality not in IMAGE2_QUALITIES:
        return ApiResponse.bad_request("图片质量参数不正确")

    try:
        size, width, height = _parse_image2_size(data)
        num_images = int(data.get("num_images") or 1)
        reference_files = [] if request.is_json else _image2_reference_files()
    except (TypeError, ValueError) as exc:
        return ApiResponse.bad_request(str(exc))

    if num_images < 1:
        return ApiResponse.bad_request("生成数量必须大于等于 1")
    if num_images > IMAGE2_MAX_IMAGES:
        return ApiResponse.bad_request(f"生成数量最大为 {IMAGE2_MAX_IMAGES}")

    endpoint = "/images/edits" if reference_files else "/images/generations"
    request_payload = {
        "model": IMAGE2_MODEL,
        "prompt": prompt,
        "output_format": IMAGE2_FORMAT,
        "quality": quality,
        "size": size,
        "n": num_images,
        "endpoint": endpoint,
        "reference_count": len(reference_files),
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
    }
    logger.info("[image2][request] payload=%s", json.dumps(request_payload, ensure_ascii=False))
    client = _create_openai_image_client()
    if reference_files:
        response = client.images.edit(
            model=IMAGE2_MODEL,
            image=reference_files,
            prompt=prompt,
            output_format=IMAGE2_FORMAT,
            quality=quality,
            size=size,
            n=num_images,
        )
    else:
        response = client.images.generate(
            model=IMAGE2_MODEL,
            prompt=prompt,
            output_format=IMAGE2_FORMAT,
            quality=quality,
            size=size,
            n=num_images,
        )

    usage = getattr(response, "usage", None)
    total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
    usage_payload = usage.model_dump() if hasattr(usage, "model_dump") else (usage or {})
    logger.info(
        "[image2][response] data_count=%s total_tokens=%s usage=%s",
        len(getattr(response, "data", []) or []),
        total_tokens,
        json.dumps(usage_payload, ensure_ascii=False, default=str),
    )
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    images = []
    for index, item in enumerate(getattr(response, "data", []) or []):
        image_bytes = _image2_item_to_bytes(item)
        saved = save_generated_image(
            user_id=user_id,
            project_id=project_id,
            prompt=prompt,
            aspect_ratio="custom",
            resolution=size,
            width=width,
            height=height,
            image_style=IMAGE2_MODEL,
            image_urls=[],
            seed=0,
            created_at=created_at,
            output_filename="image2",
            index=index,
            group_index=None,
            token_usage=total_tokens,
            content=image_bytes,
        )
        images.append(saved)
        logger.info(
            "[image2][saved] filename=%s url=%s record_id=%s total_tokens=%s",
            saved.get("filename"),
            saved.get("url"),
            saved.get("record_id"),
            total_tokens,
        )

    if not images:
        return ApiResponse.server_error("API 未返回图片")

    return ApiResponse.success(
        {
            "images": images,
            "model": IMAGE2_MODEL,
            "endpoint": endpoint,
            "reference_count": len(reference_files),
            "output_format": IMAGE2_FORMAT,
            "quality": quality,
            "size": size,
            "usage": usage_payload,
            "total_tokens": total_tokens,
        },
        "生成成功",
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
