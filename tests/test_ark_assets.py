import json
from io import BytesIO

import pytest

from app.services.ark_asset_service import ArkAssetError, ArkAssetService


def test_service_maps_action_and_result(monkeypatch):
    service = ArkAssetService()
    calls = []
    monkeypatch.setattr(
        service,
        "_send",
        lambda action, body: calls.append((action, json.loads(body)))
        or {"Result": {"AssetGroups": [{"GroupId": "group-1"}]}},
    )

    result = service.list_asset_groups({"PageNumber": 1, "PageSize": 20})

    assert result["AssetGroups"][0]["GroupId"] == "group-1"
    assert calls == [("ListAssetGroups", {"PageNumber": 1, "PageSize": 20})]


def test_service_rejects_unknown_action():
    with pytest.raises(ArkAssetError) as caught:
        ArkAssetService()._validate_action("Anything")
    assert caught.value.code == "INVALID_ACTION"


def test_service_calls_installed_volcengine_sdk(monkeypatch):
    from app.services.ark_asset_service import config
    from volcengine.base.Service import Service

    captured = {}

    monkeypatch.setattr(config, "VOLCENGINE_AK", "ak")
    monkeypatch.setattr(config, "VOLCENGINE_SK", "sk")
    monkeypatch.setattr(
        Service,
        "json",
        lambda self, action, params, body: captured.setdefault(
            "call", (action, params, json.loads(body))
        )
        and json.dumps({"Result": {"ok": True}}),
    )

    result = ArkAssetService().call("ListAssets", {"PageNumber": 1})

    assert result["Result"]["ok"] is True
    assert captured["call"] == ("ListAssets", {}, {"PageNumber": 1})


def test_service_redacts_credentials(monkeypatch):
    from app.services import ark_asset_service as module_service
    from app.services.ark_asset_service import config

    service = ArkAssetService()
    monkeypatch.setattr(config, "VOLCENGINE_AK", "secret-ak")
    monkeypatch.setattr(config, "VOLCENGINE_SK", "secret-sk")
    monkeypatch.setattr(service, "_send", lambda action, body: (_ for _ in ()).throw(RuntimeError("secret-ak secret-sk")))
    with pytest.raises(ArkAssetError) as caught:
        service.call("ListAssets", {})
    assert "secret-ak" not in str(caught.value)
    assert "secret-sk" not in str(caught.value)
    assert module_service is not None


def test_group_list_api(auth_client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.list_asset_groups",
        lambda payload: captured.setdefault("payload", payload)
        and {"AssetGroups": [{"GroupId": "group-1"}], "TotalCount": 1},
    )
    response = auth_client.get("/api/virtual-asset-groups?page=1&page_size=20")
    assert response.status_code == 200
    assert response.get_json()["items"][0]["GroupId"] == "group-1"
    assert captured["payload"]["Filter"] == {"GroupType": "AIGC"}


def test_group_crud_api(auth_client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.create_asset_group",
        lambda payload: captured.setdefault("create", payload),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.update_asset_group",
        lambda payload: captured.setdefault("update", payload),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.delete_asset_group",
        lambda payload: captured.setdefault("delete", payload),
    )
    assert auth_client.post("/api/virtual-asset-groups", json={"name": "角色", "description": "主角"}).status_code == 200
    assert auth_client.put("/api/virtual-asset-groups/group-1", json={"name": "角色2"}).status_code == 200
    assert auth_client.delete("/api/virtual-asset-groups/group-1").status_code == 200
    assert captured["create"]["Name"] == "角色"
    assert captured["update"]["Id"] == "group-1"
    assert captured["delete"] == {"Id": "group-1"}


def test_create_asset_by_file(auth_client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.api.content.file_upload_service.save_uploaded_file",
        lambda *args, **kwargs: (True, "https://cdn.example.com/hero.png", None),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.create_asset",
        lambda payload: captured.setdefault("payload", payload),
    )
    response = auth_client.post(
        "/api/virtual-assets",
        data={
            "group_id": "group-1",
            "name": "主角正面",
            "asset_type": "image",
            "file": (BytesIO(b"image"), "hero.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert captured["payload"]["AssetType"] == "Image"
    assert captured["payload"]["URL"] == "https://cdn.example.com/hero.png"
    assert captured["payload"]["ProjectName"] == "default"


def test_create_asset_rejects_url_only(auth_client):
    response = auth_client.post(
        "/api/virtual-assets",
        json={
            "group_id": "group-1",
            "name": "主角正面",
            "asset_type": "image",
            "url": "https://cdn.example.com/hero.png",
        },
    )
    assert response.status_code == 400


def test_asset_list_wraps_group_in_required_filter(auth_client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.list_assets",
        lambda payload: captured.setdefault("payload", payload) and {"Items": []},
    )
    response = auth_client.get("/api/virtual-assets?group_id=group-1&search=hero")
    assert response.status_code == 200
    assert captured["payload"]["Filter"] == {
        "GroupType": "AIGC",
        "GroupIds": ["group-1"],
        "Name": "hero",
    }


def test_create_asset_requires_public_url(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.content.file_upload_service.save_uploaded_file",
        lambda *args, **kwargs: (True, "C:/uploads/hero.png", None),
    )
    response = auth_client.post(
        "/api/virtual-assets",
        data={"group_id": "group-1", "name": "hero", "asset_type": "Image", "file": (BytesIO(b"x"), "hero.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_ark_error_is_stable_api_response(auth_client, monkeypatch):
    def fail(payload):
        raise ArkAssetError("火山引擎凭据未配置", code="ARK_ASSET_NOT_CONFIGURED", status_code=503)

    monkeypatch.setattr("app.api.content.ark_asset_service.list_asset_groups", fail)
    response = auth_client.get("/api/virtual-asset-groups")
    assert response.status_code == 503
    assert response.get_json()["code"] == "ARK_ASSET_NOT_CONFIGURED"
