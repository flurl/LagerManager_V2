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

---

## Production

Uses `docker-compose.prod.yml` with Gunicorn, Nginx (HTTPS), and a built frontend bundle.

### Build frontend

```bash
cd lager-frontend
npm run build
```

### Start production stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

Migrations and `collectstatic` run automatically on backend startup.  
Nginx serves the frontend bundle and static files, and terminates TLS.  
Place your certificates in `./certs/` (referenced in `nginx.conf`).

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