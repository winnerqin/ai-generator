import importlib


module = importlib.import_module("app.services.omni_video_service")


def test_is_tos_temp_url_accepts_china_and_international_regions():
    assert module.is_tos_temp_url("https://bucket.tos-cn-beijing.volces.com/video.mp4")
    assert module.is_tos_temp_url(
        "https://ark-acg-ap-southeast-1.tos-ap-southeast-1.volces.com/video.mp4"
        "?X-Tos-Expires=86400&X-Tos-Signature=abc"
    )


def test_is_tos_temp_url_accepts_signed_custom_domain_but_not_ordinary_url():
    assert module.is_tos_temp_url(
        "https://download.example.com/video.mp4?X-Tos-Date=20260902T055743Z"
        "&X-Tos-Signature=abc"
    )
    assert not module.is_tos_temp_url("https://cdn.example.com/video.mp4")
    assert not module.is_tos_temp_url(
        "https://example.volces.com/video.mp4?X-Tos-Signature=abc"
    )


def test_is_oss_url_accepts_configured_custom_domain(monkeypatch):
    monkeypatch.setattr(module.config, "OSS_EXTERNAL_ENDPOINT", "short-oss.aidcstore.net")
    assert module.is_oss_url("https://short-oss.aidcstore.net/ai-videos/video.mp4")
    assert not module.is_oss_url("https://cdn.example.com/video.mp4")


def test_backfill_successful_tos_task_updates_oss_url(monkeypatch):
    task = {
        "task_id": "task-intl",
        "user_id": 6,
        "project_id": 1,
        "status": "succeeded",
        "video_url": "https://bucket.tos-ap-southeast-1.volces.com/video.mp4",
    }
    monkeypatch.setattr(
        module.database, "get_successful_omni_video_tasks_with_temp_urls", lambda limit: [task]
    )
    monkeypatch.setattr(module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(
        module.omni_video_service, "_ensure_video_library_entry", lambda item: None
    )
    monkeypatch.setattr(
        module.database,
        "get_omni_video_task",
        lambda *args, **kwargs: {
            **task,
            "video_url": "https://short-oss.aidcstore.net/ai-videos/video.mp4",
        },
    )

    result = module.omni_video_service.backfill_successful_tos_tasks(limit=20)

    assert result == {"scanned": 1, "backfilled": 1, "expired": 0, "failed": 0}


def test_backfill_marks_expired_task_in_result_and_logs_alert(monkeypatch, caplog):
    task = {
        "task_id": "task-expired",
        "user_id": 6,
        "project_id": 1,
        "status": "succeeded",
        "video_url": "https://bucket.tos-ap-southeast-1.volces.com/video.mp4",
    }
    monkeypatch.setattr(
        module.database, "get_successful_omni_video_tasks_with_temp_urls", lambda limit: [task]
    )
    monkeypatch.setattr(module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(
        module.omni_video_service, "_ensure_video_library_entry", lambda item: None
    )
    monkeypatch.setattr(module.database, "get_omni_video_task", lambda *args, **kwargs: task)
    monkeypatch.setattr(
        module.database,
        "get_video_by_task_id",
        lambda *args, **kwargs: {"meta": {"url_expired": True}},
    )

    result = module.omni_video_service.backfill_successful_tos_tasks(limit=20)

    assert result == {"scanned": 1, "backfilled": 0, "expired": 1, "failed": 0}
    assert "[oss-backfill][alert]" in caplog.text


def test_backfill_rotates_transient_failure_to_end_of_backlog(monkeypatch):
    task = {
        "task_id": "task-retry",
        "user_id": 6,
        "project_id": 1,
        "status": "succeeded",
        "video_url": "https://bucket.tos-ap-southeast-1.volces.com/video.mp4",
    }
    saved = []
    monkeypatch.setattr(
        module.database, "get_successful_omni_video_tasks_with_temp_urls", lambda limit: [task]
    )
    monkeypatch.setattr(module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(
        module.omni_video_service, "_ensure_video_library_entry", lambda item: None
    )
    monkeypatch.setattr(module.database, "get_omni_video_task", lambda *args, **kwargs: task)
    monkeypatch.setattr(
        module.database, "get_video_by_task_id", lambda *args, **kwargs: {"meta": {}}
    )
    monkeypatch.setattr(module.database, "save_omni_video_task", lambda item: saved.append(item.copy()))

    result = module.omni_video_service.backfill_successful_tos_tasks(limit=20)

    assert result["failed"] == 1
    assert saved[0]["external_meta_json"]["oss_backfill_status"] == "failed"
