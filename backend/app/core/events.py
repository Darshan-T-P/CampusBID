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
        self._loops: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}  # which event loop owns each queue
        self._lock = asyncio.Lock()

    async def subscribe(self, listing_id: int | None = None) -> asyncio.Queue:
        """Subscribe to a specific listing or all listings."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._loops[q] = asyncio.get_running_loop()
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
        self._loops.pop(q, None)
        async with self._lock:
            if listing_id is not None and listing_id in self._listeners:
                self._listeners[listing_id].discard(q)
                if not self._listeners[listing_id]:
                    del self._listeners[listing_id]
            else:
                self._global_listeners.discard(q)

    def _offer(self, q: asyncio.Queue, payload: dict[str, Any]) -> None:
        """Put a message on a subscriber's queue from ANY thread.

        Bids and sale steps are published from worker threads and the closer from another one, but the queues belong
        to the event loop. Handing the put to that loop (call_soon_threadsafe) is what makes the loop wake up and
        deliver it at once, instead of whenever something else happens to wake it.
        """

        def put() -> None:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Queue full for a subscriber, dropping event")

        loop = self._loops.get(q)
        if loop is None:
            put()
            return
        try:
            loop.call_soon_threadsafe(put)
        except RuntimeError:  # the loop has shut down
            pass

    def publish_nowait(self, event_type: str, data: dict[str, Any], listing_id: int | None = None) -> None:
        """Publish an event from synchronous code (a route, a service, the closer thread)."""
        payload = {"event": event_type, "data": data}
        if listing_id is not None:
            payload["listing_id"] = listing_id

        # Deliver to specific listing subscribers, then to global ones
        if listing_id is not None:
            for q in list(self._listeners.get(listing_id, ())):
                self._offer(q, payload)
        for q in list(self._global_listeners):
            self._offer(q, payload)


broadcaster = AuctionBroadcaster()
