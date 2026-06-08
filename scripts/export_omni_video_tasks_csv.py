from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_adapter import connect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export omni_video_tasks with token usage and ledger amount to CSV."
    )
    parser.add_argument(
        "--output",
        help="Output CSV path. Defaults to ai-generator/exports/omni_video_tasks_YYYYMMDD_HHMMSS.csv",
    )
    parser.add_argument("--user-id", type=int, help="Filter by user_id")
    parser.add_argument("--project-id", type=int, help="Filter by project_id")
    parser.add_argument("--status", help="Filter by task status")
    parser.add_argument(
        "--start-date",
        help="Filter tasks created on or after this date/time, e.g. 2026-06-01 or 2026-06-01 00:00:00",
    )
    parser.add_argument(
        "--end-date",
        help="Filter tasks created on or before this date/time, e.g. 2026-06-05 or 2026-06-05 23:59:59",
    )
    return parser


def normalize_start(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 10:
        return f"{value} 00:00:00"
    return value


def normalize_end(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 10:
        return f"{value} 23:59:59"
    return value


def resolve_output_path(raw_output: str | None) -> Path:
    if raw_output:
        output_path = Path(raw_output).expanduser()
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        return output_path

    exports_dir = PROJECT_ROOT / "exports"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return exports_dir / f"omni_video_tasks_{timestamp}.csv"


def fetch_rows(
    user_id: int | None,
    project_id: int | None,
    status: str | None,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    conn = connect()
    cursor = conn.cursor()
    try:
        query = """
            SELECT
                t.task_id,
                t.user_id,
                t.project_id,
                t.created_at,
                t.updated_at,
                t.status,
                t.model,
                t.mode,
                t.prompt,
                t.duration,
                t.resolution,
                t.aspect_ratio,
                t.token_usage,
                l.amount_cent,
                ROUND(l.amount_cent / 100.0, 2) AS amount_yuan,
                l.tokens_raw,
                l.tokens_billed,
                l.unit_price_cent_per_ktoken,
                l.multiplier,
                l.created_at AS ledger_created_at
            FROM omni_video_tasks t
            LEFT JOIN account_ledger l
                ON l.biz_type = 'omni_video'
               AND l.biz_id = t.task_id
               AND l.entry_type = 'debit'
            WHERE 1 = 1
        """
        params: list[object] = []

        if user_id is not None:
            query += " AND t.user_id = ?"
            params.append(user_id)
        if project_id is not None:
            query += " AND t.project_id = ?"
            params.append(project_id)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if start_date:
            query += " AND t.created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND t.created_at <= ?"
            params.append(end_date)

        query += " ORDER BY t.created_at DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "task_id",
        "user_id",
        "project_id",
        "created_at",
        "updated_at",
        "status",
        "model",
        "mode",
        "prompt",
        "duration",
        "resolution",
        "aspect_ratio",
        "token_usage",
        "amount_cent",
        "amount_yuan",
        "tokens_raw",
        "tokens_billed",
        "unit_price_cent_per_ktoken",
        "multiplier",
        "ledger_created_at",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_path = resolve_output_path(args.output)
    rows = fetch_rows(
        user_id=args.user_id,
        project_id=args.project_id,
        status=args.status,
        start_date=normalize_start(args.start_date),
        end_date=normalize_end(args.end_date),
    )
    write_csv(rows, output_path)

    print(f"Exported {len(rows)} rows to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
