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
| 4. Auction engine, bidding, closing, sale workflow | engine + tests done; bid route, closer, sale workflow next |
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

## Design notes

- Money is whole rupees (integers), never floats.
- Server time is the only clock; all auction rules live in one service (`app/services/`).
- Datetimes are stored and returned as timezone-aware UTC.
