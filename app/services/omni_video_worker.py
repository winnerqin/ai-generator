from __future__ import annotations

import logging
import os
import threading
import time

from app.services.omni_video_service import omni_video_service
from app.services.video_enhance_service import video_enhance_service
from app.services.wan_video_service import wan_video_service

logger = logging.getLogger(__name__)

_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_BATCH_LIMIT = 200
DEFAULT_OSS_BACKFILL_INTERVAL_SECONDS = 300
_last_oss_backfill_at = 0.0


def _is_enabled() -> bool:
    return (os.environ.get("OMNI_VIDEO_WORKER_ENABLED", "true") or "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def refresh_pending_omni_video_tasks_once(
    batch_limit: int | None = None, *, run_oss_backfill: bool = False
) -> dict[str, int]:
    limit = batch_limit if batch_limit is not None else DEFAULT_BATCH_LIMIT
    seedance = omni_video_service.refresh_pending_tasks(limit=limit)
    wan = wan_video_service.refresh_pending_tasks(limit=limit)
    enhance = video_enhance_service.refresh_pending_tasks(limit=limit)
    result = {
        "scanned": seedance.get("scanned", 0) + wan.get("checked", 0) + enhance.get("scanned", 0),
        "refreshed": seedance.get("refreshed", 0) + wan.get("updated", 0) + enhance.get("refreshed", 0),
        "failed": seedance.get("failed", 0) + wan.get("failed", 0) + enhance.get("failed", 0),
    }
    if run_oss_backfill:
        backfill = omni_video_service.backfill_successful_tos_tasks(limit=limit)
        result.update({f"oss_{key}": value for key, value in backfill.items()})
        enhance_backfill = video_enhance_service.backfill_successful_tasks(limit=limit)
        result.update({f"enhance_oss_{key}": value for key, value in enhance_backfill.items()})
    return result


def _run_loop(interval_seconds: int, batch_limit: int) -> None:
    global _last_oss_backfill_at
    backfill_interval = max(
        interval_seconds,
        int(
            os.environ.get(
                "OMNI_VIDEO_OSS_BACKFILL_INTERVAL_SECONDS",
                str(DEFAULT_OSS_BACKFILL_INTERVAL_SECONDS),
            )
            or str(DEFAULT_OSS_BACKFILL_INTERVAL_SECONDS)
        ),
    )
    logger.info(
        "[omni-video][worker] started interval_seconds=%s batch_limit=%s",
        interval_seconds,
        batch_limit,
    )
    while True:
        started_at = time.time()
        try:
            now = time.monotonic()
            run_backfill = _last_oss_backfill_at == 0 or now - _last_oss_backfill_at >= backfill_interval
            result = refresh_pending_omni_video_tasks_once(
                batch_limit=batch_limit, run_oss_backfill=run_backfill
            )
            if run_backfill:
                _last_oss_backfill_at = now
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

    interval_seconds = int(
        os.environ.get("OMNI_VIDEO_WORKER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
        or str(DEFAULT_INTERVAL_SECONDS)
    )
    batch_limit = int(
        os.environ.get("OMNI_VIDEO_WORKER_BATCH_LIMIT", str(DEFAULT_BATCH_LIMIT))
        or str(DEFAULT_BATCH_LIMIT)
    )

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
