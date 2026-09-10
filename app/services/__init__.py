"""Service layer exports."""

from app.services.file_service import FileUploadService, file_upload_service
from app.services.legacy_generation_service import (
    generate_legacy_request,
    get_user_output_folder,
    resume_legacy_generation_stream,
)
from app.services.omni_video_client import OmniVideoClient, omni_video_client
from app.services.omni_video_service import OmniVideoService, omni_video_service
from app.services.oss_service import OSSService
from app.services.storage_service import (
    AIVideoBackendStorageService,
    InvalidStorageReferenceError,
    StorageBackendError,
    storage_service,
)

oss_service = storage_service
from app.services.ark_asset_service import ArkAssetError, ArkAssetService, ark_asset_service

__all__ = [
    "OSSService",
    "oss_service",
    "storage_service",
    "AIVideoBackendStorageService",
    "StorageBackendError",
    "InvalidStorageReferenceError",
    "FileUploadService",
    "file_upload_service",
    "generate_legacy_request",
    "resume_legacy_generation_stream",
    "get_user_output_folder",
    "OmniVideoClient",
    "omni_video_client",
    "OmniVideoService",
    "omni_video_service",
    "ArkAssetError",
    "ArkAssetService",
    "ark_asset_service",
]
