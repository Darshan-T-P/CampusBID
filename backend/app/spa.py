"""Production mode: one server for everything.

In development the Vite dev server serves the pages and proxies `/api/...` to this backend. In production there is
no Vite, so this wraps the API app like this:

    /api/...   -> the API (the same routes, photos and live stream the dev proxy reaches)
    anything else -> the built frontend (frontend/dist); unknown paths get index.html so React Router can handle
                     page URLs such as /listings/7

Switched on with SERVE_FRONTEND=true. Off by default, so development and the tests see the plain API app.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The API answers with "default-src 'none'" (it only returns data). A web page needs scripts, styles and images from
# itself, and the Google Fonts the design uses; nothing else is allowed.
PAGE_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


class SPAStaticFiles(StaticFiles):
    """Static files, falling back to index.html for any path that isn't a real file (client-side routes)."""

    async def get_response(self, path: str, scope: Scope):
        # Only page-like paths ("listings/7") fall back to index.html. A missing file ("assets/x.js") is a real 404:
        # answering it with an HTML page would hide the mistake.
        is_page = "." not in path.rsplit("/", 1)[-1]
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not is_page:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and is_page:
            return await super().get_response("index.html", scope)
        return response


class PageHeaders:
    """Security and caching headers for the pages and scripts (the API adds its own to its answers)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                have = {k.lower() for k, _ in headers}
                add = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"content-security-policy": PAGE_CSP.encode(),
                }
                if path.startswith("/assets/"):
                    add[b"cache-control"] = b"public, max-age=31536000, immutable"  # file names carry a content hash
                else:
                    add[b"cache-control"] = b"no-cache"  # index.html must be re-checked so a new build is picked up
                if scope.get("scheme") == "https":
                    add[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                message["headers"] = headers + [(k, v) for k, v in add.items() if k not in have]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def build_production_app(api: FastAPI, dist: Path) -> Starlette:
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(
            f"SERVE_FRONTEND is on but {index} does not exist. Build the frontend first: cd frontend && npm run build"
        )

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        # A mounted app's own startup/shutdown is not run by its parent, so run the API's (database setup, the closer) here.
        async with api.router.lifespan_context(api):
            yield

    return Starlette(
        routes=[
            Mount("/api", app=api),
            Mount("/", app=PageHeaders(SPAStaticFiles(directory=str(dist), html=True))),
        ],
        lifespan=lifespan,
    )
