#!/usr/bin/env python3
"""Safely identify and quarantine redundant files under uploads.

The default mode is read-only. A file is eligible only when all of these are true:

1. It is older than ``--min-age-days``.
2. No database field references its local ``/uploads/...`` path.
3. A database field contains a matching OSS URL.
4. OSS HEAD succeeds and the object size equals the local file size.

By default, ``--execute`` moves files to quarantine. Permanent deletion needs
the additional explicit ``--permanently-delete --yes`` confirmation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv


LOGGER = logging.getLogger("cleanup-uploads")
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
LOCAL_UPLOAD_PATTERN = re.compile(r"(?:https?://[^\s\"'<>]+)?/uploads/[^\s\"'<>]+")
TEXT_TYPES = {
    "char",
    "varchar",
    "tinytext",
    "text",
    "mediumtext",
    "longtext",
    "json",
}
LIKELY_REFERENCE_COLUMN = re.compile(r"(url|path|file|reference)", re.IGNORECASE)
LARGE_AUDIT_COLUMN = re.compile(r"(payload|raw|result|meta|input|output)", re.IGNORECASE)


@dataclass(frozen=True)
class RemoteReference:
    url: str
    object_key: str
    table: str
    column: str


@dataclass
class FileDecision:
    path: str
    relative_path: str
    size: int
    modified_at: str
    action: str
    reason: str
    oss_url: str = ""
    oss_object_key: str = ""
    database_source: str = ""
    quarantine_path: str = ""


def _endpoint_host(value: str) -> str:
    endpoint = str(value or "").strip()
    if not endpoint:
        return ""
    return (urlsplit(endpoint if "://" in endpoint else f"//{endpoint}").hostname or "").lower()


def _extract_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _extract_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _extract_strings(item)


def _strings_from_database_value(value: Any) -> Iterator[str]:
    if value is None:
        return
    if isinstance(value, (dict, list, tuple)):
        yield from _extract_strings(value)
        return
    text = str(value).strip()
    if not text:
        return
    if text[:1] in ("{", "["):
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError):
            decoded = None
        if decoded is not None:
            yield from _extract_strings(decoded)
    yield text
    yield from URL_PATTERN.findall(text)
    yield from LOCAL_UPLOAD_PATTERN.findall(text)


def _normalize_local_reference(value: str, upload_root: Path) -> str | None:
    text = unquote(str(value or "").strip()).replace("\\", "/")
    if not text:
        return None

    parsed = urlsplit(text) if text.startswith(("http://", "https://")) else None
    candidate = parsed.path if parsed else text
    marker = "/uploads/"
    if marker in candidate:
        return candidate.split(marker, 1)[1].lstrip("/")

    try:
        path = Path(text).resolve(strict=False)
        return path.relative_to(upload_root).as_posix()
    except (OSError, ValueError):
        return None


def _remote_object_key(value: str, allowed_hosts: set[str]) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if not text.startswith(("http://", "https://")):
        return None
    parsed = urlsplit(text)
    host = (parsed.hostname or "").lower()
    if not host or host not in allowed_hosts:
        return None
    object_key = unquote(parsed.path).lstrip("/")
    if not object_key:
        return None
    return text, object_key


def _identity_from_path(path: str) -> tuple[str, str, str]:
    parts = PurePosixPath(path).parts
    user = next((part for part in parts if re.fullmatch(r"user_\d+", part)), "")
    project = next((part for part in parts if re.fullmatch(r"project_\d+", part)), "")
    return user, project, parts[-1] if parts else ""


def _validated_identifier(value: str) -> str:
    if not SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _should_scan_column(column: str, data_type: str) -> bool:
    if data_type.lower() not in TEXT_TYPES:
        return False
    # Dedicated reference columns are authoritative and usually compact, even
    # when their names also contain "input".
    if "reference" in column.lower():
        return True
    return bool(LIKELY_REFERENCE_COLUMN.search(column)) and not LARGE_AUDIT_COLUMN.search(column)


def _database_reference_columns(connection, database_name: str) -> list[tuple[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (database_name,),
        )
        rows = cursor.fetchall()
    columns = []
    for row in rows:
        table = str(row[0])
        column = str(row[1])
        data_type = str(row[2]).lower()
        if _should_scan_column(column, data_type):
            columns.append((_validated_identifier(table), _validated_identifier(column)))
    return columns


def load_database_references(
    connection, database_name: str, upload_root: Path, allowed_hosts: set[str]
) -> tuple[dict[str, set[str]], list[RemoteReference]]:
    local_sources: dict[str, set[str]] = defaultdict(set)
    remote_references: list[RemoteReference] = []

    columns = _database_reference_columns(connection, database_name)
    LOGGER.info("[1/4] Scanning %d database text/JSON columns", len(columns))
    total_rows = 0
    started = time.monotonic()
    for column_index, (table, column) in enumerate(columns, start=1):
        column_rows = 0
        LOGGER.info("[1/4] DB column %d/%d: %s.%s", column_index, len(columns), table, column)
        sql = (
            f"SELECT `{column}` FROM `{table}` "
            f"WHERE CAST(`{column}` AS CHAR) LIKE %s OR CAST(`{column}` AS CHAR) LIKE %s"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, ("%/uploads/%", "%://%"))
            while True:
                rows = cursor.fetchmany(500)
                if not rows:
                    break
                column_rows += len(rows)
                total_rows += len(rows)
                for row in rows:
                    for text in _strings_from_database_value(row[0]):
                        local = _normalize_local_reference(text, upload_root)
                        if local:
                            local_sources[local].add(f"{table}.{column}")
                        remote = _remote_object_key(text, allowed_hosts)
                        if remote:
                            url, object_key = remote
                            remote_references.append(
                                RemoteReference(url, object_key, table, column)
                            )
        LOGGER.info(
            "[1/4] DB column %d/%d complete: rows=%d total_rows=%d elapsed=%.1fs",
            column_index,
            len(columns),
            column_rows,
            total_rows,
            time.monotonic() - started,
        )
    LOGGER.info(
        "[1/4] Database scan complete: rows=%d local_refs=%d remote_refs=%d elapsed=%.1fs",
        total_rows,
        len(local_sources),
        len(remote_references),
        time.monotonic() - started,
    )
    return local_sources, remote_references


def _build_remote_index(
    references: Iterable[RemoteReference],
) -> dict[tuple[str, str, str], list[RemoteReference]]:
    index: dict[tuple[str, str, str], list[RemoteReference]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for reference in references:
        identity = _identity_from_path(reference.object_key)
        unique = (reference.url, reference.table, reference.column)
        if unique in seen:
            continue
        seen.add(unique)
        index[identity].append(reference)
    return index


def _iter_upload_files(upload_root: Path) -> Iterator[Path]:
    for root, directories, files in os.walk(upload_root, followlinks=False):
        root_path = Path(root)
        safe_directories = []
        for name in directories:
            candidate = root_path / name
            if candidate.is_symlink():
                LOGGER.warning("Skipping symlinked directory: %s", candidate)
            else:
                safe_directories.append(name)
        directories[:] = safe_directories
        for name in files:
            candidate = root_path / name
            if candidate.is_symlink():
                LOGGER.warning("Skipping symlinked file: %s", candidate)
                continue
            if candidate.is_file():
                yield candidate


class OSSVerifier:
    def __init__(self, endpoint: str, access_key_id: str, access_key_secret: str):
        try:
            import oss2
        except ImportError as exc:  # pragma: no cover - production dependency check
            raise RuntimeError("oss2 is not installed; install requirements.txt first") from exc

        endpoint_host = _endpoint_host(endpoint)
        parts = endpoint_host.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid OSS endpoint: {endpoint!r}")
        bucket_name, service_endpoint = parts
        auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(auth, f"https://{service_endpoint}", bucket_name)
        self.cache: dict[str, tuple[str, int | None]] = {}

    def _head_uncached(self, object_key: str) -> tuple[str, int | None]:
        try:
            result = self.bucket.head_object(object_key)
            outcome = ("ok", int(result.content_length))
        except Exception as exc:  # distinguish missing from operational failures in report
            status = getattr(exc, "status", None)
            if status == 404 or "NoSuchKey" in str(exc):
                outcome = ("missing", None)
            else:
                outcome = (f"error:{type(exc).__name__}:{exc}", None)
        return outcome

    def head(self, object_key: str) -> tuple[str, int | None]:
        cached = self.cache.get(object_key)
        if cached:
            return cached
        outcome = self._head_uncached(object_key)
        self.cache[object_key] = outcome
        return outcome

    def prefetch(self, object_keys: Iterable[str], workers: int, progress_every: int) -> None:
        keys = sorted({key for key in object_keys if key and key not in self.cache})
        total = len(keys)
        if not total:
            LOGGER.info("[3/4] No OSS objects require verification")
            return

        LOGGER.info("[3/4] Verifying %d OSS objects with %d workers", total, workers)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="oss-head") as executor:
            futures = {executor.submit(self._head_uncached, key): key for key in keys}
            for completed, future in enumerate(as_completed(futures), start=1):
                key = futures[future]
                try:
                    self.cache[key] = future.result()
                except Exception as exc:  # defensive: _head_uncached normally converts errors
                    self.cache[key] = (f"error:{type(exc).__name__}:{exc}", None)
                if completed % progress_every == 0 or completed == total:
                    elapsed = time.monotonic() - started
                    rate = completed / elapsed if elapsed else 0
                    eta = (total - completed) / rate if rate else 0
                    LOGGER.info(
                        "[3/4] OSS progress: %d/%d (%.1f%%) rate=%.1f/s ETA=%.1fs",
                        completed,
                        total,
                        completed * 100 / total,
                        rate,
                        eta,
                    )


def decide_file(
    file_path: Path,
    upload_root: Path,
    cutoff: datetime,
    local_sources: dict[str, set[str]],
    remote_index: dict[tuple[str, str, str], list[RemoteReference]],
    verifier: OSSVerifier,
) -> FileDecision:
    stat = file_path.stat()
    relative = file_path.relative_to(upload_root).as_posix()
    modified = datetime.fromtimestamp(stat.st_mtime)
    base = FileDecision(
        path=str(file_path),
        relative_path=relative,
        size=stat.st_size,
        modified_at=modified.isoformat(timespec="seconds"),
        action="KEEP",
        reason="",
    )

    sources = local_sources.get(relative)
    if sources:
        base.reason = "database_references_local_file"
        base.database_source = ",".join(sorted(sources))
        return base
    if modified > cutoff:
        base.reason = "newer_than_retention_cutoff"
        return base

    identity = _identity_from_path(relative)
    candidates = remote_index.get(identity, [])
    if not candidates:
        base.action = "REVIEW"
        base.reason = "no_matching_oss_url_in_database"
        return base

    errors = []
    for reference in candidates:
        status, remote_size = verifier.head(reference.object_key)
        if status == "ok" and remote_size == stat.st_size:
            base.action = "ELIGIBLE"
            base.reason = "database_uses_verified_oss_copy"
            base.oss_url = reference.url
            base.oss_object_key = reference.object_key
            base.database_source = f"{reference.table}.{reference.column}"
            return base
        errors.append(f"{reference.object_key}:{status}:size={remote_size}")

    base.action = "REVIEW"
    base.reason = "oss_missing_unreachable_or_size_mismatch:" + "|".join(errors[:5])
    return base


def _move_to_quarantine(decision: FileDecision, upload_root: Path, quarantine_root: Path) -> None:
    source = Path(decision.path).resolve(strict=True)
    source.relative_to(upload_root)
    destination = (quarantine_root / decision.relative_path).resolve(strict=False)
    destination.relative_to(quarantine_root)
    if destination.exists():
        raise FileExistsError(f"Quarantine destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    decision.quarantine_path = str(destination)


def _permanently_delete(decision: FileDecision, upload_root: Path) -> None:
    source = Path(decision.path).resolve(strict=True)
    source.relative_to(upload_root)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Refusing to delete non-regular file: {source}")
    source.unlink()
    decision.quarantine_path = "<permanently-deleted>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uploads-dir",
        default=os.environ.get("UPLOAD_FOLDER", "/opt/ai_generator/uploads"),
        help="Uploads directory (default: UPLOAD_FOLDER or /opt/ai_generator/uploads)",
    )
    parser.add_argument("--min-age-days", type=int, default=7)
    parser.add_argument("--execute", action="store_true", help="Process eligible files")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation when --execute is supplied",
    )
    parser.add_argument(
        "--quarantine-dir",
        default="",
        help="Destination outside uploads; a timestamped sibling is used by default",
    )
    parser.add_argument(
        "--permanently-delete",
        action="store_true",
        help="With --execute --yes, delete eligible files instead of quarantining them",
    )
    parser.add_argument("--report", default="", help="Optional JSON Lines report path")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N files (0 = all)")
    parser.add_argument("--oss-workers", type=int, default=16, help="Concurrent OSS HEAD requests")
    parser.add_argument(
        "--db-timeout",
        type=int,
        default=120,
        help="MySQL connect/read/write timeout in seconds",
    )
    parser.add_argument(
        "--progress-every", type=int, default=100, help="Print progress every N items"
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.min_age_days < 1:
        raise ValueError("--min-age-days must be at least 1")
    if args.execute and not args.yes:
        raise ValueError("--execute requires --yes")
    if args.permanently_delete and not args.execute:
        raise ValueError("--permanently-delete requires --execute --yes")
    if not 1 <= args.oss_workers <= 64:
        raise ValueError("--oss-workers must be between 1 and 64")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be at least 1")
    if args.db_timeout < 10:
        raise ValueError("--db-timeout must be at least 10 seconds")

    upload_root = Path(args.uploads_dir).resolve(strict=True)
    if not upload_root.is_dir() or upload_root.is_symlink():
        raise ValueError(f"Uploads path must be a real directory: {upload_root}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_root = Path(
        args.quarantine_dir or upload_root.parent / f"uploads_quarantine_{timestamp}"
    ).resolve(strict=False)
    if quarantine_root == upload_root or upload_root in quarantine_root.parents:
        raise ValueError("Quarantine directory must be outside uploads")

    db_name = os.environ.get("MYSQL_DATABASE", "ai_generator")
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - production dependency check
        raise RuntimeError("pymysql is not installed; install requirements.txt first") from exc

    connection = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=db_name,
        charset=os.environ.get("MYSQL_CHARSET", "utf8mb4"),
        connect_timeout=args.db_timeout,
        read_timeout=args.db_timeout,
        write_timeout=args.db_timeout,
    )

    oss_endpoint = os.environ.get("OSS_ACCESS_ENDPOINT") or os.environ.get("OSS_ENDPOINT", "")
    external_endpoint = os.environ.get("OSS_EXTERNAL_ENDPOINT", "")
    allowed_hosts = {
        host
        for host in (
            _endpoint_host(oss_endpoint),
            _endpoint_host(os.environ.get("OSS_ENDPOINT", "")),
            _endpoint_host(external_endpoint),
            "short-oss.aidcstore.net",
        )
        if host
    }
    verifier = OSSVerifier(
        oss_endpoint,
        os.environ.get("OSS_ACCESS_KEY_ID", ""),
        os.environ.get("OSS_ACCESS_KEY_SECRET", ""),
    )

    try:
        local_sources, remote_references = load_database_references(
            connection, db_name, upload_root, allowed_hosts
        )
    finally:
        connection.close()

    remote_index = _build_remote_index(remote_references)
    cutoff = datetime.now() - timedelta(days=args.min_age_days)
    counts: dict[str, int] = defaultdict(int)
    bytes_by_action: dict[str, int] = defaultdict(int)
    decisions: list[FileDecision] = []

    LOGGER.info("[2/4] Inventorying files under %s", upload_root)
    inventory_started = time.monotonic()
    files = list(_iter_upload_files(upload_root))
    if args.limit:
        files = files[: args.limit]
    inventory_bytes = sum(path.stat().st_size for path in files)
    LOGGER.info(
        "[2/4] Inventory complete: files=%d size=%.3f GiB elapsed=%.1fs",
        len(files),
        inventory_bytes / 1024**3,
        time.monotonic() - inventory_started,
    )

    object_keys = set()
    for file_path in files:
        stat = file_path.stat()
        relative = file_path.relative_to(upload_root).as_posix()
        if relative in local_sources or datetime.fromtimestamp(stat.st_mtime) > cutoff:
            continue
        for reference in remote_index.get(_identity_from_path(relative), []):
            object_keys.add(reference.object_key)
    verifier.prefetch(object_keys, args.oss_workers, args.progress_every)

    LOGGER.info("[4/4] Classifying and processing %d files", len(files))
    processing_started = time.monotonic()
    for index, file_path in enumerate(files, start=1):
        try:
            decision = decide_file(
                file_path,
                upload_root,
                cutoff,
                local_sources,
                remote_index,
                verifier,
            )
            if args.execute and decision.action == "ELIGIBLE":
                if args.permanently_delete:
                    _permanently_delete(decision, upload_root)
                else:
                    _move_to_quarantine(decision, upload_root, quarantine_root)
        except Exception as exc:
            stat = file_path.stat()
            decision = FileDecision(
                path=str(file_path),
                relative_path=file_path.relative_to(upload_root).as_posix(),
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                action="ERROR",
                reason=f"{type(exc).__name__}:{exc}",
            )
        decisions.append(decision)
        counts[decision.action] += 1
        bytes_by_action[decision.action] += decision.size
        if index % args.progress_every == 0 or index == len(files):
            elapsed = time.monotonic() - processing_started
            rate = index / elapsed if elapsed else 0
            eta = (len(files) - index) / rate if rate else 0
            LOGGER.info(
                "[4/4] File progress: %d/%d (%.1f%%) rate=%.1f/s ETA=%.1fs "
                "eligible=%d keep=%d review=%d error=%d",
                index,
                len(files),
                index * 100 / len(files) if files else 100,
                rate,
                eta,
                counts["ELIGIBLE"],
                counts["KEEP"],
                counts["REVIEW"],
                counts["ERROR"],
            )

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as report:
            for decision in decisions:
                report.write(json.dumps(asdict(decision), ensure_ascii=False) + "\n")

    if args.permanently_delete:
        mode = "EXECUTE (permanently deleted verified files)"
    elif args.execute:
        mode = "EXECUTE (moved verified files to quarantine)"
    else:
        mode = "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Uploads: {upload_root}")
    print(f"Cutoff: {cutoff.isoformat(timespec='seconds')}")
    if args.execute and not args.permanently_delete:
        print(f"Quarantine: {quarantine_root}")
    for action in ("ELIGIBLE", "KEEP", "REVIEW", "ERROR"):
        size_gb = bytes_by_action[action] / 1024**3
        print(f"{action}: files={counts[action]} size={size_gb:.3f} GiB")
    if args.report:
        print(f"Report: {Path(args.report).resolve()}")
    return 1 if counts["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main())
