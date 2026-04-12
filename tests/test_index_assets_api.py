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


def test_image_styles_returns_flat_styles_payload(auth_client):
    response = auth_client.get("/api/image-styles")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert isinstance(data["styles"], list)
    assert data["data"]["styles"] == data["styles"]
