from __future__ import annotations

import argparse
import csv
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_adapter import connect
import database


def to_cent(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def has_video_reference(reference_urls_json: object) -> bool:
    if not reference_urls_json:
        return False
    urls = reference_urls_json
    if isinstance(urls, str):
        try:
            urls = json.loads(urls)
        except Exception:
            return False
    if not isinstance(urls, list):
        return False

    video_exts = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
    return any(Path(str(url or "")).suffix.lower() in video_exts for url in urls)


def effective_multiplier(row: dict) -> Decimal:
    role_code = row.get("role_code") or database.ROLE_EXTERNAL_USER
    role_multiplier = Decimal(str(database.get_role_pricing_multiplier(role_code) or 1))
    user_multiplier = Decimal(str(row.get("pricing_multiplier") or 1))
    return user_multiplier if user_multiplier > 0 else role_multiplier


def price_to_cny_cent(price_per_million_token_cent: int, currency_code: str) -> Decimal:
    value = Decimal(str(price_per_million_token_cent or 0))
    if (currency_code or "").upper() == database.MODEL_CURRENCY_USD:
        return value * Decimal(str(database.USD_TO_CNY_RATE))
    return value


def estimate_amount_yuan(row: dict) -> str | None:
    if row.get("amount_yuan") not in (None, ""):
        return row.get("amount_yuan")
    if row.get("token_usage") in (None, "") or not row.get("model"):
        return None

    pricing = database.resolve_model_pricing(
        model_code=row.get("model"),
        resolution=row.get("resolution"),
        has_video_reference=has_video_reference(row.get("reference_urls_json")),
    )
    if not pricing:
        return None

    multiplier = effective_multiplier(row)
    tokens_billed = to_cent(Decimal(int(row.get("token_usage") or 0)) * multiplier)
    price_per_million_cny_cent = price_to_cny_cent(
        int(pricing.get("price_per_million_token_cent") or 0),
        str(pricing.get("currency_code") or database.MODEL_CURRENCY_CNY),
    )
    unit_price_cent_per_ktoken = price_per_million_cny_cent / Decimal(1000)
    amount_cent = to_cent((Decimal(tokens_billed) / Decimal(1000)) * unit_price_cent_per_ktoken)
    return f"{amount_cent / 100:.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export omni_video_tasks summary with Chinese headers to CSV."
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
                u.username,
                u.role_code,
                u.pricing_multiplier,
                t.status,
                t.model,
                t.created_at,
                t.duration,
                t.resolution,
                t.reference_urls_json,
                t.token_usage,
                ROUND(l.amount_cent / 100.0, 2) AS amount_yuan
            FROM omni_video_tasks t
            LEFT JOIN users u
                ON u.id = t.user_id
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
    columns = [
        ("任务ID", "task_id"),
        ("用户名", "username"),
        ("状态", "status"),
        ("模型", "model"),
        ("创建时间", "created_at"),
        ("时长", "duration"),
        ("token用量", "token_usage"),
        ("金额", "amount_yuan"),
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=[label for label, _ in columns])
        writer.writeheader()
        for row in rows:
            row["amount_yuan"] = estimate_amount_yuan(row)
            writer.writerow({label: row.get(key) for label, key in columns})


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
