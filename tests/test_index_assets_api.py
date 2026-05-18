def test_sample_images_returns_flat_images_payload(auth_client, monkeypatch):
    import database
    from app.api import image as image_api

    monkeypatch.setattr(image_api.oss_service, "is_available", lambda: False)
    monkeypatch.setattr(
        database,
        "get_person_assets",
        lambda user_id, project_id=None: [
            {"id": 1, "url": "https://example.com/person.png", "filename": "person.png"}
        ],
    )
    monkeypatch.setattr(database, "get_scene_assets", lambda user_id, project_id=None: [])

    response = auth_client.get("/api/sample-images?category=person")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["images"]) == 1
    assert data["images"][0]["category"] == "person"
    assert data["data"]["images"][0]["filename"] == "person.png"


def test_recent_images_returns_flat_images_payload(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_image_assets",
        lambda user_id, project_id=None, limit=20: [
            {"id": 9, "url": "https://example.com/recent.png", "filename": "recent.png"}
        ],
    )

    response = auth_client.get("/api/recent-images?limit=50")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["images"]) == 1
    assert data["images"][0]["filename"] == "recent.png"
    assert data["data"]["images"][0]["url"] == "https://example.com/recent.png"


def test_recent_images_supports_page_params(auth_client, monkeypatch):
    import database

    calls = {}

    def fake_get_image_assets(user_id, project_id=None, limit=500, offset=0):
        calls["limit"] = limit
        calls["offset"] = offset
        return [
            {"id": 21, "url": "https://example.com/recent-21.png", "filename": "recent-21.png"}
        ]

    monkeypatch.setattr(database, "get_image_assets", fake_get_image_assets)
    monkeypatch.setattr(database, "count_image_assets", lambda user_id, project_id=None: 45)

    response = auth_client.get("/api/recent-images?page=2&page_size=20")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["page"] == 2
    assert data["page_size"] == 20
    assert data["total"] == 45
    assert calls == {"limit": 20, "offset": 20}
    assert data["images"][0]["filename"] == "recent-21.png"


def test_sample_images_supports_page_params(auth_client, monkeypatch):
    import database
    from app.api import image as image_api

    monkeypatch.setattr(image_api.oss_service, "is_available", lambda: False)
    monkeypatch.setattr(
        database,
        "get_person_assets",
        lambda user_id, project_id=None: [
            {"id": idx, "url": f"https://example.com/person-{idx}.png", "filename": f"person-{idx}.png"}
            for idx in range(1, 26)
        ],
    )
    monkeypatch.setattr(database, "get_scene_assets", lambda user_id, project_id=None: [])

    response = auth_client.get("/api/sample-images?category=person&page=2&page_size=20")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["page"] == 2
    assert data["page_size"] == 20
    assert data["total"] == 25
    assert len(data["images"]) == 5
    assert data["images"][0]["filename"] == "person-21.png"


def test_image_styles_returns_flat_styles_payload(auth_client):
    response = auth_client.get("/api/image-styles")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert isinstance(data["styles"], list)
    assert data["data"]["styles"] == data["styles"]
