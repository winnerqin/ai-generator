"""Database connection adapter for SQLite and MySQL validation."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def is_mysql_enabled() -> bool:
    return os.environ.get("DB_TYPE", "sqlite").lower() == "mysql"


try:
    import pymysql
except ImportError:  # pragma: no cover - exercised when MySQL mode is disabled
    pymysql = None


IntegrityError = pymysql.IntegrityError if pymysql is not None else sqlite3.IntegrityError


class CompatRow(dict):
    """Mapping row that also supports tuple-style integer indexing."""

    def __init__(self, keys: list[str], values: Iterable[Any]):
        super().__init__(zip(keys, values))
        self._keys = keys

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


class MySQLCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor
        self._keys: list[str] = []

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int:
        return self._cursor.lastrowid

    def execute(self, sql: str, params: Any = None) -> int:
        sql = _translate_sql(sql)
        result = self._cursor.execute(sql, params)
        self._keys = [col[0] for col in self._cursor.description or []]
        return result

    def fetchone(self) -> CompatRow | None:
        row = self._cursor.fetchone()
        return self._wrap(row) if row is not None else None

    def fetchall(self) -> list[CompatRow]:
        return [self._wrap(row) for row in self._cursor.fetchall()]

    def close(self) -> None:
        self._cursor.close()

    def _wrap(self, row: Any) -> CompatRow:
        if isinstance(row, dict):
            return CompatRow(list(row.keys()), row.values())
        return CompatRow(self._keys, row)


class MySQLConnection:
    row_factory: Any = None

    def __init__(self) -> None:
        if pymysql is None:
            raise RuntimeError(
                "DB_TYPE=mysql requires PyMySQL. Install dependencies with "
                "`python -m pip install -r requirements.txt`."
            )
        self._conn = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DATABASE", "ai_generator"),
            charset=os.environ.get("MYSQL_CHARSET", "utf8mb4"),
            autocommit=False,
        )

    def cursor(self) -> MySQLCursor:
        return MySQLCursor(self._conn.cursor())

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def connect(db_path: str | None = None) -> sqlite3.Connection | MySQLConnection:
    if is_mysql_enabled():
        return MySQLConnection()
    return sqlite3.connect(db_path or os.environ.get("DB_PATH", "generation_records.db"))


def initialize_mysql_schema() -> None:
    schema_path = Path(__file__).parent / "scripts" / "schema_mysql.sql"
    conn = connect()
    cursor = conn.cursor()
    try:
        for statement in _split_sql_script(schema_path.read_text(encoding="utf-8")):
            cursor.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements


def _translate_sql(sql: str) -> str:
    sql = sql.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
    sql = re.sub(r"(?<!`)\busage\b(?!`)", "`usage`", sql)
    sql = sql.replace("DATE('now', '-7 days')", "DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
    sql = sql.replace('DATE("now", "-7 days")', "DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
    sql = sql.replace("DATE(date, '+1 day')", "DATE_ADD(date, INTERVAL 1 DAY)")
    sql = re.sub(r"'%'\s*\|\|\s*\?\s*\|\|\s*'%'", "CONCAT('%', ?, '%')", sql)

    placeholder = "__MYSQL_PARAM_PLACEHOLDER__"
    sql = sql.replace("?", placeholder)
    sql = re.sub(r"%(?!%)", "%%", sql)
    return sql.replace(placeholder, "%s")
