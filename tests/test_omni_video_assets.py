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


def test_build_omni_video_payload_accepts_mini_model_720p():
    from app.services.omni_video_service import build_omni_video_payload

    payload = build_omni_video_payload(
        {
            "prompt": "demo prompt",
            "model": "doubao-seedance-2-0-mini-260615",
            "resolution": "720p",
            "duration": 4,
        }
    )

    assert payload["model"] == "doubao-seedance-2-0-mini-260615"
    assert payload["resolution"] == "720p"


def test_build_omni_video_payload_rejects_mini_1080p():
    import pytest
    from app.services.omni_video_service import build_omni_video_payload

    with pytest.raises(ValueError, match="480P.*720P|720P.*480P"):
        build_omni_video_payload(
            {
                "prompt": "demo prompt",
                "model": "doubao-seedance-2-0-mini-260615",
                "resolution": "1080p",
                "duration": 4,
            }
        )


def test_build_omni_video_payload_rejects_fast_1080p():
    import pytest
    from app.services.omni_video_service import build_omni_video_payload

    with pytest.raises(ValueError):
        build_omni_video_payload(
            {
                "prompt": "demo prompt",
                "model": "doubao-seedance-2-0-fast-260128",
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


def test_build_omni_video_payload_maps_virtual_assets_by_type():
    from app.services.omni_video_service import build_omni_video_payload

    references = [
        {"url": "asset://asset-image", "type": "image"},
        {"url": "asset://asset-video", "type": "video"},
        {"url": "asset://asset-audio", "type": "audio"},
    ]
    payload = build_omni_video_payload(
        {
            "prompt": "use virtual assets",
            "model": "doubao-seedance-2-0-260128",
            "resolution": "480p",
            "duration": 6,
            "reference_urls": [item["url"] for item in references],
            "reference_assets": references,
        }
    )

    assert payload["content"][1] == {
        "type": "image_url", "role": "reference_image", "image_url": {"url": "asset://asset-image"}
    }
    assert payload["content"][2] == {
        "type": "video_url", "role": "reference_video", "video_url": {"url": "asset://asset-video"}
    }
    assert payload["content"][3] == {
        "type": "audio_url", "role": "reference_audio", "audio_url": {"url": "asset://asset-audio"}
    }


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
        "query_video_assets",
        lambda user_id, project_id=None, limit=50, offset=0, search=None, library_kind="all": (
            [
                {
                    "id": 1,
                    "url": "https://example.com/uploads/media_video/demo.mp4",
                    "filename": "demo.mp4",
                    "created_at": "2026-04-11",
                    "meta": {"mime_type": "video/mp4"},
                }
            ],
            1,
        ),
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
        "query_video_assets",
        lambda user_id, project_id=None, limit=50, offset=0, search=None, library_kind="all": ([], 0),
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
        "query_video_assets",
        lambda user_id, project_id=None, limit=50, offset=0, search=None, library_kind="all": (
            [
                {
                    "id": 3,
                    "url": "https://example.com/generated.mp4",
                    "filename": "generated.mp4",
                    "created_at": "2026-04-12",
                    "meta": {"task_id": "task-1"},
                }
            ],
            1,
        ),
    )

    response = auth_client.get("/api/content-library?type=video")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["assets"][0]["type"] == "video"
    assert data["assets"][0]["meta"]["task_id"] == "task-1"


def test_content_library_media_returns_server_paged_mixed_assets(auth_client, monkeypatch):
    import database

    videos = [
        {"id": 1, "url": "https://example.com/v1.mp4", "filename": "v1.mp4", "created_at": "2026-05-18", "meta": {"mime_type": "video/mp4"}},
        {"id": 2, "url": "https://example.com/v2.mp4", "filename": "v2.mp4", "created_at": "2026-05-18", "meta": {"mime_type": "video/mp4"}},
        {"id": 3, "url": "https://example.com/v3.mp4", "filename": "v3.mp4", "created_at": "2026-05-18", "meta": {"mime_type": "video/mp4"}},
    ]
    audios = [
        {"id": 4, "url": "https://example.com/a1.mp3", "filename": "a1.mp3", "created_at": "2026-05-18", "meta": {}},
        {"id": 5, "url": "https://example.com/a2.mp3", "filename": "a2.mp3", "created_at": "2026-05-18", "meta": {}},
    ]

    monkeypatch.setattr(
        database,
        "query_video_assets",
        lambda user_id, project_id=None, limit=50, offset=0, search=None, library_kind="all": (
            videos[offset : offset + limit],
            len(videos),
        ),
    )
    monkeypatch.setattr(database, "count_audio_assets", lambda user_id, project_id=None, search=None: len(audios))
    monkeypatch.setattr(
        database,
        "query_audio_assets",
        lambda user_id, project_id=None, limit=500, offset=0, search=None: (
            audios[offset : offset + limit],
            len(audios),
        ),
    )

    response = auth_client.get("/api/content-library?type=media&page=2&page_size=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["total"] == 5
    assert [asset["filename"] for asset in data["assets"]] == ["v3.mp4", "a1.mp3"]
    assert [asset["type"] for asset in data["assets"]] == ["video", "audio"]


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


def test_content_library_image_returns_server_paged_payload(auth_client, monkeypatch):
    import database

    calls = {}

    def fake_query_image_assets(user_id, project_id=None, limit=500, offset=0, search=None):
        calls.update({"limit": limit, "offset": offset, "search": search})
        return (
            [
                {
                    "id": 21,
                    "url": "https://example.com/image-21.jpg",
                    "filename": "image-21.jpg",
                    "created_at": "2026-05-18",
                    "meta": {},
                }
            ],
            45,
        )

    monkeypatch.setattr(database, "query_image_assets", fake_query_image_assets)

    response = auth_client.get("/api/content-library?type=image&page=2&page_size=20&search=image")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["page"] == 2
    assert data["page_size"] == 20
    assert data["total"] == 45
    assert data["assets"][0]["id"] == "db_image_21"
    assert calls == {"limit": 20, "offset": 20, "search": "image"}


def test_content_library_image_material_returns_server_paged_payload(auth_client, monkeypatch):
    import database

    monkeypatch.setattr("app.api.content.oss_service.is_available", lambda: False)
    monkeypatch.setattr(database, "count_person_assets", lambda user_id, project_id=None, search=None: 3)
    monkeypatch.setattr(database, "count_scene_assets", lambda user_id, project_id=None, search=None: 2)

    def fake_query_person_assets(user_id, project_id=None, limit=500, offset=0, search=None):
        people = [
            {"id": 1, "url": "https://example.com/p1.jpg", "filename": "p1.jpg", "created_at": "2026-05-18", "meta": {}},
            {"id": 2, "url": "https://example.com/p2.jpg", "filename": "p2.jpg", "created_at": "2026-05-18", "meta": {}},
            {"id": 3, "url": "https://example.com/p3.jpg", "filename": "p3.jpg", "created_at": "2026-05-18", "meta": {}},
        ]
        return people[offset : offset + limit], 3

    def fake_query_scene_assets(user_id, project_id=None, limit=500, offset=0, search=None):
        scenes = [
            {"id": 4, "url": "https://example.com/s1.jpg", "filename": "s1.jpg", "created_at": "2026-05-18", "meta": {}},
            {"id": 5, "url": "https://example.com/s2.jpg", "filename": "s2.jpg", "created_at": "2026-05-18", "meta": {}},
        ]
        return scenes[offset : offset + limit], 2

    monkeypatch.setattr(database, "query_person_assets", fake_query_person_assets)
    monkeypatch.setattr(database, "query_scene_assets", fake_query_scene_assets)

    response = auth_client.get("/api/content-library?type=image_material&page=2&page_size=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["total"] == 5
    assert [asset["filename"] for asset in data["assets"]] == ["p3.jpg", "s1.jpg"]
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


def test_delete_video_library_asset_marks_omni_task_deleted(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_video_assets",
        lambda user_id, project_id=None: [
            {
                "id": 9,
                "filename": "demo.mp4",
                "url": "https://example.com/output/demo.mp4",
                "meta": {"task_id": "task-omni-9", "source": "omni_video"},
            }
        ],
    )

    marked = {}
    monkeypatch.setattr(
        database,
        "mark_video_task_deleted_from_library",
        lambda user_id, task_id, project_id=None: marked.update(
            {"user_id": user_id, "task_id": task_id, "project_id": project_id}
        ),
    )
    monkeypatch.setattr(database, "delete_video_asset", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        "app.api.content.file_upload_service.delete_file",
        lambda *args, **kwargs: True,
    )

    response = auth_client.post("/api/delete-library-asset", json={"id": "db_video_9"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert marked["task_id"] == "task-omni-9"
