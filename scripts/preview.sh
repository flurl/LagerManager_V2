#!/usr/bin/env bash
# Preview environments: run a branch on the production server next to the live
# stack, on a copy of the production data, without touching production.
#
#   ./scripts/preview.sh create feature/foo              # new preview on the next free port
#   ./scripts/preview.sh update feature/foo              # pull the branch, rebuild, restart
#   ./scripts/preview.sh update feature/foo --reset-db   # ... and re-copy DB + media from prod
#   ./scripts/preview.sh remove feature/foo [-y]         # delete it without leaving traces
#   ./scripts/preview.sh list
#
# Each preview is
#   - a git worktree of this checkout in $LM_PREVIEW_ROOT/<slug>
#     (default: ../lm-previews next to this checkout), detached at the branch's
#     commit, so the production checkout is never touched;
#   - a separate docker compose project "lm-preview-<slug>" built from that
#     worktree's docker-compose.prod.yml: its own containers, network and
#     volumes (database, media, static). Only db, backend and nginx run —
#     never cron, so scheduled alerts are not sent twice;
#   - reachable at https://<prod host>:<port>, ports assigned from 8443 upwards;
#   - started from a copy of the production database (pg_dump | pg_restore,
#     production connections stay untouched) and media files.
#
# Its .env is generated from the production .env with a new secret key, the
# port added to the trusted origins, and PREVIEW_BRANCH set. PREVIEW_BRANCH
# puts a warning banner on every page and redirects all outgoing mail to the
# sender address (see lagermanager/core/mail.py). The frontend banner is baked
# in at build time.
#
# The branch must contain preview support (this script's commit or later);
# older branches are refused because they would bind port 443 and send mail to
# real customers — merge master into them first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROD_ENV_FILE="$PROJECT_DIR/.env"
PROD_COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
PREVIEW_ROOT="${LM_PREVIEW_ROOT:-$(dirname "$PROJECT_DIR")/lm-previews}"

PROJECT_PREFIX="lm-preview-"
FIRST_PORT=8443
PREVIEW_WORKERS=2
# Keys the generated preview .env sets itself; dropped from the copied prod .env.
OVERRIDDEN_KEYS="HTTPS_PORT|GUNICORN_WORKERS|DJANGO_SECRET_KEY|CSRF_TRUSTED_ORIGINS"
OVERRIDDEN_KEYS+="|CORS_ALLOWED_ORIGINS|PREVIEW_[A-Z_]+|GIT_COMMIT|GIT_COMMIT_COUNT"
OVERRIDDEN_KEYS+="|COMPOSE_PROJECT_NAME"

# shellcheck source=lib/branch-slug.sh
source "$SCRIPT_DIR/lib/branch-slug.sh"

cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo "  $*"; }

# Git without hooks: the branch-db post-checkout hook is for the dev stack and
# has no business running inside preview worktrees.
git_nohooks() { git -c core.hooksPath=/dev/null "$@"; }

# Value of KEY in an env file, surrounding quotes stripped.
env_value() {
    local file=$1 key=$2 value
    value=$(sed -nE "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$file" | tail -1)
    value=${value%\"}; value=${value#\"}
    printf '%s' "$value"
}

slug_for() {
    local slug
    slug=$(branch_slug "$1") || die "cannot derive a preview name from '$1'"
    printf '%s' "${slug:0:40}"
}

preview_dir() { printf '%s/%s' "$PREVIEW_ROOT" "$1"; }

prod_compose() { docker compose -f "$PROD_COMPOSE_FILE" "$@"; }

# preview_compose <slug> <compose args...>
preview_compose() {
    local dir
    dir=$(preview_dir "$1"); shift
    docker compose -p "$PROJECT_PREFIX${dir##*/}" --project-directory "$dir" \
        -f "$dir/docker-compose.prod.yml" "$@"
}

# The named volume a container has mounted at /app/media.
media_volume_of() {
    docker inspect -f \
        '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' "$1"
}

port_in_use() { ss -Hltn "sport = :$1" 2>/dev/null | grep -q .; }

next_free_port() {
    local port=$FIRST_PORT used
    used=$(cat "$PREVIEW_ROOT"/*/.env 2>/dev/null | sed -nE 's/^HTTPS_PORT=//p' || true)
    while grep -qx "$port" <<<"$used" || port_in_use "$port"; do
        port=$((port + 1))
    done
    printf '%s' "$port"
}

# "https://a.at,https://b.at" 8443 -> "https://a.at:8443,https://b.at:8443"
origins_with_port() {
    local list=$1 port=$2 origin
    local -a items out=()
    IFS=',' read -ra items <<<"$list"
    for origin in "${items[@]}"; do
        origin=$(printf '%s' "$origin" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s#/+$##')
        [[ -n "$origin" ]] || continue
        origin=$(printf '%s' "$origin" | sed -E 's#^(https?://[^/:]+)(:[0-9]+)?#\1#')
        out+=("$origin:$port")
    done
    (IFS=,; printf '%s' "${out[*]}")
}

# Resolve a branch to a commit, preferring the freshly fetched remote branch.
resolve_ref() {
    local branch=$1
    git_nohooks fetch --quiet origin "$branch" 2>/dev/null || true
    if git rev-parse --verify --quiet "origin/$branch^{commit}" >/dev/null; then
        printf 'origin/%s' "$branch"
    elif git rev-parse --verify --quiet "$branch^{commit}" >/dev/null; then
        printf '%s' "$branch"
    else
        die "branch '$branch' not found (neither origin/$branch nor a local branch)"
    fi
}

# Refuse branches that predate preview support.
require_preview_support() {
    local dir=$1
    grep -q 'HTTPS_PORT' "$dir/docker-compose.prod.yml" \
        && [[ -f "$dir/lagermanager/core/mail.py" ]] \
        && [[ -f "$dir/lager-frontend/src/components/PreviewBanner.vue" ]] \
        || die "this branch predates preview support (it would bind port 443 and" \
               "mail real customers) — merge master into it first"
}

# write_env <slug> <branch> <port> <secret> <snapshot>
write_env() {
    local dir branch=$2 port=$3 secret=$4 snapshot=$5
    dir=$(preview_dir "$1")
    {
        echo "# Generated by scripts/preview.sh from the production .env — do not edit;"
        echo "# rewritten on every update."
        grep -vE "^[[:space:]]*(${OVERRIDDEN_KEYS})[[:space:]]*=" "$PROD_ENV_FILE" || true
        echo
        echo "# --- preview overrides ---"
        echo "HTTPS_PORT=$port"
        echo "GUNICORN_WORKERS=$PREVIEW_WORKERS"
        echo "DJANGO_SECRET_KEY=$secret"
        echo "CSRF_TRUSTED_ORIGINS=$(origins_with_port "$(env_value "$PROD_ENV_FILE" CSRF_TRUSTED_ORIGINS)" "$port")"
        echo "CORS_ALLOWED_ORIGINS=$(origins_with_port "$(env_value "$PROD_ENV_FILE" CORS_ALLOWED_ORIGINS)" "$port")"
        echo "PREVIEW_BRANCH=$branch"
        echo "PREVIEW_SNAPSHOT=\"$snapshot\""
        echo "GIT_COMMIT=$(git -C "$dir" rev-parse --short HEAD)"
        echo "GIT_COMMIT_COUNT=$(git -C "$dir" rev-list --count HEAD)"
    } > "$dir/.env.tmp"
    chmod 600 "$dir/.env.tmp"
    mv "$dir/.env.tmp" "$dir/.env"
}

preview_url() {
    local dir first
    dir=$(preview_dir "$1")
    first=$(env_value "$dir/.env" CSRF_TRUSTED_ORIGINS)
    printf '%s/' "${first%%,*}"
}

build_frontend() {
    local dir branch=$2 snapshot=$3
    dir=$(preview_dir "$1")
    step "Installing frontend dependencies..."
    npm --prefix "$dir/lager-frontend" ci --no-audit --no-fund
    step "Building frontend with preview banner..."
    VITE_PREVIEW_BRANCH="$branch" VITE_PREVIEW_SNAPSHOT="$snapshot" \
        npm --prefix "$dir/lager-frontend" run build
}

# Fresh copy of the production database into the preview's own db container.
copy_database() {
    local slug=$1 db user
    db=$(env_value "$PROD_ENV_FILE" POSTGRES_DB)
    user=$(env_value "$PROD_ENV_FILE" POSTGRES_USER)
    step "Starting preview database..."
    preview_compose "$slug" up -d --wait db
    step "Copying production database '$db'..."
    preview_compose "$slug" exec -T db psql -q -v ON_ERROR_STOP=1 -U "$user" -d postgres \
        -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" \
        -c "CREATE DATABASE \"$db\""
    # pg_dump reads from a snapshot: production keeps running undisturbed.
    prod_compose exec -T db pg_dump -Fc -U "$user" "$db" \
        | preview_compose "$slug" exec -T db \
            pg_restore -U "$user" -d "$db" --no-owner --no-privileges --exit-on-error
}

# Replace the preview's media volume content with production's.
copy_media() {
    local slug=$1 prod_backend preview_backend from to
    prod_backend=$(prod_compose ps -q backend)
    [[ -n "$prod_backend" ]] || die "production backend container not found"
    preview_compose "$slug" create backend nginx >/dev/null
    preview_backend=$(preview_compose "$slug" ps -aq backend)
    from=$(media_volume_of "$prod_backend")
    to=$(media_volume_of "$preview_backend")
    [[ -n "$from" && -n "$to" && "$from" != "$to" ]] \
        || die "could not determine media volumes (prod: '$from', preview: '$to')"
    step "Copying media files ($from -> $to)..."
    docker run --rm -v "$from":/from:ro -v "$to":/to alpine \
        sh -c 'find /to -mindepth 1 -delete && cp -a /from/. /to/'
}

start_services() {
    local slug=$1
    step "Starting backend and nginx..."
    preview_compose "$slug" up -d backend nginx
    # nginx.conf is bind-mounted; restart so edits from the branch apply.
    preview_compose "$slug" restart nginx >/dev/null
}

confirm() {
    local reply
    read -rp "$1 [y/N] " reply
    [[ "$reply" == [yY] ]]
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_create() {
    local branch=${1:-} slug dir ref port snapshot secret
    [[ -n "$branch" ]] || die "usage: $0 create <branch>"
    [[ "$branch" != "master" && "$branch" != "main" ]] \
        || die "master is production — deploy it with scripts/deploy.sh"
    [[ -f "$PROD_ENV_FILE" ]] || die "production .env not found at $PROD_ENV_FILE"
    [[ -n "$(prod_compose ps -q db)" ]] || die "production stack is not running"

    slug=$(slug_for "$branch")
    dir=$(preview_dir "$slug")
    [[ ! -e "$dir" ]] || die "preview '$slug' already exists — use: $0 update $branch"

    ref=$(resolve_ref "$branch")
    port=$(next_free_port)
    snapshot=$(date +'%d.%m.%Y %H:%M')
    secret=$(head -c 48 /dev/urandom | base64 | tr -d '/+=\n')

    echo "[$(date)] Creating preview '$slug' of $ref on port $port..."
    mkdir -p "$PREVIEW_ROOT"
    step "Checking out $ref into $dir..."
    git_nohooks worktree add --quiet --detach "$dir" "$ref"
    if ! (require_preview_support "$dir"); then
        git_nohooks worktree remove --force "$dir"
        rmdir "$PREVIEW_ROOT" 2>/dev/null || true
        exit 1
    fi
    trap '[[ $? -eq 0 ]] || echo "Creating the preview failed. Clean up with: $0 remove $branch -y" >&2' EXIT

    write_env "$slug" "$branch" "$port" "$secret" "$snapshot"
    [[ -d "$PROJECT_DIR/certs" ]] && cp -a "$PROJECT_DIR/certs" "$dir/certs"

    build_frontend "$slug" "$branch" "$snapshot"
    step "Building backend image..."
    preview_compose "$slug" build backend
    copy_database "$slug"
    copy_media "$slug"
    start_services "$slug"

    echo "[$(date)] Preview ready: $(preview_url "$slug")"
    echo "  Migrations run on backend startup; follow them with:"
    echo "    docker compose -p $PROJECT_PREFIX$slug logs -f backend"
}

cmd_update() {
    local branch="" reset_db=0 slug dir ref port secret snapshot
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reset-db) reset_db=1; shift ;;
            -*) die "unknown option for update: $1" ;;
            *) branch=$1; shift ;;
        esac
    done
    [[ -n "$branch" ]] || die "usage: $0 update <branch> [--reset-db]"
    slug=$(slug_for "$branch")
    dir=$(preview_dir "$slug")
    [[ -f "$dir/.env" ]] || die "no preview '$slug' — create it with: $0 create $branch"

    port=$(env_value "$dir/.env" HTTPS_PORT)
    secret=$(env_value "$dir/.env" DJANGO_SECRET_KEY)
    snapshot=$(env_value "$dir/.env" PREVIEW_SNAPSHOT)
    [[ $reset_db -eq 0 ]] || snapshot=$(date +'%d.%m.%Y %H:%M')

    ref=$(resolve_ref "$branch")
    echo "[$(date)] Updating preview '$slug' to $ref..."
    git_nohooks -C "$dir" checkout --quiet --detach "$ref"
    require_preview_support "$dir"
    write_env "$slug" "$branch" "$port" "$secret" "$snapshot"
    if [[ -d "$PROJECT_DIR/certs" ]]; then
        rm -rf "$dir/certs"
        cp -a "$PROJECT_DIR/certs" "$dir/certs"
    fi

    build_frontend "$slug" "$branch" "$snapshot"
    step "Building backend image..."
    preview_compose "$slug" build backend
    if [[ $reset_db -eq 1 ]]; then
        preview_compose "$slug" stop backend nginx
        copy_database "$slug"
        copy_media "$slug"
    fi
    start_services "$slug"
    echo "[$(date)] Preview updated: $(preview_url "$slug")"
}

cmd_remove() {
    local branch="" assume_yes=0 slug dir project
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--yes) assume_yes=1; shift ;;
            -*) die "unknown option for remove: $1" ;;
            *) branch=$1; shift ;;
        esac
    done
    [[ -n "$branch" ]] || die "usage: $0 remove <branch> [-y]"
    slug=$(slug_for "$branch")
    dir=$(preview_dir "$slug")
    project="$PROJECT_PREFIX$slug"
    [[ -d "$dir" ]] || die "no preview '$slug' in $PREVIEW_ROOT"
    [[ "$(cd "$dir" && pwd)" != "$PROJECT_DIR" ]] || die "refusing to remove the production checkout"

    if [[ $assume_yes -eq 0 ]]; then
        confirm "Remove preview '$slug' with its database copy, media copy and checkout?" \
            || { echo "Aborted."; return 0; }
    fi

    echo "[$(date)] Removing preview '$slug'..."
    step "Removing containers, volumes, network and images..."
    if [[ -f "$dir/docker-compose.prod.yml" ]]; then
        preview_compose "$slug" down --volumes --rmi local --remove-orphans
    fi
    # Safety net for anything compose no longer knows about (e.g. a broken worktree).
    docker ps -aq --filter "label=com.docker.compose.project=$project" | xargs -r docker rm -f >/dev/null
    docker volume ls -q --filter "label=com.docker.compose.project=$project" | xargs -r docker volume rm >/dev/null
    docker network ls -q --filter "label=com.docker.compose.project=$project" | xargs -r docker network rm >/dev/null

    step "Removing checkout $dir..."
    # Files the containers wrote into bind mounts are owned by root.
    docker run --rm -v "$dir/lagermanager":/w alpine rm -rf /w/exports
    if ! git_nohooks worktree remove --force "$dir"; then
        docker run --rm -v "$PREVIEW_ROOT":/p alpine rm -rf "/p/$slug"
    fi
    git_nohooks worktree prune
    rmdir "$PREVIEW_ROOT" 2>/dev/null || true
    echo "[$(date)] Preview '$slug' removed."
}

cmd_list() {
    local env_file dir slug running
    shopt -s nullglob
    local -a env_files=("$PREVIEW_ROOT"/*/.env)
    if [[ ${#env_files[@]} -eq 0 ]]; then
        echo "No previews in $PREVIEW_ROOT."
        return 0
    fi
    printf '%-32s %-8s %-10s %-18s %-8s %s\n' BRANCH PORT COMMIT "DATA FROM" STATUS URL
    for env_file in "${env_files[@]}"; do
        dir=$(dirname "$env_file")
        slug=${dir##*/}
        running=$(preview_compose "$slug" ps -q --status running 2>/dev/null | wc -l)
        printf '%-32s %-8s %-10s %-18s %-8s %s\n' \
            "$(env_value "$env_file" PREVIEW_BRANCH)" \
            "$(env_value "$env_file" HTTPS_PORT)" \
            "$(env_value "$env_file" GIT_COMMIT)" \
            "$(env_value "$env_file" PREVIEW_SNAPSHOT)" \
            "$([[ $running -gt 0 ]] && echo "up ($running)" || echo down)" \
            "$(preview_url "$slug")"
    done
}

usage() {
    sed -nE '2,/^[^#]/ { /^#/ { s/^# ?//; p } }' "${BASH_SOURCE[0]}"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
command=${1:-list}
shift || true
case "$command" in
    create) cmd_create "$@" ;;
    update) cmd_update "$@" ;;
    remove|rm) cmd_remove "$@" ;;
    list|ls) cmd_list "$@" ;;
    -h|--help|help) usage ;;
    *) usage >&2; die "unknown command: $command" ;;
esac
