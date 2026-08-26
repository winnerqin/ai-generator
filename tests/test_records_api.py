def test_records_api_returns_paginated_payload(auth_client, monkeypatch):
    import database

    monkeypatch.setattr(
        database,
        "get_all_records",
        lambda user_id, project_id, limit=100, offset=0, search=None: [
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
    monkeypatch.setattr(database, "get_total_count",
                        lambda user_id, project_id=None, search=None: 1)

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

    with auth_client.session_transaction() as sess:
        sess["current_project_id"] = 1

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
    assert deleted == {"record_id": 123, "user_id": 1, "project_id": 1}


def test_system_admin_can_query_all_or_selected_user_records(auth_client, monkeypatch):
    import database

    with auth_client.session_transaction() as sess:
        sess["username"] = "system_admin"
        sess["role_code"] = "system_admin"
    captured = []
    monkeypatch.setattr(
        database, "get_all_records",
        lambda user_id, project_id, limit=100, offset=0, search=None:
            captured.append((user_id, project_id, search)) or [],
    )
    monkeypatch.setattr(database, "get_total_count",
                        lambda user_id, project_id=None, search=None: 0)

    assert auth_client.get("/api/records?search=x").status_code == 200
    assert auth_client.get("/api/records?user_id=13&search=y").status_code == 200
    assert captured == [(None, None, "x"), (13, None, "y")]


def test_regular_user_cannot_query_another_users_records(auth_client, monkeypatch):
    import database

    captured = {}
    monkeypatch.setattr(database, "get_user_by_id",
                        lambda user_id: {"id": user_id, "role_code": "external_user"})
    monkeypatch.setattr(
        database, "get_all_records",
        lambda user_id, project_id, limit=100, offset=0, search=None:
            captured.update(user_id=user_id) or [],
    )
    monkeypatch.setattr(database, "get_total_count",
                        lambda user_id, project_id=None, search=None: 0)
    response = auth_client.get("/api/records?user_id=999")
    assert response.status_code == 200
    assert captured["user_id"] == 1


def test_records_export_reads_all_filtered_pages(auth_client, monkeypatch):
    import database

    calls = []
    monkeypatch.setattr(database, "get_total_count",
                        lambda user_id, project_id=None, search=None: 1001)
    monkeypatch.setattr(
        database, "get_all_records",
        lambda user_id, project_id, limit=100, offset=0, search=None:
            calls.append((limit, offset, search)) or ([{"id": offset + 1}] if offset else []),
    )
    response = auth_client.get("/api/records/export?search=cat")
    assert response.status_code == 200
    assert calls == [(1000, 0, "cat"), (1000, 1000, "cat")]
