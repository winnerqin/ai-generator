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
        lambda payload, account_id=None: (
            captured.update(payload=payload, account_id=account_id)
            or {"AssetGroups": [{"GroupId": "group-1"}], "TotalCount": 1}
        ),
    )
    response = auth_client.get("/api/virtual-asset-groups?page=1&page_size=20")
    assert response.status_code == 200
    assert response.get_json()["items"][0]["GroupId"] == "group-1"
    assert captured["payload"]["Filter"] == {"GroupType": "AIGC"}


def test_group_crud_api(auth_client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.create_asset_group",
        lambda payload, account_id=None: captured.setdefault("create", payload),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.update_asset_group",
        lambda payload, account_id=None: captured.setdefault("update", payload),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.delete_asset_group",
        lambda payload, account_id=None: captured.setdefault("delete", payload),
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
        lambda payload, account_id=None: captured.setdefault("payload", payload),
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


def test_create_asset_timeout_reconciles_committed_asset(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.content.file_upload_service.save_uploaded_file",
        lambda *args, **kwargs: (True, "https://cdn.example.com/hero.png", None),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.create_asset",
        lambda payload, account_id=None: (_ for _ in ()).throw(
            ArkAssetError("Read timed out", status_code=502)
        ),
    )
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.list_assets",
        lambda payload, account_id=None: {
            "Assets": [{"AssetId": "asset-1", "Name": "主角正面", "URL": "https://cdn.example.com/hero.png"}]
        },
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
    assert response.get_json()["item"]["AssetId"] == "asset-1"


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
        lambda payload, account_id=None: captured.setdefault("payload", payload) and {"Items": []},
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
    def fail(payload, account_id=None):
        raise ArkAssetError("火山引擎凭据未配置", code="ARK_ASSET_NOT_CONFIGURED", status_code=503)

    monkeypatch.setattr("app.api.content.ark_asset_service.list_asset_groups", fail)
    response = auth_client.get("/api/virtual-asset-groups")
    assert response.status_code == 503
    assert response.get_json()["code"] == "ARK_ASSET_NOT_CONFIGURED"


def test_account_list_and_asset_query_keep_account_id(auth_client, monkeypatch):
    from app.config import config

    accounts = [
        {"id": "account_a", "name": "账号A", "ak": "ak-a", "sk": "sk-a", "api_key": "key-a", "api_key_pool": ""},
        {"id": "account_b", "name": "账号B", "ak": "ak-b", "sk": "sk-b", "api_key": "key-b", "api_key_pool": ""},
    ]
    monkeypatch.setattr(config, "get_ark_accounts", lambda: accounts)
    monkeypatch.setattr(
        config,
        "get_ark_account",
        lambda account_id=None: next(item for item in accounts if item["id"] == (account_id or "account_a")),
    )
    monkeypatch.setattr(
        config,
        "get_ark_account_api_key_pool",
        lambda account_id=None: [config.get_ark_account(account_id)["api_key"]],
    )
    monkeypatch.setattr(
        config,
        "get_ark_account_intl_api_key_pool",
        lambda account_id=None: [f"intl-{account_id}"] if account_id == "account_b" else [],
    )
    captured = {}
    monkeypatch.setattr(
        "app.api.content.ark_asset_service.list_assets",
        lambda payload, account_id=None: captured.update(account_id=account_id) or {"Items": []},
    )

    account_response = auth_client.get("/api/ark-accounts")
    assert account_response.status_code == 200
    assert account_response.get_json()["items"] == [
        {"id": "account_a", "name": "账号A", "edition": "domestic", "asset_configured": True, "generation_configured": True, "intl_generation_configured": False},
        {"id": "account_b", "name": "账号B", "edition": "domestic", "asset_configured": True, "generation_configured": True, "intl_generation_configured": True},
    ]
    response = auth_client.get("/api/virtual-assets?account_id=account_b")
    assert response.status_code == 200
    assert response.get_json()["account_id"] == "account_b"
    assert captured["account_id"] == "account_b"


def test_config_exposes_international_asset_accounts(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "ARK_ACCOUNT_IDS", "")
    monkeypatch.setattr(config, "ARK_INTL_ACCOUNT_IDS", "byteplus_a")
    monkeypatch.setenv("ARK_INTL_ACCOUNT_BYTEPLUS_A_NAME", "国际账号A")
    monkeypatch.setenv("ARK_INTL_ACCOUNT_BYTEPLUS_A_AK", "intl-ak")
    monkeypatch.setenv("ARK_INTL_ACCOUNT_BYTEPLUS_A_SK", "intl-sk")
    monkeypatch.setenv("ARK_INTL_ACCOUNT_BYTEPLUS_A_API_KEY", "intl-api-key")

    account = config.get_ark_account("intl:byteplus_a")

    assert account["name"] == "国际账号A"
    assert account["edition"] == "international"
    assert account["asset_region"] == "ap-southeast-1"
    assert config.get_ark_account_intl_api_key_pool(account["id"]) == ["intl-api-key"]
