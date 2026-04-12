"""
文件上传服务模块

提供文件上传、验证、保存等操作的封装
"""

import mimetypes
import os
import string
from pathlib import Path
from typing import Optional, Tuple

from app.config import config
from app.services.oss_service import oss_service


class FileUploadService:
    """文件上传服务类"""

    # 允许的文件类型
    ALLOWED_IMAGE_EXTENSIONS = config.ALLOWED_IMAGE_EXTENSIONS
    ALLOWED_VIDEO_EXTENSIONS = config.ALLOWED_VIDEO_EXTENSIONS
    ALLOWED_AUDIO_EXTENSIONS = config.ALLOWED_AUDIO_EXTENSIONS
    ALLOWED_TEXT_EXTENSIONS = config.ALLOWED_TEXT_EXTENSIONS

    # 文件大小限制
    MAX_IMAGE_SIZE = config.MAX_IMAGE_SIZE
    MAX_VIDEO_SIZE = config.MAX_VIDEO_SIZE
    MAX_AUDIO_SIZE = config.MAX_AUDIO_SIZE
    MAX_TEXT_SIZE = config.MAX_TEXT_SIZE

    def __init__(self):
        """初始化文件上传服务"""
        # 确保上传目录存在
        Path(config.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        Path(config.OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)

    def generate_random_filename(self, length: int = 8) -> str:
        """
        生成随机文件名（仅包含字母和数字）

        Args:
            length: 文件名长度

        Returns:
            随机文件名
        """
        chars = string.ascii_lowercase + string.digits
        return "".join(string.SystemRandom().choice(chars) for _ in range(length))

    def get_unique_filename(self, folder: str, base_filename: str, extension: str = ".jpg") -> str:
        """
        获取唯一文件名，如果文件已存在，则添加后缀

        Args:
            folder: 目标文件夹
            base_filename: 基础文件名
            extension: 文件扩展名

        Returns:
            唯一文件名
        """
        if not base_filename or not base_filename.strip():
            # 如果文件名为空，生成随机文件名
            base_filename = self.generate_random_filename(8)

        # 确保扩展名正确
        if not base_filename.endswith(extension):
            base_filename = base_filename + extension

        # 检查文件是否存在
        filepath = os.path.join(folder, base_filename)
        if not os.path.exists(filepath):
            return base_filename

        # 如果文件存在，添加后缀
        name_without_ext = base_filename[: -len(extension)]
        counter = 1
        while True:
            new_filename = f"{name_without_ext}_{counter}{extension}"
            new_filepath = os.path.join(folder, new_filename)
            if not os.path.exists(new_filepath):
                return new_filename
            counter += 1
            if counter > 1000:  # 防止无限循环
                return self.generate_random_filename(8) + extension

    def get_file_extension(self, filename: str) -> str:
        """
        获取文件扩展名

        Args:
            filename: 文件名

        Returns:
            小写扩展名（包含点）
        """
        return os.path.splitext(filename)[1].lower()

    def validate_file(
        self, filename: str, file_size: int | None, file_type: str = "image"
    ) -> Tuple[bool, Optional[str]]:
        """
        验证文件类型和大小

        Args:
            filename: 文件名
            file_size: 文件大小（字节）
            file_type: 文件类型 (image, video, text)

        Returns:
            (是否有效, 错误信息)
        """
        ext = self.get_file_extension(filename)

        # 验证扩展名
        if file_type == "image":
            if ext not in self.ALLOWED_IMAGE_EXTENSIONS:
                return (
                    False,
                    f"不支持的图片格式: {ext}，支持的格式: {', '.join(self.ALLOWED_IMAGE_EXTENSIONS)}",
                )
            if file_size > self.MAX_IMAGE_SIZE:
                return False, f"图片大小超过限制，最大 {self.MAX_IMAGE_SIZE // 1024 // 1024}MB"
        elif file_type == "video":
            if ext not in self.ALLOWED_VIDEO_EXTENSIONS:
                return (
                    False,
                    f"不支持的视频格式: {ext}，支持的格式: {', '.join(self.ALLOWED_VIDEO_EXTENSIONS)}",
                )
            if file_size > self.MAX_VIDEO_SIZE:
                return False, f"视频大小超过限制，最大 {self.MAX_VIDEO_SIZE // 1024 // 1024}MB"
        elif file_type == "audio":
            if ext not in self.ALLOWED_AUDIO_EXTENSIONS:
                return (
                    False,
                    f"涓嶆敮鎸佺殑闊抽鏍煎紡: {ext}锛屾敮鎸佺殑鏍煎紡: {', '.join(self.ALLOWED_AUDIO_EXTENSIONS)}",
                )
            if file_size and file_size > self.MAX_AUDIO_SIZE:
                return False, f"闊抽澶у皬瓒呰繃闄愬埗锛屾渶澶?{self.MAX_AUDIO_SIZE // 1024 // 1024}MB"
        elif file_type == "text":
            if ext not in self.ALLOWED_TEXT_EXTENSIONS:
                return (
                    False,
                    f"不支持的文本格式: {ext}，支持的格式: {', '.join(self.ALLOWED_TEXT_EXTENSIONS)}",
                )
            if file_size > self.MAX_TEXT_SIZE:
                return False, f"文本大小超过限制，最大 {self.MAX_TEXT_SIZE // 1024 // 1024}MB"
        else:
            return False, f"不支持的文件类型: {file_type}"

        return True, None

    def get_mime_type(self, filename: str) -> str:
        """
        获取文件的 MIME 类型

        Args:
            filename: 文件名

        Returns:
            MIME 类型字符串
        """
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def save_uploaded_file(
        self,
        file,
        user_id: Optional[int] = None,
        project_id: Optional[int] = None,
        subfolder: str = "",
        file_type: str = "image",
        upload_to_oss: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        保存上传的文件

        Args:
            file: 文件对象（Flask 的 request.files 中的文件）
            user_id: 用户ID
            project_id: 项目ID
            subfolder: 子文件夹名称
            file_type: 文件类型
            upload_to_oss: 是否上传到 OSS

        Returns:
            (是否成功, 本地路径/URL, 错误信息)
        """
        if not file or not file.filename:
            return False, None, "未选择文件"

        filename = file.filename
        ext = self.get_file_extension(filename)

        # 验证文件
        file_size = file.content_length or 0
        is_valid, error_msg = self.validate_file(filename, file_size, file_type)
        if not is_valid:
            return False, None, error_msg

        # 构建保存路径
        if user_id:
            save_folder = os.path.join(config.UPLOAD_FOLDER, f"user_{user_id}")
        else:
            save_folder = config.UPLOAD_FOLDER

        if project_id:
            save_folder = os.path.join(save_folder, f"project_{project_id}")

        if subfolder:
            save_folder = os.path.join(save_folder, subfolder)

        os.makedirs(save_folder, exist_ok=True)

        # 生成唯一文件名
        base_filename = os.path.splitext(filename)[0]
        unique_filename = self.get_unique_filename(save_folder, base_filename, ext)
        local_path = os.path.join(save_folder, unique_filename)

        # 保存到本地
        try:
            file.save(local_path)
            print(f"[FileUpload] 文件保存成功: {local_path}")
        except Exception as e:
            return False, None, f"保存文件失败: {str(e)}"

        # 如果启用 OSS，上传到 OSS
        if upload_to_oss and oss_service.is_available():
            oss_type = {
                "image": "image",
                "video": "video",
                "audio": "document",
                "text": "document",
                "sample": "sample",
            }.get(file_type, "image")

            # 确定 OSS 文件类型
            if subfolder == "person":
                oss_type = "person"
            elif subfolder == "scene":
                oss_type = "scene"

            oss_url = oss_service.upload_file(
                local_path, user_id=user_id, project_id=project_id, file_type=oss_type
            )

            if oss_url:
                return True, oss_url, None

        return True, local_path, None

    def save_generated_file(
        self,
        source_path: str,
        user_id: Optional[int] = None,
        project_id: Optional[int] = None,
        file_type: str = "image",
        keep_local: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        保存生成的文件

        Args:
            source_path: 源文件路径
            user_id: 用户ID
            project_id: 项目ID
            file_type: 文件类型
            keep_local: 是否保留本地文件

        Returns:
            (是否成功, OSS URL 或本地路径, 错误信息)
        """
        if not os.path.exists(source_path):
            return False, None, f"源文件不存在: {source_path}"

        # 上传到 OSS
        if oss_service.is_available():
            oss_url = oss_service.upload_file(
                source_path, user_id=user_id, project_id=project_id, file_type=file_type
            )

            if oss_url:
                # 如果不需要保留本地文件，删除本地文件
                if not keep_local:
                    try:
                        os.remove(source_path)
                    except Exception:
                        pass

                return True, oss_url, None

        # OSS 不可用，返回本地路径
        return True, source_path, None

    def delete_file(self, file_path: str, is_oss: bool = False) -> bool:
        """
        删除文件

        Args:
            file_path: 文件路径（本地或 OSS URL）
            is_oss: 是否为 OSS 文件

        Returns:
            是否删除成功
        """
        if is_oss:
            # 从 OSS URL 提取对象键
            if config.OSS_ENDPOINT in file_path:
                object_key = file_path.split(config.OSS_ENDPOINT + "/", 1)[1]
                return oss_service.delete_file(object_key)
            return False

        # 删除本地文件
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[FileUpload] 删除文件: {file_path}")
                return True
        except Exception as e:
            print(f"[FileUpload] 删除文件失败: {file_path}, 错误: {e}")
            return False

        return False


# 全局文件上传服务实例
file_upload_service = FileUploadService()
