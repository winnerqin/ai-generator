def test_refresh_pending_omni_video_tasks_once(monkeypatch):
    from app.services import omni_video_worker

    captured = {}

    monkeypatch.setattr(
        omni_video_worker.omni_video_service,
        "refresh_pending_tasks",
        lambda limit: captured.update({"limit": limit})
        or {"scanned": 1, "refreshed": 1, "failed": 0},
    )

    result = omni_video_worker.refresh_pending_omni_video_tasks_once(batch_limit=25)

    assert captured["limit"] == 25
    assert result == {"scanned": 1, "refreshed": 1, "failed": 0}
