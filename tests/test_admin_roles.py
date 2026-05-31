"""
角色管理 API 测试
"""

import database


def _login_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role_code"] = database.ROLE_SYSTEM_ADMIN
        sess["project_id"] = 1


def test_create_role_success(client, monkeypatch):
    roles = [
        {
            "code": database.ROLE_SYSTEM_ADMIN,
            "name": "系统管理员",
            "menu_keys": ["admin"],
            "pricing_multiplier": 1.0,
            "built_in": True,
        }
    ]

    monkeypatch.setattr(database, "get_role_definitions", lambda: [dict(r) for r in roles])

    def _save(new_roles):
        roles[:] = [dict(r) for r in new_roles]
        return [dict(r) for r in roles]

    monkeypatch.setattr(database, "save_role_definitions", _save)
    _login_admin(client)

    resp = client.post(
        "/api/admin/roles",
        json={
            "code": "partner_user",
            "name": "渠道用户",
            "menu_keys": ["index", "records"],
            "pricing_multiplier": 1.5,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    saved = {r["code"]: r for r in data["roles"]}
    assert "partner_user" in saved
    assert saved["partner_user"]["pricing_multiplier"] == 1.5


def test_update_role_menu_and_multiplier(client, monkeypatch):
    roles = [
        {
            "code": database.ROLE_SYSTEM_ADMIN,
            "name": "系统管理员",
            "menu_keys": ["admin"],
            "pricing_multiplier": 1.0,
            "built_in": True,
        },
        {
            "code": "partner_user",
            "name": "渠道用户",
            "menu_keys": ["index"],
            "pricing_multiplier": 1.2,
            "built_in": False,
        },
    ]
    monkeypatch.setattr(database, "get_role_definitions", lambda: [dict(r) for r in roles])

    def _save(new_roles):
        roles[:] = [dict(r) for r in new_roles]
        return [dict(r) for r in roles]

    monkeypatch.setattr(database, "save_role_definitions", _save)
    _login_admin(client)

    resp = client.put(
        "/api/admin/roles/partner_user",
        json={"menu_keys": ["index", "omni_video"], "pricing_multiplier": 1.8},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    saved = {r["code"]: r for r in data["roles"]}
    assert saved["partner_user"]["menu_keys"] == ["index", "omni_video"]
    assert saved["partner_user"]["pricing_multiplier"] == 1.8


def test_delete_built_in_role_rejected(client, monkeypatch):
    monkeypatch.setattr(
        database,
        "get_role_definitions",
        lambda: [
            {
                "code": database.ROLE_SYSTEM_ADMIN,
                "name": "系统管理员",
                "menu_keys": ["admin"],
                "pricing_multiplier": 1.0,
                "built_in": True,
            }
        ],
    )
    _login_admin(client)

    resp = client.delete(f"/api/admin/roles/{database.ROLE_SYSTEM_ADMIN}")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "不可删除" in data["error"]
