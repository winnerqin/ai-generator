from pathlib import Path
import importlib
import io
from unittest.mock import Mock

import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from app.api.content import content_bp
from app.config import config
from app.services.storage_service import AIVideoBackendStorageService, StorageBackendError

storage_module = importlib.import_module("app.services.storage_service")


@pytest.fixture
def storage_config(monkeypatch):
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_BASE_URL", "https://backend.example/admin")
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_APP_KEY", "secret-app-key")
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_PROJECT_ID", 0)
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_DEFAULT_PROJECT_ID", 0)
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_PUBLIC_BASE_URL", "https://app.example")
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_PROXY_SECRET", "proxy-secret")


def _response(data):
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "code": "1", "message": "成功", "data": data}
    return response


def test_upload_file_uses_backend_multipart_and_returns_stable_url(monkeypatch, storage_config):
    source = Path("tests-storage-upload.jpg")
    source.write_bytes(b"image")
    post = Mock(
        return_value=_response(
            {
                "id": 81,
                "projectId": 7,
                "originalFileName": source.name,
                "previewUrl": "https://s3.example/temporary",
            }
        )
    )
    monkeypatch.setattr(storage_module.requests, "post", post)
    try:
        service = AIVideoBackendStorageService()
        url = service.upload_file(str(source), project_id=7)
    finally:
        source.unlink(missing_ok=True)

    assert url.startswith("https://app.example/api/storage/files/81/7/")
    assert "temporary" not in url
    assert post.call_args.args[0] == "https://backend.example/admin/file/v1/upload"
    assert post.call_args.kwargs["headers"] == {"appkey": "secret-app-key"}
    assert post.call_args.kwargs["data"] == {"projectId": "7"}
    assert "file" in post.call_args.kwargs["files"]


def test_generated_url_is_imported_by_backend_without_local_download(monkeypatch, storage_config):
    post = Mock(
        return_value=_response(
            {
                "id": 82,
                "projectId": 7,
                "originalFileName": "result.mp4",
                "previewUrl": "https://s3.example/temporary",
            }
        )
    )
    monkeypatch.setattr(storage_module.requests, "post", post)
    service = AIVideoBackendStorageService()

    url, expired = service.import_from_url(
        "https://upstream.example/result.mp4", "result.mp4", 3, 7
    )

    assert expired is False
    assert "/api/storage/files/82/7/" in url
    assert post.call_args.args[0].endswith("/file/v1/upload/url")
    assert post.call_args.kwargs["json"] == {
        "projectId": 7,
        "fileUrl": "https://upstream.example/result.mp4",
        "originalFileName": "result.mp4",
    }


def test_configured_backend_project_overrides_local_project(monkeypatch, storage_config):
    monkeypatch.setattr(config, "AI_VIDEO_BACKEND_PROJECT_ID", 4)
    post = Mock(
        return_value=_response(
            {
                "id": 90,
                "projectId": 4,
                "originalFileName": "result.mp4",
                "previewUrl": "https://s3.example/temporary",
            }
        )
    )
    monkeypatch.setattr(storage_module.requests, "post", post)

    url, expired = AIVideoBackendStorageService().import_from_url(
        "https://upstream.example/result.mp4", "result.mp4", 3, 1
    )

    assert expired is False
    assert "/api/storage/files/90/4/" in url
    assert post.call_args.kwargs["json"]["projectId"] == 4


def test_project_permission_403_is_not_reported_as_expired(monkeypatch, storage_config):
    response = Mock(status_code=403)
    response.json.return_value = {
        "success": False,
        "code": "403",
        "message": "无项目访问权限",
        "data": None,
    }
    monkeypatch.setattr(storage_module.requests, "post", Mock(return_value=response))

    url, expired = AIVideoBackendStorageService().import_from_url(
        "https://upstream.example/result.mp4", "result.mp4", 3, 1
    )

    assert url is None
    assert expired is False


def test_proxy_refreshes_expired_preview_url_with_file_page(monkeypatch, storage_config):
    service = AIVideoBackendStorageService()
    stable = service.build_access_url(
        {
            "id": 83,
            "projectId": 7,
            "originalFileName": "测试 视频.mp4",
            "previewUrl": "https://s3.example/old",
        }
    )
    service._preview_cache.clear()
    post = Mock(
        return_value=_response(
            {
                "pageParam": {"nextPage": 0},
                "items": [
                    {
                        "id": 83,
                        "projectId": 7,
                        "originalFileName": "测试 视频.mp4",
                        "previewUrl": "https://s3.example/fresh",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(storage_module.requests, "post", post)

    assert service.resolve_access_url(stable) == "https://s3.example/fresh"
    assert post.call_args.args[0].endswith("/file/v1/page")


def test_proxy_rejects_tampered_signature(storage_config):
    service = AIVideoBackendStorageService()
    stable = service.build_access_url(
        {
            "id": 84,
            "projectId": 7,
            "originalFileName": "result.mp4",
            "previewUrl": "https://s3.example/old",
        }
    )
    with pytest.raises(StorageBackendError):
        service.resolve_access_url(stable.replace("/84/", "/85/"))


def test_delete_disables_backend_file(monkeypatch, storage_config):
    service = AIVideoBackendStorageService()
    stable = service.build_access_url(
        {
            "id": 86,
            "projectId": 7,
            "originalFileName": "result.mp4",
            "previewUrl": "https://s3.example/old",
        }
    )
    post = Mock(return_value=_response({"id": 86, "updatedContent": {"status": 0}}))
    monkeypatch.setattr(storage_module.requests, "post", post)

    assert service.delete_file(stable) is True
    assert post.call_args.args[0].endswith("/file/v1/update")
    assert post.call_args.kwargs["json"] == {"id": 86, "status": 0}


def test_signed_proxy_redirects_to_fresh_preview(monkeypatch, storage_config):
    service = AIVideoBackendStorageService()
    stable = service.build_access_url(
        {
            "id": 87,
            "projectId": 7,
            "originalFileName": "result.mp4",
            "previewUrl": "https://s3.example/old",
        }
    )
    monkeypatch.setattr(
        "app.api.content.storage_service.resolve_access_url",
        lambda reference: "https://s3.example/fresh",
    )
    app = Flask(__name__)
    app.register_blueprint(content_bp)

    response = app.test_client().get(stable.removeprefix("https://app.example"))

    assert response.status_code == 302
    assert response.headers["Location"] == "https://s3.example/fresh"


def test_uploaded_file_has_no_local_fallback(monkeypatch):
    import importlib

    module = importlib.import_module("app.services.file_service")
    monkeypatch.setattr(module.config, "UPLOAD_FOLDER", ".")
    monkeypatch.setattr(module.oss_service, "upload_file", lambda *args, **kwargs: None)
    upload = FileStorage(stream=io.BytesIO(b"image"), filename="s3-required-upload.jpg")

    success, url, error = module.FileUploadService().save_uploaded_file(
        upload, project_id=7, file_type="image"
    )

    assert success is False
    assert url is None
    assert "AWS S3" in error
    assert not Path("s3-required-upload.jpg").exists()
