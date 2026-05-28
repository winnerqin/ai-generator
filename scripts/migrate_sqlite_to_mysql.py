"""Copy data from the local SQLite database into the configured MySQL database.

The script preserves primary keys by clearing target tables before inserting.
It intentionally reads MySQL connection settings from `.env`.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable

import pymysql
from dotenv import load_dotenv


TABLE_ORDER = [
    "users",
    "projects",
    "user_projects",
    "generation_records",
    "person_library",
    "scene_library",
    "image_library",
    "video_library",
    "audio_library",
    "deleted_video_library_tasks",
    "video_tasks",
    "omni_video_tasks",
    "video_enhance_tasks",
    "generation_tasks",
    "script_templates",
    "script_saves",
    "script_episode_records",
    "storyboard_saves",
    "storyboard_episode_records",
    "operation_logs",
]


def quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})")]


def mysql_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        return {row[0] for row in cur.fetchall()}


def mysql_columns(conn, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM {quote_ident(table)}")
        return [row[0] for row in cur.fetchall()]


def mysql_connect():
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ["MYSQL_DATABASE"],
        charset=os.environ.get("MYSQL_CHARSET", "utf8mb4"),
        autocommit=False,
    )


def ordered_tables(source_tables: Iterable[str], target_tables: Iterable[str]) -> list[str]:
    common = set(source_tables) & set(target_tables)
    ordered = [table for table in TABLE_ORDER if table in common]
    ordered.extend(sorted(common - set(ordered)))
    return ordered


def clear_mysql_tables(conn, tables: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for table in reversed(tables):
            cur.execute(f"DELETE FROM {quote_ident(table)}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")


def copy_table(sqlite_conn: sqlite3.Connection, mysql_conn, table: str, batch_size: int) -> int:
    source_cols = sqlite_columns(sqlite_conn, table)
    target_cols = mysql_columns(mysql_conn, table)
    columns = [col for col in source_cols if col in target_cols]
    if not columns:
        return 0

    select_sql = (
        "SELECT "
        + ", ".join(quote_ident(col) for col in columns)
        + f" FROM {quote_ident(table)}"
    )
    insert_sql = (
        f"INSERT INTO {quote_ident(table)} ("
        + ", ".join(quote_ident(col) for col in columns)
        + ") VALUES ("
        + ", ".join(["%s"] * len(columns))
        + ")"
    )

    total = 0
    cursor = sqlite_conn.execute(select_sql)
    with mysql_conn.cursor() as mysql_cur:
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            mysql_cur.executemany(insert_sql, rows)
            total += len(rows)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db", default="generation_records.db")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--replace-target",
        action="store_true",
        help="Clear matching MySQL tables before importing SQLite rows.",
    )
    args = parser.parse_args()

    load_dotenv()
    sqlite_path = Path(args.sqlite_db)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    mysql_conn = mysql_connect()
    try:
        integrity = sqlite_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity.lower() != "ok":
            raise SystemExit(f"SQLite integrity_check failed: {integrity}")

        tables = ordered_tables(sqlite_tables(sqlite_conn), mysql_tables(mysql_conn))
        if args.replace_target:
            clear_mysql_tables(mysql_conn, tables)

        total = 0
        for table in tables:
            count = copy_table(sqlite_conn, mysql_conn, table, args.batch_size)
            total += count
            print(f"{table}: {count}")
        mysql_conn.commit()
        print(f"TOTAL: {total}")
    except Exception:
        mysql_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        mysql_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
