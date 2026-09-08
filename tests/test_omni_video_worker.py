def test_refresh_pending_omni_video_tasks_once(monkeypatch):
    from app.services import omni_video_worker

    captured = {}

    monkeypatch.setattr(
        omni_video_worker.omni_video_service,
        "refresh_pending_tasks",
        lambda limit: captured.update({"limit": limit})
        or {"scanned": 1, "refreshed": 1, "failed": 0},
    )
    monkeypatch.setattr(
        omni_video_worker.wan_video_service,
        "refresh_pending_tasks",
        lambda limit: {"checked": 0, "updated": 0, "settled": 0, "failed": 0},
    )
    monkeypatch.setattr(
        omni_video_worker.video_enhance_service,
        "refresh_pending_tasks",
        lambda limit: {"scanned": 0, "refreshed": 0, "failed": 0},
    )

    result = omni_video_worker.refresh_pending_omni_video_tasks_once(batch_limit=25)

    assert captured["limit"] == 25
    assert result == {"scanned": 1, "refreshed": 1, "failed": 0}


def test_refresh_once_can_run_oss_backfill(monkeypatch):
    from app.services import omni_video_worker

    monkeypatch.setattr(
        omni_video_worker.omni_video_service,
        "refresh_pending_tasks",
        lambda limit: {"scanned": 0, "refreshed": 0, "failed": 0},
    )
    monkeypatch.setattr(
        omni_video_worker.wan_video_service,
        "refresh_pending_tasks",
        lambda limit: {"checked": 0, "updated": 0, "failed": 0},
    )
    monkeypatch.setattr(
        omni_video_worker.video_enhance_service,
        "refresh_pending_tasks",
        lambda limit: {"scanned": 0, "refreshed": 0, "failed": 0},
    )
    monkeypatch.setattr(
        omni_video_worker.omni_video_service,
        "backfill_successful_tos_tasks",
        lambda limit: {"scanned": 2, "backfilled": 1, "expired": 1, "failed": 0},
    )
    monkeypatch.setattr(
        omni_video_worker.video_enhance_service,
        "backfill_successful_tasks",
        lambda limit: {"scanned": 1, "backfilled": 1, "expired": 0, "failed": 0},
    )

    result = omni_video_worker.refresh_pending_omni_video_tasks_once(
        batch_limit=25, run_oss_backfill=True
    )

    assert result["oss_scanned"] == 2
    assert result["oss_backfilled"] == 1
    assert result["oss_expired"] == 1
    assert result["enhance_oss_backfilled"] == 1
