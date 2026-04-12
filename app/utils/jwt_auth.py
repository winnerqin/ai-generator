"""JWT authentication helpers."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from functools import wraps
from typing import Callable, Optional

from flask import jsonify
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    verify_jwt_in_request,
)
from flask_jwt_extended.exceptions import JWTExtendedException

jwt = JWTManager()


class JWTConfig:
    ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SECRET_KEY: str = "jwt-secret-key-change-in-production"
    ALGORITHM = "HS256"
    BLACKLIST_ENABLED = False


class JWTAuth:
    """JWT utility methods."""

    @staticmethod
    def init_app(app) -> None:
        secret_key = os.environ.get("JWT_SECRET_KEY", JWTConfig.SECRET_KEY)

        app.config.setdefault("JWT_SECRET_KEY", secret_key)
        app.config.setdefault("JWT_ACCESS_TOKEN_EXPIRES", JWTConfig.ACCESS_TOKEN_EXPIRES)
        app.config.setdefault("JWT_REFRESH_TOKEN_EXPIRES", JWTConfig.REFRESH_TOKEN_EXPIRES)
        app.config.setdefault("JWT_ALGORITHM", JWTConfig.ALGORITHM)
        app.config.setdefault("JWT_BLACKLIST_ENABLED", JWTConfig.BLACKLIST_ENABLED)
        app.config.setdefault("JWT_ERROR_MESSAGE_KEY", "error")

        jwt.init_app(app)

        @jwt.user_identity_loader
        def user_identity_lookup(user):
            if isinstance(user, dict):
                return json.dumps(user)
            return str(user)

        @jwt.user_lookup_loader
        def user_lookup_callback(_jwt_header, jwt_data):
            identity = jwt_data.get("sub", "{}")
            if isinstance(identity, dict):
                return identity
            try:
                return json.loads(identity)
            except (json.JSONDecodeError, TypeError):
                return {"user_id": identity, "username": str(identity)}

        @jwt.expired_token_loader
        def expired_token_callback(_jwt_header, _jwt_payload):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Token \u5df2\u8fc7\u671f",
                        "code": 401,
                    }
                ),
                401,
            )

        @jwt.invalid_token_loader
        def invalid_token_callback(_error):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "\u65e0\u6548\u7684 Token",
                        "code": 401,
                    }
                ),
                401,
            )

        @jwt.unauthorized_loader
        def missing_token_callback(_error):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "\u7f3a\u5c11\u8ba4\u8bc1 Token",
                        "code": 401,
                    }
                ),
                401,
            )

        @jwt.revoked_token_loader
        def revoked_token_callback(_jwt_header, _jwt_payload):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Token \u5df2\u64a4\u9500",
                        "code": 401,
                    }
                ),
                401,
            )

    @staticmethod
    def generate_tokens(user_id: int, username: str, **extra_claims) -> dict[str, object]:
        identity = {"user_id": user_id, "username": username, **extra_claims}
        access_token = create_access_token(identity=identity)
        refresh_token = create_refresh_token(identity=identity)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": int(JWTConfig.ACCESS_TOKEN_EXPIRES.total_seconds()),
        }

    @staticmethod
    def refresh_access_token() -> str:
        verify_jwt_in_request(refresh=True)
        identity = get_jwt_identity()
        return create_access_token(identity=identity)

    @staticmethod
    def get_current_user() -> Optional[dict]:
        try:
            verify_jwt_in_request()
            identity = get_jwt_identity()
            if isinstance(identity, str):
                try:
                    return json.loads(identity)
                except json.JSONDecodeError:
                    return {"user_id": identity, "username": str(identity)}
            return identity
        except JWTExtendedException:
            return None

    @staticmethod
    def get_current_user_id() -> Optional[int]:
        user = JWTAuth.get_current_user()
        return user.get("user_id") if user else None


def jwt_required(optional: bool = False) -> Callable:
    """App-level JWT decorator with optional access support."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request(optional=optional)
                return fn(*args, **kwargs)
            except JWTExtendedException:
                if optional:
                    return fn(*args, **kwargs)
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "\u672a\u6388\u6743\u8bbf\u95ee",
                            "code": 401,
                        }
                    ),
                    401,
                )

        return wrapper

    return decorator


def jwt_optional(fn: Callable) -> Callable:
    """Shortcut for ``@jwt_required(optional=True)``."""

    return jwt_required(optional=True)(fn)
