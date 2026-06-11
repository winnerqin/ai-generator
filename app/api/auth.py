"""
认证相关 API
"""

import json
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_jwt_extended import jwt_required

import database
from app.decorators import login_required
from app.services.payment_service import payment_service
from app.utils import ApiResponse
from app.utils.jwt_auth import JWTAuth

# 创建蓝图
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """用户登录"""
    if request.method == "GET":
        return render_template("login.html")

    username = (
        request.form.get("username", "").strip()
        if not request.is_json
        else request.json.get("username", "").strip()
    )
    password = (
        request.form.get("password", "")
        if not request.is_json
        else request.json.get("password", "")
    )

    if not username or not password:
        if request.is_json:
            return ApiResponse.bad_request("用户名和密码不能为空")
        return render_template("login.html", error="用户名和密码不能为空")

    # 验证用户
    user = database.verify_user(username, password)
    if not user:
        if request.is_json:
            return ApiResponse.unauthorized("用户名或密码错误")
        return render_template("login.html", password_error=True, username=username)

    user_id = user.get("id")

    # 设置会话
    session["user_id"] = user_id
    session["username"] = username
    session["role_code"] = user.get("role_code")
    session.permanent = True

    # 确保用户有项目
    projects = database.get_user_projects(user_id)
    if projects:
        session["current_project_id"] = projects[0].get("id")
        session["current_project_name"] = projects[0].get("name")

    # 返回 JSON 或重定向
    if request.is_json:
        return ApiResponse.success({"user_id": user_id, "username": username}, "登录成功")
    return redirect(url_for("index"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """用户注册（暂时禁用）"""
    return ApiResponse.error("注册功能已禁用，请联系管理员创建账号", 403)


@auth_bp.route("/logout")
@login_required
def logout():
    """用户登出"""
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def get_current_user():
    """获取当前用户信息"""
    user_id = session.get("user_id")
    username = session.get("username")
    project_id = session.get("current_project_id")

    # 获取用户信息
    database.get_user_by_id(user_id)

    return ApiResponse.success(
        {
            "id": user_id,
            "username": username,
            "role_code": session.get("role_code"),
            "project_id": project_id,
            "is_system_admin": session.get("role_code") == database.ROLE_SYSTEM_ADMIN,
        }
    )


@auth_bp.route("/api/me/menu-permissions", methods=["GET"])
@login_required
def get_my_menu_permissions():
    role_code = session.get("role_code") or database.ROLE_EXTERNAL_USER
    return ApiResponse.success(
        {
            "role_code": role_code,
            "menu_keys": database.get_user_menu_permissions(role_code),
        }
    )


# ========== JWT 认证端点 ==========


@auth_bp.route("/api/auth/login", methods=["POST"])
def jwt_login():
    """
    JWT 登录接口

    请求体:
        {
            "username": "用户名",
            "password": "密码"
        }

    响应:
        {
            "success": true,
            "data": {
                "access_token": "访问令牌",
                "refresh_token": "刷新令牌",
                "token_type": "bearer",
                "expires_in": 86400,
                "user": {
                    "id": 1,
                    "username": "用户名"
                }
            }
        }
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return ApiResponse.bad_request("用户名和密码不能为空")

    # 验证用户
    user = database.verify_user(username, password)
    if not user:
        return ApiResponse.unauthorized("用户名或密码错误")

    user_id = user.get("id")

    # 生成 JWT tokens
    tokens = JWTAuth.generate_tokens(user_id=user_id, username=username)

    return ApiResponse.success(
        {
            **tokens,
            "user": {"id": user_id, "username": username},
        },
        "登录成功",
    )


@auth_bp.route("/api/auth/refresh", methods=["POST"])
def jwt_refresh():
    """
    刷新 JWT 访问令牌

    请求头:
        Authorization: Bearer <refresh_token>

    响应:
        {
            "success": true,
            "data": {
                "access_token": "新的访问令牌",
                "token_type": "bearer"
            }
        }
    """
    import json

    from flask_jwt_extended import create_access_token, get_jwt_identity

    @jwt_required(refresh=True)
    def do_refresh():
        identity = get_jwt_identity()
        # 如果身份是字符串，尝试解析为 JSON
        if isinstance(identity, str):
            try:
                identity = json.loads(identity)
            except json.JSONDecodeError:
                pass

        access_token = create_access_token(identity=identity)
        return ApiResponse.success(
            {
                "access_token": access_token,
                "token_type": "bearer",
            },
            "令牌刷新成功",
        )

    return do_refresh()


@auth_bp.route("/api/auth/me", methods=["GET"])
@jwt_required()
def jwt_me():
    """
    获取当前 JWT 认证用户信息

    请求头:
        Authorization: Bearer <access_token>

    响应:
        {
            "success": true,
            "data": {
                "id": 1,
                "username": "用户名"
            }
        }
    """
    import json

    from flask_jwt_extended import get_jwt_identity

    current_user = get_jwt_identity()
    # 如果身份是字符串，尝试解析为 JSON
    if isinstance(current_user, str):
        try:
            current_user = json.loads(current_user)
        except json.JSONDecodeError:
            pass
    return ApiResponse.success(current_user)


@auth_bp.route("/api/user/profile", methods=["GET"])
@login_required
def get_user_profile():
    user = database.get_user_by_id(session.get("user_id"))
    if not user:
        return ApiResponse.not_found("用户不存在")
    return ApiResponse.success(
        {
            "id": user.get("id"),
            "username": user.get("username"),
            "role_code": user.get("role_code"),
            "status": user.get("status"),
            "balance_cent": user.get("balance_cent", 0),
            "pricing_multiplier": user.get("pricing_multiplier", 1.0),
        }
    )


def _current_recharge_user():
    user = database.get_user_by_id(session.get("user_id"))
    if not user:
        raise ValueError("用户不存在")
    if user.get("role_code") != database.ROLE_EXTERNAL_USER:
        raise PermissionError("当前仅外部用户支持自助充值")
    return user


def _serialize_recharge_order(order):
    if not order:
        return None
    return {
        "order_no": order.get("order_no"),
        "amount_cent": int(order.get("amount_cent") or 0),
        "amount_yuan": f"{(int(order.get('amount_cent') or 0) / 100):.2f}",
        "currency_code": order.get("currency_code") or database.MODEL_CURRENCY_CNY,
        "status": order.get("status"),
        "payment_channel": order.get("payment_channel") or "wechat_native",
        "payment_center_order_no": order.get("payment_center_order_no") or "",
        "channel_trade_no": order.get("channel_trade_no") or "",
        "qr_code_url": order.get("qr_code_url") or "",
        "qr_code_img_url": order.get("qr_code_img_url") or "",
        "expire_at": order.get("expire_at"),
        "paid_at": order.get("paid_at"),
        "closed_at": order.get("closed_at"),
        "fail_reason": order.get("fail_reason") or "",
        "created_at": order.get("created_at"),
        "updated_at": order.get("updated_at"),
    }


@auth_bp.route("/api/user/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")
    if not old_password or not new_password or not confirm_password:
        return ApiResponse.bad_request("请完整填写密码信息")
    if new_password != confirm_password:
        return ApiResponse.bad_request("两次输入的新密码不一致")
    if len(new_password) < 6:
        return ApiResponse.bad_request("密码至少6个字符")
    current = database.verify_user(session.get("username"), old_password)
    if not current:
        return ApiResponse.bad_request("旧密码错误")
    database.update_user_password(session.get("user_id"), new_password)
    return ApiResponse.success(message="密码修改成功")


def _display_tokens_for_ledger_item(item):
    tokens_raw = item.get("tokens_raw")
    multiplier = item.get("multiplier")
    if tokens_raw not in (None, "") and multiplier not in (None, ""):
        value = Decimal(str(tokens_raw)) * Decimal(str(multiplier))
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return item.get("tokens_billed") or tokens_raw


def _pricing_by_model_code():
    pricings = database.get_model_pricing_list(enabled=True)
    result = {}
    for pricing in pricings:
        model_code = pricing.get("model_code")
        if model_code and model_code not in result:
            result[model_code] = pricing
    return result


def _attach_consumption_display_fields(items):
    pricing_map = _pricing_by_model_code()
    for item in items:
        item["display_tokens"] = _display_tokens_for_ledger_item(item)
        pricing = pricing_map.get(item.get("model_code"))
        if not pricing and item.get("snapshot_json"):
            try:
                snapshot = json.loads(item.get("snapshot_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                snapshot = {}
            if snapshot.get("price_per_million_token_cent"):
                pricing = {
                    "currency_code": snapshot.get("currency_code") or database.MODEL_CURRENCY_CNY,
                    "price_per_million_token_cent": snapshot.get("price_per_million_token_cent"),
                }
        if pricing:
            item["model_price"] = {
                "currency_code": pricing.get("currency_code") or database.MODEL_CURRENCY_CNY,
                "price_per_million_token_cent": pricing.get("price_per_million_token_cent"),
            }
    return items


@auth_bp.route("/api/user/recharge-config", methods=["GET"])
@login_required
def get_recharge_config():
    try:
        user = _current_recharge_user()
    except PermissionError as exc:
        return ApiResponse.forbidden(str(exc))
    del user
    options = payment_service.get_recharge_options()
    options["preset_amounts_yuan"] = [f"{value / 100:.0f}" for value in options["preset_amounts_cent"]]
    options["min_amount_yuan"] = f"{options['min_amount_cent'] / 100:.2f}"
    options["max_amount_yuan"] = f"{options['max_amount_cent'] / 100:.2f}"
    return ApiResponse.success(options)


@auth_bp.route("/api/user/recharge-orders", methods=["POST"])
@login_required
def create_recharge_order():
    try:
        user = _current_recharge_user()
    except PermissionError as exc:
        return ApiResponse.forbidden(str(exc))
    data = request.get_json(silent=True) or {}
    amount_cent = payment_service.normalize_amount_cent(
        amount_yuan=data.get("amount_yuan"), amount_cent=data.get("amount_cent")
    )
    order_no = f"RC{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:10].upper()}"
    metadata = {
        "scene": "user_center",
        "selected_option": data.get("selected_option"),
    }
    order = database.create_recharge_order(
        {
            "order_no": order_no,
            "user_id": user.get("id"),
            "username": user.get("username"),
            "amount_cent": amount_cent,
            "status": "pending",
            "payment_channel": "wechat_native",
            "payment_scene": "user_center",
            "subject": "账户充值",
            "description": f"AI创作工具账户充值 {amount_cent / 100:.2f} 元",
            "metadata_json": metadata,
        }
    )
    try:
        payment_result = payment_service.create_recharge_order(
            order_no=order_no,
            user_id=int(user.get("id")),
            username=user.get("username") or "",
            amount_cent=amount_cent,
            callback_url=payment_service.build_callback_url(request.host_url.rstrip("/")),
            metadata=metadata,
        )
    except Exception as exc:
        order = database.mark_recharge_order_status(
            order_no,
            status="failed",
            fail_reason=str(exc),
        )
        return ApiResponse.server_error(str(exc))

    order = database.update_recharge_order(
        order_no,
        {
            "status": payment_result.get("pay_status") or "paying",
            "payment_center_order_no": payment_result.get("payment_center_order_no"),
            "qr_code_url": payment_result.get("qr_code_url"),
            "qr_code_img_url": payment_result.get("qr_code_img_url"),
            "expire_at": payment_result.get("expire_at"),
            "request_payload_json": payment_result.get("request_payload"),
            "callback_payload_json": payment_result.get("response_payload"),
        },
    )
    return ApiResponse.created({"order": _serialize_recharge_order(order)}, "充值订单已创建")


@auth_bp.route("/api/user/recharge-orders/<order_no>", methods=["GET"])
@login_required
def get_recharge_order_detail(order_no):
    try:
        user = _current_recharge_user()
    except PermissionError as exc:
        return ApiResponse.forbidden(str(exc))
    order = database.get_recharge_order(order_no, user_id=user.get("id"))
    if not order:
        return ApiResponse.not_found("充值订单不存在")
    return ApiResponse.success({"order": _serialize_recharge_order(order)})


@auth_bp.route("/api/user/recharge-orders", methods=["GET"])
@login_required
def list_recharge_orders():
    try:
        user = _current_recharge_user()
    except PermissionError as exc:
        return ApiResponse.forbidden(str(exc))
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    offset = (page - 1) * page_size
    items = database.get_recharge_orders(user.get("id"), limit=page_size, offset=offset)
    total = database.count_recharge_orders(user.get("id"))
    return ApiResponse.paginated(
        [_serialize_recharge_order(item) for item in items],
        total,
        page,
        page_size,
    )


@auth_bp.route("/api/user/recharge-orders/<order_no>/cancel", methods=["POST"])
@login_required
def cancel_recharge_order(order_no):
    try:
        user = _current_recharge_user()
    except PermissionError as exc:
        return ApiResponse.forbidden(str(exc))
    try:
        order = database.cancel_recharge_order(order_no, user.get("id"))
    except ValueError as exc:
        return ApiResponse.bad_request(str(exc))
    return ApiResponse.success({"order": _serialize_recharge_order(order)}, "订单已取消")


@auth_bp.route("/api/payment-center/recharge-callback", methods=["POST"])
def payment_center_recharge_callback():
    payload = request.get_json(silent=True) or {}
    signature = request.headers.get("X-Signature") or payload.get("sign") or ""
    timestamp = request.headers.get("X-Timestamp") or payload.get("timestamp") or ""
    nonce = request.headers.get("X-Nonce") or payload.get("nonce") or ""
    payload_for_sign = {
        key: value
        for key, value in payload.items()
        if key not in {"sign", "timestamp", "nonce"}
    }
    if payment_service.is_configured() and not payment_service.verify_signature(
        payload_for_sign, str(timestamp), str(nonce), str(signature)
    ):
        return ApiResponse.forbidden("回调验签失败")

    order_no = str(payload.get("merchant_order_no") or "").strip()
    if not order_no:
        return ApiResponse.bad_request("缺少 merchant_order_no")
    order = database.get_recharge_order(order_no)
    if not order:
        return ApiResponse.not_found("充值订单不存在")

    amount_cent = int(payload.get("amount_cent") or 0)
    if amount_cent and amount_cent != int(order.get("amount_cent") or 0):
        return ApiResponse.bad_request("回调金额与订单金额不一致")

    status = str(payload.get("status") or "").strip().lower()
    payment_center_order_no = payload.get("payment_center_order_no") or payload.get("order_no")
    channel_trade_no = payload.get("channel_trade_no") or payload.get("transaction_id")
    paid_at = payload.get("paid_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status == "paid":
        order = database.settle_recharge_order_paid(
            order_no,
            payment_center_order_no=payment_center_order_no,
            channel_trade_no=channel_trade_no,
            callback_payload=payload,
            paid_at=paid_at,
        )
        return ApiResponse.success({"order": _serialize_recharge_order(order)}, "ok")

    mapped_status = status if status in {"failed", "closed", "refunded"} else "failed"
    order = database.mark_recharge_order_status(
        order_no,
        status=mapped_status,
        payment_center_order_no=payment_center_order_no,
        channel_trade_no=channel_trade_no,
        fail_reason=payload.get("fail_reason") or payload.get("message") or "",
        callback_payload=payload,
        closed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if mapped_status == "closed"
        else None,
    )
    return ApiResponse.success({"order": _serialize_recharge_order(order)}, "ok")


@auth_bp.route("/api/user/model-pricing", methods=["GET"])
@login_required
def get_user_model_pricing():
    items = database.get_model_pricing_list(enabled=True)
    return ApiResponse.success({"items": items})


@auth_bp.route("/api/user/consumption-records", methods=["GET"])
@login_required
def get_user_consumption_records():
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    offset = (page - 1) * page_size
    items = database.get_user_consumption_records(
        session.get("user_id"),
        limit=page_size,
        offset=offset,
        biz_type="omni_video",
    )
    items = _attach_consumption_display_fields(items)
    total = database.count_account_ledger(
        user_id=session.get("user_id"),
        entry_type="debit",
        biz_type="omni_video",
    )
    return ApiResponse.paginated(items, total, page, page_size)
