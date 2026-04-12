"""Unified API response helpers."""

from __future__ import annotations

from functools import wraps
from typing import Any, Optional

from flask import Response, jsonify


class ApiResponse:
    """Helpers for consistent JSON responses."""

    @staticmethod
    def success(data: Any = None, message: str = "", code: int = 200) -> tuple[Response, int]:
        return jsonify({"success": True, "data": data, "message": message}), code

    @staticmethod
    def error(
        message: str, code: int = 400, details: Optional[dict[str, Any]] = None
    ) -> tuple[Response, int]:
        payload: dict[str, Any] = {"success": False, "error": message, "code": code}
        if details:
            payload["details"] = details
        return jsonify(payload), code

    @staticmethod
    def paginated(
        items: list[Any], total: int, page: int, page_size: int, message: str = ""
    ) -> tuple[Response, int]:
        return (
            jsonify(
                {
                    "success": True,
                    "data": {
                        "items": items,
                        "pagination": {
                            "total": total,
                            "page": page,
                            "page_size": page_size,
                            "total_pages": (total + page_size - 1) // page_size,
                        },
                    },
                    "message": message,
                }
            ),
            200,
        )

    @staticmethod
    def created(
        data: Any = None, message: str = "\u521b\u5efa\u6210\u529f"
    ) -> tuple[Response, int]:
        return ApiResponse.success(data, message, 201)

    @staticmethod
    def no_content(message: str = "\u64cd\u4f5c\u6210\u529f") -> tuple[str, int]:
        del message
        return "", 204

    @staticmethod
    def bad_request(
        message: str = "\u8bf7\u6c42\u53c2\u6570\u9519\u8bef",
        details: Optional[dict[str, Any]] = None,
    ) -> tuple[Response, int]:
        return ApiResponse.error(message, 400, details)

    @staticmethod
    def unauthorized(
        message: str = "\u672a\u6388\u6743\uff0c\u8bf7\u5148\u767b\u5f55"
    ) -> tuple[Response, int]:
        return ApiResponse.error(message, 401)

    @staticmethod
    def forbidden(
        message: str = "\u65e0\u6743\u9650\u8bbf\u95ee\u8be5\u8d44\u6e90"
    ) -> tuple[Response, int]:
        return ApiResponse.error(message, 403)

    @staticmethod
    def not_found(
        message: str = "\u8bf7\u6c42\u7684\u8d44\u6e90\u4e0d\u5b58\u5728"
    ) -> tuple[Response, int]:
        return ApiResponse.error(message, 404)

    @staticmethod
    def conflict(message: str = "\u8d44\u6e90\u51b2\u7a81") -> tuple[Response, int]:
        return ApiResponse.error(message, 409)

    @staticmethod
    def server_error(
        message: str = "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef"
    ) -> tuple[Response, int]:
        return ApiResponse.error(message, 500)


def handle_response(func):
    """Normalize common view return shapes into ``ApiResponse`` payloads."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)

            if isinstance(result, tuple) and len(result) == 2:
                if isinstance(result[0], Response):
                    return result
                data, message = result
                return ApiResponse.success(data, message)

            if isinstance(result, dict):
                return ApiResponse.success(result)

            if isinstance(result, str):
                return ApiResponse.error(result)

            if isinstance(result, Response):
                return result

            return ApiResponse.success(result)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            return ApiResponse.server_error(str(exc))

    return wrapper


class ErrorCode:
    """Application error code constants."""

    SUCCESS = 0
    UNKNOWN_ERROR = 1000
    INVALID_PARAMS = 1001
    MISSING_REQUIRED_PARAM = 1002

    UNAUTHORIZED = 2001
    INVALID_TOKEN = 2002
    TOKEN_EXPIRED = 2003
    PERMISSION_DENIED = 2004

    USER_NOT_FOUND = 3001
    USER_ALREADY_EXISTS = 3002
    INVALID_PASSWORD = 3003
    INVALID_USERNAME = 3004

    PROJECT_NOT_FOUND = 4001
    PROJECT_ALREADY_EXISTS = 4002

    GENERATION_FAILED = 5001
    TASK_NOT_FOUND = 5002
    TASK_TIMEOUT = 5003
    TASK_CANCELLED = 5004

    FILE_NOT_FOUND = 6001
    INVALID_FILE_TYPE = 6002
    FILE_TOO_LARGE = 6003
    FILE_UPLOAD_FAILED = 6004

    API_CALL_FAILED = 7001
    API_RATE_LIMIT = 7002
    API_INVALID_KEY = 7003
    API_QUOTA_EXCEEDED = 7004
