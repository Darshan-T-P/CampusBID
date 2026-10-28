# Relay

A modern timed-auction marketplace for college campuses — passing the baton from graduating seniors to juniors.
At the end of the semester, seniors leave cycles, calculators and books behind; instead of fastest-finger chat groups
at guessed prices, every item becomes its own auction: students browse, bid publicly, and the highest bid at closing wins,
pending the seller's approval.

## What it does

- **Campus-only accounts.** Only emails on your campus domain can register, and they must verify with a 6-digit code before listing or bidding.
- **Browse and search** open auctions: keyword, category, condition, price range, "closing soon", sorting, paging. Filters live in the URL, so a view can be shared.
- **Live auction page.** Photos, current price and leader, a full public bid history, and a countdown driven by the *server's* clock. Two browsers see each other's bids within seconds.
- **Fair bidding.** Bids must beat the current price by the seller's minimum raise; you can't bid on your own item or against yourself; two simultaneous bids can't both win; a late bid is impossible even if the closing job lags.
- **Selling.** List an item with 1-5 photos; edit it (only the description and photos once bidding starts); cancel it.
- **Sale workflow.** When an auction ends with a winner, the seller approves or rejects; after approval they confirm the handover or record that the winner didn't collect.
- **Notifications.** A bell with an unread badge, plus opt-in desktop pop-ups when the tab is in the background: outbid, new bid on your item, you won, sale approved/rejected, cancelled, and more.
- **My listings / My bids** pages that say, in plain words, what each auction means for you.

## Quick start

You need Python 3.11+ and Node 20+.

```bash
# 1. Backend (http://localhost:8000, API docs at /docs)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # then set DEV_MODE=true and AUTO_VERIFY=true for local use
.venv/bin/python scripts/seed.py           # optional: demo users + 15 auctions
.venv/bin/uvicorn app.main:app --reload

# 2. Frontend (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

The browser calls the backend under `/api`; the Vite dev server proxies that to FastAPI
(`VITE_API_TARGET` overrides the default `http://localhost:8000`).

## Demo

```bash
cd backend
.venv/bin/python scripts/seed.py            # 5 users + 15 auctions (refuses if already seeded)
.venv/bin/python scripts/seed.py --reset    # wipe ALL data first, then seed
.venv/bin/python scripts/seed.py --clear    # wipe ALL data and stop: an empty app again
```

Seed right before presenting: one auction is set to close in about 90 seconds. Sign in as
`<name>@<your domain>` (default `campus.edu`) with password `password123`:

| User | Role | What they show |
|---|---|---|
| `arjun`, `meera` | final-year sellers | Arjun has a sale awaiting handover; Meera has a sale waiting for her decision |
| `priya`, `rahul`, `sneha` | bidders | Priya leads one auction and is outbid on another |

Suggested walkthrough: browse and filter; open the 90-second auction as Priya in one window and bid as Rahul
in another (watch it update live); let it close; approve the sale as the seller and watch the winner's
notification bell light up.

## Configuration

Set via environment variables or `backend/.env` (see `backend/.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `ALLOWED_EMAIL_DOMAINS` | *(required)* | Comma-separated campus domains; subdomains match. The app refuses to start without it unless `DEV_MODE=true`. |
| `DEV_MODE` | `false` | Local/demo switch: allows running without a domain list; verification codes are printed to the server log. |
| `AUTO_VERIFY` | `false` | Mark new accounts verified immediately (skips the email step). |
| `DATABASE_URL` | `sqlite:///./campusbid.db` | Database location. |
| `SECRET_KEY` | dev value | JWT signing key. **Change it** outside local use. |
| `CLOSER_INTERVAL_SECONDS` | `1` | How often expired auctions are closed; `0` disables the background closer. |

No email service is wired up yet, so verification codes only appear in the server log (dev mode). A real
deployment needs an email transport.

## The rules

Everything about money and time lives in one place (`backend/app/services/`); routes only translate HTTP.

- **Money** is whole rupees (integers), ₹1 to ₹10,000,000. Never floats.
- **A bid is valid** when the listing is open and before its closing time (the server's clock decides), the bidder isn't the seller, the bidder isn't already the highest bidder, and the amount is at least the starting price (first bid) or the current price plus the minimum raise.
- **Auction length** is 10 minutes to 30 days.
- **Races.** Bids, edits, cancels and sale decisions run under SQLite's write lock (`BEGIN IMMEDIATE`), so two simultaneous requests are serialised and exactly one wins.
- **Closing.** A background task closes expired auctions every second; reads and bids also close an overdue auction first ("lazy close"), so a late bid can't slip in. Each closing announces itself exactly once.
- **Outcomes.** `active` → `pending_approval` (has bids) or `unsold` (none) → `reserved` / `rejected` → `completed` / `failed_pickup`; the seller can cancel while `active`. Every end state records a public note.
- **Editing.** Anything can change before the first bid; afterwards only the description and photos, and the page shows an "Edited <time>" marker.
- **Privacy.** Public bid history shows display names only, never emails.

## Tests

```bash
cd backend && .venv/bin/python -m pytest     # 185 tests: rules, races, auth, notifications, seed
cd frontend && npm test                       # 57 tests: formatting, filters, forms, bid logic
```

The concurrency tests prove the lock matters: a bid transaction holds the write lock while an edit or approval
waits, and the waiting action must then refuse because it sees the new state.

## Project layout

```
backend/
  app/
    api/routes/      thin HTTP layer: auth, listings, bids, sale, me, notifications
    services/        all business rules: auction.py (bids, closing), listings.py, sale.py, notifications.py, accounts.py, closer.py
    models/          SQLAlchemy tables (users, listings, listing_images, bids, notifications, email_verifications)
    schemas/         request/response shapes (what the public may see)
  scripts/           seed.py (demo data), dbpeek.py (read-only database viewer)
  tests/
frontend/src/
  pages/             Browse, ListingPage, Sell, EditListing, MyListings, MyBids, Login, Register, Verify
  components/        cards, bid panel, notification bell, photo picker, seller actions, countdown
  lib/ hooks/ api/   pure helpers (with tests), the shared 1-second clock, the API client
docs/PLAN.md         the build plan and the reasoning behind its order
```

## API overview

Interactive docs at `http://localhost:8000/docs`.

| Area | Endpoints |
|---|---|
| Accounts | `POST /auth/register`, `/auth/login`, `/auth/verify`, `/auth/resend-code`; `GET /me` |
| Listings | `GET/POST /listings`, `GET/PATCH /listings/{id}`, `POST /listings/{id}/cancel`, `POST/DELETE /listings/{id}/images` |
| Bids | `POST/GET /listings/{id}/bids` |
| Sale | `POST /listings/{id}/approve`, `/reject`, `/handover`, `/pickup-failed` |
| Mine | `GET /me/listings`, `GET /me/bids` |
| Notifications | `GET /notifications` (`?since_id=` for polling), `POST /notifications/{id}/read`, `/notifications/read-all` |

## Looking at the database

The data is one SQLite file, `backend/campusbid.db`.

- **Quick overview:** `cd backend && .venv/bin/python scripts/dbpeek.py` (read-only, hides password hashes; `-n 20 listings` shows more rows).
- **VS Code:** open the file with the *SQLite Viewer* extension.
- **Your own queries:** `sqlite3 -header -column backend/campusbid.db "select id, title, status, current_price from listings"`.

The server writes through a journal file (`campusbid.db-wal`), so a viewer that opens only the `.db` file can miss the newest rows;
`sqlite3 backend/campusbid.db "PRAGMA wal_checkpoint(TRUNCATE)"` merges them. There are no migrations: on startup the app adds any
new columns to an existing database (it never drops or changes data). Renaming or retyping a column needs the file deleted.

## Not built yet

- **Duplicate-listing protection** (double-submit key, same-photo detection, open-listing cap).
- **Admin role** (suspend users, remove listings, audit log).
- **Email delivery** for verification codes.
- **Optional features:** last-minute extensions, automatic bidding, saved wants, per-auction Q&A, AI assistant.

See [docs/PLAN.md](docs/PLAN.md) for the full plan and why it is ordered the way it is.
