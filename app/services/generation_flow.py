"""Core orchestration for the legacy-compatible generation flow."""

from __future__ import annotations

from typing import Any, Iterable, Optional

import requests
from flask import jsonify

from app.services.generation_client import (
    build_prompt,
    create_generation_client,
    load_style_prompt,
    request_images,
)
from app.services.generation_config import GenerationRequest, normalize_seed, resolve_dimensions
from app.services.generation_storage import save_generated_image


def stream_generated_images(
    generation_request: GenerationRequest,
    image_urls: list[str],
) -> Iterable[dict[str, Any]]:
    client = create_generation_client()
    width, height = resolve_dimensions(
        generation_request.aspect_ratio, generation_request.resolution
    )
    style_prompt = load_style_prompt(generation_request.image_style)
    total_needed = generation_request.num_images
    use_group_images = generation_request.generate_mode == "group"
    generated_count = 0

    for index in range(total_needed):
        try:
            per_seed = normalize_seed(generation_request.seed, index)
            full_prompt = build_prompt(generation_request.prompt, style_prompt)

            yield {"type": "generating", "index": index + 1, "total": total_needed}

            response = request_images(
                client=client,
                prompt=full_prompt,
                width=width,
                height=height,
                generate_mode=generation_request.generate_mode,
                image_urls=image_urls,
            )

            if not response.data:
                yield {
                    "type": "error",
                    "index": index + 1,
                    "error": "API returned no image data.",
                }
                continue

            images = response.data if use_group_images else [response.data[0]]
            for group_index, image_data in enumerate(images):
                download = requests.get(image_data.url, timeout=60)
                if download.status_code != 200:
                    yield {
                        "type": "error",
                        "index": index * 4 + group_index if use_group_images else index,
                        "error": f"Image download failed: HTTP {download.status_code}",
                    }
                    continue

                saved = save_generated_image(
                    user_id=generation_request.user_id,
                    project_id=generation_request.project_id,
                    prompt=generation_request.prompt,
                    aspect_ratio=generation_request.aspect_ratio,
                    resolution=generation_request.resolution,
                    width=width,
                    height=height,
                    image_style=generation_request.image_style,
                    image_urls=image_urls,
                    seed=per_seed,
                    output_filename=generation_request.output_filename,
                    index=index,
                    group_index=group_index if use_group_images else None,
                    content=download.content,
                )
                generated_count += 1
                yield {
                    "type": "image",
                    "index": index * 4 + group_index if use_group_images else index,
                    **saved,
                }
        except Exception as exc:
            yield {"type": "error", "index": index + 1, "error": str(exc)}

    yield {"type": "complete", "total": generated_count}


def collect_non_stream_response(
    generation_request: GenerationRequest,
    image_urls: list[str],
):
    images: list[dict[str, Any]] = []
    errors: list[str] = []
    for payload in stream_generated_images(generation_request, image_urls):
        if payload.get("type") == "image":
            images.append(payload)
        elif payload.get("type") == "error":
            errors.append(payload.get("error", "Unknown error"))

    if errors and not images:
        return jsonify({"success": False, "error": errors[0]}), 500
    return jsonify({"success": True, "images": images, "errors": errors})
