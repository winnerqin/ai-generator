"""
操作日志服务模块

提供详细的操作日志记录功能，包括：
- 用户请求与响应
- API调用参数与响应内容
- OSS操作记录
- 外部服务调用记录

日志文件按天分隔，时间精确到毫秒
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)

# 日志目录
_log_dir: Path | None = None

# 线程锁，确保文件写入安全
_file_lock = threading.Lock()


def _ensure_log_dir() -> Path:
    """确保日志目录存在"""
    global _log_dir
    if _log_dir is None:
        _log_dir = Path(config.OPERATION_LOG_DIR)
        _log_dir.mkdir(parents=True, exist_ok=True)
    return _log_dir


def _get_timestamp_ms() -> str:
    """获取精确到毫秒的时间戳"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _truncate_content(content: Any, max_length: int = 2000) -> Any:
    """截断内容以避免日志过大"""
    if isinstance(content, str):
        if len(content) > max_length:
            return content[:max_length] + f"...<truncated {len(content) - max_length} chars>"
        return content
    elif isinstance(content, dict):
        return {k: _truncate_content(v, max_length) for k, v in content.items()}
    elif isinstance(content, list):
        if len(content) > 20:
            truncated = content[:20]
            return [_truncate_content(item, max_length) for item in truncated] + [f"...<truncated {len(content) - 20} items>"]
        return [_truncate_content(item, max_length) for item in content]
    return content


def _sanitize_sensitive_data(data: dict) -> dict:
    """脱敏敏感数据"""
    sensitive_keys = {
        'password', 'password_hash', 'pwd', 'passwd',
        'api_key', 'apikey', 'api_token', 'token', 'access_token',
        'refresh_token', 'secret', 'secret_key', 'authorization',
        'credential', 'credentials', 'auth', 'private_key',
        'oss_access_key_id', 'oss_access_key_secret',
        'volcengine_ak', 'volcengine_sk',
        'ark_api_key', 'ark_intl_api_key',
        'video_enhance_api_key',
    }

    sanitized = {}
    for key, value in data.items():
        key_lower = str(key).lower()
        if key_lower in sensitive_keys:
            sanitized[key] = '***REDACTED***'
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_sensitive_data(value)
        else:
            sanitized[key] = value
    return sanitized


def _write_log_line(log_data: dict) -> None:
    """写入一行日志到文件"""
    try:
        log_dir = _ensure_log_dir()
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"operation_{today}.log"

        # 添加毫秒级时间戳
        timestamp = _get_timestamp_ms()

        # 脱敏处理
        if "request_params" in log_data:
            log_data["request_params"] = _sanitize_sensitive_data(log_data["request_params"])
        if "response_data" in log_data:
            log_data["response_data"] = _sanitize_sensitive_data(log_data["response_data"])

        # 截断长内容
        log_data = _truncate_content(log_data)

        # 构建有序字典，确保时间戳在第一列
        ordered_log_data = {"timestamp": timestamp}
        for key, value in log_data.items():
            ordered_log_data[key] = value

        # 写入JSON格式的日志
        log_line = json.dumps(ordered_log_data, ensure_ascii=False)

        with _file_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
    except Exception as e:
        logger.warning("[operation_log] file write failed: %s", e)


def log_api_request(
    *,
    user_id: int | None = None,
    username: str | None = None,
    project_id: int | None = None,
    request_path: str,
    request_method: str,
    request_params: dict | None = None,
    request_headers: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """
    记录API请求开始

    Args:
        user_id: 用户ID
        username: 用户名
        project_id: 项目ID
        request_path: 请求路径
        request_method: 请求方法
        request_params: 请求参数
        request_headers: 请求头
        ip_address: IP地址
    """
    log_data = {
        "log_type": "api_request",
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
        "request_path": request_path,
        "request_method": request_method,
        "request_params": request_params or {},
        "request_headers": request_headers or {},
        "ip_address": ip_address,
    }
    _write_log_line(log_data)


def log_api_response(
    *,
    user_id: int | None = None,
    username: str | None = None,
    project_id: int | None = None,
    request_path: str,
    request_method: str,
    request_params: dict | None = None,
    response_status: int,
    response_data: dict | Any | None = None,
    duration_ms: int,
    ip_address: str | None = None,
    error: str | None = None,
) -> None:
    """
    记录API响应

    Args:
        user_id: 用户ID
        username: 用户名
        project_id: 项目ID
        request_path: 请求路径
        request_method: 请求方法
        request_params: 请求参数
        response_status: 响应状态码
        response_data: 响应数据
        duration_ms: 耗时（毫秒）
        ip_address: IP地址
        error: 错误信息
    """
    log_data = {
        "log_type": "api_response",
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
        "request_path": request_path,
        "request_method": request_method,
        "request_params": request_params or {},
        "response_status": response_status,
        "response_data": response_data,
        "duration_ms": duration_ms,
        "ip_address": ip_address,
        "error": error,
    }
    _write_log_line(log_data)


def log_oss_operation(
    *,
    user_id: int | None = None,
    username: str | None = None,
    project_id: int | None = None,
    operation: str,
    file_path: str | None = None,
    object_key: str | None = None,
    file_type: str | None = None,
    file_size: int | None = None,
    result_url: str | None = None,
    success: bool,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """
    记录OSS操作

    Args:
        user_id: 用户ID
        username: 用户名
        project_id: 项目ID
        operation: 操作类型 (upload, delete, list, check_exists)
        file_path: 本地文件路径
        object_key: OSS对象键
        file_type: 文件类型
        file_size: 文件大小
        result_url: 结果URL
        success: 是否成功
        duration_ms: 耗时（毫秒）
        error: 错误信息
    """
    log_data = {
        "log_type": "oss_operation",
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
        "operation": operation,
        "file_path": file_path,
        "object_key": object_key,
        "file_type": file_type,
        "file_size": file_size,
        "result_url": result_url,
        "success": success,
        "duration_ms": duration_ms,
        "error": error,
    }
    _write_log_line(log_data)


def log_external_api_call(
    *,
    user_id: int | None = None,
    username: str | None = None,
    project_id: int | None = None,
    service_name: str,
    api_endpoint: str,
    request_method: str,
    request_payload: dict | None = None,
    response_status: int | None = None,
    response_data: dict | Any | None = None,
    task_id: str | None = None,
    duration_ms: int | None = None,
    success: bool,
    error: str | None = None,
) -> None:
    """
    记录外部API调用

    Args:
        user_id: 用户ID
        username: 用户名
        project_id: 项目ID
        service_name: 服务名称 (seedance, video_enhance, etc.)
        api_endpoint: API端点
        request_method: 请求方法
        request_payload: 请求数据
        response_status: 响应状态码
        response_data: 响应数据
        task_id: 任务ID
        duration_ms: 耗时（毫秒）
        success: 是否成功
        error: 错误信息
    """
    log_data = {
        "log_type": "external_api_call",
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
        "service_name": service_name,
        "api_endpoint": api_endpoint,
        "request_method": request_method,
        "request_payload": request_payload or {},
        "response_status": response_status,
        "response_data": response_data,
        "task_id": task_id,
        "duration_ms": duration_ms,
        "success": success,
        "error": error,
    }
    _write_log_line(log_data)


def log_task_operation(
    *,
    user_id: int | None = None,
    username: str | None = None,
    project_id: int | None = None,
    task_type: str,
    task_id: str | None = None,
    operation: str,
    task_status: str | None = None,
    task_data: dict | None = None,
    success: bool,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """
    记录任务操作

    Args:
        user_id: 用户ID
        username: 用户名
        project_id: 项目ID
        task_type: 任务类型 (omni_video, video_enhance, etc.)
        task_id: 任务ID
        operation: 操作类型 (create, query, cancel, delete, sync)
        task_status: 任务状态
        task_data: 任务数据
        success: 是否成功
        duration_ms: 耗时（毫秒）
        error: 错误信息
    """
    log_data = {
        "log_type": "task_operation",
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
        "task_type": task_type,
        "task_id": task_id,
        "operation": operation,
        "task_status": task_status,
        "task_data": task_data or {},
        "success": success,
        "duration_ms": duration_ms,
        "error": error,
    }
    _write_log_line(log_data)


def log_video_download(
    *,
    user_id: int | None = None,
    username: str | None = None,
    project_id: int | None = None,
    source_url: str,
    target_path: str | None = None,
    oss_url: str | None = None,
    file_size: int | None = None,
    success: bool,
    is_expired: bool = False,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """
    记录视频下载与OSS上传

    Args:
        user_id: 用户ID
        username: 用户名
        project_id: 项目ID
        source_url: 源URL
        target_path: 目标路径
        oss_url: OSS URL
        file_size: 文件大小
        success: 是否成功
        is_expired: URL是否过期
        duration_ms: 耗时（毫秒）
        error: 错误信息
    """
    log_data = {
        "log_type": "video_download",
        "user_id": user_id,
        "username": username,
        "project_id": project_id,
        "source_url": source_url,
        "target_path": target_path,
        "oss_url": oss_url,
        "file_size": file_size,
        "success": success,
        "is_expired": is_expired,
        "duration_ms": duration_ms,
        "error": error,
    }
    _write_log_line(log_data)


def log_balance_query(
    *,
    user_id: int | None = None,
    username: str | None = None,
    service_name: str,
    available_balance: float | None = None,
    total_balance: float | None = None,
    success: bool,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """
    记录余额查询

    Args:
        user_id: 用户ID
        username: 用户名
        service_name: 服务名称
        available_balance: 可用余额
        total_balance: 总余额
        success: 是否成功
        duration_ms: 耗时（毫秒）
        error: 错误信息
    """
    log_data = {
        "log_type": "balance_query",
        "user_id": user_id,
        "username": username,
        "service_name": service_name,
        "available_balance": available_balance,
        "total_balance": total_balance,
        "success": success,
        "duration_ms": duration_ms,
        "error": error,
    }
    _write_log_line(log_data)


# 全局操作日志服务实例
operation_log_service = None


def get_operation_log_service():
    """获取操作日志服务实例"""
    global operation_log_service
    if operation_log_service is None:
        operation_log_service = OperationLogService()
    return operation_log_service


class OperationLogService:
    """操作日志服务类，提供便捷的日志记录方法"""

    def log_api_request(self, **kwargs) -> None:
        """记录API请求"""
        log_api_request(**kwargs)

    def log_api_response(self, **kwargs) -> None:
        """记录API响应"""
        log_api_response(**kwargs)

    def log_oss_operation(self, **kwargs) -> None:
        """记录OSS操作"""
        log_oss_operation(**kwargs)

    def log_external_api_call(self, **kwargs) -> None:
        """记录外部API调用"""
        log_external_api_call(**kwargs)

    def log_task_operation(self, **kwargs) -> None:
        """记录任务操作"""
        log_task_operation(**kwargs)

    def log_video_download(self, **kwargs) -> None:
        """记录视频下载"""
        log_video_download(**kwargs)

    def log_balance_query(self, **kwargs) -> None:
        """记录余额查询"""
        log_balance_query(**kwargs)