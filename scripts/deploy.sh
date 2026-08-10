#!/usr/bin/env bash
# Updates the production deployment: pulls the latest code, rebuilds the
# frontend bundle, then rebuilds and restarts the backend and cron containers.
#
# Run on the production server; resolves the project directory itself, so it
# can be invoked from anywhere:
#     /path/to/LM_V2/scripts/deploy.sh
#
# Migrations and collectstatic run automatically on backend startup
# (see the backend command in docker-compose.prod.yml).
#
# NOTE ON npm ci
# --------------
# Frontend dependencies are installed with `npm ci`, which installs strictly
# from package-lock.json and never writes to it. Do not use `npm install` on
# the server: it rewrites the lockfile, and the resulting local modification
# makes the next `git pull` fail. If that has already happened, discard the
# change once with:
#     git checkout -- lager-frontend/package-lock.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"

cd "$PROJECT_DIR"

echo "[$(date)] Starting deploy..."

# ---------------------------------------------------------------------------
# 1. Pull latest code
# ---------------------------------------------------------------------------
echo "  Pulling latest code..."
git pull

# ---------------------------------------------------------------------------
# 2. Frontend bundle (nginx serves lager-frontend/dist)
# ---------------------------------------------------------------------------
echo "  Installing frontend dependencies..."
npm --prefix lager-frontend ci

echo "  Building frontend..."
npm --prefix lager-frontend run build

# ---------------------------------------------------------------------------
# 3. Backend and cron (both build from ./lagermanager, so both need rebuilding)
# ---------------------------------------------------------------------------
echo "  Rebuilding backend and cron images..."
docker compose -f "$COMPOSE_FILE" build backend cron

echo "  Restarting backend and cron..."
docker compose -f "$COMPOSE_FILE" up -d backend cron

echo "[$(date)] Deploy complete."
