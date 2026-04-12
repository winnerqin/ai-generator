"""
认证 API 单元测试
"""

import pytest


class TestAuth:
    """认证相关测试"""

    def test_login_page_get(self, client):
        """测试登录页面 GET 请求"""
        response = client.get("/login")
        assert response.status_code == 200

    def test_login_success_form(self, client, mock_user):
        """测试表单登录成功"""
        response = client.post(
            "/login",
            data={"username": "test_user", "password": "test_password"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_login_success_json(self, client, mock_user):
        """测试 JSON 登录成功"""
        response = client.post(
            "/login",
            json={"username": "test_user", "password": "test_password"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == "登录成功"
        assert data["data"]["username"] == "test_user"

    def test_login_failure_wrong_password(self, client, mock_user):
        """测试登录失败 - 密码错误"""
        response = client.post(
            "/login",
            json={"username": "test_user", "password": "wrong_password"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False
        assert "用户名或密码错误" in data["error"]

    def test_login_failure_missing_credentials(self, client):
        """测试登录失败 - 缺少凭据"""
        response = client.post("/login", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "不能为空" in data["error"]

    def test_register_disabled(self, client):
        """测试注册功能已禁用"""
        response = client.post("/register", json={"username": "new_user", "password": "pass"})
        assert response.status_code == 403
        data = response.get_json()
        assert data["success"] is False
        assert "已禁用" in data["error"]

    def test_logout(self, auth_client):
        """测试登出功能"""
        response = auth_client.get("/logout", follow_redirects=True)
        assert response.status_code == 200

    def test_get_current_user_authenticated(self, auth_client, mock_user):
        """测试获取当前用户信息 - 已认证"""
        response = auth_client.get("/api/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["id"] == 1
        assert data["data"]["username"] == "test_user"

    def test_get_current_user_unauthenticated(self, client):
        """测试获取当前用户信息 - 未认证"""
        response = client.get("/api/me")
        assert response.status_code == 401  # API 返回 401
