#!/usr/bin/env bash
# Per-branch development databases.
#
# A feature branch that adds migrations changes the database schema, so its
# database can no longer be used by other branches (and vice versa). Instead of
# migrating up and down around every `git switch`, every branch gets its own
# database inside the existing `db` container: cheap, and a clone via
# `CREATE DATABASE ... TEMPLATE` copies the full data set, not just the schema.
#
# The active database is selected by `DB_NAME` in ./.env, which
# docker-compose.yml substitutes into DATABASE_URL for `backend` and `cron`.
# `master`/`main` map to the base database (lagermanager); every other branch
# maps to lm_<sanitised-branch-name>.
#
#   ./scripts/branch-db.sh status            # what is active, what exists
#   ./scripts/branch-db.sh list
#   ./scripts/branch-db.sh create            # clone the active DB for this branch
#   ./scripts/branch-db.sh create foo --from lagermanager
#   ./scripts/branch-db.sh switch            # point the stack at this branch's DB
#   ./scripts/branch-db.sh switch master
#   ./scripts/branch-db.sh drop feature/foo
#   ./scripts/branch-db.sh sync              # used by the post-checkout hook
#   ./scripts/branch-db.sh install-hook      # install that hook
#
# Only touches the development stack (docker-compose.yml). Production runs from
# docker-compose.prod.yml and keeps its own DATABASE_URL in .env.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

BASE_DB="lagermanager"     # database used by master/main
DB_USER="lagermanager"
DB_PREFIX="lm_"            # prefix marking a database as branch-owned
MANAGED_SERVICES=(backend cron)

cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die() { echo "ERROR: $*" >&2; exit 1; }

current_branch() {
    git symbolic-ref --quiet --short HEAD 2>/dev/null || return 1
}

# master/main -> base database; anything else -> lm_<slug>, capped at the
# 63-character PostgreSQL identifier limit.
db_name_for_branch() {
    local branch=$1 slug
    if [[ "$branch" == "master" || "$branch" == "main" ]]; then
        printf '%s' "$BASE_DB"
        return
    fi
    slug=$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]' \
           | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//')
    [[ -n "$slug" ]] || die "cannot derive a database name from branch '$branch'"
    printf '%s%s' "$DB_PREFIX" "${slug:0:$((63 - ${#DB_PREFIX}))}"
}

# Database the stack currently points at.
active_db() {
    local value=""
    if [[ -f "$ENV_FILE" ]]; then
        value=$(sed -nE 's/^[[:space:]]*DB_NAME[[:space:]]*=[[:space:]]*//p' "$ENV_FILE" | tail -1)
        value=${value%\"}; value=${value#\"}
    fi
    printf '%s' "${value:-$BASE_DB}"
}

set_active_db() {
    local name=$1
    touch "$ENV_FILE"
    if grep -qE '^[[:space:]]*DB_NAME[[:space:]]*=' "$ENV_FILE"; then
        sed -i -E "s|^[[:space:]]*DB_NAME[[:space:]]*=.*|DB_NAME=${name}|" "$ENV_FILE"
    else
        printf 'DB_NAME=%s\n' "$name" >> "$ENV_FILE"
    fi
}

db_container_running() {
    docker compose ps --services --status running 2>/dev/null | grep -qx db
}

require_db_container() {
    db_container_running && return 0
    echo "Starting the db container..."
    docker compose up -d --wait db >/dev/null
}

psql_postgres() {
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d postgres "$@"
}

db_exists() {
    local name=$1 found
    found=$(psql_postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$name'" | tr -d '[:space:]')
    [[ "$found" == "1" ]]
}

terminate_connections() {
    local name=$1
    psql_postgres -tAc "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
                        WHERE datname = '$name' AND pid <> pg_backend_pid()" >/dev/null
}

# Services from MANAGED_SERVICES that are up right now — so a stack running
# without `cron` does not silently gain it on the next switch.
running_managed_services() {
    local running service
    running=$(docker compose ps --services --status running 2>/dev/null || true)
    for service in "${MANAGED_SERVICES[@]}"; do
        grep -qx "$service" <<<"$running" && printf '%s\n' "$service"
    done
    return 0
}

restart_services() {
    local services=("$@")
    [[ ${#services[@]} -gt 0 ]] || return 0
    docker compose up -d --wait "${services[@]}" >/dev/null
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_status() {
    local branch="" mapped="" active
    active=$(active_db)
    if branch=$(current_branch); then
        mapped=$(db_name_for_branch "$branch")
        echo "Branch:       $branch"
        echo "Branch DB:    $mapped"
    else
        echo "Branch:       (detached HEAD)"
    fi
    echo "Active DB:    $active   (DB_NAME in .env)"
    if db_container_running; then
        db_exists "$active" || echo "              WARNING: '$active' does not exist yet"
        if [[ -n "$mapped" && "$mapped" != "$active" ]]; then
            if db_exists "$mapped"; then
                echo "              branch DB exists but is not active — run: $0 switch"
            else
                echo "              branch DB does not exist — run: $0 create"
            fi
        fi
    else
        echo "              (db container not running; existence not checked)"
    fi
    echo
    cmd_list
}

cmd_list() {
    require_db_container
    local active
    active=$(active_db)
    echo "Databases:"
    psql_postgres -tAc "SELECT d.datname, pg_size_pretty(pg_database_size(d.datname)) \
                        FROM pg_database d \
                        WHERE d.datname = '$BASE_DB' OR d.datname LIKE '${DB_PREFIX}%' \
                        ORDER BY d.datname" \
    | while IFS='|' read -r name size; do
        [[ -n "$name" ]] || continue
        if [[ "$name" == "$active" ]]; then
            printf '  * %-45s %s\n' "$name" "$size"
        else
            printf '    %-45s %s\n' "$name" "$size"
        fi
    done
}

cmd_create() {
    local branch="" template="" switch_after=1
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --from) template=${2:-}; shift 2 ;;
            --no-switch) switch_after=0; shift ;;
            -*) die "unknown option for create: $1" ;;
            *) branch=$1; shift ;;
        esac
    done
    [[ -n "$branch" ]] || branch=$(current_branch) || die "detached HEAD — pass a branch name"

    local target
    target=$(db_name_for_branch "$branch")
    if [[ "$target" == "$BASE_DB" ]]; then
        die "'$branch' maps to the base database '$BASE_DB' — nothing to create"
    fi

    require_db_container
    db_exists "$target" && die "database '$target' already exists (use 'switch' or 'drop')"

    [[ -n "$template" ]] || template=$(active_db)
    db_exists "$template" || die "template database '$template' does not exist"

    # CREATE DATABASE ... TEMPLATE requires the template to have no other
    # sessions, so the app containers have to let go of it first.
    local -a restart=()
    mapfile -t restart < <(running_managed_services)
    if [[ ${#restart[@]} -gt 0 ]]; then
        echo "Stopping ${restart[*]} (the template must have no open connections)..."
        docker compose stop "${restart[@]}" >/dev/null
    fi
    terminate_connections "$template"

    echo "Creating '$target' from template '$template' (full copy, data included)..."
    psql_postgres -c "CREATE DATABASE \"$target\" TEMPLATE \"$template\"" >/dev/null

    if [[ $switch_after -eq 1 ]]; then
        set_active_db "$target"
        echo "Active database is now '$target'."
    fi
    restart_services "${restart[@]}"
    echo "Done. Apply this branch's migrations with:"
    echo "  docker compose exec backend python manage.py migrate"
}

cmd_switch() {
    local branch="" target=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --db) target=${2:-}; shift 2 ;;
            -*) die "unknown option for switch: $1" ;;
            *) branch=$1; shift ;;
        esac
    done
    if [[ -z "$target" ]]; then
        [[ -n "$branch" ]] || branch=$(current_branch) || die "detached HEAD — pass a branch name or --db"
        target=$(db_name_for_branch "$branch")
    fi

    require_db_container
    db_exists "$target" || die "database '$target' does not exist — create it with: $0 create${branch:+ $branch}"

    if [[ "$(active_db)" == "$target" ]]; then
        echo "Already using '$target'."
        return 0
    fi

    set_active_db "$target"
    local -a restart=()
    mapfile -t restart < <(running_managed_services)
    echo "Switched to '$target'.${restart[*]:+ Recreating ${restart[*]}...}"
    restart_services "${restart[@]}"
}

cmd_drop() {
    local branch="" target="" assume_yes=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --db) target=${2:-}; shift 2 ;;
            -y|--yes) assume_yes=1; shift ;;
            -*) die "unknown option for drop: $1" ;;
            *) branch=$1; shift ;;
        esac
    done
    if [[ -z "$target" ]]; then
        [[ -n "$branch" ]] || branch=$(current_branch) || die "detached HEAD — pass a branch name or --db"
        target=$(db_name_for_branch "$branch")
    fi

    [[ "$target" != "$BASE_DB" ]] || die "refusing to drop the base database '$BASE_DB'"
    [[ "$target" != "$(active_db)" ]] || die "'$target' is the active database — switch away first: $0 switch master"

    require_db_container
    db_exists "$target" || die "database '$target' does not exist"

    if [[ $assume_yes -eq 0 ]]; then
        read -rp "Permanently drop database '$target' and all its data? [y/N] " reply
        [[ "$reply" == [yY] ]] || { echo "Aborted."; return 0; }
    fi

    terminate_connections "$target"
    psql_postgres -c "DROP DATABASE \"$target\"" >/dev/null
    echo "Dropped '$target'."
}

# Called by the post-checkout hook: quiet when there is nothing to do, and
# never fatal — a checkout must not fail because Docker is down.
cmd_sync() {
    local branch target active
    branch=$(current_branch) || return 0
    target=$(db_name_for_branch "$branch") || return 0
    active=$(active_db)
    [[ "$target" != "$active" ]] || return 0
    db_container_running || return 0

    if db_exists "$target"; then
        cmd_switch --db "$target"
        return 0
    fi

    if [[ "${BRANCH_DB_AUTOCREATE:-0}" == "1" ]]; then
        cmd_create "$branch"
        return 0
    fi

    echo "branch-db: '$branch' has no database yet; still using '$active'."
    echo "branch-db: before applying migrations on this branch, run:"
    echo "           ./scripts/branch-db.sh create"
}

cmd_install_hook() {
    local force=0
    [[ "${1:-}" == "--force" ]] && force=1
    local hooks_dir source_hook
    hooks_dir="$(cd "$(git rev-parse --git-common-dir)" && pwd)/hooks"
    source_hook="$SCRIPT_DIR/hooks/post-checkout"
    [[ -f "$source_hook" ]] || die "hook template not found at $source_hook"
    mkdir -p "$hooks_dir"

    local target="$hooks_dir/post-checkout"
    if [[ -e "$target" && ! -L "$target" && $force -eq 0 ]]; then
        die "$target already exists and is not a symlink — inspect it, then re-run with --force"
    fi
    ln -sfn "$source_hook" "$target"
    echo "Installed $target -> $source_hook"
}

usage() {
    sed -nE '2,/^[^#]/ { /^#/ { s/^# ?//; p } }' "${BASH_SOURCE[0]}"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
command=${1:-status}
shift || true
case "$command" in
    status)       cmd_status "$@" ;;
    list)         cmd_list "$@" ;;
    create)       cmd_create "$@" ;;
    switch|use)   cmd_switch "$@" ;;
    drop)         cmd_drop "$@" ;;
    sync)         cmd_sync "$@" ;;
    install-hook) cmd_install_hook "$@" ;;
    -h|--help|help) usage ;;
    *) usage >&2; die "unknown command: $command" ;;
esac
