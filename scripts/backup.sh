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
# 3. Restore media files. Mount the volume at /data, *not* /media: /media is a
#    non-empty directory in the alpine image, so Docker would copy its
#    cdrom/floppy/usb stubs into the volume whenever the volume is empty.
#    Use the volume the backend really has mounted at /app/media:
#      VOL=$(docker inspect -f \
#        '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' \
#        "$(docker compose -f docker-compose.prod.yml ps -q backend)")
#      docker run --rm \
#        -v "$VOL":/data \
#        -v "$PWD":/in \
#        alpine \
#        tar xzf /in/media_YYYYMMDD_HHMMSS.tar.gz -C /data
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
# Ask the running backend which volume is actually mounted at MEDIA_ROOT instead
# of hardcoding the name. Compose derives it from the project name, so a renamed
# deployment directory would otherwise make `docker run -v <name>:...` silently
# create a new, empty volume and back that up.
BACKEND_CID=$(docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" ps -q backend)
if [[ -z "$BACKEND_CID" ]]; then
    echo "ERROR: backend container is not running - cannot resolve media volume" >&2
    exit 1
fi
MEDIA_VOLUME=$(docker inspect -f \
    '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' \
    "$BACKEND_CID")
if [[ -z "$MEDIA_VOLUME" ]]; then
    echo "ERROR: no named volume mounted at /app/media in the backend container" >&2
    exit 1
fi
echo "  Media volume: $MEDIA_VOLUME"

# Mount at /data, not /media: /media is non-empty in the alpine image, so Docker
# would copy its cdrom/floppy/usb stubs into an empty volume before we read it.
docker run --rm \
    -v "$MEDIA_VOLUME":/data:ro \
    -v "$WORK_DIR":/out \
    alpine \
    tar czf "/out/$(basename "$MEDIA_ARCHIVE")" -C /data .
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
