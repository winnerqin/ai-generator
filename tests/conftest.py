"""
测试配置和 Fixtures
"""

import os

# 在导入 app 之前设置 JWT 密钥
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-that-is-32-bytes-long-for-security"

import pytest
from app_factory import create_app
import database


@pytest.fixture
def app():
    """创建测试应用实例"""
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }
    )
    yield app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """创建已认证的测试客户端"""
    # 使用测试用户登录 (ID=1, 通常是 admin)
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "test_user"
        sess["project_id"] = 1
    return client


@pytest.fixture
def mock_user(monkeypatch):
    """模拟用户数据"""

    def mock_get_user_by_id(user_id):
        return {
            "id": user_id,
            "username": "test_user",
            "password": "test_password",
        }

    def mock_verify_user(username, password):
        if username == "test_user" and password == "test_password":
            return {"id": 1, "username": username, "password": password}
        return None

    monkeypatch.setattr(database, "get_user_by_id", mock_get_user_by_id)
    monkeypatch.setattr(database, "verify_user", mock_verify_user)


@pytest.fixture
def mock_projects(monkeypatch):
    """模拟项目数据"""

    def mock_get_user_projects(user_id):
        return [
            {"id": 1, "name": "Test Project 1", "owner_id": user_id},
            {"id": 2, "name": "Test Project 2", "owner_id": user_id},
        ]

    def mock_get_project_by_id(project_id):
        return {
            "id": project_id,
            "name": f"Project {project_id}",
            "owner_id": 1,
        }

    def mock_create_project(name, owner_id):
        return 3

    def mock_assign_user_to_project(user_id, project_id):
        pass

    monkeypatch.setattr(database, "get_user_projects", mock_get_user_projects)
    monkeypatch.setattr(database, "get_project_by_id", mock_get_project_by_id)
    monkeypatch.setattr(database, "create_project", mock_create_project)
    monkeypatch.setattr(database, "assign_user_to_project", mock_assign_user_to_project)
