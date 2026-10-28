# CampusBid

A per-item, timed auction marketplace for a campus. At the end of the semester, seniors
leave cycles, calculators and books behind; instead of fastest-finger chat groups at guessed
prices, juniors bid and the highest bid at closing wins.

Stack: FastAPI + SQLite (SQLAlchemy 2) backend, React + Vite frontend (plain JavaScript), email+password JWT auth.

The build order and the reasoning behind it are in [docs/PLAN.md](docs/PLAN.md).

## Status

| Milestone | State |
|---|---|
| 1. Backend skeleton (config, DB, models, health) | done |
| 2. Auth (register / login / `/me`) | done |
| 3. Listings, photos, browse/search, edit/cancel, my listings/bids | done |
| 4. Auction engine, bidding, closing, sale workflow | done |
| 5. Notifications | done |
| 6. Frontend: scaffold, login/register/verify, browse with filters | done |
| 6. Frontend: auction page with live bidding | done |
| 6. Frontend: create listing (photos, closing-time presets) | done |
| 6. Frontend: my listings (seller actions) / my bids, notifications UI | next |
| 7–8. Seed data, demo polish | |

## Run the backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload      # http://localhost:8000, docs at /docs
.venv/bin/python -m pytest                   # run tests
```

Configuration is via environment variables or `backend/.env` (see `backend/.env.example`).

**Campus-only accounts.** Set `ALLOWED_EMAIL_DOMAINS` (comma-separated, subdomains match). The app
refuses to start without it unless `DEV_MODE=true`. New users must verify their campus email with a
6-digit code before they can list or bid; unverified users can browse. For local demos set
`DEV_MODE=true` (codes are printed to the server log) and `AUTO_VERIFY=true` (skip the code step).
No email transport is wired up yet, so a real deployment still needs one.

There are no migrations. On startup the app adds any new columns to an existing local database
(it never drops or changes data). Renaming or retyping a column still needs the local
`backend/campusbid.db*` files deleted.

## Run the frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 (needs the backend running on :8000)
npm run build    # production build
npm test         # unit tests (formatting, filters, URL handling)
```

The browser calls the backend under `/api`; the Vite dev server proxies that to FastAPI
(`VITE_API_TARGET` overrides the target, default `http://localhost:8000`).

## Look at the database

The data is one SQLite file, `backend/campusbid.db`.

- **In VS Code:** click the file in the Explorer (the *SQLite Viewer* extension opens it as tables).
- **Quick text overview:** `cd backend && .venv/bin/python scripts/dbpeek.py` (read-only, hides password hashes; `-n 20 listings` shows more rows).
- **Your own queries:** `sqlite3 -header -column backend/campusbid.db "select id, title, status, current_price from listings"`.

The server writes through a journal file (`campusbid.db-wal`), so a viewer that opens only the `.db` file can miss
the newest rows. `sqlite3 backend/campusbid.db "PRAGMA wal_checkpoint(TRUNCATE)"` merges them. Don't edit the
data by hand while the server is running.

## Design notes

- Money is whole rupees (integers), never floats.
- Server time is the only clock; all auction rules live in one service (`app/services/`).
- Datetimes are stored and returned as timezone-aware UTC.
