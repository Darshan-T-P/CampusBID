import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("campusbid.events")


class AuctionBroadcaster:
    """In-memory pub/sub for real-time Server-Sent Events (SSE).

    Allows any client viewing an auction page to receive instant push updates
    when a bid is placed, time is extended, or the auction state changes.
    """

    def __init__(self) -> None:
        self._listeners: dict[int, set[asyncio.Queue]] = {}
        self._global_listeners: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, listing_id: int | None = None) -> asyncio.Queue:
        """Subscribe to a specific listing or all listings."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if listing_id is not None:
                if listing_id not in self._listeners:
                    self._listeners[listing_id] = set()
                self._listeners[listing_id].add(q)
            else:
                self._global_listeners.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue, listing_id: int | None = None) -> None:
        """Remove a subscription queue."""
        async with self._lock:
            if listing_id is not None and listing_id in self._listeners:
                self._listeners[listing_id].discard(q)
                if not self._listeners[listing_id]:
                    del self._listeners[listing_id]
            else:
                self._global_listeners.discard(q)

    def publish_nowait(self, event_type: str, data: dict[str, Any], listing_id: int | None = None) -> None:
        """Publish an event from synchronous code (e.g. database route/service)."""
        payload = {"event": event_type, "data": data}
        if listing_id is not None:
            payload["listing_id"] = listing_id

        # Deliver to specific listing subscribers
        if listing_id is not None and listing_id in self._listeners:
            for q in list(self._listeners[listing_id]):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.warning("Queue full for subscriber on listing %s, dropping event", listing_id)

        # Deliver to global subscribers
        for q in list(self._global_listeners):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Queue full for global subscriber, dropping event")


broadcaster = AuctionBroadcaster()
