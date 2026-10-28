"""Background closer: closes auctions whose time has passed, even if nobody is looking at them.

This complements the lazy close in auction.py (bids and reads close an expired listing on
the spot). The lazy close keeps the rules correct; this sweep makes closing happen on time,
and is where "you won" / "ended unsold" notifications and "closing soon" reminders are sent from.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.services.auction import close_due_listings, has_due_listings
from app.services.watchlist import send_due_reminders

logger = logging.getLogger("campusbid.closer")


def sweep_once(session_factory: Callable[[], Session], now: datetime | None = None) -> int:
    """Close every expired auction, then send any "closing soon" reminders that are due. Returns how many closed."""
    now = now or utcnow()
    with session_factory() as db:
        closed = []
        if has_due_listings(db, now):  # otherwise don't touch the write lock
            closed = close_due_listings(db, now)
            for listing in closed:
                logger.info("Closed listing %s -> %s", listing.id, listing.status.value)
        send_due_reminders(db, now)  # cheap read first; locks only when something is due
        return len(closed)


async def run_closer(session_factory: Callable[[], Session], interval: float) -> None:
    """Sweep forever until cancelled. One failed sweep never stops the loop."""
    while True:
        try:
            # Database work is blocking, so keep it off the event loop.
            await asyncio.to_thread(sweep_once, session_factory)
        except Exception:
            logger.exception("Closer sweep failed; will retry")
        await asyncio.sleep(interval)
