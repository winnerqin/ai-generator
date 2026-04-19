#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频库清理脚本（生产环境版本）

功能：
1. 检测视频库中所有URL的可访问性
2. 将未过期的临时URL视频迁移到OSS（获取永久URL）
3. 删除已过期不可访问的视频记录
4. 支持MySQL和SQLite数据库
5. 支持dry-run模式预览操作

使用方法：
    # 使用环境变量配置
    export DB_TYPE=mysql
    export MYSQL_HOST=127.0.0.1
    export MYSQL_PORT=3306
    export MYSQL_USER=root
    export MYSQL_PASSWORD=password
    export MYSQL_DATABASE=ai_generator

    export OSS_ENABLED=true
    export OSS_ENDPOINT=bucket.oss-cn-region.aliyuncs.com
    export OSS_ACCESS_KEY_ID=your_key
    export OSS_ACCESS_KEY_SECRET=your_secret

    # 预览操作
    python cleanup_video_library_production.py --dry-run

    # 执行清理
    python cleanup_video_library_production.py

    # 使用SQLite
    export DB_TYPE=sqlite
    export DB_PATH=/path/to/generation_records.db
    python cleanup_video_library_production.py

参数：
    --dry-run: 仅显示操作，不实际执行
    --batch-size: 每批处理数量，默认50
    --timeout: URL检测超时时间（秒），默认10
    --log-file: 日志文件路径，默认stdout
"""

import argparse
import json
import logging
import os
import tempfile
import sys
from datetime import datetime

# Windows UTF-8编码支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 尝试导入MySQL依赖
try:
    import pymysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

# 尝试导入OSS依赖
try:
    import oss2
    OSS_AVAILABLE = True
except ImportError:
    OSS_AVAILABLE = False

import requests


# ============================================================
# 配置类
# ============================================================

class Config:
    """从环境变量加载配置"""

    # 数据库配置
    DB_TYPE: str = os.environ.get("DB_TYPE", "sqlite").lower()
    DB_PATH: str = os.environ.get("DB_PATH", "generation_records.db")

    # MySQL配置
    MYSQL_HOST: str = os.environ.get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.environ.get("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.environ.get("MYSQL_DATABASE", "ai_generator")
    MYSQL_CHARSET: str = os.environ.get("MYSQL_CHARSET", "utf8mb4")

    # OSS配置
    OSS_ENABLED: bool = os.environ.get("OSS_ENABLED", "false").lower() == "true"
    OSS_ENDPOINT: str = os.environ.get("OSS_ENDPOINT", "")
    OSS_ACCESS_KEY_ID: str = os.environ.get("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET: str = os.environ.get("OSS_ACCESS_KEY_SECRET", "")

    def is_mysql(self) -> bool:
        return self.DB_TYPE == "mysql"

    def is_oss_enabled(self) -> bool:
        return self.OSS_ENABLED and bool(self.OSS_ACCESS_KEY_ID and self.OSS_ACCESS_KEY_SECRET)


config = Config()


# ============================================================
# 日志配置
# ============================================================

def setup_logging(log_file: str | None = None):
    """配置日志"""
    level = logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(message)s"

    if log_file:
        logging.basicConfig(level=level, format=format_str, filename=log_file)
    else:
        logging.basicConfig(level=level, format=format_str, stream=sys.stdout)

    return logging.getLogger("cleanup")


logger = setup_logging()


# ============================================================
# 数据库操作
# ============================================================

class Database:
    """数据库操作封装，支持MySQL和SQLite"""

    def __init__(self):
        self._conn = None
        self._bucket = None
        self._oss_endpoint_full = None

    def connect(self):
        """建立数据库连接"""
        if config.is_mysql():
            if not MYSQL_AVAILABLE:
                raise RuntimeError("MySQL模式需要安装pymysql: pip install pymysql")
            self._conn = pymysql.connect(
                host=config.MYSQL_HOST,
                port=config.MYSQL_PORT,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                charset=config.MYSQL_CHARSET,
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info(f"已连接MySQL: {config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}")
        else:
            import sqlite3
            self._conn = sqlite3.connect(config.DB_PATH)
            self._conn.row_factory = sqlite3.Row
            logger.info(f"已连接SQLite: {config.DB_PATH}")

    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_all_video_assets(self, limit: int = 1000):
        """获取所有视频库记录"""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM video_library ORDER BY created_at DESC LIMIT ?", (limit,))

        if config.is_mysql():
            rows = cursor.fetchall()
        else:
            rows = [dict(r) for r in cursor.fetchall()]

        # 解析meta字段
        for row in rows:
            try:
                row['meta'] = json.loads(row.get('meta') or '{}')
            except Exception:
                row['meta'] = {}

        return rows

    def count_video_assets(self):
        """获取视频库记录总数"""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM video_library")
        result = cursor.fetchone()
        return result['cnt'] if config.is_mysql() else result['cnt']

    def delete_video_asset(self, asset_id: int):
        """删除视频记录"""
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM video_library WHERE id = ?", (asset_id,))
        self._conn.commit()
        logger.info(f"已删除记录: id={asset_id}")

    def update_video_url(self, asset_id: int, new_url: str):
        """更新视频URL"""
        cursor = self._conn.cursor()
        cursor.execute("UPDATE video_library SET url = ? WHERE id = ?", (new_url, asset_id))
        self._conn.commit()
        logger.info(f"已更新URL: id={asset_id} -> {new_url[:80]}...")

    def init_oss(self):
        """初始化OSS客户端"""
        if not config.is_oss_enabled():
            return False

        if not OSS_AVAILABLE:
            logger.warning("OSS模式需要安装oss2: pip install oss2")
            return False

        try:
            # 从endpoint提取bucket名
            # 格式: bucket-name.oss-region.aliyuncs.com
            parts = config.OSS_ENDPOINT.split(".", 1)
            if len(parts) != 2:
                logger.error(f"OSS_ENDPOINT格式不正确: {config.OSS_ENDPOINT}")
                return False

            bucket_name = parts[0]
            oss_endpoint = parts[1]

            auth = oss2.Auth(config.OSS_ACCESS_KEY_ID, config.OSS_ACCESS_KEY_SECRET)
            self._bucket = oss2.Bucket(auth, f"https://{oss_endpoint}", bucket_name)
            self._oss_endpoint_full = config.OSS_ENDPOINT
            logger.info(f"OSS已初始化: {config.OSS_ENDPOINT}")
            return True
        except Exception as e:
            logger.error(f"OSS初始化失败: {e}")
            return False

    def upload_to_oss(self, local_path: str, user_id: int, project_id: int | None, filename: str) -> str | None:
        """上传文件到OSS"""
        if not self._bucket:
            return None

        try:
            # 生成object key
            timestamp = datetime.now().strftime("%Y%m%d")
            if project_id and user_id:
                object_key = f"video_generator/user_{user_id}/project_{project_id}/{filename}"
            elif user_id:
                object_key = f"video_generator/user_{user_id}/{filename}"
            else:
                object_key = f"video_generator/{timestamp}/{filename}"

            # 上传
            with open(local_path, "rb") as f:
                self._bucket.put_object(object_key, f)

            oss_url = f"https://{self._oss_endpoint_full}/{object_key}"
            logger.info(f"OSS上传成功: {object_key}")
            return oss_url
        except Exception as e:
            logger.error(f"OSS上传失败: {e}")
            return None


db = Database()


# ============================================================
# URL检测和处理
# ============================================================

# 火山引擎TOS临时URL特征
TOS_URL_PATTERNS = ["tos-cn-beijing.volces.com", "tos-cn"]
# OSS永久URL特征
OSS_URL_PATTERNS = ["oss-cn", "aliyuncs.com"]


def is_tos_temp_url(url: str) -> bool:
    """判断是否是火山引擎TOS临时URL"""
    if not url:
        return False
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in TOS_URL_PATTERNS)


def is_oss_url(url: str) -> bool:
    """判断是否是OSS永久URL"""
    if not url:
        return False
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in OSS_URL_PATTERNS)


def check_url_accessible(url: str, timeout: int = 10) -> tuple[bool, str]:
    """检查URL是否可访问"""
    if not url:
        return False, "URL为空"

    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return True, "可访问"
        elif response.status_code == 403:
            return False, "403 Forbidden (已过期或无权限)"
        elif response.status_code == 404:
            return False, "404 Not Found"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "请求超时"
    except requests.exceptions.ConnectionError as e:
        return False, f"连接错误"
    except Exception as e:
        return False, f"检测失败"


def download_video(url: str, filename: str, timeout: int = 120) -> tuple[str | None, str]:
    """下载视频到临时文件"""
    try:
        logger.info(f"下载视频: {url[:80]}...")
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, filename)

        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        logger.info(f"下载完成: {temp_file}")
        return temp_file, "下载成功"
    except Exception as e:
        return None, f"下载失败: {e}"


def cleanup_temp_file(path: str):
    """清理临时文件"""
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass


# ============================================================
# 主处理逻辑
# ============================================================

def process_video_asset(asset: dict, dry_run: bool, timeout: int) -> dict:
    """处理单个视频记录"""
    result = {
        "id": asset["id"],
        "filename": asset.get("filename") or f"video_{asset['id']}.mp4",
        "url": asset.get("url") or "",
        "created_at": asset.get("created_at") or "",
        "action": "none",
        "detail": "",
    }

    url = result["url"]

    # 判断URL类型
    if is_oss_url(url):
        result["url_type"] = "oss"
        result["action"] = "keep"
        result["detail"] = "OSS永久URL，无需处理"
        return result

    if is_tos_temp_url(url):
        result["url_type"] = "tos_temp"
    else:
        result["url_type"] = "other"

    # 检查可访问性
    accessible, reason = check_url_accessible(url, timeout)
    result["accessible"] = accessible
    result["access_reason"] = reason

    if accessible:
        # URL仍可访问，尝试迁移到OSS
        result["action"] = "migrate"

        if dry_run:
            result["detail"] = "[DRY-RUN] 将迁移到OSS"
            return result

        # 下载并上传到OSS
        if db._bucket:
            temp_file, download_result = download_video(url, result["filename"])
            if temp_file:
                oss_url = db.upload_to_oss(
                    temp_file,
                    asset.get("user_id"),
                    asset.get("project_id"),
                    result["filename"]
                )
                cleanup_temp_file(temp_file)

                if oss_url:
                    db.update_video_url(asset["id"], oss_url)
                    result["detail"] = f"已迁移到OSS: {oss_url[:60]}..."
                    result["new_url"] = oss_url
                else:
                    result["detail"] = "OSS上传失败，保留原URL"
                    result["action"] = "keep"
            else:
                result["detail"] = f"下载失败: {download_result}"
                result["action"] = "error"
        else:
            result["detail"] = "OSS未配置，保留原URL（注意：24小时后过期）"
            result["action"] = "keep"
    else:
        # URL不可访问，删除记录
        result["action"] = "delete"

        if dry_run:
            result["detail"] = f"[DRY-RUN] 将删除记录 ({reason})"
            return result

        db.delete_video_asset(asset["id"])
        result["detail"] = f"已删除 ({reason})"

    return result


def main():
    parser = argparse.ArgumentParser(description="视频库清理脚本（生产环境版本）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览操作，不实际执行")
    parser.add_argument("--batch-size", type=int, default=1000, help="每批处理数量")
    parser.add_argument("--timeout", type=int, default=10, help="URL检测超时时间（秒）")
    parser.add_argument("--log-file", type=str, default=None, help="日志文件路径")
    args = parser.parse_args()

    # 配置日志文件（如果指定）
    if args.log_file:
        global logger
        logger = setup_logging(args.log_file)

    logger.info("=" * 60)
    logger.info("视频库清理脚本（生产环境版本）")
    logger.info("=" * 60)
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Dry-run模式: {args.dry_run}")
    logger.info(f"数据库类型: {config.DB_TYPE}")

    if args.dry_run:
        logger.info("[DRY-RUN] 仅预览操作，不会实际执行")

    # 连接数据库
    try:
        db.connect()
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        sys.exit(1)

    # 初始化OSS
    oss_ready = db.init_oss()
    logger.info(f"OSS状态: {'可用' if oss_ready else '不可用'}")

    # 获取记录总数
    total_count = db.count_video_assets()
    logger.info(f"视频库总记录数: {total_count}")
    logger.info("")

    if total_count == 0:
        logger.info("视频库为空，无需清理")
        db.close()
        return

    # 统计
    stats = {
        "total": total_count,
        "oss_url": 0,
        "tos_accessible": 0,
        "tos_expired": 0,
        "other_accessible": 0,
        "other_expired": 0,
        "migrated": 0,
        "deleted": 0,
        "errors": 0,
        "kept": 0,
    }

    # 分批处理
    processed = 0
    assets = db.get_all_video_assets(limit=args.batch_size)

    for asset in assets:
        processed += 1

        # 处理记录
        result = process_video_asset(asset, args.dry_run, args.timeout)

        # 打印结果
        logger.info(f"[{processed}/{total_count}] id={result['id']} filename={result['filename'][:30]}")
        logger.info(f"  URL类型: {result.get('url_type', 'unknown')}")
        logger.info(f"  操作: {result['action']} - {result['detail']}")

        # 更新统计
        if result.get("url_type") == "oss":
            stats["oss_url"] += 1
        elif result.get("url_type") == "tos_temp":
            if result.get("accessible"):
                stats["tos_accessible"] += 1
            else:
                stats["tos_expired"] += 1
        else:
            if result.get("accessible"):
                stats["other_accessible"] += 1
            else:
                stats["other_expired"] += 1

        if result["action"] == "migrate":
            stats["migrated"] += 1
        elif result["action"] == "delete":
            stats["deleted"] += 1
        elif result["action"] == "keep":
            stats["kept"] += 1
        elif result["action"] == "error":
            stats["errors"] += 1

    # 关闭数据库
    db.close()

    # 打印统计
    logger.info("")
    logger.info("=" * 60)
    logger.info("统计结果")
    logger.info("=" * 60)
    logger.info(f"处理总数: {processed}")
    logger.info(f"OSS永久URL: {stats['oss_url']}")
    logger.info(f"TOS临时URL(可访问): {stats['tos_accessible']}")
    logger.info(f"TOS临时URL(已过期): {stats['tos_expired']}")
    logger.info(f"其他URL(可访问): {stats['other_accessible']}")
    logger.info(f"其他URL(不可访问): {stats['other_expired']}")
    logger.info("-" * 40)
    logger.info(f"迁移到OSS: {stats['migrated']}")
    logger.info(f"删除记录: {stats['deleted']}")
    logger.info(f"保留记录: {stats['kept']}")
    logger.info(f"错误数: {stats['errors']}")

    if args.dry_run:
        logger.info("")
        logger.info("[DRY-RUN] 以上操作未实际执行")
        logger.info("运行不带 --dry-run 参数执行实际操作")

    logger.info("")
    logger.info(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()