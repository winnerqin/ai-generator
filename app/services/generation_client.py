"""Client and prompt helpers for the image generation flow."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from app.services.generation_config import DEFAULT_ARK_BASE_URL, MODEL_NAME


def create_generation_client() -> OpenAI:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise ValueError("ARK_API_KEY is not configured")
    base_url = os.environ.get("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def load_style_prompt(style_id: str, styles_file: str = os.path.join("static", "styles.json")) -> str:
    if not style_id or not os.path.exists(styles_file):
        return ""
    try:
        with open(styles_file, "r", encoding="utf-8") as file:
            styles_data = json.load(file)
    except Exception:
        return ""

    style_obj = next(
        (item for item in styles_data.get("styles", []) if item.get("id") == style_id),
        None,
    )
    return style_obj.get("prompt", "").strip() if style_obj else ""


def build_prompt(prompt: str, style_prompt: str) -> str:
    return f"{prompt}, {style_prompt}" if style_prompt else prompt


def build_extra_body(generate_mode: str, image_urls: list[str]) -> dict[str, Any]:
    extra_body: dict[str, Any] = {"watermark": False}
    if generate_mode == "group":
        extra_body["sequential_image_generation"] = "auto"
        extra_body["sequential_image_generation_options"] = {"max_images": 4}
    else:
        extra_body["sequential_image_generation"] = "disabled"

    if image_urls:
        extra_body["image"] = image_urls[0]
        if len(image_urls) > 1:
            extra_body["image_urls"] = image_urls
    return extra_body


def request_images(
    client: OpenAI,
    prompt: str,
    width: int,
    height: int,
    generate_mode: str,
    image_urls: list[str],
):
    return client.images.generate(
        model=MODEL_NAME,
        prompt=prompt,
        size=f"{width}x{height}",
        response_format="url",
        extra_body=build_extra_body(generate_mode, image_urls),
    )
