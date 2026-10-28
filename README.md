# CampusBid

A per-item, timed auction marketplace for a campus. At the end of the semester, seniors
leave cycles, calculators and books behind; instead of fastest-finger chat groups at guessed
prices, juniors bid and the highest bid at closing wins.

Stack: FastAPI + SQLite (SQLAlchemy 2) backend, React/Vite frontend (planned), email+password JWT auth.

The build order and the reasoning behind it are in [docs/PLAN.md](docs/PLAN.md).

## Status

| Milestone | State |
|---|---|
| 1. Backend skeleton (config, DB, models, health) | done |
| 2. Auth (register / login / `/me`) | done |
| 3. Listings, photos, browse/search, edit/cancel, my listings/bids | done |
| 4. Auction engine, bidding, closing, sale workflow | engine, bid API and background closer done; sale workflow next |
| 5. Notifications | |
| 6–8. Frontend, seed data, demo polish | |

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

If you change the models, delete the local `backend/campusbid.db*` files: there are no migrations.

## Design notes

- Money is whole rupees (integers), never floats.
- Server time is the only clock; all auction rules live in one service (`app/services/`).
- Datetimes are stored and returned as timezone-aware UTC.
