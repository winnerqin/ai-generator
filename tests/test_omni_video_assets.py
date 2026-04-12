from io import BytesIO


def test_build_omni_video_payload_restricts_model_and_resolution():
    from app.services.omni_video_service import build_omni_video_payload

    payload = build_omni_video_payload(
        {
            "prompt": "demo prompt",
            "model": "doubao-seedance-2-0-fast-260128",
            "resolution": "720p",
            "duration": 4,
            "reference_urls": ["https://example.com/a.mp4"],
        }
    )
    assert payload["model"] == "doubao-seedance-2-0-fast-260128"
    assert payload["resolution"] == "720p"
    assert payload["ratio"] == "16:9"
    assert payload["generate_audio"] is True


def test_build_omni_video_payload_rejects_1080p():
    import pytest
    from app.services.omni_video_service import build_omni_video_payload

    with pytest.raises(ValueError):
        build_omni_video_payload(
            {
                "prompt": "demo prompt",
                "model": "doubao-seedance-2-0-260128",
                "resolution": "1080p",
                "duration": 4,
            }
        )


def test_build_omni_video_payload_accepts_frame_count_and_ignores_duration():
    from app.services.omni_video_service import build_omni_video_payload

    payload = build_omni_video_payload(
        {
            "prompt": "demo prompt",
            "model": "doubao-seedance-2-0-260128",
            "resolution": "480p",
            "aspect_ratio": "3:4",
            "duration": 15,
            "frame_count": 120,
        }
    )
    assert payload["frame_count"] == 120
    assert payload["duration"] is None
    assert payload["aspect_ratio"] == "3:4"
    assert payload["ratio"] == "3:4"


def test_build_omni_video_payload_respects_generate_audio_false():
    from app.services.omni_video_service import build_omni_video_payload

    payload = build_omni_video_payload(
        {
            "prompt": "demo prompt",
            "model": "doubao-seedance-2-0-260128",
            "resolution": "480p",
            "duration": 6,
            "generate_audio": False,
        }
    )
    assert payload["generate_audio"] is False


def test_build_omni_video_payload_rejects_invalid_duration_range():
    import pytest
    from app.services.omni_video_service import build_omni_video_payload

    with pytest.raises(ValueError):
        build_omni_video_payload(
            {
                "prompt": "demo prompt",
                "model": "doubao-seedance-2-0-260128",
                "resolution": "720p",
                "duration": 3,
            }
        )


def test_content_library_media_returns_video_and_audio(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_video_assets",
        lambda user_id, project_id=None: [
            {
                "id": 1,
                "url": "https://example.com/uploads/media_video/demo.mp4",
                "filename": "demo.mp4",
                "created_at": "2026-04-11",
                "meta": {"mime_type": "video/mp4"},
            }
        ],
    )
    monkeypatch.setattr(
        database,
        "get_audio_assets",
        lambda user_id, project_id=None: [
            {"id": 2, "url": "https://example.com/music.mp3", "filename": "music.mp3", "created_at": "2026-04-11", "meta": {}}
        ],
    )

    response = auth_client.get("/api/content-library?type=media")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    kinds = {asset["type"] for asset in data["assets"]}
    assert "video" in kinds
    assert "audio" in kinds


def test_content_library_media_excludes_generated_video_assets(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_video_assets",
        lambda user_id, project_id=None: [
            {
                "id": 3,
                "url": "https://example.com/output/generated.mp4",
                "filename": "generated.mp4",
                "created_at": "2026-04-12",
                "meta": {"task_id": "task-1", "source": "omni_video"},
            }
        ],
    )
    monkeypatch.setattr(database, "get_audio_assets", lambda user_id, project_id=None: [])

    response = auth_client.get("/api/content-library?type=media")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["assets"] == []


def test_content_library_video_returns_video_assets(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_video_assets",
        lambda user_id, project_id=None: [
            {
                "id": 3,
                "url": "https://example.com/generated.mp4",
                "filename": "generated.mp4",
                "created_at": "2026-04-12",
                "meta": {"task_id": "task-1"},
            }
        ],
    )

    response = auth_client.get("/api/content-library?type=video")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["assets"][0]["type"] == "video"
    assert data["assets"][0]["meta"]["task_id"] == "task-1"


def test_content_library_image_material_merges_person_and_scene(auth_client, monkeypatch):
    import database

    monkeypatch.setattr("app.api.content.oss_service.is_available", lambda: False)
    monkeypatch.setattr(
        database,
        "get_person_assets",
        lambda user_id, project_id=None: [
            {"id": 1, "url": "https://example.com/p1.jpg", "filename": "p1.jpg", "created_at": "2026-04-12", "meta": {}}
        ],
    )
    monkeypatch.setattr(
        database,
        "get_scene_assets",
        lambda user_id, project_id=None: [
            {"id": 2, "url": "https://example.com/s1.jpg", "filename": "s1.jpg", "created_at": "2026-04-12", "meta": {}}
        ],
    )

    response = auth_client.get("/api/content-library?type=image_material")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["assets"]) == 2
    assert {asset["type"] for asset in data["assets"]} == {"image"}


def test_upload_media_asset_to_audio_library(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        "app.api.content.file_upload_service.save_uploaded_file",
        lambda **kwargs: (True, "https://oss.example.com/music.mp3", None),
    )
    monkeypatch.setattr(
        database,
        "save_audio_asset",
        lambda user_id, filename, url, meta=None, project_id=None: 12,
    )

    response = auth_client.post(
        "/api/upload-media-asset",
        data={
            "type": "media",
            "file": (BytesIO(b"fake audio bytes"), "music.mp3"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["asset"]["type"] == "audio"


def test_upload_media_asset_to_video_library(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        "app.api.content.file_upload_service.save_uploaded_file",
        lambda **kwargs: (True, "https://oss.example.com/movie.mp4", None),
    )
    monkeypatch.setattr(
        database,
        "save_video_asset",
        lambda user_id, filename, url, meta=None, project_id=None: 23,
    )

    response = auth_client.post(
        "/api/upload-media-asset",
        data={
            "type": "video",
            "file": (BytesIO(b"fake video bytes"), "movie.mp4"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["asset"]["type"] == "video"


def test_upload_media_asset_to_image_material_library(auth_client, monkeypatch):
    import database

    auth_client.application.config["UPLOAD_FOLDER"] = "C:/repo/uploads"
    monkeypatch.setattr(
        "app.api.content.file_upload_service.save_uploaded_file",
        lambda **kwargs: (True, "C:/repo/uploads/user_1/project_1/material_image/material.png", None),
    )
    monkeypatch.setattr(
        database,
        "save_person_asset",
        lambda user_id, filename, url, meta=None, project_id=None: 31,
    )

    response = auth_client.post(
        "/api/upload-media-asset",
        data={
            "type": "image_material",
            "file": (BytesIO(b"fake image bytes"), "material.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["asset"]["type"] == "image"
    assert data["asset"]["url"].startswith("/uploads/")


def test_add_image_to_image_material(auth_client, monkeypatch):
    import database

    captured = {}

    def _save_person_asset(user_id, filename, url, meta=None, project_id=None):
        captured["filename"] = filename
        captured["url"] = url
        captured["meta"] = meta
        return 41

    monkeypatch.setattr(database, "save_person_asset", _save_person_asset)

    response = auth_client.post(
        "/api/add-to-image-material",
        json={
            "filename": "generated.png",
            "url": "/uploads/user_1/project_1/material_image/generated.png",
            "meta": {"source": "generated"},
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["id"] == 41
    assert captured["filename"] == "generated.png"
    assert captured["meta"]["library_group"] == "image_material"
    assert captured["meta"]["source_library"] == "image_library"


def test_add_image_to_image_material_is_idempotent(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_person_assets",
        lambda user_id, project_id=None: [
            {
                "id": 41,
                "filename": "generated.png",
                "url": "/uploads/user_1/project_1/material_image/generated.png",
                "meta": {"library_group": "image_material"},
            }
        ],
    )
    monkeypatch.setattr(
        database,
        "save_person_asset",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not insert duplicate asset")),
    )

    response = auth_client.post(
        "/api/add-to-image-material",
        json={
            "filename": "generated.png",
            "url": "/uploads/user_1/project_1/material_image/generated.png",
            "meta": {"source": "generated"},
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["id"] == 41
    assert data["message"] == "该图片已在图片素材中"


def test_rename_video_library_asset(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(database, "rename_video_asset", lambda *args, **kwargs: 1)

    response = auth_client.post(
        "/api/rename-library-asset",
        json={"id": "db_video_9", "filename": "renamed-video.mp4"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["filename"] == "renamed-video.mp4"
