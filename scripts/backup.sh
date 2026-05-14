#!/usr/bin/env bash
# Backs up the PostgreSQL database and media files, then bundles them into
# a single timestamped archive in BACKUP_DIR.
#
# RESTORE
# -------
# 1. Extract the bundle:
#      tar xzf lagermanager_YYYYMMDD_HHMMSS.tar.gz
#
# 2. Restore the database (drop existing connections first if needed):
#      gunzip -c db_YYYYMMDD_HHMMSS.sql.gz | \
#        docker compose -f docker-compose.prod.yml exec -T db \
#        psql -U lagermanager lagermanager
#
# 3. Restore media files:
#      docker run --rm \
#        -v lm_v2_media_data:/media \
#        -v "$PWD":/in \
#        alpine \
#        tar xzf /in/media_YYYYMMDD_HHMMSS.tar.gz -C /media
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

BACKUP_DIR="/srv/backups/lagermanager"
KEEP_DAYS=7

# ---------------------------------------------------------------------------
# Load env vars (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE" >&2
    exit 1
fi
# shellcheck source=/dev/null
set -a; source "$ENV_FILE"; set +a

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

DB_DUMP="$WORK_DIR/db_${TIMESTAMP}.sql.gz"
MEDIA_ARCHIVE="$WORK_DIR/media_${TIMESTAMP}.tar.gz"
FINAL_ARCHIVE="$BACKUP_DIR/lagermanager_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# ---------------------------------------------------------------------------
# 1. Database dump
# ---------------------------------------------------------------------------
echo "  Dumping database..."
docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" exec -T db \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$DB_DUMP"
echo "  DB dump: $(du -sh "$DB_DUMP" | cut -f1)"

# ---------------------------------------------------------------------------
# 2. Media files from Docker volume
# ---------------------------------------------------------------------------
echo "  Archiving media files..."
docker run --rm \
    -v lm_v2_media_data:/media:ro \
    -v "$WORK_DIR":/out \
    alpine \
    tar czf "/out/$(basename "$MEDIA_ARCHIVE")" -C /media .
echo "  Media archive: $(du -sh "$MEDIA_ARCHIVE" | cut -f1)"

# ---------------------------------------------------------------------------
# 3. Bundle into a single archive
# ---------------------------------------------------------------------------
echo "  Bundling into final archive..."
tar czf "$FINAL_ARCHIVE" -C "$WORK_DIR" \
    "$(basename "$DB_DUMP")" \
    "$(basename "$MEDIA_ARCHIVE")"
echo "  Final archive: $(du -sh "$FINAL_ARCHIVE" | cut -f1)"
echo "  Saved to: $FINAL_ARCHIVE"

# ---------------------------------------------------------------------------
# 4. Remove old backups
# ---------------------------------------------------------------------------
echo "  Removing backups older than ${KEEP_DAYS} days..."
find "$BACKUP_DIR" -name "lagermanager_*.tar.gz" -mtime +"$KEEP_DAYS" -delete

echo "[$(date)] Backup complete."
