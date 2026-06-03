def test_create_omni_video_task(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    captured = {}

    def fake_create_task(user_id, project_id, data):
        captured["data"] = data
        return {
            "task_id": "task-123",
            "status": "queued",
            "prompt": data["prompt"],
            "model": data["model"],
        }

    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "create_task",
        fake_create_task,
    )

    response = auth_client.post(
        "/api/omni-video/tasks",
        json={
            "prompt": "a cat walking in the rain",
            "model": "doubao-seedance-2-0-fast-260128",
            "resolution": "480p",
            "aspect_ratio": "3:4",
            "duration": 5,
            "generate_audio": True,
            "reference_urls": ["https://example.com/a.png"],
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["task_id"] == "task-123"
    assert data["task"]["prompt"] == "a cat walking in the rain"
    assert captured["data"]["model"] == "doubao-seedance-2-0-fast-260128"
    assert captured["data"]["resolution"] == "480p"
    assert captured["data"]["aspect_ratio"] == "3:4"
    assert captured["data"]["duration"] == 5
    assert captured["data"]["generate_audio"] is True


def test_list_omni_video_tasks(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    captured = {}

    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "list_tasks",
        lambda user_id, project_id, **kwargs: captured.update(kwargs)
        or (
            [{"task_id": "task-1", "status": "queued", "prompt": "demo"}],
            1,
        ),
    )

    response = auth_client.get(
        "/api/omni-video/tasks?page=2&page_size=10&start_date=2026-04-01&end_date=2026-04-12"
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["items"][0]["task_id"] == "task-1"
    assert captured["page"] == 2
    assert captured["page_size"] == 10
    assert captured["start_date"] == "2026-04-01"
    assert captured["end_date"] == "2026-04-12"


def test_list_omni_video_tasks_supports_batch_id(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    captured = {}

    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "list_tasks",
        lambda user_id, project_id, **kwargs: captured.update(kwargs) or ([], 0),
    )

    response = auth_client.get("/api/omni-video/tasks?batch_id=batch-001")
    assert response.status_code == 200
    assert captured["batch_id"] == "batch-001"


def test_external_batch_create_with_api_key(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    captured = {}

    monkeypatch.setattr(
        omni_video_api.database,
        "get_external_api_key",
        lambda api_key: (
            {
                "user_id": 7,
                "username": "partner",
                "project_id": 9,
            }
            if api_key == "secret-key"
            else None
        ),
    )
    monkeypatch.setattr(omni_video_api.database, "has_project_access", lambda user_id, pid: True)
    monkeypatch.setattr(
        omni_video_api.database,
        "get_omni_video_task_by_client_request_id",
        lambda *args, **kwargs: None,
    )

    def fake_create_task(user_id, project_id, data):
        captured["user_id"] = user_id
        captured["project_id"] = project_id
        captured["data"] = data
        return {"task_id": "task-001", "status": "queued"}

    monkeypatch.setattr(omni_video_api.omni_video_service, "create_task", fake_create_task)

    response = auth_client.post(
        "/api/external/omni-video/tasks/batch",
        headers={"X-API-Key": "secret-key"},
        json={
            "batch_id": "batch-001",
            "tasks": [
                {
                    "client_request_id": "client-001",
                    "prompt": "demo",
                    "model": "doubao-seedance-2-0-fast-260128",
                }
            ],
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["created"] == 1
    assert data["items"][0]["status_code"] == 201
    assert captured["user_id"] == 7
    assert captured["project_id"] == 9
    assert captured["data"]["batch_id"] == "batch-001"
    assert captured["data"]["client_request_id"] == "client-001"
    assert captured["data"]["source"] == "external_api"


def test_external_batch_create_is_idempotent(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    monkeypatch.setattr(
        omni_video_api.database,
        "get_external_api_key",
        lambda api_key: {"user_id": 7, "username": "partner", "project_id": 9},
    )
    monkeypatch.setattr(omni_video_api.database, "has_project_access", lambda user_id, pid: True)
    monkeypatch.setattr(
        omni_video_api.database,
        "get_omni_video_task_by_client_request_id",
        lambda *args, **kwargs: {"task_id": "task-existing", "status": "queued"},
    )

    def fail_create_task(*args, **kwargs):
        raise AssertionError("create_task should not be called for idempotent requests")

    monkeypatch.setattr(omni_video_api.omni_video_service, "create_task", fail_create_task)

    response = auth_client.post(
        "/api/external/omni-video/tasks/batch",
        headers={"X-API-Key": "secret-key"},
        json={
            "tasks": [
                {
                    "client_request_id": "client-001",
                    "prompt": "demo",
                }
            ]
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["created"] == 0
    assert data["reused"] == 1
    assert data["items"][0]["task_id"] == "task-existing"
    assert data["items"][0]["idempotent"] is True


def test_external_batch_create_with_jwt(client, app, monkeypatch):
    from app.api import omni_video as omni_video_api
    from app.utils.jwt_auth import JWTAuth

    monkeypatch.setattr(
        omni_video_api.database,
        "get_user_by_id",
        lambda user_id: {"id": user_id, "username": "jwt_user", "role_code": "external_user"},
    )
    monkeypatch.setattr(omni_video_api.database, "has_project_access", lambda user_id, pid: True)
    monkeypatch.setattr(
        omni_video_api.database,
        "get_omni_video_task_by_client_request_id",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "create_task",
        lambda user_id, project_id, data: {"task_id": "task-jwt", "status": "queued"},
    )

    with app.app_context():
        token = JWTAuth.generate_tokens(user_id=3, username="jwt_user")["access_token"]

    response = client.post(
        "/api/external/omni-video/tasks/batch",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": 1, "tasks": [{"prompt": "demo"}]},
    )

    assert response.status_code == 201
    assert response.get_json()["items"][0]["task_id"] == "task-jwt"


def test_external_get_task_with_api_key(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    monkeypatch.setattr(
        omni_video_api.database,
        "get_external_api_key",
        lambda api_key: {"user_id": 7, "username": "partner", "project_id": 9},
    )
    monkeypatch.setattr(omni_video_api.database, "has_project_access", lambda user_id, pid: True)
    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "get_task",
        lambda user_id, project_id, task_id: {
            "task_id": task_id,
            "status": "succeeded",
            "batch_id": "batch-001",
            "client_request_id": "client-001",
            "video_url": "https://example.com/video.mp4",
        },
    )

    response = auth_client.get(
        "/api/external/omni-video/tasks/task-001",
        headers={"X-API-Key": "secret-key"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["task"]["task_id"] == "task-001"
    assert data["task"]["batch_id"] == "batch-001"
    assert data["task"]["video_url"] == "https://example.com/video.mp4"


def test_external_list_batch_tasks_with_api_key(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    captured = {}

    monkeypatch.setattr(
        omni_video_api.database,
        "get_external_api_key",
        lambda api_key: {"user_id": 7, "username": "partner", "project_id": 9},
    )
    monkeypatch.setattr(omni_video_api.database, "has_project_access", lambda user_id, pid: True)
    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "list_tasks",
        lambda user_id, project_id, **kwargs: captured.update(
            {"user_id": user_id, "project_id": project_id, **kwargs}
        )
        or (
            [
                {
                    "task_id": "task-001",
                    "status": "queued",
                    "batch_id": "batch-001",
                }
            ],
            1,
        ),
    )

    response = auth_client.get(
        "/api/external/omni-video/batches/batch-001?page=2&page_size=20&sync_running=false",
        headers={"X-API-Key": "secret-key"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["items"][0]["task_id"] == "task-001"
    assert captured["user_id"] == 7
    assert captured["project_id"] == 9
    assert captured["batch_id"] == "batch-001"
    assert captured["page"] == 2
    assert captured["page_size"] == 20
    assert captured["sync_running"] is False


def test_get_omni_video_task(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "get_task",
        lambda user_id, project_id, task_id: {"task_id": task_id, "status": "succeeded"},
    )

    response = auth_client.get("/api/omni-video/tasks/task-2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["task"]["task_id"] == "task-2"


def test_refresh_cancel_and_delete_omni_video_task(auth_client, monkeypatch):
    from app.api import omni_video as omni_video_api

    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "refresh_task",
        lambda user_id, project_id, task_id: {"task_id": task_id, "status": "running"},
    )
    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "cancel_task",
        lambda user_id, project_id, task_id: {"task_id": task_id, "status": "cancelled"},
    )
    monkeypatch.setattr(
        omni_video_api.omni_video_service,
        "delete_task",
        lambda user_id, project_id, task_id: 1,
    )

    refresh = auth_client.post("/api/omni-video/tasks/task-3/refresh")
    assert refresh.status_code == 200
    assert refresh.get_json()["task"]["status"] == "running"

    cancel = auth_client.post("/api/omni-video/tasks/task-3/cancel")
    assert cancel.status_code == 200
    assert cancel.get_json()["task"]["status"] == "cancelled"

    delete = auth_client.delete("/api/omni-video/tasks/task-3")
    assert delete.status_code == 200
    assert delete.get_json()["success"] is True
