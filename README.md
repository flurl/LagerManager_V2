# LagerManager V2

Web-based rewrite of the LagerManager desktop application. Manages warehouse inventory, supplier deliveries, POS data integration, and reporting for a hospitality business.

**Stack:** Django 5 + Django REST Framework · PostgreSQL 16 · Vue 3 + Vuetify 3 · Vite

---

## Prerequisites

- Docker + Docker Compose
- Node.js (v18+)
- Python 3.12 (only needed for running the backend outside Docker)

---

## Install

### 1. Clone and configure

```bash
git clone <repo-url>
cd LagerManager_V2
cp .env.example .env
```

Edit `.env` and set at minimum:
- `POSTGRES_PASSWORD` — strong database password
- `DJANGO_SECRET_KEY` — long random string
- `DJANGO_ALLOWED_HOSTS` — your domain(s)
- `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS` — your origin(s)

### 2. Install frontend dependencies

```bash
cd lager-frontend
npm install
```

---

## Development

### Start database and backend

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** on `localhost:5432`
- **Django backend** on `localhost:8000` (via `runserver`)

First run — apply migrations and create an admin user:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

### Start the frontend dev server

```bash
cd lager-frontend
npm run dev
```

Frontend is available at **http://localhost:5173**.  
Vite proxies all `/api/*` requests to the Django backend.

### Per-branch databases

A feature branch that adds migrations changes the schema, so its database no
longer matches the models on other branches — switching back to `master` can
break inserts (a new `NOT NULL` column), reads (a renamed or dropped column) or
constraints. `scripts/branch-db.sh` gives every branch its own database inside
the existing `db` container; `DB_NAME` in `.env` selects which one the
`backend` and `cron` containers use.

```bash
./scripts/branch-db.sh install-hook   # once: switch databases on git checkout
./scripts/branch-db.sh status         # branch, active database, what exists
./scripts/branch-db.sh create         # clone the active DB for this branch
./scripts/branch-db.sh switch master  # point the stack at another branch's DB
./scripts/branch-db.sh drop feature/x # after the branch is merged
./scripts/branch-db.sh list
```

`create` uses `CREATE DATABASE ... TEMPLATE`, a **full physical copy** — schema
*and* data, in a couple of seconds. It therefore needs the template database to
have no open connections, so it stops `backend`/`cron` for the duration and
restarts exactly those that were running. After creating the clone, apply the
branch's new migrations to it:

```bash
docker compose exec backend python manage.py migrate
```

`master` and `main` map to the base database `lagermanager`; every other branch
maps to `lm_<sanitised-branch-name>`. The installed `post-checkout` hook
switches automatically when the branch's database exists, and otherwise just
prints a reminder to create it — it never fails a checkout, and does nothing
when the dev stack is not running. Set `BRANCH_DB_AUTOCREATE=1` to have the
hook clone the database on checkout instead of reminding you.

Notes:

- Only the development stack is affected. `docker-compose.prod.yml` keeps its
  own `DATABASE_URL` from `.env`.
- The `media_data` volume (attachments) is **shared** across branch databases,
  so a row may reference a file another branch deleted.
- Tests are unaffected either way — Django always builds a fresh `test_*`
  database.
- Each clone costs as much disk as the original; drop them when branches are
  merged.

---

## Production

Uses `docker-compose.prod.yml` with Gunicorn, Nginx (HTTPS), and a built frontend bundle.

### First-time setup

```bash
npm --prefix lager-frontend ci
npm --prefix lager-frontend run build
docker compose -f docker-compose.prod.yml up -d
```

Migrations and `collectstatic` run automatically on backend startup.  
Nginx serves the frontend bundle and static files, and terminates TLS.  
Place your certificates in `./certs/` (referenced in `nginx.conf`).

### Deploying an update

```bash
./scripts/deploy.sh
```

Pulls the latest code, reinstalls frontend dependencies, rebuilds the bundle,
then rebuilds and restarts the `backend` and `cron` containers, and finally
restarts `nginx`. Both backend and cron build from `./lagermanager`, so both
have to be rebuilt — restarting only `backend` leaves the scheduled jobs
running the previous code.

**Why nginx is restarted too.** Recreating the backend container gives it a new
IP. A bare hostname in `proxy_pass` is resolved once when nginx loads its
config and cached for the life of the process, so nginx kept proxying to the
old address and every `/api/` request returned 502 while the SPA itself still
loaded fine. `nginx.conf` now resolves the upstream per request (see the
`resolver` there), which fixes it on its own; the restart in the deploy is a
second line of defence and also picks up `nginx.conf` edits.

**Use `npm ci`, never `npm install`, on the server.** `npm ci` installs strictly
from `package-lock.json` and never writes to it; `npm install` rewrites the
lockfile, and the resulting local modification makes the next `git pull` fail.
If that has already happened, discard the change once:

```bash
git checkout -- lager-frontend/package-lock.json
```

---

## URLs

### Development

| Service | URL |
|---------|-----|
| Frontend (SPA) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/ |
| Django Admin | http://localhost:8000/admin/ |
| Database | localhost:5432 (user/pass: `lagermanager`) |

---

## Accessing the database

Via Docker:

```bash
docker compose exec db psql -U lagermanager
```

Or directly from the host (requires `psql`):

```bash
psql -h localhost -p 5432 -U lagermanager -d lagermanager
```

---

## Running the backend without Docker

Requires a local PostgreSQL instance with a `lagermanager` database.

```bash
cd lagermanager
source ../.venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## Linting

```bash
.venv/bin/ruff check lagermanager/   # lint
.venv/bin/ruff format lagermanager/  # format
```

---

## Tests

Requires the Docker backend to be running (`docker compose up -d`).

```bash
docker compose exec backend python manage.py test --verbosity=2
```

---

## Backend Apps

| App | Purpose |
|-----|---------|
| `core` | `Period` (accounting periods), `Location` (bars/warehouses), `Config` |
| `inventory` | Stock tracking: `PeriodStartStockLevel`, `InitialInventory`, `PhysicalCount` |
| `deliveries` | `Partner`, `StockMovement`, `StockMovementDetail`, `TaxRate`, `Attachment` |
| `stock_count` | Physical inventory counts |
| `staff_consumption` | Staff consumption tracking — kiosk UI with offline IndexedDB support |
| `exports` | WZ export — writes semicolon-delimited CSV to the server export directory |
| `pos_import` | Read-only POS mirror from MSSQL (Wiffzack): articles, recipes, receipts |
| `reports` | Aggregated analytics, CSV exports, chart data endpoints |