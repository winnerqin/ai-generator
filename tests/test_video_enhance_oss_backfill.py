import importlib


module = importlib.import_module("app.services.video_enhance_service")


def test_existing_enhanced_https_video_is_migrated_to_oss(monkeypatch):
    task = {
        "task_id": "enhance-1",
        "user_id": 6,
        "project_id": 1,
        "status": "succeeded",
        "video_url": "https://upstream.example.com/result.mp4?expires=123",
        "output_filename": "result-enhanced-1080p.mp4",
    }
    updated_assets = []
    saved_tasks = []
    monkeypatch.setattr(module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(
        module.database,
        "get_video_by_task_id",
        lambda *args, **kwargs: {"id": 88, "url": task["video_url"], "meta": {}},
    )
    monkeypatch.setattr(
        module.database,
        "update_video_asset_url",
        lambda asset_id, url: updated_assets.append((asset_id, url)),
    )
    monkeypatch.setattr(
        module.database, "save_video_enhance_task", lambda item: saved_tasks.append(item.copy())
    )
    monkeypatch.setattr(
        module.video_enhance_service,
        "_download_and_upload_to_oss",
        lambda *args: ("https://short-oss.aidcstore.net/ai-videos/result.mp4", False),
    )

    module.video_enhance_service._save_to_video_library(task)

    assert updated_assets == [(88, "https://short-oss.aidcstore.net/ai-videos/result.mp4")]
    assert saved_tasks[0]["video_url"].startswith("https://short-oss.aidcstore.net/")


def test_enhance_backfill_scans_successful_remote_urls(monkeypatch):
    captured = {}
    monkeypatch.setattr(module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(
        module.database,
        "get_successful_video_enhance_tasks_with_remote_urls",
        lambda limit, excluded_hosts: captured.update(
            {"limit": limit, "excluded_hosts": excluded_hosts}
        )
        or [],
    )

    result = module.video_enhance_service.backfill_successful_tasks(limit=25)

    assert result == {"scanned": 0, "backfilled": 0, "expired": 0, "failed": 0}
    assert captured["limit"] == 25
    assert "short-oss.aidcstore.net" in captured["excluded_hosts"]
