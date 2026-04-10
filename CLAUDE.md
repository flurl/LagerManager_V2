# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Web migration of a legacy PyQt4/Python2 desktop warehouse management app (LagerManager) to a Django REST + Vue 3 SPA. Manages warehouse inventory, supplier deliveries, POS data integration, and reporting for a hospitality business.

## Dev Environment

```bash
# Start database and backend (PostgreSQL + Django via Docker)
docker compose up -d

# Run frontend dev server
cd lager-frontend && npm run dev
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/api/
- Django Admin: http://localhost:8000/admin/

Vite proxies `/api/*` to the Django backend on `:8000`.

### Backend (without Docker)
```bash
cd lagermanager
source ../.venv/bin/activate  # or your venv
python manage.py migrate
python manage.py runserver
```

### Frontend
```bash
cd lager-frontend
npm install
npm run dev    # dev server
npm run build  # production build
```

**Linting:** `ruff` is installed in `.venv`. Run from the project root:
```bash
.venv/bin/ruff check lagermanager/   # lint
.venv/bin/ruff format lagermanager/  # format
```

**Tests:** Run from the project root (requires the Docker backend to be running):
```bash
docker compose exec backend python manage.py test --verbosity=2
```

## Architecture

### Stack
- **Backend:** Django 5.0 + Django REST Framework, PostgreSQL 16, JWT auth (simplejwt)
- **Frontend:** Vue 3, Vuetify 3, Pinia, Vue Router, Axios, Chart.js, Vite
- **MSSQL Bridge:** pymssql — reads POS data from legacy Wiffzack system (synchronous, no Celery)

### Backend Apps (`lagermanager/`)

| App | Purpose |
|-----|---------|
| `core` | `Period` (accounting periods), `Location` (bars/warehouses), `Config` |
| `inventory` | Stock tracking: `PeriodStartStockLevel`, `InitialInventory`, `PhysicalCount` |
| `deliveries` | `Partner`, `PartnerAiInstruction`, `StockMovement`, `StockMovementDetail`, `TaxRate`, `Attachment` |
| `pos_import` | Read-only POS mirror from MSSQL: `TischBon`, `TischBonDetail`, `RechnungBasis`, `Article`, `ArticleGroup`, `Recipe`, `WarehouseArticle`, `WarehouseUnit`, `ArticleMeta`, etc. |
| `reports` | Aggregated analytics, CSV exports, chart data endpoints |

Every major entity links to a `Period` — this is the fundamental multi-period isolation mechanism.

**Key services:**
- `core/services/purchase_price.py` — Weighted average cost (EK) calculation
- `inventory/services/stock_calculation.py` — Complex UNION query: Initial + Deliveries − Consumption
- `inventory/services/init_period.py` — Period initialisation logic
- `reports/services/` — Report-specific query services (consumption, stock level, inventory, total movements)
- `pos_import/services/mssql_import.py` — Synchronous blocking POS sync (1000-item bulk_create batches, 10-min Axios timeout on frontend)
- `StockMovement.apply_skonto()` — Skonto (percentage discount) applied directly as a model method

**Stock formula:** `Current Stock = PeriodStartStockLevel + Deliveries − Consumption`
Consumption uses recipe decomposition: a sold item decomposes into its ingredient articles via the `Recipe` model.

### Frontend (`lager-frontend/src/`)

- `main.js` — Vue app bootstrap (Vuetify, Pinia, Router)
- `router.js` — Routes (German labels), all guarded by JWT auth
- `api.js` — Axios instance with Bearer token interceptor
- `stores/auth.js` — JWT tokens in localStorage, login/logout
- `stores/period.js` — Currently selected accounting period (shared state)
- `views/` — One component per route (`{Feature}View.vue`)
- `views/reports/` — Report views (`{Feature}{Type}Report.vue`, e.g. `StockLevelChartReport.vue`)
- `components/AppShell.vue` — Main layout with navigation drawer
- `ai/` — AI provider abstraction (Gemini, Mistral) used for OCR/document processing on attachments

### AI Integration

`lager-frontend/src/ai/` contains a provider abstraction for AI-assisted document processing:
- Providers: `GeminiProvider`, `MistralProvider`
- Mistral requires a merged PDF (all attachments combined server-side before the API call)
- Provider selection and API keys come from Django Constance config (`/api/config/`)

### `null=True` on String Fields

Many string/text fields across all apps use `null=True, blank=True` — this is intentional because they mirror a legacy schema where those columns already contain NULLs (especially all `pos_import` models which are imported from MSSQL). DJ001 is suppressed in `ruff.toml` for this reason.

**When writing code that reads these fields, always handle both `None` and `""` as empty.** Do not assume a blank string field is non-null. When adding *new* string fields to non-legacy models, prefer `blank=True` without `null=True` per Django convention.

### POS Import Design
- MSSQL records store original `source_id` as IntegerField; uniqueness is `unique_together(['source_id', 'period'])`
- Import is triggered from `ImportDialog.vue` via a long HTTP request (synchronous, no job queue)

### Locale
German/Austria (`de-at`), timezone `Europe/Vienna`.

## Testing Policy

- Every feature and every feature modification must be accompanied by a suitable test, unless there is a clear reason why a test is not practical (e.g. a thin view that only proxies a serializer, or pure UI glue code).
- For new features, prefer TDD: write the failing test first, then implement.
- Tests live in `<app>/tests/` and use Django's `TestCase`. Run via:
  ```bash
  docker compose exec backend python manage.py test --verbosity=2
  ```

## Legacy Reference
`lagerManager/` — Original PyQt4/Python 2 desktop app. Read-only reference for business logic. Do not modify.
