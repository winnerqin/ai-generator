"""
工具函数模块
"""

from app.utils.response import ApiResponse, ErrorCode, handle_response

# 为了向后兼容，提供 paginated 别名
paginated = ApiResponse.paginated

__all__ = ["ApiResponse", "handle_response", "ErrorCode", "paginated"]
