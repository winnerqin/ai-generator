from __future__ import annotations

import logging
import os
import threading
import time

from app.services.omni_video_service import omni_video_service

logger = logging.getLogger(__name__)

_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def _is_enabled() -> bool:
    return (os.environ.get("OMNI_VIDEO_WORKER_ENABLED", "true") or "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _run_loop(interval_seconds: int, batch_limit: int) -> None:
    logger.info(
        "[omni-video][worker] started interval_seconds=%s batch_limit=%s",
        interval_seconds,
        batch_limit,
    )
    while True:
        started_at = time.time()
        try:
            result = omni_video_service.refresh_pending_tasks(limit=batch_limit)
            logger.info("[omni-video][worker] tick result=%s", result)
        except Exception:
            logger.exception("[omni-video][worker] tick failed")

        elapsed = time.time() - started_at
        sleep_seconds = max(1, interval_seconds - int(elapsed))
        time.sleep(sleep_seconds)


def start_omni_video_worker() -> bool:
    global _worker_thread
    if not _is_enabled():
        logger.info("[omni-video][worker] disabled by OMNI_VIDEO_WORKER_ENABLED")
        return False

    interval_seconds = int(os.environ.get("OMNI_VIDEO_WORKER_INTERVAL_SECONDS", "3600") or "3600")
    batch_limit = int(os.environ.get("OMNI_VIDEO_WORKER_BATCH_LIMIT", "200") or "200")

    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return False
        _worker_thread = threading.Thread(
            target=_run_loop,
            args=(interval_seconds, batch_limit),
            daemon=True,
            name="omni-video-refresh-worker",
        )
        _worker_thread.start()
        return True
