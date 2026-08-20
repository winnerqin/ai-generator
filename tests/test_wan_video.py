import importlib

import pytest


def test_build_text_to_video_payload():
    module = importlib.import_module("app.services.wan_video_service")
    payload, canonical = module.build_wan_video_payload({
        "mode": "text_to_video", "model": "wan3.0-video", "prompt": "海边日落",
        "resolution": "1080P", "ratio": "16:9", "duration": 5,
    })
    assert payload["input"] == {"prompt": "海边日落"}
    assert payload["parameters"]["resolution"] == "1080P"
    assert canonical["mode"] == "text_to_video"


def test_build_first_last_frame_payload():
    module = importlib.import_module("app.services.wan_video_service")
    payload, _ = module.build_wan_video_payload({
        "mode": "image_to_video_first_last", "model": "wan3.0-video", "prompt": "镜头推进",
        "media": [{"role": "first_frame", "url": "https://a/first.png"},
                  {"role": "last_frame", "url": "https://a/last.png"}],
    })
    assert [item["type"] for item in payload["input"]["media"]] == ["first_frame", "last_frame"]


@pytest.mark.parametrize("data", [
    {"mode": "text_to_video", "prompt": "x", "media": [{"role": "first_frame", "url": "https://a/x.png"}]},
    {"mode": "image_to_video_first", "prompt": "x", "media": []},
    {"mode": "image_to_video_first_last", "prompt": "x", "media": [{"role": "first_frame", "url": "https://a/x.png"}]},
    {"mode": "reference_to_video", "prompt": "x", "media": []},
])
def test_invalid_mode_media_combinations(data):
    module = importlib.import_module("app.services.wan_video_service")
    data["model"] = "wan3.0-video"
    with pytest.raises(ValueError):
        module.build_wan_video_payload(data)


def test_client_sends_dashscope_async_header(monkeypatch):
    module = importlib.import_module("app.services.wan_video_client")
    monkeypatch.setattr(module.config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(module.config, "DASHSCOPE_API_KEY_POOL", "")

    class Response:
        ok = True
        def json(self): return {"output": {"task_id": "wan-task-1"}}

    captured = {}
    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()
    monkeypatch.setattr(module.requests, "post", fake_post)
    result, slot = module.wan_video_client.create_task({"model": "wan3.0-video"}, route_key="abc")
    assert result["output"]["task_id"] == "wan-task-1"
    assert slot == 0
    assert captured["headers"]["X-DashScope-Async"] == "enable"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_create_wan_video_api(auth_client, monkeypatch):
    module = importlib.import_module("app.api.wan_video")
    monkeypatch.setattr(module.database, "get_omni_video_task_by_client_request_id", lambda *a, **k: None)
    monkeypatch.setattr(module.wan_video_service, "create_task", lambda data, **kwargs: {
        "task_id": "wan-task-api", "status": "queued", "source": "wan_video",
        "mode": data["mode"],
    })
    response = auth_client.post("/api/wan-video/tasks", json={
        "mode": "text_to_video", "prompt": "云海", "client_request_id": "req-wan-1",
    })
    assert response.status_code == 201
    assert response.get_json()["task"]["task_id"] == "wan-task-api"


def test_get_wan_config(auth_client, monkeypatch):
    module = importlib.import_module("app.api.wan_video")
    monkeypatch.setattr(module.config, "WAN_VIDEO_MODELS", "wan3.0-video,wan3.0-video-fast")
    response = auth_client.get("/api/wan-video/config")
    assert response.status_code == 200
    assert response.get_json()["models"] == ["wan3.0-video", "wan3.0-video-fast"]


def test_wan_page_reuses_content_library_and_oss_upload(auth_client):
    response = auth_client.get("/wan-video")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/api/content-library" in html
    assert "/api/upload-media-asset" in html
    assert "上传本地素材" in html
    assert "批量上传至 OSS" in html
    assert "assetPanel').classList.toggle('hidden'" not in html
    assert "recent_generated" in html
    assert "最近生成" in html
    assert '<option value="reference_to_video" selected>参考生视频</option>' in html
    assert "primary-row" in html
    assert "wan-library-toolbar" in html
    assert "<option>480P</option>" in html
    assert "<option selected>720P</option>" in html
    assert "data-open=" not in html
    assert "/api/omni-video/tasks" in html
    assert "first_frame" in html
    assert "last_frame" in html
    assert "reference_video" in html
