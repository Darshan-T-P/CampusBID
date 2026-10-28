"""Request-level defences: a size cap and standard security headers, applied to every response."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# The interactive docs load their own scripts/styles, so a strict CSP would break them.
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityMiddleware:
    """Pure ASGI middleware (no buffering, so it adds no cost to ordinary requests)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read the path now: routing (a Mount) rewrites scope["root_path"] while the request is handled, so reading it
        # later would see a different path. In production the API sits under /api; strip that so /api/media is /media.
        path = scope.get("path", "").removeprefix(scope.get("root_path", ""))

        limit = settings.max_request_bytes
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(scope, send, path)  # refuse before reading a single byte of the body
            return

        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # A client that lies about its size, or streams without declaring one (chunked).
                    # Pretend it disconnected so the app stops reading; we answer 413 ourselves below.
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if exceeded:
                # The app only saw a "disconnect" and may answer with its own error (FastAPI says 400).
                # Replace whatever it sends with a clear 413, once.
                if not started:
                    started = True
                    await self._reject(scope, send, path)
                return
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = self._with_security_headers(scope, message.get("headers", []), path)
            await send(message)

        try:
            await self.app(scope, limited_receive, send_with_headers)
        finally:
            if exceeded and not started:
                await self._reject(scope, send)

    @staticmethod
    def _with_security_headers(scope: Scope, raw: list, path: str) -> list:
        existing = {k.lower() for k, _ in raw}
        add = {
            b"x-content-type-options": b"nosniff",  # never let a browser guess a file is HTML or script
            b"x-frame-options": b"DENY",
            b"referrer-policy": b"no-referrer",
        }
        if not path.startswith("/media"):
            add[b"cache-control"] = b"no-store"  # API answers are personal; photos may be cached
        if not path.startswith(_DOC_PATHS):
            add[b"content-security-policy"] = b"default-src 'none'; frame-ancestors 'none'"
        if scope.get("scheme") == "https":
            add[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
        return list(raw) + [(k, v) for k, v in add.items() if k not in existing]

    @staticmethod
    async def _reject(scope: Scope, send: Send, path: str) -> None:
        body = json.dumps({"detail": "Request too large"}).encode()
        headers = SecurityMiddleware._with_security_headers(
            scope, [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())], path
        )
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send({"type": "http.response.body", "body": body})
