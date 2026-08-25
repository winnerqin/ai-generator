import importlib
from decimal import Decimal

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


def test_build_international_payload_uses_same_upstream_model(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_MODELS", "wan3.0-video")
    monkeypatch.setattr(module.config, "WAN_VIDEO_INTL_MODEL", "wan3.0-video-intl")
    monkeypatch.setattr(module.config, "WAN_VIDEO_UPSTREAM_MODEL", "wan3.0-video")
    payload, canonical = module.build_wan_video_payload({
        "mode": "text_to_video", "model": "wan3.0-video-intl",
        "prompt": "Singapore", "resolution": "480P", "duration": 5,
    })
    assert payload["model"] == "wan3.0-video"
    assert canonical["model"] == "wan3.0-video-intl"
    assert module._region_for_model(canonical["model"]) == "intl"


def test_international_price_keeps_sub_cent_precision(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_INTL_MODEL", "wan3.0-video-intl")
    monkeypatch.setattr(module.config, "WAN_VIDEO_INTL_PRICE_480P_YUAN_PER_SECOND", "0.495838")
    assert module._price_cent_per_second("480P", "wan3.0-video-intl") == Decimal("49.583800")


@pytest.mark.parametrize(("resolution", "setting", "expected"), [
    ("480P", "WAN_VIDEO_PRICE_480P_YUAN_PER_SECOND", "0.3"),
    ("720p", "WAN_VIDEO_PRICE_720P_YUAN_PER_SECOND", "0.6"),
    ("1080P", "WAN_VIDEO_PRICE_1080P_YUAN_PER_SECOND", "1.2"),
])
def test_wan_price_is_selected_by_resolution(monkeypatch, resolution, setting, expected):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, setting, expected)
    assert module._price_cent_per_second(resolution) == Decimal(expected) * Decimal("100")


def test_wan_balance_check_uses_resolution_price(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_PRICE_1080P_YUAN_PER_SECOND", "1.2")
    monkeypatch.setattr(module.database, "get_user_by_id", lambda _user_id: {
        "role_code": module.database.ROLE_EXTERNAL_USER,
        "pricing_multiplier": 1,
        "balance_cent": 599,
    })
    monkeypatch.setattr(module.database, "get_role_pricing_multiplier", lambda _role: 1)
    with pytest.raises(ValueError, match="余额不足"):
        module.wan_video_service._ensure_balance(1, 5, "1080P")


def test_smart_duration_reserves_configured_maximum(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_PRICE_720P_YUAN_PER_SECOND", "0.6")
    monkeypatch.setattr(module.config, "WAN_VIDEO_SMART_DURATION_MAX_SECONDS", 30)
    monkeypatch.setattr(module.database, "get_user_by_id", lambda _user_id: {
        "role_code": module.database.ROLE_EXTERNAL_USER,
        "pricing_multiplier": 1,
        "balance_cent": 1799,
    })
    monkeypatch.setattr(module.database, "get_role_pricing_multiplier", lambda _role: 1)
    with pytest.raises(ValueError, match="余额不足"):
        module.wan_video_service._ensure_balance(1, -1, "720P")


def test_smart_duration_payload_and_actual_usage_billing():
    module = importlib.import_module("app.services.wan_video_service")
    payload, canonical = module.build_wan_video_payload({
        "mode": "text_to_video", "model": "wan3.0-video", "prompt": "智能时长",
        "resolution": "720P", "duration": -1,
    })
    assert payload["parameters"]["duration"] == -1
    assert canonical["duration"] == -1
    assert module._billable_seconds({
        "duration": -1,
        "usage_json": {"duration": 12, "input_video_duration": 3,
                       "output_video_duration": 9},
    }) == 12


def test_smart_duration_without_usage_is_pending(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_PRICE_480P_YUAN_PER_SECOND", "0.3")
    monkeypatch.setattr(module.database, "has_ledger_entry", lambda *args: False)
    monkeypatch.setattr(module.database, "get_user_by_id", lambda _user_id: {
        "role_code": module.database.ROLE_EXTERNAL_USER, "pricing_multiplier": 1,
    })
    monkeypatch.setattr(module.database, "get_role_pricing_multiplier", lambda _role: 1)
    monkeypatch.setattr(module.database, "create_account_ledger_entry",
                        lambda **kwargs: pytest.fail("缺少实际时长时不应扣费"))
    status = module.wan_video_service._settle({
        "status": "succeeded", "user_id": 1, "task_id": "wan-smart-pending",
        "model": "wan3.0-video", "resolution": "480P", "duration": -1,
        "usage_json": {},
    })
    assert status == "pending"


@pytest.mark.parametrize("duration", [-2, 0, 1, 31, "abc"])
def test_invalid_wan_duration_is_rejected(duration):
    module = importlib.import_module("app.services.wan_video_service")
    with pytest.raises(ValueError, match="时长"):
        module.build_wan_video_payload({
            "mode": "text_to_video", "model": "wan3.0-video", "prompt": "x",
            "duration": duration,
        })


def test_wan_settlement_records_resolution_price(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_PRICE_480P_YUAN_PER_SECOND", "0.3")
    monkeypatch.setattr(module.database, "has_ledger_entry", lambda *args: False)
    monkeypatch.setattr(module.database, "get_user_by_id", lambda _user_id: {
        "role_code": module.database.ROLE_EXTERNAL_USER, "pricing_multiplier": 1,
    })
    monkeypatch.setattr(module.database, "get_role_pricing_multiplier", lambda _role: 1)
    captured = {}
    monkeypatch.setattr(module.database, "create_account_ledger_entry",
                        lambda **kwargs: captured.update(kwargs))
    module.wan_video_service._settle({
        "status": "succeeded", "user_id": 1, "task_id": "wan-price-1",
        "model": "wan3.0-video", "resolution": "480P", "duration": 5,
    })
    assert captured["amount_cent"] == 150
    assert captured["snapshot_json"]["resolution"] == "480P"
    assert Decimal(captured["snapshot_json"]["price_cent_per_second"]) == Decimal("30")


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


def test_client_does_not_send_async_header_when_querying(monkeypatch):
    module = importlib.import_module("app.services.wan_video_client")
    monkeypatch.setattr(module.config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(module.config, "DASHSCOPE_API_KEY_POOL", "")

    class Response:
        ok = True
        def json(self): return {"output": {"task_status": "RUNNING"}}

    captured = {}
    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()
    monkeypatch.setattr(module.requests, "get", fake_get)
    module.wan_video_client.get_task("wan-task-1")
    assert "X-DashScope-Async" not in captured["headers"]
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_client_routes_international_calls_to_singapore(monkeypatch):
    module = importlib.import_module("app.services.wan_video_client")
    monkeypatch.setattr(module.config, "DASHSCOPE_INTL_API_KEY", "sk-intl")
    monkeypatch.setattr(module.config, "DASHSCOPE_INTL_API_KEY_POOL", "")
    monkeypatch.setattr(module.config, "WAN_INTL_BASE_URL", "https://dashscope-intl.aliyuncs.com/api/v1")

    class Response:
        ok = True
        def json(self): return {"output": {"task_id": "intl-task"}}

    captured = {}
    monkeypatch.setattr(module.requests, "post",
                        lambda url, **kwargs: captured.update(url=url, **kwargs) or Response())
    module.wan_video_client.create_task(
        {"model": "wan3.0-video"}, route_key="intl", region="intl"
    )
    assert captured["url"] == (
        "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
    )
    assert captured["headers"]["Authorization"] == "Bearer sk-intl"
    assert captured["headers"]["X-DashScope-Async"] == "enable"


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
    monkeypatch.setattr(module.config, "WAN_VIDEO_INTL_MODEL", "wan3.0-video-intl")
    response = auth_client.get("/api/wan-video/config")
    assert response.status_code == 200
    data = response.get_json()
    assert data["models"] == ["wan3.0-video", "wan3.0-video-fast", "wan3.0-video-intl"]
    assert data["model_aliases"]["wan3.0-video-intl"] == "WAN3.0-video国际版"


def test_get_aliyun_balance(auth_client, monkeypatch):
    module = importlib.import_module("app.api.wan_video")
    monkeypatch.setattr(module.aliyun_balance_service, "query", lambda **kwargs: {
        "available_amount": "123.45", "available_cash_amount": "120.00", "currency": "CNY",
    })
    monkeypatch.setattr(module, "log_balance_query", lambda **kwargs: None)
    response = auth_client.get("/api/wan-video/balance")
    assert response.status_code == 200
    assert response.get_json()["available_amount"] == "123.45"
    assert "access_key" not in str(response.get_json()).lower()


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
    assert "阿里云余额" in html
    assert '<option value="-1" selected>智能时长</option>' in html
    assert "-1 为智能时长；固定时长支持 2–30 秒" not in html
    assert '<option value="wan3.0-video" selected>wan3.0-video</option>' in html
    assert "draggable=\"true\"" in html
    assert "data-insert" in html
    assert "lightboxPrev" in html
    assert 'class="prompt-editor" contenteditable="true"' in html
    assert "prompt-reference" in html
    assert "contentEditable='false'" in html
    assert "lightboxDelete" not in html
    assert "lightboxClear" not in html
    assert "/api/wan-video/balance" in html
    assert "wan-video-generation-settings-v1" in html
    assert "persistGenerationSettings()" in html
    assert "restoreGenerationSettings()" in html
    assert "data-open=" not in html
    assert "/api/omni-video/tasks" in html
    assert "first_frame" in html
    assert "last_frame" in html
    assert "reference_video" in html


def test_omni_task_decorator_estimates_wan_amount_from_resolution(monkeypatch):
    module = importlib.import_module("app.services.omni_video_service")
    monkeypatch.setattr(module.config, "WAN_VIDEO_PRICE_480P_YUAN_PER_SECOND", "0.6")
    monkeypatch.setattr(module.database, "get_ledger_debit_amount_cent", lambda *args: None)
    monkeypatch.setattr(module.database, "get_user_by_id", lambda _user_id: {
        "role_code": "system_admin", "pricing_multiplier": 1,
    })
    monkeypatch.setattr(module.database, "get_role_pricing_multiplier", lambda _role: 1)
    decorated = module._decorate_task({
        "task_id": "wan-amount", "user_id": 1, "source": "wan_video",
        "model": "wan3.0-video", "status": "succeeded", "resolution": "480P",
        "duration": 5, "token_usage": 5, "usage_json": {"duration": 5},
    })
    assert decorated["amount_cent"] == 300
    assert decorated["amount_yuan"] == 3


def test_wan_library_keeps_upstream_video_when_oss_backfill_fails(monkeypatch):
    module = importlib.import_module("app.services.wan_video_service")
    monkeypatch.setattr(module.database, "is_video_task_deleted_from_library", lambda *a, **k: False)
    monkeypatch.setattr(module.database, "get_video_by_task_id", lambda *a, **k: None)
    captured = {}
    monkeypatch.setattr(module.database, "save_video_asset",
                        lambda **kwargs: captured.update(kwargs) or 9)
    monkeypatch.setattr(module.oss_service, "is_available", lambda: True)
    monkeypatch.setattr(module, "_download_and_upload_to_oss",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("oss unavailable")))
    module.wan_video_service._ensure_library({
        "status": "succeeded", "user_id": 1, "project_id": 3,
        "task_id": "wan-library", "video_url": "https://upstream/video.mp4",
        "model": "wan3.0-video", "resolution": "480P", "duration": 5,
    })
    assert captured["url"] == "https://upstream/video.mp4"
    assert captured["meta"]["library_group"] == "video"
