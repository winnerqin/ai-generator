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
        lambda user_id, project_id, **kwargs: captured.update(kwargs) or (
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
