import importlib

import requests


def test_create_task_uses_hashed_api_key_slot(monkeypatch):
    client_module = importlib.import_module("app.services.omni_video_client")
    monkeypatch.setattr(client_module.config, "ARK_API_KEY", "key-a")
    monkeypatch.setattr(client_module.config, "ARK_API_KEY_POOL", "key-a,key-b")
    monkeypatch.setattr(client_module.config, "ARK_BASE_URL", "https://example.com")
    client = client_module.OmniVideoClient()

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "task-1"}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["authorization"] = headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr(client_module.requests, "post", fake_post)
    slot = client.select_upstream_slot(route_key="batch-001")
    client.create_task({"prompt": "demo"}, route_key="batch-001")

    assert captured["url"] == "https://example.com/contents/generations/tasks"
    assert captured["authorization"] == f"Bearer {'key-a' if slot == 0 else 'key-b'}"


def test_get_task_uses_explicit_slot(monkeypatch):
    client_module = importlib.import_module("app.services.omni_video_client")
    monkeypatch.setattr(client_module.config, "ARK_API_KEY", "key-a")
    monkeypatch.setattr(client_module.config, "ARK_API_KEY_POOL", "key-a,key-b")
    monkeypatch.setattr(client_module.config, "ARK_BASE_URL", "https://example.com")
    client = client_module.OmniVideoClient()

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "task-1", "status": "queued"}

    def fake_get(url, headers=None, timeout=None, params=None):
        captured["authorization"] = headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr(client_module.requests, "get", fake_get)
    client.get_task("task-1", slot=1)

    assert captured["authorization"] == "Bearer key-b"


def test_create_task_timeout_raises_friendly_error(monkeypatch):
    client_module = importlib.import_module("app.services.omni_video_client")
    client = client_module.OmniVideoClient()

    def fake_post(*args, **kwargs):
        raise requests.ReadTimeout("read timed out")

    monkeypatch.setattr(client_module.requests, "post", fake_post)

    try:
        client.create_task({"prompt": "demo"})
    except ValueError as exc:
        assert "请求超时" in str(exc)
        assert "create_task" in str(exc)
    else:
        raise AssertionError("timeout should be converted into a friendly ValueError")


def test_get_task_timeout_raises_friendly_error(monkeypatch):
    client_module = importlib.import_module("app.services.omni_video_client")
    client = client_module.OmniVideoClient()

    def fake_get(*args, **kwargs):
        raise requests.ReadTimeout("read timed out")

    monkeypatch.setattr(client_module.requests, "get", fake_get)

    try:
        client.get_task("task-1")
    except ValueError as exc:
        assert "请求超时" in str(exc)
        assert "get_task" in str(exc)
    else:
        raise AssertionError("timeout should be converted into a friendly ValueError")
