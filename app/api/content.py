"""Content management and asset library APIs."""

from __future__ import annotations

import mimetypes
from io import BytesIO
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session

import database
from app.decorators import handle_api_error, login_required
from app.services import file_upload_service, oss_service

content_bp = Blueprint("content", __name__)


def _current_user_context() -> dict[str, object]:
    return {"username": session.get("username", ""), "id": session.get("user_id")}


def _append_assets(target: list[dict], items: list[dict], prefix: str, asset_type: str) -> None:
    for item in items:
        target.append(
            {
                "id": f"{prefix}_{item.get('id')}",
                "url": item.get("url"),
                "filename": item.get("filename"),
                "type": asset_type,
                "source": "database",
                "created_at": item.get("created_at"),
                "meta": item.get("meta", {}),
            }
        )


def _append_image_material_assets(target: list[dict], items: list[dict], prefix: str, origin: str) -> None:
    for item in items:
        meta = item.get("meta", {}) or {}
        meta.setdefault("source_library", origin)
        target.append(
            {
                "id": f"{prefix}_{item.get('id')}",
                "url": item.get("url"),
                "filename": item.get("filename"),
                "type": "image",
                "source": "database",
                "created_at": item.get("created_at"),
                "meta": meta,
            }
        )


def _public_asset_url(path_or_url: str) -> str:
    if not path_or_url:
        return path_or_url
    if path_or_url.startswith(("http://", "https://", "/uploads/")):
        return path_or_url

    upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve()
    asset_path = Path(path_or_url).resolve()
    try:
        relative_path = asset_path.relative_to(upload_root)
    except ValueError:
        return path_or_url
    return f"/uploads/{relative_path.as_posix()}"


def _normalized_asset_url(path_or_url: str) -> str:
    return _public_asset_url((path_or_url or "").strip())


def _is_media_upload_asset(item: dict) -> bool:
    meta = item.get("meta") or {}
    url = str(item.get("url") or "").lower()
    if meta.get("library_group") == "media":
        return True
    if meta.get("library_group") == "video":
        return False
    if meta.get("task_id") or meta.get("source") == "omni_video" or meta.get("model"):
        return False
    if meta.get("mime_type"):
        return True
    return "media_video" in url or "media_audio" in url


def _is_generated_video_asset(item: dict) -> bool:
    meta = item.get("meta") or {}
    if meta.get("library_group") == "video":
        return True
    return bool(meta.get("task_id") or meta.get("source") == "omni_video" or meta.get("model"))


def _get_database_asset(asset_id: str, user_id: int, project_id: int | None) -> dict | None:
    sources = (
        ("db_person_", database.get_person_assets),
        ("db_scene_", database.get_scene_assets),
        ("db_image_", database.get_image_assets),
        ("db_video_", database.get_video_assets),
        ("db_audio_", database.get_audio_assets),
    )
    for prefix, loader in sources:
        if not asset_id.startswith(prefix):
            continue
        raw_id = asset_id.removeprefix(prefix)
        for asset in loader(user_id, project_id):
            if str(asset.get("id")) == raw_id:
                return asset
        return None
    return None


def _resolve_local_file_path(path_or_url: str) -> Path | None:
    value = (path_or_url or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return None
    if value.startswith("/uploads/"):
        upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve()
        return (upload_root / value.removeprefix("/uploads/").lstrip("/\\")).resolve()
    if value.startswith("/output/"):
        output_root = Path(current_app.config.get("OUTPUT_FOLDER", "output")).resolve()
        return (output_root / value.removeprefix("/output/").lstrip("/\\")).resolve()

    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    return None


@content_bp.route("/content-management")
@login_required
def content_management_page():
    return render_template("content_management.html", user=_current_user_context())


@content_bp.route("/manage-samples")
@login_required
def manage_samples_page():
    return render_template("manage_samples.html", user=_current_user_context())


@content_bp.route("/api/content-library", methods=["GET"])
@login_required
def get_content_library():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    library_type = request.args.get("type", "all")

    assets: list[dict] = []

    if oss_service.is_available():
        if library_type in ("person", "all", "image_material"):
            for item in oss_service.list_sample_images(user_id, project_id, "person"):
                assets.append(
                    {
                        "id": item.get("key", "oss_person"),
                        "url": item.get("url"),
                        "filename": item.get("filename"),
                        "type": "image" if library_type == "image_material" else "person",
                        "source": "oss",
                        "created_at": item.get("last_modified"),
                        "meta": {"source_library": "person"},
                    }
                )
        if library_type in ("scene", "all", "image_material"):
            for item in oss_service.list_sample_images(user_id, project_id, "scene"):
                assets.append(
                    {
                        "id": item.get("key", "oss_scene"),
                        "url": item.get("url"),
                        "filename": item.get("filename"),
                        "type": "image" if library_type == "image_material" else "scene",
                        "source": "oss",
                        "created_at": item.get("last_modified"),
                        "meta": {"source_library": "scene"},
                    }
                )

    if library_type in ("person", "all"):
        _append_assets(assets, database.get_person_assets(user_id, project_id), "db_person", "person")
    if library_type in ("scene", "all"):
        _append_assets(assets, database.get_scene_assets(user_id, project_id), "db_scene", "scene")
    if library_type == "image_material":
        _append_image_material_assets(
            assets,
            database.get_person_assets(user_id, project_id),
            "db_person",
            "person",
        )
        _append_image_material_assets(
            assets,
            database.get_scene_assets(user_id, project_id),
            "db_scene",
            "scene",
        )
    if library_type in ("image", "all"):
        _append_assets(assets, database.get_image_assets(user_id, project_id), "db_image", "image")
    video_assets = database.get_video_assets(user_id, project_id)
    if library_type == "video":
        _append_assets(
            assets,
            [item for item in video_assets if _is_generated_video_asset(item)],
            "db_video",
            "video",
        )
    if library_type == "all":
        _append_assets(assets, video_assets, "db_video", "video")
    if library_type == "media":
        _append_assets(
            assets,
            [item for item in video_assets if _is_media_upload_asset(item)],
            "db_video",
            "video",
        )
    if library_type in ("audio", "all", "media"):
        _append_assets(assets, database.get_audio_assets(user_id, project_id), "db_audio", "audio")

    for asset in assets:
        asset["url"] = _public_asset_url(str(asset.get("url") or ""))

    return jsonify({"success": True, "assets": assets})


@content_bp.route("/api/upload-media-asset", methods=["POST"])
@login_required
@handle_api_error
def upload_media_asset():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")

    file = request.files.get("file")
    library_type = (request.form.get("type") or "media").strip().lower()
    if not file:
        return jsonify({"success": False, "error": "鏈€夋嫨鏂囦欢"}), 400

    filename = file.filename or ""
    mime_type = mimetypes.guess_type(filename)[0] or ""
    if library_type == "media":
        if mime_type.startswith("audio/"):
            library_type = "audio"
        elif mime_type.startswith("video/"):
            library_type = "video"
        else:
            return jsonify({"success": False, "error": "音视频素材仅支持音频或视频文件"}), 400
    elif library_type == "image_material":
        if not mime_type.startswith("image/"):
            return jsonify({"success": False, "error": "图片素材仅支持图片文件"}), 400

    if library_type == "audio":
        file_type = "audio"
        subfolder = "media_audio"
    elif library_type == "video":
        file_type = "video"
        subfolder = "media_video"
    else:
        file_type = "image"
        subfolder = "material_image"

    success, path_or_url, error = file_upload_service.save_uploaded_file(
        file=file,
        user_id=user_id,
        project_id=project_id,
        subfolder=subfolder,
        file_type=file_type,
        upload_to_oss=True,
    )
    if not success:
        return jsonify({"success": False, "error": error}), 400

    meta = {"mime_type": mime_type}
    if library_type == "audio":
        meta["library_group"] = "media"
        asset_id = database.save_audio_asset(
            user_id=user_id,
            filename=filename,
            url=path_or_url,
            meta=meta,
            project_id=project_id,
        )
    elif library_type == "video":
        meta["library_group"] = "media"
        asset_id = database.save_video_asset(
            user_id=user_id,
            filename=filename,
            url=path_or_url,
            meta=meta,
            project_id=project_id,
        )
    else:
        meta["library_group"] = "image_material"
        asset_id = database.save_person_asset(
            user_id=user_id,
            filename=filename,
            url=path_or_url,
            meta=meta,
            project_id=project_id,
        )

    public_url = _public_asset_url(path_or_url)
    return jsonify(
        {
            "success": True,
            "asset": {
                "id": asset_id,
                "filename": filename,
                "url": public_url,
                "type": "image" if library_type == "image_material" else library_type,
                "meta": meta,
            },
            "message": "绱犳潗涓婁紶鎴愬姛",
        }
    )
@content_bp.route("/api/add-to-image-material", methods=["POST"])
@login_required
@handle_api_error
def add_to_image_material():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}
    url = _normalized_asset_url(data.get("url") or "")
    if not url:
        return jsonify({"success": False, "error": "URL 不能为空"}), 400

    meta = data.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    meta["library_group"] = "image_material"
    meta.setdefault("source_library", "image_library")

    for existing_asset in database.get_person_assets(user_id, project_id):
        existing_url = _normalized_asset_url(str(existing_asset.get("url") or ""))
        if existing_url == url:
            return jsonify(
                {
                    "success": True,
                    "id": existing_asset.get("id"),
                    "message": "该图片已在图片素材中",
                }
            )

    library_id = database.save_person_asset(
        user_id=user_id,
        filename=(data.get("filename") or "").strip(),
        url=url,
        meta=meta,
        project_id=project_id,
    )
    return jsonify({"success": True, "id": library_id, "message": "已添加到图片素材"})


@content_bp.route("/api/add-to-person-library", methods=["POST"])
@login_required
@handle_api_error
def add_to_person_library():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    if not url:
        return jsonify({"success": False, "error": "URL 涓嶈兘涓虹┖"}), 400

    library_id = database.save_person_asset(
        user_id=user_id,
        filename=data.get("filename", ""),
        url=url,
        meta=data.get("meta"),
        project_id=project_id,
    )
    return jsonify({"success": True, "id": library_id, "message": "已添加到人物素材"})


@content_bp.route("/api/add-to-scene-library", methods=["POST"])
@login_required
@handle_api_error
def add_to_scene_library():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    if not url:
        return jsonify({"success": False, "error": "URL 涓嶈兘涓虹┖"}), 400

    library_id = database.save_scene_asset(
        user_id=user_id,
        filename=data.get("filename", ""),
        url=url,
        meta=data.get("meta"),
        project_id=project_id,
    )
    return jsonify({"success": True, "id": library_id, "message": "已添加到场景素材"})


@content_bp.route("/api/delete-library-asset", methods=["POST"])
@login_required
def delete_library_asset():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or request.form.to_dict()
    asset_id = (data.get("id") or data.get("key") or "").strip()
    if not asset_id:
        return jsonify({"success": False, "error": "参数不完整"}), 400

    try:
        asset = _get_database_asset(asset_id, user_id, project_id)
        if asset_id.startswith("db_person_"):
            database.delete_person_asset(int(asset_id.replace("db_person_", "")), user_id)
        elif asset_id.startswith("db_scene_"):
            database.delete_scene_asset(int(asset_id.replace("db_scene_", "")), user_id)
        elif asset_id.startswith("db_image_"):
            database.delete_image_asset(int(asset_id.replace("db_image_", "")), user_id)
        elif asset_id.startswith("db_video_"):
            meta = (asset or {}).get("meta") or {}
            task_id = (meta.get("task_id") or "").strip()
            if task_id:
                database.mark_video_task_deleted_from_library(user_id, task_id, project_id=project_id)
            database.delete_video_asset(int(asset_id.replace("db_video_", "")), user_id)
        elif asset_id.startswith("db_audio_"):
            database.delete_audio_asset(int(asset_id.replace("db_audio_", "")), user_id)
        else:
            file_upload_service.delete_file(asset_id, is_oss=True)

        asset_url = str((asset or {}).get("url") or "").strip()
        if asset_url.startswith(("http://", "https://")):
            file_upload_service.delete_file(asset_url, is_oss=True)
        else:
            local_path = _resolve_local_file_path(asset_url)
            if local_path and local_path.exists():
                local_path.unlink()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({"success": True, "message": "资源已删除"})


@content_bp.route("/api/rename-library-asset", methods=["POST"])
@login_required
def rename_library_asset():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    data = request.get_json(silent=True) or request.form.to_dict()
    asset_id = (data.get("id") or "").strip()
    filename = (data.get("filename") or "").strip()

    if not asset_id or not filename:
        return jsonify({"success": False, "error": "缂哄皯绱犳潗 ID 鎴栨枃浠跺悕"}), 400

    try:
        if asset_id.startswith("db_video_"):
            updated = database.rename_video_asset(
                int(asset_id.replace("db_video_", "")),
                filename,
                user_id=user_id,
                project_id=project_id,
            )
        else:
            return jsonify({"success": False, "error": "当前仅支持视频库重命名"}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    if not updated:
        return jsonify({"success": False, "error": "素材不存在"}), 404
    return jsonify({"success": True, "message": "重命名成功", "filename": filename})


@content_bp.route("/api/download-library-asset", methods=["GET"])
@login_required
def download_library_asset():
    user_id = session.get("user_id")
    project_id = session.get("current_project_id")
    asset_id = (request.args.get("id") or "").strip()
    if not asset_id:
        return jsonify({"success": False, "error": "缺少素材 ID"}), 400

    asset = _get_database_asset(asset_id, user_id, project_id)
    if not asset:
        return jsonify({"success": False, "error": "素材不存在"}), 404

    filename = (asset.get("filename") or "asset").strip() or "asset"
    asset_url = str(asset.get("url") or "").strip()
    local_path = _resolve_local_file_path(asset_url)
    if local_path and local_path.exists():
        return send_file(local_path, as_attachment=True, download_name=filename)

    if not asset_url:
        return jsonify({"success": False, "error": "素材无可下载地址"}), 400

    try:
        response = requests.get(_public_asset_url(asset_url), timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"success": False, "error": f"下载失败: {exc}"}), 502

    mimetype = response.headers.get("Content-Type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return send_file(
        BytesIO(response.content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@content_bp.route("/api/image-styles", methods=["POST"])
@login_required
@handle_api_error
def create_image_style():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "鏍峰紡鍚嶇О涓嶈兘涓虹┖"}), 400
    return jsonify({"success": True, "id": 1, "message": "样式已创建"})


@content_bp.route("/api/image-styles/<int:style_id>", methods=["DELETE"])
@login_required
def delete_image_style(style_id: int):
    return jsonify({"success": True, "message": "样式已删除"})


@content_bp.route("/output/<int:user_id>/<int:project_id>/<filename>")
@login_required
def get_output_file(user_id: int, project_id: int, filename: str):
    current_user_id = session.get("user_id")
    if current_user_id != user_id:
        return jsonify({"success": False, "error": "无权访问该文件"}), 403

    output_dir = Path(current_app.config.get("OUTPUT_FOLDER", "output"))
    file_path = output_dir / str(user_id) / str(project_id) / filename
    if not file_path.exists():
        return jsonify({"success": False, "error": "文件不存在"}), 404
    return send_file(file_path)


@content_bp.route("/output/<int:user_id>/<filename>")
@login_required
def get_output_file_simple(user_id: int, filename: str):
    current_user_id = session.get("user_id")
    if current_user_id != user_id:
        return jsonify({"success": False, "error": "无权访问该文件"}), 403

    output_dir = Path(current_app.config.get("OUTPUT_FOLDER", "output"))
    file_path = output_dir / str(user_id) / filename
    if not file_path.exists():
        return jsonify({"success": False, "error": "文件不存在"}), 404
    return send_file(file_path)

