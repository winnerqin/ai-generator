"""SSE channel state for the legacy image generation flow."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any, Iterable, Optional

_channels: dict[str, dict[str, Any]] = {}
_channels_lock = threading.Lock()


def format_sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def cleanup_channels(max_age_seconds: int = 3600) -> None:
    now = time.time()
    with _channels_lock:
        stale_ids = [
            generation_id
            for generation_id, channel in _channels.items()
            if channel.get("done") and now - channel.get("created_at", now) > max_age_seconds
        ]
        for generation_id in stale_ids:
            _channels.pop(generation_id, None)


def create_channel(user_id: int) -> dict[str, Any]:
    cleanup_channels()
    generation_id = uuid.uuid4().hex
    channel = {
        "id": generation_id,
        "user_id": user_id,
        "history": [],
        "subscribers": set(),
        "done": False,
        "created_at": time.time(),
    }
    with _channels_lock:
        _channels[generation_id] = channel
    return channel


def get_channel(generation_id: str) -> Optional[dict[str, Any]]:
    with _channels_lock:
        return _channels.get(generation_id)


def publish_event(channel: dict[str, Any], payload: dict[str, Any], event_index: int) -> None:
    data = dict(payload)
    data.setdefault("generation_id", channel["id"])
    data["event_index"] = event_index
    sse_data = format_sse_event(data)
    with _channels_lock:
        channel["history"].append(sse_data)
        subscribers = list(channel["subscribers"])
    for subscriber in subscribers:
        try:
            subscriber.put(sse_data, timeout=1)
        except queue.Full:
            continue


def stream_from_channel(channel: dict[str, Any], start_index: int = 0) -> Iterable[str]:
    local_queue: queue.Queue[str | None] = queue.Queue(maxsize=200)
    with _channels_lock:
        history = list(channel["history"])
        done = channel["done"]
        if not done:
            channel["subscribers"].add(local_queue)

    for item in history[start_index:]:
        yield item

    if done:
        return

    try:
        while True:
            item = local_queue.get()
            if item is None:
                break
            yield item
    finally:
        with _channels_lock:
            channel["subscribers"].discard(local_queue)


def finalize_channel(channel: dict[str, Any]) -> None:
    with _channels_lock:
        channel["done"] = True
        subscribers = list(channel["subscribers"])
    for subscriber in subscribers:
        try:
            subscriber.put(None, timeout=1)
        except queue.Full:
            continue
