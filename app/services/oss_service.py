"""
阿里云 OSS 服务模块

提供 OSS 文件上传、下载、列表等操作的封装
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import config


class OSSService:
    """阿里云 OSS 服务类"""

    def __init__(self):
        """初始化 OSS 服务"""
        self._bucket = None
        self._endpoint_full = None
        self._oss2 = None

        # 延迟导入，避免未安装 oss2 时出错
        self._initialized = False

    def _init_oss(self):
        """延迟初始化 OSS 客户端"""
        if self._initialized:
            return

        if not config.is_oss_enabled():
            raise RuntimeError("OSS 未启用，请检查配置")

        try:
            import oss2

            self._oss2 = oss2
        except ImportError:
            raise RuntimeError("未安装 oss2 SDK，请运行: pip install oss2")

        # 从完整的 endpoint 中提取 bucket 和实际 endpoint
        # 格式: bucket-name.oss-region.aliyuncs.com
        parts = config.OSS_ENDPOINT.split(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"OSS_ENDPOINT 格式不正确: {config.OSS_ENDPOINT}，"
                "应为 bucket-name.oss-region.aliyuncs.com"
            )

        bucket_name = parts[0]
        oss_endpoint = parts[1]

        # 初始化 OSS 客户端
        auth = oss2.Auth(config.OSS_ACCESS_KEY_ID, config.OSS_ACCESS_KEY_SECRET)
        self._bucket = oss2.Bucket(auth, f"https://{oss_endpoint}", bucket_name)
        self._endpoint_full = config.OSS_ENDPOINT
        self._initialized = True

    def is_available(self) -> bool:
        """检查 OSS 是否可用"""
        if not config.is_oss_enabled():
            return False
        try:
            self._init_oss()
            return self._bucket is not None
        except Exception:
            return False

    def upload_file(
        self,
        file_path: str,
        user_id: Optional[int] = None,
        project_id: Optional[int] = None,
        file_type: str = "image",
    ) -> Optional[str]:
        """
        上传文件到 OSS

        Args:
            file_path: 本地文件路径
            user_id: 用户ID，用于隔离用户文件
            project_id: 项目ID，用于项目隔离
            file_type: 文件类型 (image, video, sample, person, scene, document)

        Returns:
            公网访问 URL，失败返回 None
        """
        if not os.path.exists(file_path):
            print(f"[OSS] 文件不存在: {file_path}")
            return None

        try:
            self._init_oss()

            filename = os.path.basename(file_path)
            object_key = self._generate_object_key(filename, user_id, project_id, file_type)

            # 上传文件
            with open(file_path, "rb") as f:
                self._bucket.put_object(object_key, f)

            # 返回公网访问 URL
            public_url = f"https://{self._endpoint_full}/{object_key}"
            print(f"[OSS] 上传成功: {file_path} -> {object_key}")
            return public_url

        except Exception as e:
            print(f"[OSS] 上传失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _generate_object_key(
        self, filename: str, user_id: Optional[int], project_id: Optional[int], file_type: str
    ) -> str:
        """
        生成对象键（文件路径）

        Args:
            filename: 文件名
            user_id: 用户ID
            project_id: 项目ID
            file_type: 文件类型

        Returns:
            OSS 对象键
        """
        timestamp = datetime.now().strftime("%Y%m%d")

        # 根据类型生成不同的路径
        if file_type == "sample":
            # 示例图
            if project_id and user_id:
                return f"sample/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                return f"sample/user_{user_id}/{filename}"
            else:
                return f"sample/{filename}"

        elif file_type == "person":
            # 人物库图片
            if project_id and user_id:
                return f"sample/person/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                return f"sample/person/user_{user_id}/{filename}"
            else:
                return f"sample/person/{filename}"

        elif file_type == "scene":
            # 场景库图片
            if project_id and user_id:
                return f"sample/scene/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                return f"sample/scene/user_{user_id}/{filename}"
            else:
                return f"sample/scene/{filename}"

        elif file_type == "video":
            # 视频文件
            if project_id and user_id:
                return f"video_generator/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                return f"video_generator/user_{user_id}/{filename}"
            else:
                return f"video_generator/{filename}"

        elif file_type == "document":
            # 文档文件
            if project_id and user_id:
                return f"documents/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                return f"documents/user_{user_id}/{filename}"
            else:
                return f"documents/{filename}"

        else:  # image
            # 默认：生成的图片
            if user_id and project_id:
                return f"ai-images/{timestamp}/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                return f"ai-images/{timestamp}/user_{user_id}/{filename}"
            else:
                return f"ai-images/{timestamp}/{filename}"

    def delete_file(self, object_key: str) -> bool:
        """
        删除 OSS 中的文件

        Args:
            object_key: OSS 对象键

        Returns:
            是否删除成功
        """
        try:
            self._init_oss()
            self._bucket.delete_object(object_key)
            print(f"[OSS] 删除成功: {object_key}")
            return True
        except Exception as e:
            print(f"[OSS] 删除失败: {object_key}, 错误: {e}")
            return False

    def file_exists(self, object_key: str) -> bool:
        """
        检查文件是否存在

        Args:
            object_key: OSS 对象键

        Returns:
            文件是否存在
        """
        try:
            self._init_oss()
            return self._bucket.object_exists(object_key)
        except Exception as e:
            error_str = str(e).lower()

            # 检查是否是文件不存在的错误
            no_such_key_indicators = [
                "nosuchkey",
                "404",
                "does not exist",
                "the specified key does not exist",
            ]

            if any(indicator in error_str for indicator in no_such_key_indicators):
                return False

            # 其他异常记录日志
            print(f"[OSS] 检查文件存在性时出错: {object_key}, 错误: {e}")
            return False

    def list_files(
        self, prefix: str, max_keys: int = 1000, extensions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        列出指定前缀下的文件

        Args:
            prefix: 对象键前缀
            max_keys: 最大返回数量
            extensions: 文件扩展名过滤（如 ['.jpg', '.png']）

        Returns:
            文件列表，每项包含 url, filename, size, key
        """
        try:
            self._init_oss()

            files = []
            for obj in self._oss2.ObjectIterator(self._bucket, prefix=prefix, max_keys=max_keys):
                # 扩展名过滤
                if extensions:
                    ext = os.path.splitext(obj.key)[1].lower()
                    if ext not in extensions:
                        continue

                filename = os.path.basename(obj.key)
                url = f"https://{self._endpoint_full}/{obj.key}"

                files.append(
                    {
                        "url": url,
                        "filename": filename,
                        "size": obj.size,
                        "key": obj.key,
                        "last_modified": obj.last_modified,
                    }
                )

            return files

        except Exception as e:
            print(f"[OSS] 列出文件失败: {prefix}, 错误: {e}")
            return []

    def list_sample_images(
        self,
        user_id: Optional[int] = None,
        project_id: Optional[int] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        列出示例图片

        Args:
            user_id: 用户ID
            project_id: 项目ID
            category: 类别 (person, scene, all)

        Returns:
            示例图片列表
        """
        if not user_id:
            return []

        # 构建搜索前缀
        prefixes = []

        if project_id:
            if category in ("person", None):
                prefixes.append(f"sample/person/user_{user_id}/project_{project_id}/")
            if category in ("scene", None):
                prefixes.append(f"sample/scene/user_{user_id}/project_{project_id}/")

        if category in ("person", None):
            prefixes.append(f"sample/person/user_{user_id}/")
        if category in ("scene", None):
            prefixes.append(f"sample/scene/user_{user_id}/")

        # 兼容旧路径
        prefixes.append(f"sample/user_{user_id}/")

        # 支持的图片扩展名
        extensions = [".jpg", ".jpeg", ".png", ".webp", ".gif"]

        # 列出所有文件并去重
        seen_keys = set()
        all_images = []

        for prefix in prefixes:
            files = self.list_files(prefix, max_keys=500, extensions=extensions)
            for file_info in files:
                if file_info["key"] in seen_keys:
                    continue

                seen_keys.add(file_info["key"])

                # 推断类别
                if "/person/" in file_info["key"]:
                    file_info["category"] = "person"
                elif "/scene/" in file_info["key"]:
                    file_info["category"] = "scene"
                else:
                    file_info["category"] = "unknown"

                all_images.append(file_info)

        return all_images

    def get_file_url(self, object_key: str) -> Optional[str]:
        """
        获取文件的公网访问 URL

        Args:
            object_key: OSS 对象键

        Returns:
            公网 URL
        """
        if not self.is_available():
            return None

        return f"https://{self._endpoint_full}/{object_key}"

    def get_bucket(self):
        """
        获取 OSS Bucket 对象

        Returns:
            (bucket, endpoint_full) 或 (None, None)
        """
        try:
            self._init_oss()
            return self._bucket, self._endpoint_full
        except Exception:
            return None, None


# 全局 OSS 服务实例
oss_service = OSSService()
