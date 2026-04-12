"""
项目 API 单元测试
"""

import pytest


class TestProjects:
    """项目相关测试"""

    def test_get_projects_authenticated(self, auth_client, mock_projects):
        """测试获取项目列表 - 已认证"""
        response = auth_client.get("/api/projects")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "projects" in data
        assert len(data["projects"]) == 2
        assert data["projects"][0]["name"] == "Test Project 1"

    def test_get_projects_unauthenticated(self, client):
        """测试获取项目列表 - 未认证"""
        response = client.get("/api/projects")
        assert response.status_code == 401

    def test_create_project_success(self, auth_client, mock_projects):
        """测试创建项目成功"""
        response = auth_client.post("/api/projects", json={"name": "New Project"})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == "项目创建成功"
        assert data["id"] == 3
        assert data["name"] == "New Project"

    def test_create_project_missing_name(self, auth_client):
        """测试创建项目 - 缺少名称"""
        response = auth_client.post("/api/projects", json={"name": ""})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "项目名称不能为空" in data["error"]

    def test_create_project_whitespace_name(self, auth_client):
        """测试创建项目 - 空白名称"""
        response = auth_client.post("/api/projects", json={"name": "   "})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_switch_project_success(self, auth_client, mock_projects):
        """测试切换项目成功"""
        response = auth_client.post("/api/projects/switch", json={"project_id": 2})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == "项目切换成功"
        assert data["project_id"] == 2

    def test_switch_project_missing_id(self, auth_client):
        """测试切换项目 - 缺少项目ID"""
        response = auth_client.post("/api/projects/switch", json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "项目ID不能为空" in data["error"]

    def test_switch_project_no_access(self, auth_client, mock_projects, monkeypatch):
        """测试切换项目 - 无权限"""
        import database

        def mock_get_user_projects(user_id):
            return [{"id": 1, "name": "Test Project 1", "owner_id": user_id}]

        monkeypatch.setattr(database, "get_user_projects", mock_get_user_projects)

        response = auth_client.post("/api/projects/switch", json={"project_id": 2})
        assert response.status_code == 403
        data = response.get_json()
        assert data["success"] is False
        assert "无权访问该项目" in data["error"]

    def test_delete_project_success(self, auth_client, mock_projects):
        """测试删除项目成功"""
        response = auth_client.delete("/api/projects/1")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "项目删除成功" in data["message"]

    def test_delete_project_not_found(self, auth_client, mock_projects, monkeypatch):
        """测试删除项目 - 项目不存在"""
        import database

        def mock_get_project_by_id(project_id):
            return None

        monkeypatch.setattr(database, "get_project_by_id", mock_get_project_by_id)

        response = auth_client.delete("/api/projects/999")
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False
        assert "项目不存在" in data["error"]

    def test_delete_project_no_permission(self, auth_client, mock_projects, monkeypatch):
        """测试删除项目 - 无权限"""
        import database

        def mock_get_project_by_id(project_id):
            return {
                "id": project_id,
                "name": "Other User Project",
                "owner_id": 999,  # 不同用户
            }

        monkeypatch.setattr(database, "get_project_by_id", mock_get_project_by_id)

        response = auth_client.delete("/api/projects/2")
        assert response.status_code == 403
        data = response.get_json()
        assert data["success"] is False
        assert "无权删除该项目" in data["error"]


class TestProjectUtils:
    """项目工具函数测试"""

    def test_user_has_project_true(self, mock_projects):
        """测试用户有项目访问权限"""
        from app.api.projects import user_has_project

        result = user_has_project(1, 1)
        assert result is True

    def test_user_has_project_false(self, mock_projects, monkeypatch):
        """测试用户无项目访问权限"""
        import database
        from app.api.projects import user_has_project

        def mock_get_user_projects(user_id):
            return [{"id": 1, "name": "Test Project 1"}]

        monkeypatch.setattr(database, "get_user_projects", mock_get_user_projects)

        result = user_has_project(1, 2)
        assert result is False

    def test_user_has_project_empty_list(self, mock_projects, monkeypatch):
        """测试用户项目列表为空"""
        import database
        from app.api.projects import user_has_project

        def mock_get_user_projects(user_id):
            return []

        monkeypatch.setattr(database, "get_user_projects", mock_get_user_projects)

        result = user_has_project(1, 1)
        assert result is False
