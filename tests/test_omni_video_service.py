def test_get_task_auto_saves_completed_video_to_library(monkeypatch):
    import importlib

    omni_module = importlib.import_module("app.services.omni_video_service")
    from app.services.omni_video_service import OmniVideoService

    service = OmniVideoService()
    service.client = type(
        "StubClient",
        (),
        {
            "is_configured": lambda self: True,
            "get_task": lambda self, task_id: {
                "id": task_id,
                "status": "succeeded",
                "model": "doubao-seedance-2-0-fast-260128",
                "usage": {"total_tokens": 321},
                "data": {
                    "video_url": "https://example.com/output/demo.mp4",
                    "cover_url": "https://example.com/output/demo.jpg",
                    "resolution": "720p",
                    "aspect_ratio": "16:9",
                },
            },
        },
    )()

    saved_video = {}

    task_state = {
        "task_id": "task-99",
        "user_id": 7,
        "project_id": 3,
        "status": "running",
        "prompt": "horse takes off",
        "input_payload_json": {
            "model": "doubao-seedance-2-0-fast-260128",
            "prompt": "horse takes off",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "duration": 5,
            "seed": -1,
            "reference_urls": ["https://example.com/ref-1.png"],
        },
        "raw_response_json": {},
        "result_json": {},
        "reference_urls_json": ["https://example.com/ref-1.png"],
        "duration": 5,
        "frame_count": None,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "seed": -1,
        "token_usage": None,
        "usage_json": {},
    }

    monkeypatch.setattr(
        omni_module.database,
        "get_omni_video_task",
        lambda task_id, user_id=None, project_id=None: dict(task_state),
    )

    def fake_save_task(data):
        task_state.update(data)
        return 1

    monkeypatch.setattr(omni_module.database, "save_omni_video_task", fake_save_task)
    monkeypatch.setattr(omni_module.database, "get_video_by_task_id", lambda *args, **kwargs: None)

    def fake_save_video_asset(user_id, filename, url, meta=None, project_id=None):
        saved_video.update(
            {
                "user_id": user_id,
                "filename": filename,
                "url": url,
                "meta": meta,
                "project_id": project_id,
            }
        )
        return 99

    monkeypatch.setattr(omni_module.database, "save_video_asset", fake_save_video_asset)

    task = service.get_task(7, 3, "task-99")
    assert task["status"] == "succeeded"
    assert task["token_usage"] == 321
    assert task["video_url"] == "https://example.com/output/demo.mp4"
    assert saved_video["filename"] == "task-99.mp4"
    assert saved_video["meta"]["task_id"] == "task-99"
    assert saved_video["meta"]["token_usage"] == 321


def test_list_tasks_syncs_running_task_and_auto_saves_video(monkeypatch):
    import importlib

    omni_module = importlib.import_module("app.services.omni_video_service")
    from app.services.omni_video_service import OmniVideoService

    service = OmniVideoService()
    service.client = type(
        "StubClient",
        (),
        {
            "is_configured": lambda self: True,
            "get_task": lambda self, task_id: {
                "id": task_id,
                "status": "succeeded",
                "usage": {"total_tokens": 88},
                "data": {
                    "video_url": "https://example.com/output/list-demo.mp4",
                    "resolution": "720P",
                    "ratio": "16:9",
                },
            },
        },
    )()

    task_state = {
        "task_id": "task-list-1",
        "user_id": 7,
        "project_id": 3,
        "status": "running",
        "prompt": "list sync task",
        "input_payload_json": {
            "model": "doubao-seedance-2-0-fast-260128",
            "prompt": "list sync task",
            "resolution": "720P",
            "aspect_ratio": "16:9",
            "duration": 5,
            "generate_audio": True,
        },
        "raw_response_json": {},
        "result_json": {},
        "reference_urls_json": [],
        "duration": 5,
        "frame_count": None,
        "resolution": "720P",
        "aspect_ratio": "16:9",
        "seed": -1,
        "token_usage": None,
        "usage_json": {},
    }
    saved_video = {}

    monkeypatch.setattr(
        omni_module.database,
        "get_omni_video_tasks",
        lambda *args, **kwargs: [dict(task_state)],
    )
    monkeypatch.setattr(omni_module.database, "count_omni_video_tasks", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        omni_module.database,
        "get_omni_video_task",
        lambda task_id, user_id=None, project_id=None: dict(task_state),
    )

    def fake_save_task(data):
        task_state.update(data)
        return 1

    monkeypatch.setattr(omni_module.database, "save_omni_video_task", fake_save_task)
    monkeypatch.setattr(omni_module.database, "get_video_by_task_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        omni_module.database,
        "save_video_asset",
        lambda user_id, filename, url, meta=None, project_id=None: saved_video.update(
            {"filename": filename, "url": url, "meta": meta}
        ) or 1,
    )

    items, total = service.list_tasks(7, 3, page=1, page_size=20)
    assert total == 1
    assert items[0]["status"] == "succeeded"
    assert items[0]["video_url"] == "https://example.com/output/list-demo.mp4"
    assert saved_video["filename"] == "task-list-1.mp4"
    assert saved_video["meta"]["task_id"] == "task-list-1"


def test_get_task_extracts_video_url_from_content_blob(monkeypatch):
    import importlib

    omni_module = importlib.import_module("app.services.omni_video_service")
    from app.services.omni_video_service import OmniVideoService

    service = OmniVideoService()
    service.client = type(
        "StubClient",
        (),
        {
            "is_configured": lambda self: True,
            "get_task": lambda self, task_id: {
                "id": task_id,
                "status": "succeeded",
                "content": {
                    "video_url": "https://example.com/content-result.mp4",
                },
                "resolution": "720p",
                "ratio": "9:16",
                "duration": 7,
                "seed": 4546,
                "usage": {"completion_tokens": 152100, "total_tokens": 152100},
            },
        },
    )()

    task_state = {
        "task_id": "task-content-1",
        "user_id": 5,
        "project_id": 2,
        "status": "running",
        "prompt": "content blob result",
        "input_payload_json": {
            "model": "doubao-seedance-2-0-fast-260128",
            "prompt": "content blob result",
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "duration": 7,
            "generate_audio": True,
        },
        "raw_response_json": {},
        "result_json": {},
        "reference_urls_json": [],
        "duration": 7,
        "frame_count": None,
        "resolution": "720p",
        "aspect_ratio": "9:16",
        "seed": -1,
        "token_usage": None,
        "usage_json": {},
    }
    saved_video = {}

    monkeypatch.setattr(
        omni_module.database,
        "get_omni_video_task",
        lambda task_id, user_id=None, project_id=None: dict(task_state),
    )

    def fake_save_task(data):
        task_state.update(data)
        return 1

    monkeypatch.setattr(omni_module.database, "save_omni_video_task", fake_save_task)
    monkeypatch.setattr(omni_module.database, "get_video_by_task_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        omni_module.database,
        "save_video_asset",
        lambda user_id, filename, url, meta=None, project_id=None: saved_video.update(
            {"filename": filename, "url": url, "meta": meta}
        ) or 1,
    )

    task = service.get_task(5, 2, "task-content-1")
    assert task["video_url"] == "https://example.com/content-result.mp4"
    assert task["token_usage"] == 152100
    assert saved_video["url"] == "https://example.com/content-result.mp4"
    assert saved_video["filename"] == "task-content-1.mp4"


def test_get_task_for_terminal_status_uses_local_data_only(monkeypatch):
    import importlib

    omni_module = importlib.import_module("app.services.omni_video_service")
    from app.services.omni_video_service import OmniVideoService

    service = OmniVideoService()

    class StubClient:
        def is_configured(self):
            return True

        def get_task(self, task_id):
            raise AssertionError("terminal task should not request remote detail")

    service.client = StubClient()

    local_task = {
        "task_id": "task-local-only",
        "user_id": 8,
        "project_id": 4,
        "status": "expired",
        "prompt": "expired task",
        "input_payload_json": {
            "model": "doubao-seedance-2-0-260128",
            "prompt": "expired task",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "duration": 6,
        },
        "raw_response_json": {},
        "result_json": {},
        "reference_urls_json": [],
        "duration": 6,
        "frame_count": None,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "seed": 123,
        "token_usage": 77,
        "usage_json": {"total_tokens": 77},
        "created_at": "2026-04-12 10:00:00",
        "updated_at": "2026-04-12 10:05:00",
    }

    monkeypatch.setattr(
        omni_module.database,
        "get_omni_video_task",
        lambda task_id, user_id=None, project_id=None: dict(local_task),
    )
    monkeypatch.setattr(omni_module.database, "get_video_by_task_id", lambda *args, **kwargs: None)
    saved_video = {}
    monkeypatch.setattr(
        omni_module.database,
        "save_video_asset",
        lambda user_id, filename, url, meta=None, project_id=None: saved_video.update(
            {"filename": filename, "url": url, "meta": meta}
        ) or 1,
    )

    task = service.get_task(8, 4, "task-local-only")
    assert task["status"] == "expired"
    assert task["updated_at"] == "2026-04-12 10:05:00"
    assert task["token_usage"] == 77
    assert saved_video == {}


def test_build_payload_resolves_local_upload_reference_urls(monkeypatch, tmp_path):
    import importlib
    from pathlib import Path

    omni_module = importlib.import_module("app.services.omni_video_service")

    upload_root = tmp_path / "uploads"
    image_path = upload_root / "user_1" / "material_image" / "demo.jpg"
    video_path = upload_root / "user_1" / "media_video" / "demo.mp4"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"img")
    video_path.write_bytes(b"video")

    monkeypatch.setattr(omni_module.config, "UPLOAD_FOLDER", str(upload_root))

    uploaded = []

    def fake_upload(file_path, user_id=None, project_id=None, file_type="image"):
        uploaded.append((Path(file_path).name, user_id, project_id, file_type))
        return f"https://cdn.example.com/{Path(file_path).name}"

    monkeypatch.setattr(omni_module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(omni_module.oss_service, "upload_file", fake_upload)

    payload = omni_module.build_omni_video_payload(
        {
            "_user_id": 1,
            "_project_id": 2,
            "prompt": "pet joins the battle",
            "model": "doubao-seedance-2-0-260128",
            "resolution": "480p",
            "aspect_ratio": "9:16",
            "duration": 6,
            "reference_urls": [
                "/uploads/user_1/material_image/demo.jpg",
                "/uploads/user_1/media_video/demo.mp4",
            ],
        }
    )

    assert payload["reference_urls"] == [
        "https://cdn.example.com/demo.jpg",
        "https://cdn.example.com/demo.mp4",
    ]
    assert payload["content"][1]["image_url"]["url"] == "https://cdn.example.com/demo.jpg"
    assert payload["content"][2]["video_url"]["url"] == "https://cdn.example.com/demo.mp4"
    assert uploaded == [
        ("demo.jpg", 1, 2, "image"),
        ("demo.mp4", 1, 2, "video"),
    ]


def test_build_payload_encodes_public_reference_urls():
    import importlib

    omni_module = importlib.import_module("app.services.omni_video_service")

    payload = omni_module.build_omni_video_payload(
        {
            "prompt": "pet joins the battle",
            "model": "doubao-seedance-2-0-fast-260128",
            "resolution": "480p",
            "aspect_ratio": "9:16",
            "duration": 6,
            "reference_urls": [
                "https://cdn.example.com/material/last frame (2).jpg",
                "https://cdn.example.com/media/demo.mp4",
            ],
        }
    )

    assert payload["reference_urls"][0] == "https://cdn.example.com/material/last%20frame%20(2).jpg"
    assert payload["content"][1]["image_url"]["url"] == "https://cdn.example.com/material/last%20frame%20(2).jpg"
    assert payload["content"][2]["video_url"]["url"] == "https://cdn.example.com/media/demo.mp4"


def test_build_payload_allows_site_upload_urls_without_oss(monkeypatch, tmp_path):
    import importlib

    omni_module = importlib.import_module("app.services.omni_video_service")

    upload_root = tmp_path / "uploads"
    image_path = upload_root / "user_1" / "material_image" / "demo.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"img")

    monkeypatch.setattr(omni_module.config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(omni_module.oss_service, "is_available", lambda: False)

    payload = omni_module.build_omni_video_payload(
        {
            "prompt": "pet joins the battle",
            "model": "doubao-seedance-2-0-fast-260128",
            "resolution": "480p",
            "aspect_ratio": "9:16",
            "duration": 6,
            "_public_origin": "http://short.wyydym.cc",
            "reference_urls": [
                "http://short.wyydym.cc/uploads/user_1/material_image/demo.jpg",
            ],
        }
    )

    assert payload["reference_urls"] == [
        "http://short.wyydym.cc/uploads/user_1/material_image/demo.jpg",
    ]
    assert payload["content"][1]["image_url"]["url"] == (
        "http://short.wyydym.cc/uploads/user_1/material_image/demo.jpg"
    )
