#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性清理 video_library 重复记录（按 source_task_id + filename + user_id + project_id 去重）。

规则：
1. 只处理 meta 中包含 source_task_id 的记录。
2. 相同 (source_task_id, filename, user_id, project_id) 视为重复组。
3. 每组保留“最新”一条（created_at DESC, id DESC），其余删除。

默认行为是 dry-run，仅输出计划删除项；传入 --apply 才执行删除。

用法：
    python scripts/dedupe_video_library_by_source_task.py
    python scripts/dedupe_video_library_by_source_task.py --apply
    python scripts/dedupe_video_library_by_source_task.py --db-path generation_records.db --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AssetRow:
    id: int
    user_id: int
    project_id: int | None
    filename: str
    created_at: str
    source_task_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 source_task_id + filename + user_id + project_id 去重 video_library。")
    parser.add_argument("--db-path", default="generation_records.db", help="SQLite 数据库路径（默认: generation_records.db）")
    parser.add_argument("--apply", action="store_true", help="执行删除（默认仅预览，不删除）")
    return parser.parse_args()


def load_rows(conn: sqlite3.Connection) -> list[AssetRow]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user_id, project_id, filename, created_at, meta
        FROM video_library
        WHERE meta IS NOT NULL AND meta != ''
        """
    )
    rows: list[AssetRow] = []
    for row in cur.fetchall():
        meta_raw = row["meta"] or "{}"
        try:
            meta: dict[str, Any] = json.loads(meta_raw)
        except Exception:
            continue
        source_task_id = str(meta.get("source_task_id") or "").strip()
        if not source_task_id:
            continue
        rows.append(
            AssetRow(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                project_id=row["project_id"],
                filename=str(row["filename"] or ""),
                created_at=str(row["created_at"] or ""),
                source_task_id=source_task_id,
            )
        )
    return rows


def build_delete_plan(rows: list[AssetRow]) -> tuple[list[AssetRow], dict[tuple[Any, ...], list[AssetRow]]]:
    groups: dict[tuple[Any, ...], list[AssetRow]] = defaultdict(list)
    for r in rows:
        key = (r.source_task_id, r.filename, r.user_id, r.project_id)
        groups[key].append(r)

    to_delete: list[AssetRow] = []
    for _, group_rows in groups.items():
        if len(group_rows) <= 1:
            continue
        # 最新优先：created_at DESC, id DESC
        ordered = sorted(group_rows, key=lambda x: (x.created_at, x.id), reverse=True)
        to_delete.extend(ordered[1:])
    return to_delete, groups


def apply_delete(conn: sqlite3.Connection, rows: list[AssetRow]) -> int:
    if not rows:
        return 0
    ids = [r.id for r in rows]
    cur = conn.cursor()
    cur.executemany("DELETE FROM video_library WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    return cur.rowcount


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"[ERROR] 数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        rows = load_rows(conn)
        to_delete, groups = build_delete_plan(rows)

        dup_group_count = sum(1 for g in groups.values() if len(g) > 1)
        print(f"[INFO] 扫描记录（含 source_task_id）: {len(rows)}")
        print(f"[INFO] 重复分组数量: {dup_group_count}")
        print(f"[INFO] 计划删除记录数: {len(to_delete)}")

        preview_limit = 30
        if to_delete:
            print(f"[INFO] 删除预览（最多显示 {preview_limit} 条）:")
            for r in to_delete[:preview_limit]:
                print(
                    f"  - id={r.id}, user_id={r.user_id}, project_id={r.project_id}, "
                    f"source_task_id={r.source_task_id}, filename={r.filename}, created_at={r.created_at}"
                )
            if len(to_delete) > preview_limit:
                print(f"  ... 其余 {len(to_delete) - preview_limit} 条省略")

        if not args.apply:
            print("[DRY-RUN] 未执行删除。传入 --apply 才会真正删除。")
            return 0

        deleted = apply_delete(conn, to_delete)
        print(f"[DONE] 已删除重复记录: {deleted}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    # Windows 终端编码友好
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())

