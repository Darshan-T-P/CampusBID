# CampusBid — Implementation Plan

## Context
Final-semester exam week: seniors leave items (cycles, calculators, books) and juniors currently buy them via fastest-finger chat groups at guessed prices. CampusBid is a per-item timed auction marketplace for a campus. The brief has a mandatory **Basics** layer (listings, browsing, bidding, closing/sale, notifications) and five optional **Key features** (AI assistant, Q&A, saved wants, last-minute extensions, auto-bidding).

Decision from the user: **build and polish the Basics first; Key features come last.** Stack: FastAPI + SQLite + React/Vite; email+password JWT auth. Repo is greenfield (empty `backend/app/{api/routes,services,models,schemas,db,core}`, `backend/tests`, `docs`, empty README).

Judging cares about: public GitHub repo with frequent commits, one planning chat session (this one), and being able to justify what we chose and in what order.

## Development strategy
**Core = the auction engine, not the UI.** Everything a judge will probe ("can I bid late?", "does the increment hold?", "who wins a tie?", "what happens at close?") lives in one place. So we de-risk in this order:
1. **Engine first, test-first.** `services/auction.py` (`place_bid`, `close_if_due`, state transitions) with pytest and an injectable clock *before* any UI. Highest risk (concurrency, time), cheapest to verify headlessly.
2. **Thin vertical slices over layers.** Each slice = model → service → route → test → UI → commit, in this order: auth → create/browse listing → bid → close/sale → notifications. After each slice the app is runnable and demo-able, so we never end with "backend done, nothing works".
3. **Freeze the API contract early.** FastAPI's OpenAPI schema is the contract; frontend consumes it from slice 3 onward, so backend and frontend can proceed without rework.
4. **Extension points, not speculative features.** Single `place_bid` entry, generic `Notification`, mutable `closes_at`, public `is_auto` on `Bid` — the five Key features then slot in without schema rewrites.
5. **Cut line is explicit.** Basics must be complete and demoed (seed data + README) before any Key feature starts. Key features then go in ascending effort / descending value (extensions → auto-bid → wants → Q&A → AI), and each is independently shippable, so stopping at any point leaves a coherent app.
6. **Commit discipline:** one commit per finished piece, conventional messages (`feat(bids): ...`, `test(auction): ...`) so history reads as the build story.

**Core parts at a glance (priority order):** (1) bid validation + atomic placement, (2) closing worker + lazy close, (3) sale state machine with explicit outcomes, (4) public bid history/privacy boundary, (5) live countdown driven by server time, (6) notifications (in-app + browser pop-up).

## Guiding decisions (and why)
- **Correctness of the auction engine is the product.** All money/time rules live in one service (`services/auction.py`), used by every route, the background closer, and later the auto-bidder and AI assistant. Routes stay thin.
- **Server time is the only clock.** Clients render countdowns from `closes_at` plus a server-time offset, never decide validity.
- **Closing is both lazy and scheduled.** A background asyncio task sweeps every ~1s for listings past `closes_at`, *and* `place_bid`/reads call `ensure_closed(listing)` so a stale sweep can never allow a late bid.
- **Bids placed in one `BEGIN IMMEDIATE` transaction** (SQLite write lock): re-read listing + current price, validate, insert bid. Prevents two racing bids both passing the increment check.
- **Money = integer rupees.** No floats.
- **Public bidding.** Bid history returns bidder display name, amount, time. Never email/phone (matters later for the AI assistant).
- **Design now for Key features, build later:** `Bid` carries `is_auto` and `place_bid` is the single insertion point (so proxy bidding and anti-sniping bolt in); `Notification` is a generic table (so saved-want matches and Q&A alerts reuse it); `closes_at` is mutable on `Listing` (extensions).

## Data model (SQLAlchemy 2.x, SQLite)
- **User**: id, email (unique), password_hash, display_name, created_at.
- **Listing**: id, seller_id, title, category (enum: cycle, calculator, books, electronics, other…), description, condition (enum: new, like_new, good, fair, poor), starting_price, min_increment, closes_at, status, current_price (nullable), leading_bid_id (nullable), created_at, updated_at, outcome_note.
- **ListingImage**: id, listing_id, path, position.
- **Bid**: id, listing_id, bidder_id, amount, created_at, is_auto (default false).
- **Notification**: id, user_id, type, title, body, listing_id, created_at, read_at.

### Listing status state machine
```
active ──(closes_at passes, ≥1 bid)──▶ pending_approval ──approve──▶ reserved ──handover confirmed──▶ completed
   │                                          │                         └──pickup failed──▶ failed_pickup
   │                                          └──reject──▶ rejected
   ├──(closes_at passes, 0 bids)──▶ unsold
   └──seller cancels──▶ cancelled
```
Every terminal state records a clear outcome (status + `outcome_note`) and notifies the affected users.

## API surface (`backend/app/api/routes`)
- `auth`: `POST /auth/register`, `POST /auth/login`, `GET /me`.
- `listings`: `POST /listings` (multipart with photos), `GET /listings` (query `q`, `category`, `condition`, `min_price`, `max_price`, `closing_soon`, `status`, `sort`), `GET /listings/{id}` (details + leading bid + server_time), `PATCH /listings/{id}` (edit), `POST /listings/{id}/cancel`, `GET /me/listings`, `GET /me/bids`.
- `bids`: `POST /listings/{id}/bids`, `GET /listings/{id}/bids` (full public history).
- `sale`: `POST /listings/{id}/approve`, `/reject`, `/handover` (seller confirms handover → completed), `/pickup-failed`.
- `notifications`: `GET /notifications` (supports `since` for polling), `POST /notifications/{id}/read`, `POST /notifications/read-all`.
- `GET /health`, static `/media/*` for photos.

## Business rules (all in `services/auction.py`, unit-tested with an injectable clock)
- **Create:** `closes_at` must be in the future; `starting_price ≥ 1`; `min_increment ≥ 1`; 1–5 photos (type/size limited).
- **Bid valid iff:** listing `active` AND `now < closes_at` AND bidder ≠ seller AND amount ≥ (`starting_price` if no bids else `current_price + min_increment`). Ties impossible by construction; earliest bid wins on equal amounts regardless.
- **Edit:** while no bids: any field. After a bid: only description/photos (price, increment, closing time, category frozen so bidders aren't misled). Only while `active`.
- **Cancel:** seller may cancel while `active` (even with bids) → status `cancelled`, bidders notified.
- **Close:** highest bid → `pending_approval`, winner provisional; none → `unsold`.
- **Approve:** seller only, from `pending_approval` → `reserved`, notify winner. **Reject** → `rejected`, notify winner. **Handover** from `reserved` → `completed`; **pickup-failed** → `failed_pickup`.
- **Notification triggers:** outbid, new bid on my listing, auction won (provisional), auction ended unsold/cancelled, approved/rejected, listing I bid on cancelled, ending-soon for items I bid on (optional, if time permits).

## Frontend (`frontend/`, React + Vite + TypeScript, React Router, TanStack Query)
Pages: Login/Register · Browse (search box, category/condition/price filters, "closing soon" toggle, cards with live countdown) · Auction detail (gallery, leading bid, bid form with min-valid hint, full bid history, countdown, seller panel) · Create/Edit listing · My listings (seller actions: approve/reject/handover/pickup-failed/cancel) · My bids · Notification bell + dropdown.
- **Live updates:** TanStack Query polling (2–3s on the detail page, 15s elsewhere) — simple and robust; upgrade to SSE only if time remains.
- **Countdown:** shared `useCountdown(closesAt, serverOffset)` hook; shows "Closed" and disables the bid form on expiry, backend still authoritative.
- **Browser notifications:** an opt-in "Enable alerts" button calls `Notification.requestPermission()`; the notification poller fires `new Notification(...)` for new unseen items when `document.hidden`. No service worker/push needed (brief only requires background-tab pop-ups).
- Vite dev proxy to FastAPI; production build optionally served by FastAPI static mount.

## Milestones (each ends in a commit; repo created first)
0. **Repo bootstrap:** create public GitHub repo (`gh repo create CampusBid --public --source=. --push`), `.gitignore`, README stub, this plan copied to `docs/PLAN.md`. *Note: `gh` is logged in as `darshan-tp-adg` while git user is `Darshan-T-P` — confirm which account should own the repo before creating it.*
1. **Backend skeleton:** FastAPI app, config, DB session, models, Alembic-free `create_all`, health route. Commit.
2. **Auth:** register/login/JWT, `get_current_user` dependency. Commit.
3. **Listings CRUD + images + search/filter.** Commit.
4. **Auction engine + bidding + closing worker + sale workflow** with pytest coverage (increment rule, late bid, own-item bid, concurrent bids, closing with/without bids, every state transition and permission). Commit per sub-piece.
5. **Notifications backend.** Commit.
6. **Frontend scaffold + auth + browse/detail/create/my-pages.** Commit per page group.
7. **Notifications UI + browser pop-ups.** Commit.
8. **Seed script + demo polish + README** (setup, architecture, rules, how to demo). Basics DONE — freeze.
9. **Key features, in this order** (value ÷ effort, and dependency order):
   1. *Last-minute extensions* — ~10 lines inside `place_bid`: if `closes_at − now ≤ 30s` → `closes_at = bid_time + 60s`; UI picks up new countdown via polling. Add tests.
   2. *Automatic bidding* — `AutoBid(listing, user, max_amount)` (public). After each bid, resolve: leader-with-max bids minimum needed to stay ahead (`min(max, other_top + increment)`), tie on max → earlier proxy wins. Mark generated bids `is_auto`. Must compose correctly with extensions (auto bids in last 30s also extend).
   3. *Never miss what you need* — `Want(user, keywords, category?, max_price)`; on listing create, match and create a Notification (delivered when the user next opens the app + browser pop-up if open). Persisted server-side so it isn't lost offline.
   4. *Questions before bidding* — `Question(listing, asker, text, answer, answered_at, pinned)`; public thread on the auction page, seller answers once for everyone, duplicate hint via simple similarity, rate-limit per user per listing, seller can hide spam, notify seller/asker.
   5. *AI assistant tab* — Claude with tool use (`search_listings`, `get_listing`, `propose_bid`); bids are never placed without an explicit UI confirm step carrying a user-approved max, server re-validates against that cap, tools only ever return public fields. Uses `claude-sonnet-5-5` via the Anthropic SDK (load the `claude-api` skill when we get there). Biggest effort; only if time remains.

## Critical files (to be created)
- `backend/app/main.py`, `core/config.py`, `core/security.py`, `db/session.py`
- `backend/app/models/{user,listing,bid,notification}.py`, `schemas/*`
- `backend/app/services/{auction,listings,notifications,closer}.py` ← core logic
- `backend/app/api/routes/{auth,listings,bids,sale,notifications}.py`
- `backend/tests/test_auction.py` (+ one file per feature), `backend/scripts/seed.py`
- `frontend/src/{pages,components,hooks/useCountdown.ts,api}/…`
- `docs/PLAN.md`, `README.md`

## Verification
- `cd backend && pytest` — engine tests listed in milestone 4 must pass, including a threaded concurrent-bid test.
- Run backend (`uvicorn app.main:app --reload`) + frontend (`npm run dev`); run `scripts/seed.py` for demo users/listings including one closing in ~1 minute.
- Manual end-to-end with two browsers (two users): list item → bid → outbid notification pop-up in a background tab → wait for close → seller approves → handover → completed; also reject, cancel, unsold, and a late-bid attempt (must be rejected by server).
- After each Key feature: its dedicated tests plus a manual re-run of the closing flow to check for regressions.

## Open items to confirm at execution
- GitHub account/owner for the public repo (see milestone 0).
- Whether to restrict registration to a campus email domain (default: no restriction, configurable via env var).
- Approval timeout (default: none; seller acts manually, per the brief).
