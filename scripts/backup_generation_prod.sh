#!/usr/bin/env bash

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/dbbackup}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-generation_prod}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%F_%H-%M-%S)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

if ! command -v mysqldump >/dev/null 2>&1; then
  echo "未找到 mysqldump，请先安装 MySQL Client。" >&2
  exit 1
fi

if ! command -v gzip >/dev/null 2>&1; then
  echo "未找到 gzip，请先安装 gzip。" >&2
  exit 1
fi

export MYSQL_PWD="${DB_PASSWORD}"

mysqldump \
  --single-transaction \
  --quick \
  --routines \
  --triggers \
  --no-tablespaces \
  --default-character-set=utf8mb4 \
  -h "${DB_HOST}" \
  -P "${DB_PORT}" \
  -u "${DB_USER}" \
  "${DB_NAME}" | gzip > "${BACKUP_FILE}"

unset MYSQL_PWD

find "${BACKUP_DIR}" \
  -maxdepth 1 \
  -type f \
  -name "${DB_NAME}_*.sql.gz" \
  -mtime +"$((RETENTION_DAYS - 1))" \
  -delete

echo "备份完成: ${BACKUP_FILE}"
