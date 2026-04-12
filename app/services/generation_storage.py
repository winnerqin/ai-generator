"""Storage helpers for generated and uploaded image assets."""

from __future__ import annotations

import os
import random
from typing import Any, Optional

import database
from werkzeug.utils import secure_filename

from app.services.oss_service import oss_service


def get_scoped_folder(root_folder: str, user_id: int, project_id: Optional[int]) -> str:
    folder = os.path.join(root_folder, str(user_id))
    if project_id:
        folder = os.path.join(folder, f"project_{project_id}")
    os.makedirs(folder, exist_ok=True)
    return folder


def get_user_upload_folder(user_id: int, project_id: Optional[int]) -> str:
    return get_scoped_folder("uploads", user_id, project_id)


def get_user_output_folder(user_id: int, project_id: Optional[int]) -> str:
    return get_scoped_folder("output", user_id, project_id)


def generate_random_filename(length: int = 8) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(chars) for _ in range(length))


def get_unique_filename(folder: str, base_filename: str, extension: str = ".jpg") -> str:
    if not base_filename or not base_filename.strip():
        base_filename = generate_random_filename(8)
    if not base_filename.endswith(extension):
        base_filename = f"{base_filename}{extension}"
    if not os.path.exists(os.path.join(folder, base_filename)):
        return base_filename

    name_without_ext = base_filename[: -len(extension)]
    for counter in range(1, 1001):
        candidate = f"{name_without_ext}_{counter}{extension}"
        if not os.path.exists(os.path.join(folder, candidate)):
            return candidate
    return f"{generate_random_filename(8)}{extension}"


def build_output_url(user_id: int, project_id: Optional[int], filename: str) -> str:
    if project_id:
        return f"/output/{user_id}/{project_id}/{filename}"
    return f"/output/{user_id}/{filename}"


def save_uploaded_reference_images(
    user_id: int,
    project_id: Optional[int],
    uploaded_files,
) -> list[str]:
    image_urls: list[str] = []
    upload_folder = get_user_upload_folder(user_id, project_id)
    upload_to_oss = os.environ.get("OSS_ENABLED", "false").lower() == "true"

    for file in uploaded_files:
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        if upload_to_oss and oss_service.is_available():
            uploaded_url = oss_service.upload_file(
                file_path=file_path,
                user_id=user_id,
                project_id=project_id,
                file_type="image",
            )
            if uploaded_url:
                image_urls.append(uploaded_url)
    return image_urls


def _build_filename(output_folder: str, output_filename: str, index: int, group_index: Optional[int]) -> str:
    if output_filename:
        base_name = output_filename[:-4] if output_filename.endswith(".jpg") else output_filename
        suffix = f"_g{index + 1}_{group_index + 1}" if group_index is not None else f"_{index + 1}"
        return get_unique_filename(output_folder, f"{base_name}{suffix}", ".jpg")

    random_name = generate_random_filename(8)
    if group_index is not None:
        return f"{random_name}_g{index + 1}_{group_index + 1}.jpg"
    return f"{random_name}_{index + 1}.jpg"


def save_generated_image(
    *,
    user_id: int,
    project_id: Optional[int],
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    width: int,
    height: int,
    image_style: str,
    image_urls: list[str],
    seed: int,
    output_filename: str,
    index: int,
    group_index: Optional[int],
    content: bytes,
) -> dict[str, Any]:
    output_folder = get_user_output_folder(user_id, project_id)
    filename = _build_filename(output_folder, output_filename, index, group_index)
    output_path = os.path.join(output_folder, filename)
    with open(output_path, "wb") as file:
        file.write(content)

    final_url = build_output_url(user_id, project_id, filename)
    if oss_service.is_available():
        uploaded_url = oss_service.upload_file(
            file_path=output_path,
            user_id=user_id,
            project_id=project_id,
            file_type="image",
        )
        if uploaded_url:
            final_url = uploaded_url

    sample_images = [{"url": url, "filename": os.path.basename(url)} for url in image_urls]
    record_id = database.save_generation_record(
        {
            "user_id": user_id,
            "project_id": project_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "width": width,
            "height": height,
            "num_images": 1,
            "seed": seed,
            "image_style": image_style,
            "sample_images": sample_images,
            "image_path": final_url,
            "filename": filename,
            "status": "success",
        }
    )

    database.save_image_asset(
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        url=final_url,
        meta={
            "record_id": record_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "width": width,
            "height": height,
            "seed": seed,
            "image_style": image_style,
        },
    )

    return {
        "filename": filename,
        "url": final_url,
        "seed": seed,
        "record_id": record_id,
    }
