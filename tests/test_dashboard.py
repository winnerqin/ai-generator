from datetime import datetime

import database


def _login(client, *, admin=False):
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["username"] = "system_admin" if admin else "creator"
        session["role_code"] = "system_admin" if admin else "internal_user"
        session["current_project_id"] = 3


def _payload(include_admin=False):
    result = {
        "summary": {"total": 2, "today": 1, "running": 1, "failed": 0, "completed_30d": 1, "success_rate": 100},
        "task_status": {"image": {"waiting": 0, "running": 1, "succeeded": 1, "failed": 0, "cancelled": 0}},
        "trends": [], "recent_assets": [], "attention_tasks": [],
    }
    if include_admin:
        result["admin_insights"] = {"models": [], "active_users": []}
    return result


def test_root_redirects_to_dashboard_and_image_has_new_route(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(database, "get_user_by_id", lambda _id: {"role_code": "internal_user"})
    root = client.get("/")
    assert root.status_code == 302
    assert root.headers["Location"].endswith("/dashboard")
    assert client.get("/image-generate").status_code == 200


def test_dashboard_scopes_regular_user_to_authorized_project(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(database, "get_user_by_id", lambda _id: {"role_code": "internal_user"})
    monkeypatch.setattr(database, "has_project_access", lambda user_id, project_id: (user_id, project_id) == (7, 3))
    captured = {}
    monkeypatch.setattr(database, "get_dashboard_data", lambda **kwargs: captured.update(kwargs) or _payload())
    response = client.get("/api/dashboard?period=30d&project_id=3&scope=global")
    assert response.status_code == 200
    assert captured["user_id"] == 7
    assert captured["project_id"] == 3
    assert "admin_insights" not in response.get_json()


def test_dashboard_rejects_unauthorized_project(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(database, "get_user_by_id", lambda _id: {"role_code": "internal_user"})
    monkeypatch.setattr(database, "has_project_access", lambda *_args: False)
    assert client.get("/api/dashboard?project_id=99").status_code == 403


def test_admin_global_dashboard_is_unscoped(client, monkeypatch):
    _login(client, admin=True)
    monkeypatch.setattr(database, "get_user_by_id", lambda _id: {"role_code": "system_admin"})
    captured = {}
    monkeypatch.setattr(database, "get_dashboard_data", lambda **kwargs: captured.update(kwargs) or _payload(True))
    response = client.get("/api/dashboard?scope=global&period=7d")
    assert response.status_code == 200
    assert captured["user_id"] is None and captured["project_id"] is None
    assert "admin_insights" in response.get_json()


def test_custom_dashboard_period_validation(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(database, "get_user_by_id", lambda _id: {"role_code": "internal_user"})
    response = client.get("/api/dashboard?period=custom&start_date=bad&end_date=2026-08-24")
    assert response.status_code == 400


def test_dashboard_page_contains_required_sections(client, monkeypatch):
    _login(client, admin=True)
    monkeypatch.setattr(database, "get_user_by_id", lambda _id: {"role_code": "system_admin"})
    html = client.get("/dashboard").get_data(as_text=True)
    assert "任务状态" in html
    assert "创作趋势" in html
    assert "最近作品" in html
    assert "模型稳定性" in html
    assert "余额" not in html and "Token" not in html and "快捷入口" not in html
