import importlib

import requests


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
