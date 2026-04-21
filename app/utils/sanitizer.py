"""
敏感数据脱敏工具模块
用于操作日志记录时对敏感字段进行脱敏处理
"""

from __future__ import annotations

import json
from typing import Any


# 需要脱敏的字段名（不区分大小写）
SENSITIVE_FIELDS = {
    'password', 'password_hash', 'pwd', 'passwd',
    'api_key', 'apikey', 'api_token', 'token', 'access_token',
    'refresh_token', 'secret', 'secret_key', 'authorization',
    'credential', 'credentials', 'auth', 'private_key',
}

# 需要跳过日志记录的路径前缀
SKIP_LOG_PATHS = {
    '/static/',
    '/favicon.ico',
    '/health',
    '/api/health',
}

# 参数截断长度
MAX_PARAM_LENGTH = 500


def should_skip_logging(path: str) -> bool:
    """检查是否应跳过日志记录"""
    for skip_path in SKIP_LOG_PATHS:
        if path.startswith(skip_path):
            return True
    return False


def sanitize_request_params(params: dict | Any | None, max_length: int = MAX_PARAM_LENGTH) -> dict:
    """
    脱敏请求参数

    Args:
        params: 请求参数（可能是dict、list或其他类型）
        max_length: 字符串截断长度

    Returns:
        脱敏后的参数字典
    """
    if params is None:
        return {}

    # 非字典类型，包装为字典
    if not isinstance(params, dict):
        return {'value': _sanitize_value(params, max_length)}

    sanitized = {}
    for key, value in params.items():
        key_lower = key.lower() if isinstance(key, str) else str(key).lower()
        if key_lower in SENSITIVE_FIELDS:
            sanitized[key] = '***REDACTED***'
        else:
            sanitized[key] = _sanitize_value(value, max_length)

    return sanitized


def _sanitize_value(value: Any, max_length: int) -> Any:
    """对单个值进行脱敏处理"""
    if isinstance(value, dict):
        return sanitize_request_params(value, max_length)
    elif isinstance(value, list):
        return [_sanitize_value(item, max_length) for item in value]
    elif isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + '...<truncated>'
        return value
    else:
        return value


def extract_response_summary(response) -> str:
    """
    提取响应摘要

    Args:
        response: Flask响应对象

    Returns:
        响应摘要字符串
    """
    try:
        content_type = (response.headers.get('Content-Type') or '').lower()

        # 非JSON响应，返回类型标识
        if 'application/json' not in content_type:
            if 'text/html' in content_type:
                return '<html>'
            elif 'image/' in content_type:
                return '<image>'
            elif 'video/' in content_type:
                return '<video>'
            return f'<{content_type or "unknown"}>'

        # 解析JSON响应
        body = response.get_data(as_text=True)
        data = json.loads(body)

        if isinstance(data, dict):
            if data.get('success'):
                return data.get('message', 'success') or 'success'
            else:
                return data.get('error', 'unknown error') or 'error'
        else:
            return f'<json: {type(data).__name__}>'

    except Exception:
        return '<unavailable>'