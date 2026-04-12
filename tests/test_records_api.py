def test_records_api_returns_paginated_payload(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_all_records",
        lambda user_id, project_id, limit=100, offset=0: [
            {
                "id": 1,
                "user_id": user_id,
                "project_id": project_id,
                "prompt": "test prompt",
                "filename": "image.jpg",
                "sample_images": [],
            }
        ],
    )
    monkeypatch.setattr(database, "get_total_count", lambda user_id, project_id=None: 1)

    response = auth_client.get("/api/records?limit=24&offset=0&search=")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["total"] == 1
    assert len(data["records"]) == 1
    assert data["data"]["total"] == 1
    assert len(data["data"]["records"]) == 1


def test_delete_record_returns_json_success(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_record_by_id",
        lambda record_id: {"id": record_id, "user_id": 1, "project_id": 1},
    )
    deleted = {}

    def fake_delete_record(record_id, user_id=None, project_id=None):
        deleted["record_id"] = record_id
        deleted["user_id"] = user_id
        deleted["project_id"] = project_id

    monkeypatch.setattr(database, "delete_record", fake_delete_record)

    response = auth_client.delete("/api/records/123")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert deleted == {"record_id": 123, "user_id": 1, "project_id": None}
