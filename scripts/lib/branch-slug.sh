# shellcheck shell=bash
# Shared by branch-db.sh and preview.sh: maps a branch name to an identifier
# usable as a database, docker compose project and directory name.

# feature/Foo-Bar -> feature_foo_bar. Fails (prints nothing) if nothing usable remains.
branch_slug() {
    local slug
    slug=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
           | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//')
    [[ -n "$slug" ]] || return 1
    printf '%s' "$slug"
}
