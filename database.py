"""
数据库模型 - 存储图片生成记录和用户信息
"""

import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from db_adapter import IntegrityError, connect, initialize_mysql_schema

load_dotenv()

ROLE_SYSTEM_ADMIN = "system_admin"
ROLE_INTERNAL_USER = "internal_user"
ROLE_EXTERNAL_USER = "external_user"
MODEL_CURRENCY_CNY = "CNY"
MODEL_CURRENCY_USD = "USD"
USD_TO_CNY_RATE = 7
REFERENCE_VIDEO_MODE_ANY = "any"
REFERENCE_VIDEO_MODE_WITH = "with_video_ref"
REFERENCE_VIDEO_MODE_WITHOUT = "without_video_ref"

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"

MENU_DEFINITIONS = [
    {"key": "index", "label": "单图生成"},
    {"key": "batch", "label": "批量生成"},
    {"key": "records", "label": "生图任务"},
    {"key": "video_generate", "label": "视频生成"},
    {"key": "video_tasks", "label": "视频任务"},
    {"key": "omni_video", "label": "全能视频"},
    {"key": "omni_video_tasks", "label": "全能任务"},
    {"key": "enhance_tasks", "label": "增强任务"},
    {"key": "script_generate", "label": "剧本生成"},
    {"key": "storyboard_studio", "label": "分镜制作"},
    {"key": "txt2csv", "label": "转换工具"},
    {"key": "content_management", "label": "内容管理"},
    {"key": "user_center", "label": "用户中心"},
    {"key": "admin", "label": "系统管理"},
    {"key": "role_management", "label": "角色管理"},
    {"key": "stats", "label": "系统统计"},
]

DEFAULT_ROLE_DEFINITIONS = [
    {
        "code": ROLE_SYSTEM_ADMIN,
        "name": "系统管理员",
        "menu_keys": [item["key"] for item in MENU_DEFINITIONS],
        "pricing_multiplier": 1.0,
        "built_in": True,
    },
    {
        "code": ROLE_INTERNAL_USER,
        "name": "内部用户",
        "menu_keys": [
            "index",
            "batch",
            "records",
            "video_generate",
            "video_tasks",
            "omni_video",
            "omni_video_tasks",
            "enhance_tasks",
            "script_generate",
            "storyboard_studio",
            "txt2csv",
            "content_management",
            "user_center",
        ],
        "pricing_multiplier": 1.0,
        "built_in": True,
    },
    {
        "code": ROLE_EXTERNAL_USER,
        "name": "外部用户",
        "menu_keys": [
            "index",
            "records",
            "omni_video",
            "omni_video_tasks",
            "user_center",
        ],
        "pricing_multiplier": 1.0,
        "built_in": True,
    },
]


def ensure_media_library_tables():
    """Ensure MySQL media library tables exist."""
    initialize_mysql_schema()


def _ensure_users_extended_columns():
    """Backfill users table columns for older databases."""
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM users")
        existing = {str(row["Field"]).lower() for row in cursor.fetchall()}

        alters = []
        if "role_code" not in existing:
            alters.append(
                "ALTER TABLE users ADD COLUMN role_code VARCHAR(32) NOT NULL DEFAULT 'external_user'"
            )
        if "status" not in existing:
            alters.append(
                "ALTER TABLE users ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active'"
            )
        if "balance_cent" not in existing:
            alters.append("ALTER TABLE users ADD COLUMN balance_cent BIGINT NOT NULL DEFAULT 0")
        if "pricing_multiplier" not in existing:
            alters.append(
                "ALTER TABLE users ADD COLUMN pricing_multiplier DECIMAL(10,4) NOT NULL DEFAULT 1.0000"
            )
        if "updated_at" not in existing:
            alters.append(
                "ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            )

        for sql in alters:
            try:
                cursor.execute(sql)
            except Exception:
                # Some deployed DB accounts may not have ALTER privilege.
                # In that case we keep runtime compatibility fallbacks.
                pass

        conn.commit()
    finally:
        conn.close()


def _ensure_model_pricing_columns():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM model_pricing")
        existing = {str(row["Field"]).lower() for row in cursor.fetchall()}
        alters = []
        if "currency_code" not in existing:
            alters.append(
                "ALTER TABLE model_pricing ADD COLUMN currency_code VARCHAR(8) NOT NULL DEFAULT 'CNY'"
            )
        if "resolution_code" not in existing:
            alters.append(
                "ALTER TABLE model_pricing ADD COLUMN resolution_code VARCHAR(16) NOT NULL DEFAULT ''"
            )
        if "reference_video_mode" not in existing:
            alters.append(
                "ALTER TABLE model_pricing ADD COLUMN reference_video_mode VARCHAR(32) NOT NULL DEFAULT 'any'"
            )
        for sql in alters:
            try:
                cursor.execute(sql)
            except Exception:
                pass
        # Ensure column length is enough for value "without_video_ref".
        try:
            cursor.execute(
                "ALTER TABLE model_pricing MODIFY COLUMN reference_video_mode VARCHAR(32) NOT NULL DEFAULT 'any'"
            )
        except Exception:
            pass
        # Drop legacy unique index on model_code so one model can have multiple pricing rules.
        try:
            cursor.execute("SHOW INDEX FROM model_pricing")
            index_rows = cursor.fetchall()
            unique_model_indexes = []
            for row in index_rows:
                if int(row["Non_unique"]) == 0 and str(row["Column_name"]).lower() == "model_code":
                    key_name = str(row["Key_name"])
                    if key_name != "PRIMARY":
                        unique_model_indexes.append(key_name)
            for key_name in sorted(set(unique_model_indexes)):
                try:
                    cursor.execute(f"ALTER TABLE model_pricing DROP INDEX `{key_name}`")
                except Exception:
                    pass
            if not any(str(row["Key_name"]) == "uk_model_pricing_rule" for row in index_rows):
                try:
                    cursor.execute(
                        "ALTER TABLE model_pricing ADD UNIQUE KEY uk_model_pricing_rule (model_code, currency_code, resolution_code, reference_video_mode)"
                    )
                except Exception:
                    pass
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()


def _get_user_table_columns():
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM users")
        return {str(row["Field"]).lower() for row in cursor.fetchall()}
    finally:
        conn.close()


def init_database():
    """初始化 MySQL 数据库"""
    initialize_mysql_schema()
    _ensure_users_extended_columns()
    _ensure_model_pricing_columns()
    print("数据库初始化完成: MySQL")


def _role_menu_config_path() -> Path:
    return Path(__file__).parent / "config" / "role_definitions.json"


def _normalize_role_definitions(raw):
    all_menu_keys = {item["key"] for item in MENU_DEFINITIONS}
    normalized = []
    if not isinstance(raw, list):
        raw = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        menu_keys = item.get("menu_keys")
        if not isinstance(menu_keys, list):
            menu_keys = []
        menu_keys = [str(k) for k in menu_keys if str(k) in all_menu_keys]
        try:
            multiplier = float(item.get("pricing_multiplier", 1.0))
        except (TypeError, ValueError):
            multiplier = 1.0
        normalized.append(
            {
                "code": code,
                "name": str(item.get("name") or code),
                "menu_keys": menu_keys,
                "pricing_multiplier": max(multiplier, 0.0001),
                "built_in": bool(item.get("built_in", False)),
            }
        )
    return normalized


def get_role_definitions():
    defaults = [dict(x) for x in DEFAULT_ROLE_DEFINITIONS]
    path = _role_menu_config_path()
    if not path.exists():
        return defaults
    try:
        loaded = _normalize_role_definitions(json.loads(path.read_text(encoding="utf-8")))
        by_code = {r["code"]: r for r in loaded}
        # Ensure built-in roles always exist
        for d in defaults:
            if d["code"] not in by_code:
                by_code[d["code"]] = d
            else:
                by_code[d["code"]]["built_in"] = True
                if not by_code[d["code"]].get("name"):
                    by_code[d["code"]]["name"] = d["name"]
        return list(by_code.values())
    except Exception:
        return defaults


def save_role_definitions(role_definitions):
    normalized = _normalize_role_definitions(role_definitions)
    # always keep built-in roles
    by_code = {r["code"]: r for r in normalized}
    for d in DEFAULT_ROLE_DEFINITIONS:
        if d["code"] not in by_code:
            by_code[d["code"]] = dict(d)
        else:
            by_code[d["code"]]["built_in"] = True
    values = list(by_code.values())
    path = _role_menu_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    return values


def get_role_definition_map():
    return {r["code"]: r for r in get_role_definitions()}


def get_user_menu_permissions(role_code):
    role = role_code or ROLE_EXTERNAL_USER
    role_map = get_role_definition_map()
    fallback = role_map.get(ROLE_EXTERNAL_USER, {"menu_keys": []})
    return list(role_map.get(role, fallback).get("menu_keys", []))


def get_role_pricing_multiplier(role_code):
    role = role_code or ROLE_EXTERNAL_USER
    role_map = get_role_definition_map()
    fallback = role_map.get(ROLE_EXTERNAL_USER, {"pricing_multiplier": 1.0})
    try:
        return float(role_map.get(role, fallback).get("pricing_multiplier", 1.0))
    except (TypeError, ValueError):
        return 1.0


def get_available_role_codes():
    return [r["code"] for r in get_role_definitions()]


def save_generation_record(data):
    """
    保存生成记录

    Args:
        data: dict with keys:
            - user_id (required)
            - prompt, negative_prompt, aspect_ratio, resolution
            - width, height, num_images, seed, steps
            - sample_images (list), image_path, filename
            - batch_id (optional)
            - created_at (optional) - 用于同批次请求归并标识
            - token_usage (optional) - 图片生成消耗的token
    """
    conn = connect()
    cursor = conn.cursor()

    sample_images_json = json.dumps(data.get("sample_images", []))
    # 使用调用方传入的 created_at 作为同批次标识；未传时使用当前时间
    local_time = data.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 防止重复保存相同的 image_path（避免前端/网络重试导致重复记录）
    existing = None
    try:
        cursor.execute(
            "SELECT id FROM generation_records WHERE user_id = ? AND image_path = ? LIMIT 1",
            (data.get("user_id"), data.get("image_path")),
        )
        row = cursor.fetchone()
        if row:
            existing = row[0]
    except Exception:
        existing = None

    if existing:
        # 已存在相同记录，返回已有 ID 并不重复插入
        conn.close()
        return existing

    cursor.execute(
        """
        INSERT INTO generation_records
        (user_id, project_id, created_at, prompt, negative_prompt, aspect_ratio, resolution, width, height,
         num_images, seed, steps, sample_images, image_path, filename, batch_id, status, token_usage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            data.get("user_id"),
            data.get("project_id"),
            local_time,
            data.get("prompt"),
            data.get("negative_prompt", ""),
            data.get("aspect_ratio"),
            data.get("resolution"),
            data.get("width"),
            data.get("height"),
            data.get("num_images", 1),
            data.get("seed", 0),
            data.get("steps", 28),
            sample_images_json,
            data.get("image_path"),
            data.get("filename"),
            data.get("batch_id"),
            data.get("status", "success"),
            data.get("token_usage"),  # 新增token_usage字段
        ),
    )

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return record_id


def save_person_asset(user_id, filename, url, meta=None, project_id=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO person_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            url,
            json.dumps(meta or {}),
        ),
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def save_scene_asset(user_id, filename, url, meta=None, project_id=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scene_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            url,
            json.dumps(meta or {}),
        ),
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_person_assets(user_id, project_id=None, limit=500, offset=0):
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM person_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    else:
        cursor.execute(
            "SELECT * FROM person_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, project_id, limit, offset),
        )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets


def get_scene_assets(user_id, project_id=None, limit=500, offset=0):
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM scene_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    else:
        cursor.execute(
            "SELECT * FROM scene_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, project_id, limit, offset),
        )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets


def _query_asset_table(table_name, user_id, project_id=None, limit=500, offset=0, search=None):
    conn = connect()
    cursor = conn.cursor()

    where_parts = ["user_id = ?"]
    params = [user_id]
    if project_id is not None:
        where_parts.append("project_id = ?")
        params.append(project_id)
    if search:
        where_parts.append("filename LIKE ?")
        params.append(f"%{search}%")

    where_sql = " AND ".join(where_parts)
    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_sql}", tuple(params))
    total = cursor.fetchone()[0]

    query_params = list(params) + [limit, offset]
    cursor.execute(
        f"SELECT * FROM {table_name} WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        tuple(query_params),
    )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets, total


def query_person_assets(user_id, project_id=None, limit=500, offset=0, search=None):
    return _query_asset_table("person_library", user_id, project_id, limit, offset, search)


def query_scene_assets(user_id, project_id=None, limit=500, offset=0, search=None):
    return _query_asset_table("scene_library", user_id, project_id, limit, offset, search)


def count_person_assets(user_id, project_id=None, search=None):
    _, total = query_person_assets(user_id, project_id, limit=1, offset=0, search=search)
    return total


def count_scene_assets(user_id, project_id=None, search=None):
    _, total = query_scene_assets(user_id, project_id, limit=1, offset=0, search=search)
    return total


def delete_person_asset(asset_id, user_id=None, project_id=None):
    """删除人物库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    conn = connect()
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            "DELETE FROM person_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (asset_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute(
            "DELETE FROM person_library WHERE id = ? AND user_id = ?", (asset_id, user_id)
        )
    else:
        cursor.execute("DELETE FROM person_library WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()


def delete_scene_asset(asset_id, user_id=None, project_id=None):
    """删除场景库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    conn = connect()
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            "DELETE FROM scene_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (asset_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute(
            "DELETE FROM scene_library WHERE id = ? AND user_id = ?", (asset_id, user_id)
        )
    else:
        cursor.execute("DELETE FROM scene_library WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()


def save_image_asset(user_id, filename, url, meta=None, project_id=None):
    """保存图片到图片库"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO image_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            url,
            json.dumps(meta or {}),
        ),
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def save_video_asset(user_id, filename, url, meta=None, project_id=None):
    """保存视频到视频库"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO video_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            url,
            json.dumps(meta or {}),
        ),
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_image_assets(user_id, project_id=None, limit=500, offset=0):
    """获取图片库资源"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM image_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    else:
        cursor.execute(
            "SELECT * FROM image_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, project_id, limit, offset),
        )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets


def count_image_assets(user_id, project_id=None):
    """统计图片库资源数量"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute("SELECT COUNT(*) FROM image_library WHERE user_id = ?", (user_id,))
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM image_library WHERE user_id = ? AND project_id = ?",
            (user_id, project_id),
        )
    total = cursor.fetchone()[0]
    conn.close()
    return total


def query_image_assets(user_id, project_id=None, limit=500, offset=0, search=None):
    """分页查询图片库资源"""
    ensure_media_library_tables()
    return _query_asset_table("image_library", user_id, project_id, limit, offset, search)


def query_audio_assets(user_id, project_id=None, limit=500, offset=0, search=None):
    """分页查询音频库资源"""
    ensure_media_library_tables()
    return _query_asset_table("audio_library", user_id, project_id, limit, offset, search)


def count_audio_assets(user_id, project_id=None, search=None):
    _, total = query_audio_assets(user_id, project_id, limit=1, offset=0, search=search)
    return total


def get_video_assets(user_id, project_id=None, limit=500):
    """获取视频库资源"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM video_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM video_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, project_id, limit),
        )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets


def query_video_assets(
    user_id, project_id=None, limit=50, offset=0, search=None, library_kind="all"
):
    """
    分页查询视频库资源，并在 SQL 层完成库类型过滤与搜索。

    Args:
        user_id: 用户 ID
        project_id: 项目 ID（可选）
        limit: 单页条数
        offset: 偏移量
        search: 文件名关键词（可选）
        library_kind: all | video | media

    Returns:
        (assets, total)
    """
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()

    where_parts = ["user_id = ?"]
    params = [user_id]

    if project_id is None:
        where_parts.append("project_id IS NULL")
    else:
        where_parts.append("project_id = ?")
        params.append(project_id)

    if search:
        where_parts.append("filename LIKE ?")
        params.append(f"%{search}%")

    kind = (library_kind or "all").lower()
    if kind == "video":
        where_parts.append(
            "("
            'meta LIKE \'%"library_group": "video"%\' '
            "OR meta LIKE '%\"task_id\"%' "
            'OR meta LIKE \'%"source": "omni_video"%\' '
            "OR meta LIKE '%\"model\"%'"
            ")"
        )
    elif kind == "media":
        where_parts.append(
            "("
            "("
            'meta LIKE \'%"library_group": "media"%\' '
            "OR meta LIKE '%\"mime_type\"%' "
            "OR url LIKE '%media_video%' "
            "OR url LIKE '%media_audio%'"
            ") "
            'AND meta NOT LIKE \'%"library_group": "video"%\' '
            "AND meta NOT LIKE '%\"task_id\"%' "
            'AND meta NOT LIKE \'%"source": "omni_video"%\' '
            "AND meta NOT LIKE '%\"model\"%'"
            ")"
        )

    where_sql = " AND ".join(where_parts)

    cursor.execute(f"SELECT COUNT(*) FROM video_library WHERE {where_sql}", tuple(params))
    total = cursor.fetchone()[0]

    query_params = list(params) + [limit, offset]
    cursor.execute(
        f"""
        SELECT * FROM video_library
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(query_params),
    )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets, total


def rename_video_asset(asset_id, filename, user_id=None, project_id=None):
    """Rename a video asset in the video library."""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    query = "UPDATE video_library SET filename = ? WHERE id = ?"
    params = [filename, asset_id]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    cursor.execute(query, tuple(params))
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated


def update_video_asset_url(asset_id, new_url):
    """更新视频库记录的URL"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE video_library SET url = ? WHERE id = ?", (new_url, asset_id))
    conn.commit()
    conn.close()


def update_video_asset_url_by_task_id(user_id, task_id, new_url, project_id=None):
    """根据task_id更新视频库记录的URL"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute("SELECT * FROM video_library WHERE user_id = ?", (user_id,))
    else:
        cursor.execute(
            "SELECT * FROM video_library WHERE user_id = ? AND project_id = ?",
            (user_id, project_id),
        )
    rows = cursor.fetchall()
    for row in rows:
        asset = dict(row)
        try:
            meta = json.loads(asset.get("meta") or "{}")
            if meta.get("task_id") == task_id:
                cursor.execute(
                    "UPDATE video_library SET url = ? WHERE id = ?", (new_url, asset["id"])
                )
                conn.commit()
                conn.close()
                return True
        except Exception:
            pass
    conn.close()
    return False


def update_video_asset_meta(asset_id, meta_update):
    """更新视频库记录的meta字段（合并更新）"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT meta FROM video_library WHERE id = ?", (asset_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    try:
        existing_meta = json.loads(row["meta"] or "{}")
        if not isinstance(existing_meta, dict):
            existing_meta = {}
        # 合并新的meta数据
        existing_meta.update(meta_update)
        cursor.execute(
            "UPDATE video_library SET meta = ? WHERE id = ?", (json.dumps(existing_meta), asset_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def save_audio_asset(user_id, filename, url, meta=None, project_id=None):
    """淇濆瓨闊抽鍒伴煶棰戝簱"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO audio_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            url,
            json.dumps(meta or {}),
        ),
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_audio_assets(user_id, project_id=None, limit=500):
    """鑾峰彇闊抽搴撹祫婧?"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM audio_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM audio_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, project_id, limit),
        )
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a["meta"] = json.loads(a.get("meta") or "{}")
        except Exception:
            a["meta"] = {}
    conn.close()
    return assets


def get_video_by_task_id(user_id, task_id, project_id=None):
    """根据任务ID获取视频库中的视频"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute("SELECT * FROM video_library WHERE user_id = ?", (user_id,))
    else:
        cursor.execute(
            "SELECT * FROM video_library WHERE user_id = ? AND project_id = ?",
            (user_id, project_id),
        )
    rows = cursor.fetchall()
    for row in rows:
        asset = dict(row)
        try:
            meta = json.loads(asset.get("meta") or "{}")
            if meta.get("task_id") == task_id or meta.get("source_task_id") == task_id:
                asset["meta"] = meta
                conn.close()
                return asset
        except Exception:
            pass
    conn.close()
    return None


def save_video_task(data):
    """保存视频任务记录"""
    conn = connect()
    cursor = conn.cursor()

    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 检查任务是否已存在
    cursor.execute("SELECT id FROM video_tasks WHERE task_id = ?", (data.get("task_id"),))
    existing = cursor.fetchone()

    if existing:
        # 更新现有记录
        cursor.execute(
            """
            UPDATE video_tasks SET
                updated_at = ?,
                status = ?,
                video_url = ?,
                last_frame_image_url = ?,
                project_id = COALESCE(?, project_id),
                token = ?,
                usage = ?,
                content = ?,
                error_message = ?
            WHERE task_id = ?
        """,
            (
                local_time,
                data.get("status", "pending"),
                data.get("video_url"),
                data.get("last_frame_image_url"),
                data.get("project_id"),
                data.get("token"),
                json.dumps(data.get("usage", {})) if data.get("usage") else None,
                json.dumps(data.get("content", {})) if data.get("content") else None,
                data.get("error_message"),
                data.get("task_id"),
            ),
        )
        task_id = existing[0]
    else:
        # 插入新记录
        cursor.execute(
            """
            INSERT INTO video_tasks
            (user_id, task_id, project_id, created_at, updated_at, status, prompt, generate_type, resolution, ratio,
             duration, seed, camera_fixed, watermark, generate_audio, return_last_frame,
             first_frame_url, last_frame_url, reference_image_urls, video_url, last_frame_image_url,
             token, usage, content, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                data.get("user_id"),
                data.get("task_id"),
                data.get("project_id"),
                local_time,
                local_time,
                data.get("status", "pending"),
                data.get("prompt"),
                data.get("generate_type"),
                data.get("resolution"),
                data.get("ratio"),
                data.get("duration"),
                data.get("seed"),
                1 if data.get("camera_fixed") else 0,
                1 if data.get("watermark") else 0,
                1 if data.get("generate_audio") else 0,
                1 if data.get("return_last_frame") else 0,
                data.get("first_frame_url"),
                data.get("last_frame_url"),
                (
                    json.dumps(data.get("reference_image_urls", []))
                    if data.get("reference_image_urls")
                    else None
                ),
                data.get("video_url"),
                data.get("last_frame_image_url"),
                data.get("token"),
                json.dumps(data.get("usage", {})) if data.get("usage") else None,
                json.dumps(data.get("content", {})) if data.get("content") else None,
                data.get("error_message"),
            ),
        )
        task_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return task_id


def update_video_task_media(
    task_id, video_url=None, last_frame_image_url=None, first_frame_url=None, last_frame_url=None
):
    """仅更新视频任务的媒体链接字段"""
    if not task_id:
        return
    updates = []
    params = []
    if video_url is not None:
        updates.append("video_url = ?")
        params.append(video_url)
    if last_frame_image_url is not None:
        updates.append("last_frame_image_url = ?")
        params.append(last_frame_image_url)
    if first_frame_url is not None:
        updates.append("first_frame_url = ?")
        params.append(first_frame_url)
    if last_frame_url is not None:
        updates.append("last_frame_url = ?")
        params.append(last_frame_url)
    if not updates:
        return

    conn = connect()
    cursor = conn.cursor()
    updates.append("updated_at = ?")
    params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(task_id)
    cursor.execute(f"UPDATE video_tasks SET {', '.join(updates)} WHERE task_id = ?", params)
    conn.commit()
    conn.close()


def get_video_tasks(
    user_id, project_id=None, status=None, start_date=None, end_date=None, limit=100, offset=0
):
    """获取视频任务列表"""
    conn = connect()
    cursor = conn.cursor()

    query = "SELECT * FROM video_tasks WHERE user_id = ?"
    params = [user_id]

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    if status:
        query += " AND status = ?"
        params.append(status)

    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)

    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    tasks = []
    for row in rows:
        task = dict(row)
        # 解析JSON字段
        try:
            if task.get("reference_image_urls"):
                task["reference_image_urls"] = json.loads(task["reference_image_urls"])
            if task.get("usage"):
                task["usage"] = json.loads(task["usage"])
            if task.get("content"):
                task["content"] = json.loads(task["content"])
        except Exception:
            pass
        tasks.append(task)

    conn.close()
    return tasks


def get_video_task_by_id(task_id):
    """根据任务ID获取视频任务"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    if row:
        task = dict(row)
        # 解析JSON字段
        try:
            if task.get("reference_image_urls"):
                task["reference_image_urls"] = json.loads(task["reference_image_urls"])
            if task.get("usage"):
                task["usage"] = json.loads(task["usage"])
            if task.get("content"):
                task["content"] = json.loads(task["content"])
        except Exception:
            pass
        conn.close()
        return task
    conn.close()
    return None


def mark_video_task_deleted_from_library(user_id, task_id, project_id=None):
    """Remember that a generated video task was manually removed from the library."""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO deleted_video_library_tasks (user_id, project_id, task_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, project_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def is_video_task_deleted_from_library(user_id, task_id, project_id=None):
    """Check whether a generated video task was manually removed from the library."""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT 1
            FROM deleted_video_library_tasks
            WHERE user_id = ? AND task_id = ? AND project_id IS NULL
            LIMIT 1
            """,
            (user_id, task_id),
        )
    else:
        cursor.execute(
            """
            SELECT 1
            FROM deleted_video_library_tasks
            WHERE user_id = ? AND task_id = ? AND project_id = ?
            LIMIT 1
            """,
            (user_id, task_id, project_id),
        )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def _ensure_omni_video_task_schema(cursor):
    """MySQL schema is managed by scripts/schema_mysql.sql."""
    return


def _decode_omni_video_task(row):
    task = dict(row)
    json_field_defaults = {
        "input_payload_json": {},
        "raw_response_json": {},
        "result_json": {},
        "reference_urls_json": [],
        "usage_json": {},
        "external_meta_json": {},
    }
    for field, default_value in json_field_defaults.items():
        raw = task.get(field)
        if raw in (None, ""):
            task[field] = (
                default_value.copy() if isinstance(default_value, (dict, list)) else default_value
            )
            continue
        # MySQL JSON columns may already be decoded into native Python objects.
        if field == "reference_urls_json" and isinstance(raw, list):
            task[field] = raw
            continue
        if field != "reference_urls_json" and isinstance(raw, dict):
            task[field] = raw
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if field == "reference_urls_json":
                task[field] = parsed if isinstance(parsed, list) else []
            else:
                task[field] = parsed if isinstance(parsed, dict) else {}
        except Exception:
            task[field] = (
                default_value.copy() if isinstance(default_value, (dict, list)) else default_value
            )
    return task


def save_omni_video_task(data):
    """Insert or update an omni video task."""

    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT id FROM omni_video_tasks WHERE task_id = ?", (data.get("task_id"),))
    existing = cursor.fetchone()

    params = (
        data.get("user_id"),
        data.get("task_id"),
        data.get("project_id"),
        now,
        now,
        data.get("status", "queued"),
        data.get("model"),
        data.get("mode"),
        data.get("prompt"),
        json.dumps(data.get("input_payload_json", {})),
        json.dumps(data.get("raw_response_json", {})),
        json.dumps(data.get("result_json", {})),
        data.get("fail_reason"),
        data.get("video_url"),
        data.get("cover_url"),
        data.get("first_frame_url"),
        data.get("last_frame_url"),
        json.dumps(data.get("reference_urls_json", [])),
        data.get("duration"),
        data.get("frame_count"),
        data.get("resolution"),
        data.get("aspect_ratio"),
        data.get("filename"),
        data.get("seed"),
        data.get("token_usage"),
        json.dumps(data.get("usage_json", {})),
        data.get("batch_id"),
        data.get("client_request_id"),
        data.get("source"),
        data.get("callback_url"),
        json.dumps(data.get("external_meta_json", {})),
    )

    if existing:
        cursor.execute(
            """
            UPDATE omni_video_tasks
            SET user_id = ?, project_id = ?, updated_at = ?, status = ?, model = ?, mode = ?,
                prompt = ?, input_payload_json = ?, raw_response_json = ?, result_json = ?,
                fail_reason = ?, video_url = ?, cover_url = ?, first_frame_url = ?,
                last_frame_url = ?, reference_urls_json = ?, duration = ?, frame_count = ?,
                resolution = ?, aspect_ratio = ?, filename = ?, seed = ?, token_usage = ?, usage_json = ?,
                batch_id = ?, client_request_id = ?, source = ?, callback_url = ?, external_meta_json = ?
            WHERE task_id = ?
        """,
            (
                data.get("user_id"),
                data.get("project_id"),
                now,
                data.get("status", "queued"),
                data.get("model"),
                data.get("mode"),
                data.get("prompt"),
                json.dumps(data.get("input_payload_json", {})),
                json.dumps(data.get("raw_response_json", {})),
                json.dumps(data.get("result_json", {})),
                data.get("fail_reason"),
                data.get("video_url"),
                data.get("cover_url"),
                data.get("first_frame_url"),
                data.get("last_frame_url"),
                json.dumps(data.get("reference_urls_json", [])),
                data.get("duration"),
                data.get("frame_count"),
                data.get("resolution"),
                data.get("aspect_ratio"),
                data.get("filename"),
                data.get("seed"),
                data.get("token_usage"),
                json.dumps(data.get("usage_json", {})),
                data.get("batch_id"),
                data.get("client_request_id"),
                data.get("source"),
                data.get("callback_url"),
                json.dumps(data.get("external_meta_json", {})),
                data.get("task_id"),
            ),
        )
        record_id = existing[0]
    else:
        cursor.execute(
            """
            INSERT INTO omni_video_tasks (
                user_id, task_id, project_id, created_at, updated_at, status, model, mode,
                prompt, input_payload_json, raw_response_json, result_json, fail_reason,
                video_url, cover_url, first_frame_url, last_frame_url, reference_urls_json,
                duration, frame_count, resolution, aspect_ratio, filename, seed, token_usage, usage_json,
                batch_id, client_request_id, source, callback_url, external_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            params,
        )
        record_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return record_id


def get_omni_video_task(task_id, user_id=None, project_id=None):
    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = "SELECT * FROM omni_video_tasks WHERE task_id = ?"
    params = [task_id]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return _decode_omni_video_task(row) if row else None


def get_omni_video_task_by_client_request_id(user_id, client_request_id, source=None):
    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = "SELECT * FROM omni_video_tasks WHERE user_id = ? AND client_request_id = ?"
    params = [user_id, client_request_id]
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY id DESC LIMIT 1"

    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return _decode_omni_video_task(row) if row else None


def get_omni_video_tasks(
    user_id,
    project_id=None,
    status=None,
    search=None,
    start_date=None,
    end_date=None,
    batch_id=None,
    limit=20,
    offset=0,
    include_heavy_fields=True,
):
    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    if include_heavy_fields:
        select_fields = "*"
    else:
        select_fields = (
            "id, user_id, task_id, project_id, created_at, updated_at, status, model, mode, prompt, "
            "fail_reason, video_url, cover_url, first_frame_url, last_frame_url, "
            "duration, frame_count, resolution, aspect_ratio, filename, seed, token_usage, "
            "batch_id, client_request_id, source, callback_url"
        )

    query = f"SELECT {select_fields} FROM omni_video_tasks WHERE user_id = ?"
    params = [user_id]
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (task_id LIKE ? OR prompt LIKE ? OR filename LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if start_date:
        query += " AND created_at >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query += " AND created_at < DATE_ADD(?, INTERVAL 1 DAY)"
        params.append(end_date)
    if batch_id:
        query += " AND batch_id = ?"
        params.append(batch_id)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [_decode_omni_video_task(row) for row in rows]


def count_omni_video_tasks(
    user_id,
    project_id=None,
    status=None,
    search=None,
    start_date=None,
    end_date=None,
    batch_id=None,
):
    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = "SELECT COUNT(*) FROM omni_video_tasks WHERE user_id = ?"
    params = [user_id]
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (task_id LIKE ? OR prompt LIKE ? OR filename LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if start_date:
        query += " AND created_at >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query += " AND created_at < DATE_ADD(?, INTERVAL 1 DAY)"
        params.append(end_date)
    if batch_id:
        query += " AND batch_id = ?"
        params.append(batch_id)

    cursor.execute(query, params)
    total = cursor.fetchone()[0]
    conn.close()
    return total


def get_omni_video_tasks_by_statuses(statuses, limit=200):
    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    cleaned = [str(s).strip() for s in (statuses or []) if str(s).strip()]
    if not cleaned:
        conn.close()
        return []

    placeholders = ", ".join(["?"] * len(cleaned))
    query = (
        f"SELECT * FROM omni_video_tasks WHERE status IN ({placeholders}) "
        "ORDER BY created_at ASC LIMIT ?"
    )
    params = list(cleaned) + [int(limit or 200)]
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [_decode_omni_video_task(row) for row in rows]


def delete_omni_video_task(task_id, user_id=None, project_id=None):
    conn = connect()
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = "DELETE FROM omni_video_tasks WHERE task_id = ?"
    params = [task_id]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    cursor.execute(query, params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


# ==================== 视频画质增强任务函数 ====================


def _ensure_video_enhance_tasks_schema(cursor):
    """MySQL schema is managed by scripts/schema_mysql.sql."""
    return


def _decode_video_enhance_task(row):
    """将数据库行解码为字典，处理JSON字段。"""
    task = dict(row)
    for field in (
        "input_payload_json",
        "raw_response_json",
        "result_json",
        "usage_json",
    ):
        raw = task.get(field)
        if not raw:
            task[field] = {}
            continue
        try:
            task[field] = json.loads(raw)
        except Exception:
            task[field] = {}
    return task


def save_video_enhance_task(data):
    """插入或更新视频画质增强任务。"""
    conn = connect()
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT id FROM video_enhance_tasks WHERE task_id = ?", (data.get("task_id"),))
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            """
            UPDATE video_enhance_tasks
            SET user_id = ?, project_id = ?, updated_at = ?, status = ?,
                source_video_url = ?, source_video_id = ?, source_filename = ?,
                input_payload_json = ?, tool_version = ?, resolution = ?, raw_response_json = ?,
                result_json = ?, video_url = ?, output_filename = ?, cover_url = ?,
                fail_reason = ?, token_usage = ?, usage_json = ?
            WHERE task_id = ?
            """,
            (
                data.get("user_id"),
                data.get("project_id"),
                now,
                data.get("status", "queued"),
                data.get("source_video_url"),
                data.get("source_video_id"),
                data.get("source_filename"),
                json.dumps(data.get("input_payload_json", {})),
                data.get("tool_version"),
                data.get("resolution"),
                json.dumps(data.get("raw_response_json", {})),
                json.dumps(data.get("result_json", {})),
                data.get("video_url"),
                data.get("output_filename"),
                data.get("cover_url"),
                data.get("fail_reason"),
                data.get("token_usage"),
                json.dumps(data.get("usage_json", {})),
                data.get("task_id"),
            ),
        )
        record_id = existing[0]
    else:
        cursor.execute(
            """
            INSERT INTO video_enhance_tasks (
                user_id, task_id, project_id, created_at, updated_at, status,
                source_video_url, source_video_id, source_filename, input_payload_json,
                tool_version, resolution, raw_response_json, result_json, video_url, output_filename,
                cover_url, fail_reason, token_usage, usage_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("user_id"),
                data.get("task_id"),
                data.get("project_id"),
                now,
                now,
                data.get("status", "queued"),
                data.get("source_video_url"),
                data.get("source_video_id"),
                data.get("source_filename"),
                json.dumps(data.get("input_payload_json", {})),
                data.get("tool_version"),
                data.get("resolution"),
                json.dumps(data.get("raw_response_json", {})),
                json.dumps(data.get("result_json", {})),
                data.get("video_url"),
                data.get("output_filename"),
                data.get("cover_url"),
                data.get("fail_reason"),
                data.get("token_usage"),
                json.dumps(data.get("usage_json", {})),
            ),
        )
        record_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return record_id


def get_video_enhance_task(task_id, user_id=None, project_id=None):
    """获取单个视频画质增强任务。"""
    conn = connect()
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = "SELECT * FROM video_enhance_tasks WHERE task_id = ?"
    params = [task_id]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return _decode_video_enhance_task(row) if row else None


def get_video_enhance_tasks(
    user_id,
    project_id=None,
    status=None,
    search=None,
    start_date=None,
    end_date=None,
    limit=20,
    offset=0,
):
    """分页查询视频画质增强任务列表。"""
    conn = connect()
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = "SELECT * FROM video_enhance_tasks WHERE user_id = ?"
    params = [user_id]

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)
    if search:
        query += " AND (task_id LIKE ? OR source_filename LIKE ? OR output_filename LIKE ?)"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [_decode_video_enhance_task(row) for row in rows]


def count_video_enhance_tasks(
    user_id, project_id=None, status=None, search=None, start_date=None, end_date=None
):
    """计数视频画质增强任务。"""
    conn = connect()
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = "SELECT COUNT(*) FROM video_enhance_tasks WHERE user_id = ?"
    params = [user_id]

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)
    if search:
        query += " AND (task_id LIKE ? OR source_filename LIKE ? OR output_filename LIKE ?)"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    cursor.execute(query, params)
    total = cursor.fetchone()[0]
    conn.close()
    return total


def delete_video_enhance_task(task_id, user_id=None, project_id=None):
    """删除视频画质增强任务。"""
    conn = connect()
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = "DELETE FROM video_enhance_tasks WHERE task_id = ?"
    params = [task_id]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    cursor.execute(query, params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_image_asset(asset_id, user_id=None, project_id=None):
    """删除图片库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            "DELETE FROM image_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (asset_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute(
            "DELETE FROM image_library WHERE id = ? AND user_id = ?", (asset_id, user_id)
        )
    else:
        cursor.execute("DELETE FROM image_library WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()


def delete_video_asset(asset_id, user_id=None, project_id=None):
    """删除视频库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            "DELETE FROM video_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (asset_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute(
            "DELETE FROM video_library WHERE id = ? AND user_id = ?", (asset_id, user_id)
        )
    else:
        cursor.execute("DELETE FROM video_library WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()


def delete_audio_asset(asset_id, user_id=None, project_id=None):
    """鍒犻櫎闊抽搴撹祫婧愩€?"""
    ensure_media_library_tables()
    conn = connect()
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            "DELETE FROM audio_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (asset_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute(
            "DELETE FROM audio_library WHERE id = ? AND user_id = ?", (asset_id, user_id)
        )
    else:
        cursor.execute("DELETE FROM audio_library WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()


def get_all_records(user_id, project_id=None, limit=100, offset=0):
    """获取指定用户的所有记录"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT * FROM generation_records
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, limit, offset),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM generation_records
            WHERE user_id = ? AND project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, project_id, limit, offset),
        )

    rows = cursor.fetchall()
    records = []

    for row in rows:
        record = dict(row)
        # 解析 JSON 字段
        if record["sample_images"]:
            record["sample_images"] = json.loads(record["sample_images"])
        records.append(record)

    conn.close()
    return records


def get_records_by_batch(batch_id, project_id=None):
    """获取指定批次的记录"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT * FROM generation_records
            WHERE batch_id = ?
            ORDER BY created_at DESC
        """,
            (batch_id,),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM generation_records
            WHERE batch_id = ? AND project_id = ?
            ORDER BY created_at DESC
        """,
            (batch_id, project_id),
        )

    rows = cursor.fetchall()
    records = []

    for row in rows:
        record = dict(row)
        if record["sample_images"]:
            record["sample_images"] = json.loads(record["sample_images"])
        records.append(record)

    conn.close()
    return records


def get_record_by_id(record_id):
    """获取单条记录"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM generation_records WHERE id = ?", (record_id,))
    row = cursor.fetchone()

    if row:
        record = dict(row)
        if record["sample_images"]:
            record["sample_images"] = json.loads(record["sample_images"])
        conn.close()
        return record

    conn.close()
    return None


def delete_record(record_id, user_id=None, project_id=None):
    """删除生成记录。传入 user_id、project_id 时仅当记录属于该用户且属于该项目时删除（项目隔离）。"""
    conn = connect()
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            "DELETE FROM generation_records WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (record_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute(
            "DELETE FROM generation_records WHERE id = ? AND user_id = ?", (record_id, user_id)
        )
    else:
        cursor.execute("DELETE FROM generation_records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


def get_total_count(user_id, project_id=None):
    """获取指定用户的总记录数"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute("SELECT COUNT(*) FROM generation_records WHERE user_id = ?", (user_id,))
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM generation_records WHERE user_id = ? AND project_id = ?",
            (user_id, project_id),
        )
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ==================== 用户管理函数 ====================


def hash_password(password):
    """生成密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(
    username,
    password,
    role_code=ROLE_EXTERNAL_USER,
    status=STATUS_ACTIVE,
    pricing_multiplier=None,
):
    """创建新用户"""
    conn = connect()
    cursor = conn.cursor()

    try:
        password_hash = hash_password(password)
        if pricing_multiplier is None:
            pricing_multiplier = get_role_pricing_multiplier(role_code or ROLE_EXTERNAL_USER)
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role_code, status, balance_cent, pricing_multiplier, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                username,
                password_hash,
                role_code or ROLE_EXTERNAL_USER,
                status or STATUS_ACTIVE,
                0,
                pricing_multiplier if pricing_multiplier is not None else 1.0,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except IntegrityError:
        conn.close()
        return None  # 用户名已存在


def verify_user(username, password):
    """验证用户登录"""
    conn = connect()
    cursor = conn.cursor()

    password_hash = hash_password(password)
    columns = _get_user_table_columns()
    if "status" in columns:
        cursor.execute(
            """
            SELECT * FROM users
            WHERE username = ? AND password_hash = ? AND status = ?
        """,
            (username, password_hash, STATUS_ACTIVE),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM users
            WHERE username = ? AND password_hash = ?
        """,
            (username, password_hash),
        )

    row = cursor.fetchone()

    if row:
        user = dict(row)
        # 更新最后登录时间
        cursor.execute(
            """
            UPDATE users SET last_login = ? WHERE id = ?
        """,
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["id"]),
        )
        conn.commit()
        conn.close()
        return user

    conn.close()
    return None


def has_project_access(user_id, project_id):
    if project_id in (None, ""):
        return True
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM user_projects WHERE user_id = ? AND project_id = ? LIMIT 1",
        (user_id, project_id),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_external_api_key(api_key):
    value = str(api_key or "").strip()
    if not value:
        return None

    key_hash = hashlib.sha256(value.encode()).hexdigest()
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT k.*, u.username, u.role_code, u.status AS user_status
            FROM external_api_keys k
            JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = ? AND k.status = ? AND u.status = ?
            LIMIT 1
            """,
            (key_hash, STATUS_ACTIVE, STATUS_ACTIVE),
        )
        row = cursor.fetchone()
    except Exception:
        row = None
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """根据ID获取用户信息"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()

    if row:
        user = dict(row)
        user.setdefault("role_code", ROLE_EXTERNAL_USER)
        user.setdefault("status", STATUS_ACTIVE)
        user.setdefault("balance_cent", 0)
        user.setdefault("pricing_multiplier", 1.0)
        conn.close()
        return user

    conn.close()
    return None


def get_all_users():
    """获取所有用户列表"""
    conn = connect()
    cursor = conn.cursor()

    columns = _get_user_table_columns()
    if {"role_code", "status", "balance_cent", "pricing_multiplier"}.issubset(columns):
        cursor.execute("""
            SELECT id, username, role_code, status, balance_cent, pricing_multiplier, created_at, last_login
            FROM users
            ORDER BY id
        """)
    else:
        cursor.execute("SELECT id, username, created_at, last_login FROM users ORDER BY id")
    rows = cursor.fetchall()

    users = []
    for row in rows:
        user = dict(row)
        user.setdefault("role_code", ROLE_EXTERNAL_USER)
        user.setdefault("status", STATUS_ACTIVE)
        user.setdefault("balance_cent", 0)
        user.setdefault("pricing_multiplier", 1.0)
        users.append(user)
    conn.close()
    return users


def delete_user(user_id):
    """删除用户"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def update_user_password(user_id, new_password):
    """更新用户密码"""
    conn = connect()
    cursor = conn.cursor()
    password_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()
    conn.close()


def update_user_pricing_multiplier(user_id, pricing_multiplier):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET pricing_multiplier = ?, updated_at = ? WHERE id = ?",
        (pricing_multiplier, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected


def update_user_role(user_id, role_code):
    conn = connect()
    cursor = conn.cursor()
    columns = _get_user_table_columns()
    if "role_code" in columns:
        role_multiplier = get_role_pricing_multiplier(role_code)
        if "updated_at" in columns:
            cursor.execute(
                "UPDATE users SET role_code = ?, pricing_multiplier = ?, updated_at = ? WHERE id = ?",
                (role_code, role_multiplier, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
            )
        else:
            cursor.execute(
                "UPDATE users SET role_code = ?, pricing_multiplier = ? WHERE id = ?",
                (role_code, role_multiplier, user_id),
            )
    else:
        conn.close()
        return 0
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected


def upsert_model_pricing(
    model_code,
    model_name,
    currency_code,
    price_per_million_token_cent,
    resolution_code="",
    reference_video_mode=REFERENCE_VIDEO_MODE_ANY,
    enabled=True,
):
    conn = connect()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        SELECT id FROM model_pricing
        WHERE model_code = ? AND currency_code = ? AND resolution_code = ? AND reference_video_mode = ?
    """,
        (model_code, currency_code, resolution_code, reference_video_mode),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            """
            UPDATE model_pricing
            SET model_name = ?, price_per_million_token_cent = ?, enabled = ?, updated_at = ?
            WHERE model_code = ? AND currency_code = ? AND resolution_code = ? AND reference_video_mode = ?
        """,
            (
                model_name,
                price_per_million_token_cent,
                1 if enabled else 0,
                now,
                model_code,
                currency_code,
                resolution_code,
                reference_video_mode,
            ),
        )
        pricing_id = row[0]
    else:
        cursor.execute(
            """
            INSERT INTO model_pricing (
                model_code, model_name, currency_code, resolution_code, reference_video_mode,
                price_per_million_token_cent, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                model_code,
                model_name,
                currency_code,
                resolution_code,
                reference_video_mode,
                price_per_million_token_cent,
                1 if enabled else 0,
                now,
                now,
            ),
        )
        pricing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pricing_id


def update_model_pricing_by_id(
    pricing_id,
    model_name,
    currency_code,
    price_per_million_token_cent,
    resolution_code="",
    reference_video_mode=REFERENCE_VIDEO_MODE_ANY,
    enabled=True,
):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE model_pricing
        SET model_name = ?, currency_code = ?, resolution_code = ?, reference_video_mode = ?, price_per_million_token_cent = ?, enabled = ?, updated_at = ?
        WHERE id = ?
    """,
        (
            model_name,
            currency_code,
            resolution_code,
            reference_video_mode,
            price_per_million_token_cent,
            1 if enabled else 0,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            pricing_id,
        ),
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected


def get_model_pricing(model_code):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM model_pricing WHERE model_code = ?", (model_code,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result.setdefault("currency_code", MODEL_CURRENCY_CNY)
    result.setdefault("resolution_code", "")
    result.setdefault("reference_video_mode", REFERENCE_VIDEO_MODE_ANY)
    return result


def resolve_model_pricing(model_code, resolution=None, has_video_reference=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM model_pricing WHERE model_code = ? AND enabled = 1",
        (model_code,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    if not rows:
        return None

    normalized_resolution = str(resolution or "").strip().lower()
    mode = REFERENCE_VIDEO_MODE_ANY
    if has_video_reference is True:
        mode = REFERENCE_VIDEO_MODE_WITH
    elif has_video_reference is False:
        mode = REFERENCE_VIDEO_MODE_WITHOUT

    def _score(item):
        resolution_code = str(item.get("resolution_code") or "").strip().lower()
        ref_mode = str(item.get("reference_video_mode") or REFERENCE_VIDEO_MODE_ANY).strip().lower()
        score = 0
        if resolution_code:
            if normalized_resolution and resolution_code == normalized_resolution:
                score += 100
            else:
                score -= 100
        if ref_mode != REFERENCE_VIDEO_MODE_ANY:
            if ref_mode == mode:
                score += 10
            else:
                score -= 10
        return score

    best = max(rows, key=_score)
    if _score(best) < 0:
        return None
    best.setdefault("currency_code", MODEL_CURRENCY_CNY)
    best.setdefault("resolution_code", "")
    best.setdefault("reference_video_mode", REFERENCE_VIDEO_MODE_ANY)
    return best


def get_model_pricing_list(enabled=None):
    conn = connect()
    cursor = conn.cursor()
    query = "SELECT * FROM model_pricing"
    params = []
    if enabled is not None:
        query += " WHERE enabled = ?"
        params.append(1 if enabled else 0)
    query += " ORDER BY model_code"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    for item in items:
        item.setdefault("currency_code", MODEL_CURRENCY_CNY)
        item.setdefault("resolution_code", "")
        item.setdefault("reference_video_mode", REFERENCE_VIDEO_MODE_ANY)
    return items


def get_min_enabled_model_price_per_million_cent():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT currency_code, price_per_million_token_cent FROM model_pricing WHERE enabled = 1"
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    min_value = None
    for row in rows:
        currency_code = str(row.get("currency_code") or MODEL_CURRENCY_CNY).upper()
        price = int(row.get("price_per_million_token_cent") or 0)
        if currency_code == MODEL_CURRENCY_USD:
            price *= USD_TO_CNY_RATE
        if min_value is None or price < min_value:
            min_value = price
    return min_value


def get_user_consumption_records(user_id, limit=100, offset=0, biz_type=None):
    conn = connect()
    cursor = conn.cursor()
    if biz_type:
        cursor.execute(
            """
            SELECT *
            FROM account_ledger
            WHERE user_id = ? AND entry_type = 'debit' AND biz_type = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, biz_type, limit, offset),
        )
    else:
        cursor.execute(
            """
            SELECT *
            FROM account_ledger
            WHERE user_id = ? AND entry_type = 'debit'
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, limit, offset),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_account_ledger(user_id=None, limit=100, offset=0):
    conn = connect()
    cursor = conn.cursor()
    query = "SELECT * FROM account_ledger WHERE 1=1"
    params = []
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_account_ledger(user_id=None, entry_type=None, biz_type=None):
    conn = connect()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM account_ledger WHERE 1=1"
    params = []
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if entry_type:
        query += " AND entry_type = ?"
        params.append(entry_type)
    if biz_type:
        query += " AND biz_type = ?"
        params.append(biz_type)
    cursor.execute(query, params)
    total = cursor.fetchone()[0]
    conn.close()
    return total


def has_ledger_entry(user_id, entry_type, biz_type, biz_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1 FROM account_ledger
        WHERE user_id = ? AND entry_type = ? AND biz_type = ? AND biz_id = ?
        LIMIT 1
    """,
        (user_id, entry_type, biz_type, biz_id),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_ledger_debit_amount_cent(user_id, biz_type, biz_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT amount_cent
        FROM account_ledger
        WHERE user_id = ? AND entry_type = 'debit' AND biz_type = ? AND biz_id = ?
        LIMIT 1
    """,
        (user_id, biz_type, biz_id),
    )
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row and row[0] is not None else None


def get_ledger_debit_amounts_cent(user_id, biz_type, biz_ids):
    cleaned_ids = [str(biz_id).strip() for biz_id in (biz_ids or []) if str(biz_id).strip()]
    if not cleaned_ids:
        return {}

    conn = connect()
    cursor = conn.cursor()
    placeholders = ", ".join(["?"] * len(cleaned_ids))
    cursor.execute(
        f"""
        SELECT biz_id, amount_cent
        FROM account_ledger
        WHERE user_id = ? AND entry_type = 'debit' AND biz_type = ? AND biz_id IN ({placeholders})
        """,
        (user_id, biz_type, *cleaned_ids),
    )
    rows = cursor.fetchall()
    conn.close()
    return {
        str(row["biz_id"]): int(row["amount_cent"])
        for row in rows
        if row["biz_id"] is not None and row["amount_cent"] is not None
    }


def create_account_ledger_entry(
    user_id,
    entry_type,
    amount_cent,
    biz_type,
    biz_id=None,
    model_code=None,
    tokens_raw=None,
    tokens_billed=None,
    unit_price_cent_per_ktoken=None,
    multiplier=None,
    snapshot_json=None,
    operator_user_id=None,
):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance_cent FROM users WHERE id = ? FOR UPDATE", (user_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("用户不存在")
        before = int(row[0] or 0)
        delta = int(amount_cent)
        after = before + delta if entry_type == "credit" else before - abs(delta)
        if after < 0:
            raise ValueError("余额不足")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE users SET balance_cent = ?, updated_at = ? WHERE id = ?", (after, now, user_id)
        )
        cursor.execute(
            """
            INSERT INTO account_ledger (
                user_id, entry_type, amount_cent, balance_before_cent, balance_after_cent,
                biz_type, biz_id, model_code, tokens_raw, tokens_billed, unit_price_cent_per_ktoken,
                multiplier, snapshot_json, operator_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                entry_type,
                abs(delta),
                before,
                after,
                biz_type,
                biz_id,
                model_code,
                tokens_raw,
                tokens_billed,
                unit_price_cent_per_ktoken,
                multiplier,
                json.dumps(snapshot_json or {}),
                operator_user_id,
                now,
            ),
        )
        conn.commit()
        return {"before": before, "after": after, "ledger_id": cursor.lastrowid}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def compute_tokens_billed(tokens_raw):
    value = max(int(tokens_raw or 0), 1000)
    return int(math.ceil(value / 1000.0) * 1000)


def create_project(name, owner_id=None):
    """创建项目"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (name, owner_id, created_at)
        VALUES (?, ?, ?)
    """,
        (name, owner_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def get_all_projects():
    """获取所有项目"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY id DESC")
    rows = cursor.fetchall()
    projects = [dict(r) for r in rows]
    conn.close()
    return projects


def get_user_projects(user_id):
    """获取用户可用项目"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.* FROM projects p
        JOIN user_projects up ON up.project_id = p.id
        WHERE up.user_id = ?
        ORDER BY p.id DESC
    """,
        (user_id,),
    )
    rows = cursor.fetchall()
    projects = [dict(r) for r in rows]
    conn.close()
    return projects


def assign_user_to_project(user_id, project_id):
    """授权用户到项目"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO user_projects (user_id, project_id, created_at)
        VALUES (?, ?, ?)
    """,
        (user_id, project_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def revoke_user_from_project(user_id, project_id):
    """取消用户项目授权"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM user_projects WHERE user_id = ? AND project_id = ?", (user_id, project_id)
    )
    conn.commit()
    conn.close()


def get_project_by_id(project_id):
    """获取项目"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_project(project_id):
    """Delete a project and its membership relations."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_projects WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted > 0


def get_project_users(project_id):
    """获取项目内用户"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.id, u.username, u.created_at, u.last_login
        FROM users u
        JOIN user_projects up ON up.user_id = u.id
        WHERE up.project_id = ?
        ORDER BY u.id
    """,
        (project_id,),
    )
    rows = cursor.fetchall()
    users = [dict(r) for r in rows]
    conn.close()
    return users


def get_script_templates(user_id, project_id=None):
    """获取剧本提示词模板"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM script_templates WHERE user_id = ? ORDER BY id DESC", (user_id,)
        )
    else:
        cursor.execute(
            "SELECT * FROM script_templates WHERE user_id = ? AND project_id = ? ORDER BY id DESC",
            (user_id, project_id),
        )
    rows = cursor.fetchall()
    templates = [dict(r) for r in rows]
    conn.close()
    return templates


def create_script_template(user_id, project_id, name, prompt):
    """创建剧本提示词模板"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO script_templates (user_id, project_id, name, prompt, created_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (user_id, project_id, name, prompt, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    template_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return template_id


def delete_script_template(user_id, template_id, project_id=None):
    """删除剧本提示词模板。传入 project_id 时仅删除该项目下的模板（项目隔离）。"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is not None:
        cursor.execute(
            "DELETE FROM script_templates WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
            (template_id, user_id, project_id, project_id),
        )
    else:
        cursor.execute(
            "DELETE FROM script_templates WHERE id = ? AND user_id = ?", (template_id, user_id)
        )
    conn.commit()
    conn.close()


def create_generation_task(user_id, project_id, task_type, payload):
    """创建生成任务"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO generation_tasks (
            user_id, project_id, task_type, status, progress, payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            task_type,
            "running",
            0,
            json.dumps(payload or {}, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id


def update_generation_task(task_id, status=None, progress=None, result=None, error=None):
    """更新生成任务"""
    fields = []
    values = []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if progress is not None:
        fields.append("progress = ?")
        values.append(progress)
    if result is not None:
        fields.append("result_json = ?")
        values.append(json.dumps(result, ensure_ascii=False))
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(task_id)
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE generation_tasks
        SET {", ".join(fields)}
        WHERE id = ?
    """,
        tuple(values),
    )
    conn.commit()
    conn.close()


def get_generation_task(user_id, project_id, task_id):
    """获取生成任务"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM generation_tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
    else:
        cursor.execute(
            "SELECT * FROM generation_tasks WHERE id = ? AND user_id = ? AND project_id = ?",
            (task_id, user_id, project_id),
        )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_script_record(
    user_id,
    project_id,
    title,
    novel_text,
    prompt,
    min_seconds,
    max_seconds,
    script_text,
    episodes,
    record_id=None,
):
    """保存剧本记录"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    cursor = conn.cursor()
    episodes_json = json.dumps(episodes or [], ensure_ascii=False)
    if record_id:
        cursor.execute(
            """
            UPDATE script_saves
            SET title = ?, novel_text = ?, prompt = ?, min_seconds = ?, max_seconds = ?, script_text = ?, episodes_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """,
            (
                title,
                novel_text,
                prompt,
                min_seconds,
                max_seconds,
                script_text,
                episodes_json,
                now,
                record_id,
                user_id,
            ),
        )
        conn.commit()
        conn.close()
        return record_id
    cursor.execute(
        """
        INSERT INTO script_saves (
            user_id, project_id, title, novel_text, prompt, min_seconds, max_seconds, script_text, episodes_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            title,
            novel_text,
            prompt,
            min_seconds,
            max_seconds,
            script_text,
            episodes_json,
            now,
            now,
        ),
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def list_script_records(user_id, project_id=None):
    """获取剧本保存列表"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT id, title, created_at, updated_at FROM script_saves WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM script_saves
            WHERE user_id = ? AND project_id = ?
            ORDER BY updated_at DESC
        """,
            (user_id, project_id),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_script_record(user_id, project_id, record_id):
    """获取剧本记录"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM script_saves WHERE id = ? AND user_id = ?", (record_id, user_id)
        )
    else:
        cursor.execute(
            "SELECT * FROM script_saves WHERE id = ? AND user_id = ? AND project_id = ?",
            (record_id, user_id, project_id),
        )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_script_episodes(script_id, user_id, project_id, episodes):
    """保存剧本分集记录"""
    conn = connect()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for ep in episodes:
        cursor.execute(
            """
            INSERT INTO script_episode_records (
                script_id, user_id, project_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                script_id,
                user_id,
                project_id,
                ep.get("episode_index"),
                ep.get("title"),
                ep.get("duration_seconds"),
                ep.get("summary"),
                ep.get("content_url"),
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()


def list_script_episodes(script_id, user_id, project_id=None):
    """获取剧本分集列表"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE script_id = ? AND user_id = ?
            ORDER BY episode_index ASC, id ASC
        """,
            (script_id, user_id),
        )
    else:
        cursor.execute(
            """
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE script_id = ? AND user_id = ? AND project_id = ?
            ORDER BY episode_index ASC, id ASC
        """,
            (script_id, user_id, project_id),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_script_episode(episode_id, user_id, project_id=None):
    """获取单集记录"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM script_episode_records WHERE id = ? AND user_id = ?",
            (episode_id, user_id),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM script_episode_records
            WHERE id = ? AND user_id = ? AND project_id = ?
        """,
            (episode_id, user_id, project_id),
        )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_max_script_episode_index(script_id, user_id, project_id=None):
    """获取剧本当前最大集数"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT MAX(episode_index) FROM script_episode_records WHERE script_id = ? AND user_id = ?",
            (script_id, user_id),
        )
    else:
        cursor.execute(
            """
            SELECT MAX(episode_index) FROM script_episode_records
            WHERE script_id = ? AND user_id = ? AND project_id = ?
        """,
            (script_id, user_id, project_id),
        )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0


def list_all_script_episodes(user_id, project_id=None):
    """获取所有剧本分集列表"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE user_id = ?
            ORDER BY id ASC
        """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE user_id = ? AND project_id = ?
            ORDER BY id ASC
        """,
            (user_id, project_id),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_script_episode(
    episode_id,
    user_id,
    content_url=None,
    summary=None,
    title=None,
    episode_index=None,
    duration_seconds=None,
):
    """更新剧本分集内容"""
    fields = []
    values = []
    if content_url is not None:
        fields.append("content_url = ?")
        values.append(content_url)
    if summary is not None:
        fields.append("summary = ?")
        values.append(summary)
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if episode_index is not None:
        fields.append("episode_index = ?")
        values.append(episode_index)
    if duration_seconds is not None:
        fields.append("duration_seconds = ?")
        values.append(duration_seconds)
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(episode_id)
    values.append(user_id)
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE script_episode_records
        SET {", ".join(fields)}
        WHERE id = ? AND user_id = ?
    """,
        tuple(values),
    )
    conn.commit()
    conn.close()


def delete_script_episode(episode_id, user_id):
    """删除剧本分集"""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM script_episode_records WHERE id = ? AND user_id = ?", (episode_id, user_id)
    )
    conn.commit()
    conn.close()


def save_storyboard_record(
    user_id,
    project_id,
    title,
    script_text,
    prompt,
    storyboard_json,
    storyboard_text,
    record_id=None,
    series_id=None,
    create_version=False,
):
    """保存分镜记录"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    cursor = conn.cursor()
    storyboard_json_text = json.dumps(storyboard_json or {}, ensure_ascii=False)
    if record_id and not create_version:
        cursor.execute(
            """
            UPDATE storyboard_saves
            SET title = ?, script_text = ?, prompt = ?, storyboard_json = ?, storyboard_text = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """,
            (
                title,
                script_text,
                prompt,
                storyboard_json_text,
                storyboard_text,
                now,
                record_id,
                user_id,
            ),
        )
        conn.commit()
        conn.close()
        return record_id
    version = 1
    if series_id:
        cursor.execute(
            "SELECT MAX(version) FROM storyboard_saves WHERE series_id = ? AND user_id = ?",
            (series_id, user_id),
        )
        row = cursor.fetchone()
        max_ver = row[0] if row else None
        version = (max_ver or 0) + 1
    cursor.execute(
        """
        INSERT INTO storyboard_saves (
            user_id, project_id, title, script_text, prompt, storyboard_json, storyboard_text, created_at, updated_at, series_id, version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            project_id,
            title,
            script_text,
            prompt,
            storyboard_json_text,
            storyboard_text,
            now,
            now,
            series_id,
            version,
        ),
    )
    record_id = cursor.lastrowid
    if not series_id:
        cursor.execute(
            "UPDATE storyboard_saves SET series_id = ? WHERE id = ?", (record_id, record_id)
        )
    conn.commit()
    conn.close()
    return record_id


def list_storyboard_records(user_id, project_id=None):
    """获取分镜保存列表"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT id, title, created_at, updated_at, series_id, version FROM storyboard_saves WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT id, title, created_at, updated_at, series_id, version
            FROM storyboard_saves
            WHERE user_id = ? AND project_id = ?
            ORDER BY updated_at DESC
        """,
            (user_id, project_id),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_storyboard_series(user_id, project_id=None):
    """获取分镜系列列表（每个系列最新版本）"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT s.*
            FROM storyboard_saves s
            JOIN (
                SELECT series_id, MAX(version) AS max_version
                FROM storyboard_saves
                WHERE user_id = ?
                GROUP BY series_id
            ) latest ON latest.series_id = s.series_id AND latest.max_version = s.version
            WHERE s.user_id = ?
            ORDER BY s.updated_at DESC
        """,
            (user_id, user_id),
        )
    else:
        cursor.execute(
            """
            SELECT s.*
            FROM storyboard_saves s
            JOIN (
                SELECT series_id, MAX(version) AS max_version
                FROM storyboard_saves
                WHERE user_id = ? AND project_id = ?
                GROUP BY series_id
            ) latest ON latest.series_id = s.series_id AND latest.max_version = s.version
            WHERE s.user_id = ? AND s.project_id = ?
            ORDER BY s.updated_at DESC
        """,
            (user_id, project_id, user_id, project_id),
        )
    rows = cursor.fetchall()
    series = [dict(r) for r in rows]
    for item in series:
        cursor.execute(
            "SELECT COUNT(*) FROM storyboard_saves WHERE series_id = ? AND user_id = ?",
            (item.get("series_id"), user_id),
        )
        item["version_count"] = cursor.fetchone()[0]
    conn.close()
    return series


def list_storyboard_versions(user_id, project_id, series_id):
    """获取分镜系列的版本列表"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT id, title, created_at, updated_at, series_id, version
            FROM storyboard_saves
            WHERE user_id = ? AND series_id = ?
            ORDER BY version DESC
        """,
            (user_id, series_id),
        )
    else:
        cursor.execute(
            """
            SELECT id, title, created_at, updated_at, series_id, version
            FROM storyboard_saves
            WHERE user_id = ? AND project_id = ? AND series_id = ?
            ORDER BY version DESC
        """,
            (user_id, project_id, series_id),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_storyboard_episode(
    user_id, project_id, script_episode_id, prompt, storyboard_json, storyboard_text, images_json
):
    """保存分镜分集记录（按剧本分集）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM storyboard_episode_records
        WHERE script_episode_id = ? AND user_id = ?
    """,
        (script_episode_id, user_id),
    )
    row = cursor.fetchone()
    storyboard_json_text = json.dumps(storyboard_json or {}, ensure_ascii=False)
    images_json_text = json.dumps(images_json or {}, ensure_ascii=False)
    if row:
        record_id = row[0]
        cursor.execute(
            """
            UPDATE storyboard_episode_records
            SET prompt = ?, storyboard_json = ?, storyboard_text = ?, images_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """,
            (
                prompt,
                storyboard_json_text,
                storyboard_text,
                images_json_text,
                now,
                record_id,
                user_id,
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO storyboard_episode_records (
                script_episode_id, user_id, project_id, prompt, storyboard_json, storyboard_text, images_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                script_episode_id,
                user_id,
                project_id,
                prompt,
                storyboard_json_text,
                storyboard_text,
                images_json_text,
                now,
                now,
            ),
        )
        record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_storyboard_episode(user_id, project_id, script_episode_id):
    """获取分镜分集记录"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            """
            SELECT * FROM storyboard_episode_records
            WHERE script_episode_id = ? AND user_id = ?
            ORDER BY updated_at DESC LIMIT 1
        """,
            (script_episode_id, user_id),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM storyboard_episode_records
            WHERE script_episode_id = ? AND user_id = ? AND project_id = ?
            ORDER BY updated_at DESC LIMIT 1
        """,
            (script_episode_id, user_id, project_id),
        )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    record = dict(row)
    for key in ("storyboard_json", "images_json"):
        if record.get(key):
            try:
                record[key] = json.loads(record[key])
            except Exception:
                record[key] = {}
        else:
            record[key] = {}
    return record


def get_storyboard_record(user_id, project_id, record_id):
    """获取分镜记录"""
    conn = connect()
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            "SELECT * FROM storyboard_saves WHERE id = ? AND user_id = ?", (record_id, user_id)
        )
    else:
        cursor.execute(
            "SELECT * FROM storyboard_saves WHERE id = ? AND user_id = ? AND project_id = ?",
            (record_id, user_id, project_id),
        )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats_overview():
    """获取统计概览"""
    conn = connect()
    cursor = conn.cursor()

    # 总用户数
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # 总图片数
    cursor.execute("SELECT COUNT(*) FROM generation_records")
    total_images = cursor.fetchone()[0]

    # 今日图片数
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        """
        SELECT COUNT(*) FROM generation_records
        WHERE DATE(created_at) = ?
    """,
        (today,),
    )
    today_images = cursor.fetchone()[0]

    # 本周图片数
    cursor.execute("""
        SELECT COUNT(*) FROM generation_records
        WHERE DATE(created_at) >= DATE('now', '-7 days')
    """)
    week_images = cursor.fetchone()[0]

    conn.close()

    return {
        "total_users": total_users,
        "total_images": total_images,
        "today_images": today_images,
        "week_images": week_images,
    }


def get_user_stats(start_date=None, end_date=None):
    """获取每个用户的统计信息"""
    conn = connect()
    cursor = conn.cursor()

    # 获取所有用户
    users = get_all_users()

    today = datetime.now().strftime("%Y-%m-%d")

    stats = []
    for user in users:
        user_id = user["id"]

        # 总生成数
        if start_date and end_date:
            cursor.execute(
                """
                SELECT COUNT(*) FROM generation_records
                WHERE user_id = ? AND DATE(created_at) BETWEEN ? AND ?
            """,
                (user_id, start_date, end_date),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM generation_records WHERE user_id = ?", (user_id,))
        total_count = cursor.fetchone()[0]

        # 今日生成数
        cursor.execute(
            """
            SELECT COUNT(*) FROM generation_records
            WHERE user_id = ? AND DATE(created_at) = ?
        """,
            (user_id, today),
        )
        today_count = cursor.fetchone()[0]

        # 本周生成数
        cursor.execute(
            """
            SELECT COUNT(*) FROM generation_records
            WHERE user_id = ? AND DATE(created_at) >= DATE('now', '-7 days')
        """,
            (user_id,),
        )
        week_count = cursor.fetchone()[0]

        # 最后生成时间
        cursor.execute(
            """
            SELECT created_at FROM generation_records
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 1
        """,
            (user_id,),
        )
        last_row = cursor.fetchone()
        last_generated = last_row[0] if last_row else None

        stats.append(
            {
                "user_id": user_id,
                "username": user["username"],
                "total_count": total_count,
                "today_count": today_count,
                "week_count": week_count,
                "last_generated": last_generated,
            }
        )

    conn.close()
    return stats


def get_daily_stats(days=7):
    """获取每日生成统计"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            DATE(created_at) as date,
            COUNT(*) as count,
            COUNT(DISTINCT user_id) as user_count
        FROM generation_records
        WHERE DATE(created_at) >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    """,
        (days,),
    )

    rows = cursor.fetchall()

    stats = [{"date": row[0], "count": row[1], "user_count": row[2]} for row in rows]

    conn.close()
    return stats


# ========== 报表统计函数 ==========


def get_report_overview(start_date=None, end_date=None):
    """
    获取报表概览统计（图片、视频、增强三种任务）

    返回: {
        'total_users': int,
        'image': {'total': int, 'today': int, 'last7days': int, 'period': int},
        'video': {'total': int, 'today': int, 'last7days': int, 'period': int, 'total_duration': int, 'today_duration': int, 'last7days_duration': int, 'period_duration': int},
        'enhance': {'total': int, 'today': int, 'last7days': int, 'period': int}
    }
    """
    conn = connect()
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    # 近7天：从前一天开始往前推6天（不含今天）
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last7days_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # 总用户数
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # 图片统计
    image_stats = {"total": 0, "today": 0, "last7days": 0, "period": 0}
    cursor.execute("SELECT COUNT(*) FROM generation_records")
    image_stats["total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM generation_records WHERE DATE(created_at) = ?", (today,))
    image_stats["today"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM generation_records WHERE DATE(created_at) BETWEEN ? AND ?",
        (last7days_start, yesterday),
    )
    image_stats["last7days"] = cursor.fetchone()[0]

    if start_date and end_date:
        cursor.execute(
            "SELECT COUNT(*) FROM generation_records WHERE DATE(created_at) BETWEEN ? AND ?",
            (start_date, end_date),
        )
        image_stats["period"] = cursor.fetchone()[0]

    # 视频统计（合并 video_tasks 和 omni_video_tasks）
    video_stats = {
        "total": 0,
        "today": 0,
        "last7days": 0,
        "period": 0,
        "total_duration": 0,
        "today_duration": 0,
        "last7days_duration": 0,
        "period_duration": 0,
    }

    # 总数和总时长
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
            SELECT duration FROM video_tasks
            UNION ALL
            SELECT duration FROM omni_video_tasks
        ) video_union
    """)
    row = cursor.fetchone()
    video_stats["total"] = row[0] or 0
    video_stats["total_duration"] = row[1] or 0

    # 今日
    cursor.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
            SELECT duration, created_at FROM video_tasks
            UNION ALL
            SELECT duration, created_at FROM omni_video_tasks
        ) video_union WHERE DATE(created_at) = ?
    """,
        (today,),
    )
    row = cursor.fetchone()
    video_stats["today"] = row[0] or 0
    video_stats["today_duration"] = row[1] or 0

    # 近7天
    cursor.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
            SELECT duration, created_at FROM video_tasks
            UNION ALL
            SELECT duration, created_at FROM omni_video_tasks
        ) video_union WHERE DATE(created_at) BETWEEN ? AND ?
    """,
        (last7days_start, yesterday),
    )
    row = cursor.fetchone()
    video_stats["last7days"] = row[0] or 0
    video_stats["last7days_duration"] = row[1] or 0

    # 指定时间段
    if start_date and end_date:
        cursor.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
                SELECT duration, created_at FROM video_tasks
                UNION ALL
                SELECT duration, created_at FROM omni_video_tasks
            ) video_union WHERE DATE(created_at) BETWEEN ? AND ?
        """,
            (start_date, end_date),
        )
        row = cursor.fetchone()
        video_stats["period"] = row[0] or 0
        video_stats["period_duration"] = row[1] or 0

    # 增强统计
    enhance_stats = {"total": 0, "today": 0, "last7days": 0, "period": 0}
    cursor.execute("SELECT COUNT(*) FROM video_enhance_tasks")
    enhance_stats["total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM video_enhance_tasks WHERE DATE(created_at) = ?", (today,))
    enhance_stats["today"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM video_enhance_tasks WHERE DATE(created_at) BETWEEN ? AND ?",
        (last7days_start, yesterday),
    )
    enhance_stats["last7days"] = cursor.fetchone()[0]

    if start_date and end_date:
        cursor.execute(
            "SELECT COUNT(*) FROM video_enhance_tasks WHERE DATE(created_at) BETWEEN ? AND ?",
            (start_date, end_date),
        )
        enhance_stats["period"] = cursor.fetchone()[0]

    conn.close()

    return {
        "total_users": total_users,
        "image": image_stats,
        "video": video_stats,
        "enhance": enhance_stats,
    }


def get_user_report(start_date=None, end_date=None, username_filter=None):
    """
    获取用户维度统计（使用单次聚合查询，消除N+1问题）

    Args:
        start_date: 开始日期
        end_date: 结束日期
        username_filter: 用户名筛选（可选）

    返回: List[{
        'user_id': int, 'username': str,
        'image_count': int, 'video_count': int, 'video_duration': int,
        'enhance_count': int, 'total_count': int, 'last_active': str,
        'video_tokens': int, 'enhance_tokens': int, 'total_tokens': int
    }]
    """
    conn = connect()
    cursor = conn.cursor()

    # 构建日期条件
    date_condition = ""
    date_params = []
    if start_date and end_date:
        date_condition = "AND DATE(created_at) BETWEEN ? AND ?"
        date_params = [start_date, end_date]

    # 用户名筛选条件
    username_condition = ""
    username_params = []
    if username_filter:
        username_condition = "AND u.username LIKE ?"
        username_params = [f"%{username_filter}%"]

    # 单次聚合查询，合并所有表的统计
    # 使用LEFT JOIN确保所有用户都被包含，即使没有记录
    # Token只统计全能视频(omni_video_tasks)
    # 视频统计合并 video_tasks 和 omni_video_tasks
    last_active_expr = (
        "GREATEST(COALESCE(g.last_active, ''), COALESCE(v.last_active, ''), "
        "COALESCE(e.last_active, ''), COALESCE(ov.last_active, ''))"
    )
    query = f"""
        SELECT
            u.id as user_id,
            u.username,
            COALESCE(g.image_count, 0) as image_count,
            COALESCE(v.video_count, 0) as video_count,
            COALESCE(v.video_duration, 0) as video_duration,
            COALESCE(e.enhance_count, 0) as enhance_count,
            COALESCE(ov.video_tokens, 0) as video_tokens,
            {last_active_expr} as last_active
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) as image_count, MAX(created_at) as last_active
            FROM generation_records
            WHERE 1=1 {date_condition}
            GROUP BY user_id
        ) g ON u.id = g.user_id
        LEFT JOIN (
            SELECT user_id, COUNT(*) as video_count, SUM(COALESCE(duration, 0)) as video_duration, MAX(created_at) as last_active
            FROM (
                SELECT user_id, duration, created_at FROM video_tasks WHERE 1=1 {date_condition}
                UNION ALL
                SELECT user_id, COALESCE(duration, 0) as duration, created_at FROM omni_video_tasks WHERE 1=1 {date_condition}
            ) video_union
            GROUP BY user_id
        ) v ON u.id = v.user_id
        LEFT JOIN (
            SELECT user_id, COUNT(*) as enhance_count, MAX(created_at) as last_active
            FROM video_enhance_tasks
            WHERE 1=1 {date_condition}
            GROUP BY user_id
        ) e ON u.id = e.user_id
        LEFT JOIN (
            SELECT user_id, SUM(COALESCE(token_usage, 0)) as video_tokens, MAX(created_at) as last_active
            FROM omni_video_tasks
            WHERE 1=1 {date_condition}
            GROUP BY user_id
        ) ov ON u.id = ov.user_id
        WHERE 1=1 {username_condition}
        ORDER BY u.id
    """

    params = date_params + date_params + date_params + date_params + date_params + username_params
    cursor.execute(query, params)
    rows = cursor.fetchall()

    stats = []
    for row in rows:
        total_count = (
            (row["image_count"] or 0) + (row["video_count"] or 0) + (row["enhance_count"] or 0)
        )
        video_tokens = row["video_tokens"] or 0
        last_active = row["last_active"] if row["last_active"] else None
        stats.append(
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "image_count": row["image_count"] or 0,
                "video_count": row["video_count"] or 0,
                "video_duration": row["video_duration"] or 0,
                "enhance_count": row["enhance_count"] or 0,
                "total_count": total_count,
                "last_active": last_active,
                "video_tokens": video_tokens,
                "total_tokens": video_tokens,
            }
        )

    conn.close()
    return stats


def get_daily_report(start_date=None, end_date=None, days=30):
    """
    获取每日趋势统计（使用子查询优化，消除循环查询）

    返回: List[{
        'date': str, 'image_count': int, 'video_count': int,
        'video_duration': int, 'enhance_count': int, 'user_count': int,
        'video_tokens': int
    }]
    """
    conn = connect()
    cursor = conn.cursor()

    # 确定日期范围
    if not start_date or not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    # 单次查询获取所有日期的统计数据（使用UNION合并所有活动）
    # Token只统计全能视频(omni_video_tasks)
    cursor.execute(
        """
        WITH all_activities AS (
            -- 图片生成（不计token）
            SELECT DATE(created_at) as date, user_id, 'image' as type, 0 as duration, 0 as video_tokens
            FROM generation_records
            WHERE DATE(created_at) BETWEEN ? AND ?
            UNION ALL
            -- 视频任务（不计token）
            SELECT DATE(created_at) as date, user_id, 'video' as type, COALESCE(duration, 0) as duration, 0 as video_tokens
            FROM video_tasks
            WHERE DATE(created_at) BETWEEN ? AND ?
            UNION ALL
            -- 全能视频任务（统计token）
            SELECT DATE(created_at) as date, user_id, 'omni_video' as type, COALESCE(duration, 0) as duration, COALESCE(token_usage, 0) as video_tokens
            FROM omni_video_tasks
            WHERE DATE(created_at) BETWEEN ? AND ?
            UNION ALL
            -- 视频增强（不计token）
            SELECT DATE(created_at) as date, user_id, 'enhance' as type, 0 as duration, 0 as video_tokens
            FROM video_enhance_tasks
            WHERE DATE(created_at) BETWEEN ? AND ?
        ),
        daily_stats AS (
            SELECT
                date,
                SUM(CASE WHEN type = 'image' THEN 1 ELSE 0 END) as image_count,
                SUM(CASE WHEN type IN ('video', 'omni_video') THEN 1 ELSE 0 END) as video_count,
                SUM(CASE WHEN type IN ('video', 'omni_video') THEN duration ELSE 0 END) as video_duration,
                SUM(CASE WHEN type = 'enhance' THEN 1 ELSE 0 END) as enhance_count,
                COUNT(DISTINCT user_id) as user_count,
                SUM(video_tokens) as video_tokens
            FROM all_activities
            GROUP BY date
        )
        SELECT * FROM daily_stats ORDER BY date DESC
    """,
        (start_date, end_date, start_date, end_date, start_date, end_date, start_date, end_date),
    )

    rows = cursor.fetchall()

    # 如果需要补全日期（无数据的日期也要显示）
    # 获取日期范围内的所有日期
    dates_cte = "WITH RECURSIVE"
    next_date_expr = "DATE_ADD(date, INTERVAL 1 DAY)"
    cursor.execute(
        f"""
        {dates_cte} dates(date) AS (
            SELECT DATE(?) as date
            UNION ALL
            SELECT {next_date_expr}
            FROM dates
            WHERE date < DATE(?)
        )
        SELECT date FROM dates ORDER BY date DESC
    """,
        (start_date, end_date),
    )
    all_dates = [row[0] for row in cursor.fetchall()]

    # 合并数据，补全无数据的日期
    stats_dict = {row["date"]: dict(row) for row in rows}
    stats = []
    for date in all_dates:
        if date in stats_dict:
            stats.append(stats_dict[date])
        else:
            stats.append(
                {
                    "date": date,
                    "image_count": 0,
                    "video_count": 0,
                    "video_duration": 0,
                    "enhance_count": 0,
                    "user_count": 0,
                    "video_tokens": 0,
                }
            )

    conn.close()
    return stats


def get_task_status_report(start_date=None, end_date=None):
    """
    获取任务状态统计（成功率、失败率分析）

    返回: {
        'image': {'success': int, 'failed': int, 'total': int, 'success_rate': float},
        'video': {'success': int, 'failed': int, 'pending': int, 'total': int, 'success_rate': float},
        'omni_video': {'success': int, 'failed': int, 'queued': int, 'total': int, 'success_rate': float},
        'enhance': {'success': int, 'failed': int, 'queued': int, 'total': int, 'success_rate': float}
    }
    """
    conn = connect()
    cursor = conn.cursor()

    date_condition = ""
    date_params = []
    if start_date and end_date:
        date_condition = "AND DATE(created_at) BETWEEN ? AND ?"
        date_params = [start_date, end_date]

    result = {}

    # 图片生成状态统计
    query = f"""
        SELECT status, COUNT(*) as count
        FROM generation_records
        WHERE 1=1 {date_condition}
        GROUP BY status
    """
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    image_stats = {"success": 0, "failed": 0, "total": 0}
    for row in rows:
        status = row[0] or "success"
        count = row[1]
        if status == "success":
            image_stats["success"] = count
        else:
            image_stats["failed"] += count
        image_stats["total"] += count
    image_stats["success_rate"] = round(
        image_stats["success"] / max(image_stats["total"], 1) * 100, 2
    )
    result["image"] = image_stats

    # 视频任务状态统计
    query = f"""
        SELECT status, COUNT(*) as count
        FROM video_tasks
        WHERE 1=1 {date_condition}
        GROUP BY status
    """
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    video_stats = {"success": 0, "failed": 0, "pending": 0, "total": 0}
    for row in rows:
        status = row[0] or "pending"
        count = row[1]
        if status in ("success", "completed", "done"):
            video_stats["success"] += count
        elif status in ("failed", "error"):
            video_stats["failed"] += count
        else:
            video_stats["pending"] += count
        video_stats["total"] += count
    video_stats["success_rate"] = round(
        video_stats["success"] / max(video_stats["total"], 1) * 100, 2
    )
    result["video"] = video_stats

    # 全能视频任务状态统计
    query = f"""
        SELECT status, COUNT(*) as count
        FROM omni_video_tasks
        WHERE 1=1 {date_condition}
        GROUP BY status
    """
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    omni_stats = {"success": 0, "failed": 0, "queued": 0, "total": 0}
    for row in rows:
        status = row[0] or "queued"
        count = row[1]
        # 成功状态包括: success, succeeded, completed, done, finished
        if status in ("success", "succeeded", "completed", "done", "finished"):
            omni_stats["success"] += count
        elif status in ("failed", "error", "cancelled", "canceled", "expired"):
            omni_stats["failed"] += count
        else:
            # queued, running, pending 等都归为排队/处理中
            omni_stats["queued"] += count
        omni_stats["total"] += count
    omni_stats["success_rate"] = round(omni_stats["success"] / max(omni_stats["total"], 1) * 100, 2)
    result["omni_video"] = omni_stats

    # 视频增强任务状态统计
    query = f"""
        SELECT status, COUNT(*) as count
        FROM video_enhance_tasks
        WHERE 1=1 {date_condition}
        GROUP BY status
    """
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    enhance_stats = {"success": 0, "failed": 0, "queued": 0, "total": 0}
    for row in rows:
        status = row[0] or "queued"
        count = row[1]
        # 成功状态包括: success, succeeded, completed, done, finished
        if status in ("success", "succeeded", "completed", "done", "finished"):
            enhance_stats["success"] += count
        elif status in ("failed", "error", "cancelled", "canceled", "expired"):
            enhance_stats["failed"] += count
        else:
            # queued, running, pending 等都归为排队/处理中
            enhance_stats["queued"] += count
        enhance_stats["total"] += count
    enhance_stats["success_rate"] = round(
        enhance_stats["success"] / max(enhance_stats["total"], 1) * 100, 2
    )
    result["enhance"] = enhance_stats

    conn.close()
    return result


def get_token_usage_report(start_date=None, end_date=None):
    """
    获取Token消耗统计（只统计全能视频生成token）

    返回: {
        'total_tokens': int,  # 总消耗（所有时间）
        'today_tokens': int,  # 今日消耗
        'last7days_tokens': int,  # 近7日消耗
        'period_tokens': int,  # 所选时间范围消耗
        'video_generation_tokens': int,  # 全能视频生成(omni_video_tasks)
        'daily_tokens': List[{date: str, video_tokens: int}],
        'user_tokens': List[{user_id: int, username: str, video_tokens: int}]
    }
    """
    conn = connect()
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last7days_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # 确定日期范围
    if not start_date or not end_date:
        end_date = yesterday
        start_date = last7days_start

    # 总消耗（所有时间）
    cursor.execute("SELECT COALESCE(SUM(token_usage), 0) FROM omni_video_tasks")
    total_tokens_all = cursor.fetchone()[0] or 0

    # 今日消耗
    cursor.execute(
        "SELECT COALESCE(SUM(token_usage), 0) FROM omni_video_tasks WHERE DATE(created_at) = ?",
        (today,),
    )
    today_tokens = cursor.fetchone()[0] or 0

    # 近7日消耗（不含今天）
    cursor.execute(
        "SELECT COALESCE(SUM(token_usage), 0) FROM omni_video_tasks WHERE DATE(created_at) BETWEEN ? AND ?",
        (last7days_start, yesterday),
    )
    last7days_tokens = cursor.fetchone()[0] or 0

    # 所选时间范围消耗（omni_video_tasks）
    cursor.execute(
        """
        SELECT COALESCE(SUM(token_usage), 0) as tokens
        FROM omni_video_tasks
        WHERE DATE(created_at) BETWEEN ? AND ?
    """,
        (start_date, end_date),
    )
    period_tokens = cursor.fetchone()[0] or 0

    video_generation_tokens = period_tokens

    # 每日Token消耗（只统计全能视频）
    cursor.execute(
        """
        SELECT DATE(created_at) as date, SUM(COALESCE(token_usage, 0)) as video_tokens
        FROM omni_video_tasks
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY DATE(created_at)
    """,
        (start_date, end_date),
    )
    daily_tokens = [{"date": row[0], "video_tokens": row[1]} for row in cursor.fetchall()]

    # 用户Token消耗（只统计全能视频）
    cursor.execute(
        """
        SELECT user_id, SUM(COALESCE(token_usage, 0)) as video_tokens
        FROM omni_video_tasks
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY user_id
    """,
        (start_date, end_date),
    )
    video_user = {row[0]: row[1] for row in cursor.fetchall()}

    # 获取所有用户
    cursor.execute("SELECT id, username FROM users")
    users = cursor.fetchall()

    user_tokens = []
    for user in users:
        user_id = user[0]
        username = user[1]
        vt = video_user.get(user_id, 0)
        user_tokens.append({"user_id": user_id, "username": username, "video_tokens": vt})

    # 按消耗排序
    user_tokens.sort(key=lambda x: x["video_tokens"], reverse=True)

    conn.close()
    return {
        "total_tokens": total_tokens_all,
        "today_tokens": today_tokens,
        "last7days_tokens": last7days_tokens,
        "period_tokens": period_tokens,
        "video_generation_tokens": video_generation_tokens,
        "daily_tokens": daily_tokens,
        "user_tokens": user_tokens,
    }


# ==================== 操作日志函数 ====================


def _ensure_operation_logs_schema():
    """Ensure the MySQL operation logs table exists."""
    initialize_mysql_schema()


def save_operation_log(data: dict) -> int | None:
    """
    保存操作日志。

    Args:
        data: 包含以下字段的字典：
            - user_id: 用户ID（可选）
            - username: 用户名（可选）
            - project_id: 项目ID（可选）
            - request_path: API路径
            - request_method: HTTP方法
            - request_params: 请求参数（dict，可选）
            - response_status: 响应状态码
            - response_summary: 响应摘要（可选）
            - ip_address: 客户端IP（可选）
            - duration_ms: 耗时毫秒（可选）

    Returns:
        日志记录ID，失败时返回None
    """
    try:
        _ensure_operation_logs_schema()
        conn = connect()
        cursor = conn.cursor()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        params_json = json.dumps(data.get("request_params") or {}, ensure_ascii=False)

        cursor.execute(
            """
            INSERT INTO operation_logs
            (user_id, username, project_id, request_path, request_method,
             request_params, response_status, response_summary, ip_address,
             duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("user_id"),
                data.get("username"),
                data.get("project_id"),
                data.get("request_path"),
                data.get("request_method"),
                params_json,
                data.get("response_status"),
                data.get("response_summary"),
                data.get("ip_address"),
                data.get("duration_ms"),
                now,
            ),
        )

        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id

    except Exception as e:
        # 日志写入失败不应影响主流程，静默处理
        print(f"[operation_log] save failed: {e}")
        return None


def get_operation_logs(
    user_id: int | None = None,
    project_id: int | None = None,
    path_prefix: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    查询操作日志。

    Args:
        user_id: 按用户ID筛选（可选）
        project_id: 按项目ID筛选（可选）
        path_prefix: 按路径前缀筛选（可选）
        limit: 返回数量限制，最大500
        offset: 偏移量

    Returns:
        操作日志列表
    """
    _ensure_operation_logs_schema()
    conn = connect()
    cursor = conn.cursor()

    limit = min(limit, 500)  # 限制最大返回量

    query = "SELECT * FROM operation_logs WHERE 1=1"
    params = []

    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    if path_prefix:
        query += " AND request_path LIKE ?"
        params.append(f"{path_prefix}%")

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    logs = [dict(row) for row in rows]

    # 解析JSON字段
    for log in logs:
        try:
            log["request_params"] = json.loads(log.get("request_params") or "{}")
        except Exception:
            log["request_params"] = {}

    conn.close()
    return logs


def count_operation_logs(
    user_id: int | None = None,
    project_id: int | None = None,
    path_prefix: str | None = None,
) -> int:
    """
    统计操作日志数量。

    Args:
        user_id: 按用户ID筛选（可选）
        project_id: 按项目ID筛选（可选）
        path_prefix: 按路径前缀筛选（可选）

    Returns:
        日志数量
    """
    _ensure_operation_logs_schema()
    conn = connect()
    cursor = conn.cursor()

    query = "SELECT COUNT(*) FROM operation_logs WHERE 1=1"
    params = []

    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    if path_prefix:
        query += " AND request_path LIKE ?"
        params.append(f"{path_prefix}%")

    cursor.execute(query, params)
    count = cursor.fetchone()[0]

    conn.close()
    return count


def delete_old_operation_logs(days: int = 30) -> int:
    """
    删除指定天数之前的操作日志。

    Args:
        days: 保留天数，默认30天

    Returns:
        删除的记录数量
    """
    _ensure_operation_logs_schema()
    conn = connect()
    cursor = conn.cursor()

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("DELETE FROM operation_logs WHERE created_at < ?", (cutoff_date,))
    deleted = cursor.rowcount

    conn.commit()
    conn.close()
    return deleted


if __name__ == "__main__":
    # 测试数据库
    init_database()
    print("✅ 数据库表创建成功")

    # 创建测试用户
    test_user = create_user("admin", "admin123")
    if test_user:
        print("✅ 创建测试用户: admin / admin123")
    else:
        print("⚠️ 测试用户已存在")
