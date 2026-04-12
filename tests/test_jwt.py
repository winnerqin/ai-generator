"""
JWT 认证 API 单元测试
"""

import pytest


class TestJWTAuth:
    """JWT 认证相关测试"""

    def test_jwt_login_success(self, client, mock_user):
        """测试 JWT 登录成功"""
        response = client.post(
            "/api/auth/login",
            json={"username": "test_user", "password": "test_password"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == "登录成功"
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert "user" in data["data"]
        assert data["data"]["user"]["username"] == "test_user"

    def test_jwt_login_failure_wrong_password(self, client, mock_user):
        """测试 JWT 登录失败 - 密码错误"""
        response = client.post(
            "/api/auth/login",
            json={"username": "test_user", "password": "wrong_password"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False
        assert "用户名或密码错误" in data["error"]

    def test_jwt_login_missing_credentials(self, client):
        """测试 JWT 登录 - 缺少凭据"""
        response = client.post("/api/auth/login", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_jwt_me_with_token(self, client, mock_user):
        """测试使用 JWT 令牌获取当前用户信息"""
        # 先登录获取 token
        login_response = client.post(
            "/api/auth/login",
            json={"username": "test_user", "password": "test_password"},
        )
        token = login_response.get_json()["data"]["access_token"]

        # 使用 token 访问 /api/auth/me
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["user_id"] == 1
        assert data["data"]["username"] == "test_user"

    def test_jwt_me_without_token(self, client):
        """测试未提供 JWT 令牌"""
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False
        # 检查是否返回了缺少认证的错误信息
        assert "Token" in data["error"] or "认证" in data["error"]

    def test_jwt_me_with_invalid_token(self, client):
        """测试使用无效的 JWT 令牌"""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False


class TestJWTRefresh:
    """JWT 令牌刷新测试"""

    def test_jwt_refresh_success(self, client, mock_user):
        """测试 JWT 令牌刷新成功"""
        # 先登录获取 tokens
        login_response = client.post(
            "/api/auth/login",
            json={"username": "test_user", "password": "test_password"},
        )
        refresh_token = login_response.get_json()["data"]["refresh_token"]

        # 使用 refresh token 刷新
        response = client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    def test_jwt_refresh_without_token(self, client):
        """测试未提供刷新令牌"""
        response = client.post("/api/auth/refresh")
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False

    def test_jwt_refresh_with_access_token(self, client, mock_user):
        """测试错误地使用访问令牌进行刷新"""
        # 先登录获取 token
        login_response = client.post(
            "/api/auth/login",
            json={"username": "test_user", "password": "test_password"},
        )
        access_token = login_response.get_json()["data"]["access_token"]

        # 错误地使用 access token 刷新
        response = client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        # 应该返回 401，因为 access token 不能用于刷新
        assert response.status_code == 401
