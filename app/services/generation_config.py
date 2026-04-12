"""Shared configuration and request models for image generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MODEL_NAME = "doubao-seedream-4-5-251128"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
MAX_SEED = 99999999

ASPECT_RATIOS = {
    "1:1": {"2k": (2048, 2048), "4k": (4096, 4096)},
    "4:3": {"2k": (2560, 1920), "4k": (3840, 2880)},
    "3:4": {"2k": (1920, 2560), "4k": (2880, 3840)},
    "16:9": {"2k": (2560, 1920), "4k": (3840, 2160)},
    "9:16": {"2k": (1440, 2560), "4k": (2160, 3840)},
    "3:2": {"2k": (2560, 1706), "4k": (3840, 2560)},
    "2:3": {"2k": (1706, 2560), "4k": (2560, 3840)},
}


@dataclass(frozen=True)
class GenerationRequest:
    user_id: int
    project_id: Optional[int]
    prompt: str
    aspect_ratio: str
    resolution: str
    generate_mode: str
    num_images: int
    image_style: str
    seed: int
    output_filename: str
    stream: bool


def resolve_dimensions(aspect_ratio: str, resolution: str) -> tuple[int, int]:
    return ASPECT_RATIOS.get(aspect_ratio, {}).get(resolution, (2048, 2048))


def normalize_seed(seed: int, index: int) -> int:
    if seed:
        candidate = seed + index
        if candidate > MAX_SEED:
            candidate = (candidate % MAX_SEED) + 1
        return candidate
    import random

    return random.randint(1, MAX_SEED)
