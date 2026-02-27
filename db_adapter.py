# -*- coding: utf-8 -*-
"""
数据库适配层：支持 SQLite / MySQL 切换。
通过环境变量 DB_TYPE=mysql 使用 MySQL，否则使用 SQLite。
MySQL 需配置：MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, MYSQL_CHARSET
"""
import os
import re

DB_TYPE = (os.environ.get('DB_TYPE') or '').strip().lower()
USE_MYSQL = DB_TYPE == 'mysql'

# SQLite
if not USE_MYSQL:
    import sqlite3
    DB_PATH = os.environ.get('DB_PATH', 'generation_records.db')

    def get_conn():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def get_placeholder():
        return '?'

    def execute(cursor, sql, params=None):
        if params is None:
            params = ()
        cursor.execute(sql, params)

    IntegrityError = sqlite3.IntegrityError

    def table_exists(cursor, table_name):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cursor.fetchone() is not None

    def column_exists(cursor, table_name, column_name):
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [row[1] for row in cursor.fetchall()]
        return column_name in cols

else:
    # MySQL (PyMySQL)
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError:
        raise ImportError('使用 MySQL 请安装: pip install PyMySQL')

    _mysql_config = {
        'host': os.environ.get('MYSQL_HOST', '127.0.0.1'),
        'port': int(os.environ.get('MYSQL_PORT', '3306')),
        'user': os.environ.get('MYSQL_USER', 'root'),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
        'database': os.environ.get('MYSQL_DATABASE', 'ai_generator'),
        'charset': os.environ.get('MYSQL_CHARSET', 'utf8mb4'),
        'cursorclass': DictCursor,
        'autocommit': False,
    }

    def get_conn():
        return pymysql.connect(**_mysql_config)

    def get_placeholder():
        return '%s'

    # MySQL 使用 %s，若传入的 SQL 是 ? 占位则替换（仅当 ? 在占位位置时安全）
    def _convert_placeholders(sql):
        return sql.replace('?', '%s')

    def execute(cursor, sql, params=None):
        if params is None:
            params = ()
        cursor.execute(_convert_placeholders(sql), params)

    IntegrityError = pymysql.IntegrityError

    def table_exists(cursor, table_name):
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def column_exists(cursor, table_name, column_name):
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table_name, column_name)
        )
        return cursor.fetchone() is not None


def row_to_dict(row):
    """将一行转为 dict。SQLite 的 Row / MySQL 的 DictCursor 均兼容。"""
    if row is None:
        return None
    if hasattr(row, 'keys'):
        return dict(row)
    return row
