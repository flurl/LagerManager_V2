# LagerManager V2

Web-based rewrite of the LagerManager desktop application. Manages warehouse inventory, supplier deliveries, POS data integration, and reporting for a hospitality business.

**Stack:** Django 5 + Django REST Framework · PostgreSQL 16 · Vue 3 + Vuetify 3 · Vite

---

## Prerequisites

- Docker + Docker Compose
- Node.js (v18+)
- Python 3.12 (for running backend outside Docker)

---

## Startup

### 1. Start the database and backend

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** on `localhost:5432`
- **Django backend** on `localhost:8000`

First run — apply migrations and create an admin user:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

### 2. Start the frontend

```bash
cd lager-frontend
npm install
npm run dev
```

Frontend is available at **http://localhost:5173**.
Vite proxies all `/api/*` requests to the Django backend.

---

## URLs

| Service | URL |
|---------|-----|
| Frontend (SPA) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/ |
| Django Admin | http://localhost:8000/admin/ |
| Database | localhost:5432 (user/pass: `lagermanager`) |

---

## Accessing the database

Connect via the running Docker container:

```bash
docker compose exec db psql -U lagermanager
```

Or connect directly from the host (requires `psql` installed locally):

```bash
psql -h localhost -p 5432 -U lagermanager -d lagermanager
```

Password: `lagermanager`

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

