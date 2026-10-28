"""Fill the database with a believable demo marketplace.

    cd backend
    .venv/bin/python scripts/seed.py            # add demo users + auctions (refuses if already seeded)
    .venv/bin/python scripts/seed.py --reset    # wipe ALL data (and uploaded photos) first, then seed
    .venv/bin/python scripts/seed.py --clear    # wipe ALL data and photos, and do NOT seed (back to an empty app)
    .venv/bin/python scripts/seed.py --domain college.edu

Everything goes through the app's own services (create listing, place bid, close, approve...), so the data
obeys the same rules as real use and notifications are created naturally. Run it right before a demo:
one auction is set to close in about 90 seconds.
"""

import argparse
import functools
import shutil
import struct
import sys
import zlib
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.clock import utcnow  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.models import Category, Condition, Listing, User  # noqa: E402
from app.services import sale  # noqa: E402
from app.services.auction import cancel_listing, close_due_listings, place_bid  # noqa: E402
from app.services.listings import create_listing  # noqa: E402

PASSWORD = "password123"

# (key, display name). Two final-year sellers and three juniors who bid.
USERS = [
    ("arjun", "Arjun K"),
    ("meera", "Meera S"),
    ("priya", "Priya"),
    ("rahul", "Rahul"),
    ("sneha", "Sneha"),
]

H, D = 1, 24  # hours, hours per day

# end: how the auction should be left. None = still open.
LISTINGS = [
    # --- open auctions, soonest first ---
    dict(title="Hero Sprint 21-speed cycle", cat="cycle", cond="good", seller="arjun", start=2500, inc=100,
         closes=timedelta(seconds=90), colour=(52, 110, 190),
         desc="Hero Sprint, 21 gears, new tyres last month. Light scratches on the frame. Selling before I leave campus.",
         bids=[("priya", 2500), ("rahul", 2600), ("priya", 2800)]),
    dict(title="Casio fx-991EX calculator", cat="calculator", cond="like_new", seller="meera", start=450, inc=25,
         closes=timedelta(minutes=25), colour=(70, 70, 82),
         desc="Used for two semesters, no scratches on the screen. Cover included.",
         bids=[("sneha", 450), ("rahul", 500)]),
    dict(title="Arduino Uno starter kit", cat="electronics", cond="like_new", seller="meera", start=700, inc=50,
         closes=timedelta(hours=6), colour=(0, 128, 140),
         desc="Uno board, breadboard, jumper wires, LEDs, sensors and a USB cable. Everything from the lab course.",
         bids=[("priya", 700), ("sneha", 750), ("priya", 800), ("rahul", 850)]),
    dict(title="Engineering Mathematics (Kreyszig)", cat="books", cond="good", seller="arjun", start=200, inc=10,
         closes=timedelta(hours=3), colour=(150, 100, 56),
         desc="10th edition. Some highlighting in the first chapters, otherwise clean.", bids=[]),
    dict(title="Table lamp", cat="electronics", cond="new", seller="meera", start=300, inc=20,
         closes=timedelta(hours=12), colour=(214, 178, 70), desc="Never used. LED, adjustable arm.", bids=[]),
    dict(title="Hostel bucket and mug set", cat="other", cond="new", seller="meera", start=100, inc=10,
         closes=timedelta(hours=20), colour=(96, 170, 176), desc="Bucket, mug and a soap case. Bought, never opened.", bids=[]),
    dict(title="Study table with drawer", cat="furniture", cond="good", seller="arjun", start=1200, inc=50,
         closes=timedelta(days=1, hours=4), colour=(116, 78, 48),
         desc="Solid wood, 120 x 60 cm, one drawer with a lock. Buyer collects from Hostel B.", bids=[("rahul", 1200)]),
    dict(title="Firefox mountain bike", cat="cycle", cond="like_new", seller="arjun", start=6000, inc=250,
         closes=timedelta(days=2), colour=(196, 86, 56),
         desc="Firefox 21-speed, front suspension. Ridden a few times only.", bids=[("sneha", 6000)]),
    dict(title="Data Structures notes bundle", cat="books", cond="fair", seller="arjun", start=150, inc=10,
         closes=timedelta(days=3), colour=(170, 60, 116),
         desc="Handwritten notes and solved previous-year papers, semester 3 and 4.", bids=[("sneha", 150)]),
    dict(title="Plastic chairs (set of 2)", cat="furniture", cond="fair", seller="arjun", start=400, inc=25,
         closes=timedelta(days=5), colour=(56, 150, 88), desc="Sturdy, a few scuffs. Stackable.", bids=[]),
    # --- already finished, one of each outcome ---
    dict(title="Scientific calculator (Sharp)", cat="calculator", cond="good", seller="meera", start=120, inc=10,
         closes=timedelta(days=1), colour=(100, 100, 140), end="pending",
         desc="Works perfectly. Solar plus battery.", bids=[("priya", 120), ("sneha", 150)]),
    dict(title="Hercules city cycle", cat="cycle", cond="fair", seller="arjun", start=1800, inc=100,
         closes=timedelta(days=1), colour=(146, 60, 60), end="reserved",
         desc="Basic city cycle with a carrier. Needs a new bell.", bids=[("rahul", 1800), ("priya", 1900)]),
    dict(title="Organic Chemistry textbook", cat="books", cond="like_new", seller="arjun", start=500, inc=25,
         closes=timedelta(days=1), colour=(200, 140, 40), end="completed", desc="Morrison & Boyd, barely opened.",
         bids=[("sneha", 500)]),
    dict(title="Old desk fan", cat="electronics", cond="poor", seller="meera", start=100, inc=10,
         closes=timedelta(days=1), colour=(120, 120, 120), end="unsold", desc="Works, but noisy.", bids=[]),
    dict(title="Yoga mat", cat="other", cond="good", seller="meera", start=150, inc=10,
         closes=timedelta(days=2), colour=(120, 70, 150), end="cancelled", desc="Thick 8 mm mat.",
         bids=[("rahul", 150)]),
]


@functools.lru_cache(maxsize=None)  # the same few colours repeat; no need to redraw them
def make_photo(rgb, w=480, h=360):
    """A soft gradient with a light disc, as PNG bytes. Stands in for a real photo, with no image library."""
    r0, g0, b0 = rgb
    cx, cy, radius = w * 0.5, h * 0.52, h * 0.28
    rows = []
    for y in range(h):
        shade = 1.12 - 0.35 * (y / h)
        row = bytearray([0])  # PNG filter type 0 for this scanline
        for x in range(w):
            inside = (x - cx) ** 2 + (y - cy) ** 2 < radius**2
            k = 1.45 if inside else shade
            row += bytes(min(255, int(c * k)) for c in (r0, g0, b0))
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
        + chunk(b"IEND", b"")
    )


def wipe(db: Session) -> None:
    for table in reversed(db_session.Base.metadata.sorted_tables):
        db.execute(delete(table))
    db.commit()
    db.expunge_all()  # forget the deleted rows: ids get reused, and stale objects would clash
    shutil.rmtree(Path(settings.media_dir) / "listings", ignore_errors=True)


def run_seed(db: Session, domain: str) -> dict:
    """Create the demo data. Returns {'users': {key: User}, 'listings': {title: Listing}}."""
    users = {}
    for key, name in USERS:
        user = User(email=f"{key}@{domain}", password_hash=hash_password(PASSWORD), display_name=name, is_verified=True)
        db.add(user)
        users[key] = user
    db.commit()

    listings = {}
    for spec in LISTINGS:
        seller = users[spec["seller"]]
        shade = tuple(min(255, c + 40) for c in spec["colour"])
        photos = [make_photo(spec["colour"])] + ([make_photo(shade)] if spec["start"] >= 1000 else [])
        listing = create_listing(
            db, seller,
            title=spec["title"], category=Category(spec["cat"]), condition=Condition(spec["cond"]),
            description=spec["desc"], starting_price=spec["start"], min_increment=spec["inc"],
            closes_at=utcnow() + max(spec["closes"], timedelta(minutes=11)), images=photos,
        )
        if spec["closes"] < timedelta(minutes=10):
            # The app (rightly) refuses auctions shorter than 10 minutes; the demo's live-close
            # auction is shortened directly in the database.
            db.get(Listing, listing.id).closes_at = utcnow() + spec["closes"]
            db.commit()
        # Spread the bids over the past so the history looks lived-in, newest bid a few minutes ago.
        count = len(spec["bids"])
        for i, (who, amount) in enumerate(spec["bids"]):
            place_bid(db, listing.id, users[who].id, amount, now=utcnow() - timedelta(minutes=(count - i) * 9 + 3))
        listings[spec["title"]] = listing

    # Finished auctions: let the clock run out for real, so the normal closing path (and its
    # notifications) does the work, then walk the sale through the seller's decisions.
    for spec in LISTINGS:
        end = spec.get("end")
        if not end:
            continue
        listing = listings[spec["title"]]
        seller_id = users[spec["seller"]].id
        if end == "cancelled":
            cancel_listing(db, listing.id, seller_id)
            continue
        db.get(Listing, listing.id).closes_at = utcnow() - timedelta(minutes=1)
        db.commit()
        close_due_listings(db)
        if end in ("reserved", "completed"):
            sale.approve(db, listing.id, seller_id)
        if end == "completed":
            sale.confirm_handover(db, listing.id, seller_id)
    return {"users": users, "listings": listings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete ALL existing data and photos first, then seed")
    parser.add_argument("--force", action="store_true", help="allow seeding when DEV_MODE is off (creates accounts with a KNOWN password!)")
    parser.add_argument("--clear", action="store_true", help="delete ALL data and photos and stop (no seeding)")
    parser.add_argument("--domain", default=(settings.email_domains or ["campus.edu"])[0], help="email domain for the demo users")
    args = parser.parse_args()

    if not (settings.dev_mode or args.force or args.clear):
        sys.exit(
            "Refusing to seed: DEV_MODE is off, and the demo accounts all share the password 'password123'.\n"
            "Set DEV_MODE=true for a local/demo database, or pass --force if you really mean it."
        )

    db_session.init_db()
    with db_session.SessionLocal() as db:
        if args.clear:
            wipe(db)
            print(f"Cleared every table in {settings.database_url} and removed {settings.media_dir}/listings. Nothing was seeded.")
            return
        if args.reset:
            print(f"Resetting {settings.database_url} and {settings.media_dir}/listings ...")
            wipe(db)
        elif db.scalar(select(User).where(User.email == f"{USERS[0][0]}@{args.domain}")):
            sys.exit("Demo data already exists. Run with --reset to wipe everything and start fresh.")
        run_seed(db, args.domain)

    print(f"\nSeeded {len(USERS)} users and {len(LISTINGS)} auctions. Sign in (password: {PASSWORD}) as:")
    for key, name in USERS:
        role = "seller (final-year)" if key in ("arjun", "meera") else "bidder"
        print(f"  {key}@{args.domain:<14} {name:<8} {role}")
    print("\nTry: Arjun's 'My listings' (handover pending), Meera's 'My listings' (a sale awaiting her decision),")
    print("Priya's 'My bids' (leading one auction, outbid on another), and watch the first auction close in ~90s.")


if __name__ == "__main__":
    main()
