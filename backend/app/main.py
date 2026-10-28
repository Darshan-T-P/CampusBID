import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import analytics, auth, bids, listings, me, notifications, pricing, questions, sale, wants, watchlist
from app.core.clock import utcnow
from app.core.config import settings
from app.core.middleware import SecurityMiddleware
from app.db.session import SessionLocal, init_db
from app.services.closer import run_closer, run_mail_sender
from app.api.routes import assistant  # the AI assistant (kept apart so it can be committed on its own)


def check_startup_settings() -> None:
    """Refuse to start without a campus-domain allow-list, unless in dev mode."""
    if not settings.email_domains and not settings.dev_mode:
        raise RuntimeError(
            "ALLOWED_EMAIL_DOMAINS is required (e.g. college.edu). "
            "Set DEV_MODE=true to run without it for local development."
        )
    if not settings.dev_mode and not settings.auto_verify and not settings.smtp_ready:
        raise RuntimeError(
            "Email is not configured, so nobody could verify their address. Set EMAIL_BACKEND=smtp with SMTP_HOST and "
            "EMAIL_FROM (see backend/.env.example), or set DEV_MODE=true / AUTO_VERIFY=true for local use."
        )
    if settings.secret_key_is_weak and not settings.dev_mode:
        raise RuntimeError(
            "SECRET_KEY is missing, too short (< 32 chars) or still a placeholder. Anyone could forge login tokens. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_startup_settings()
    init_db()
    with SessionLocal() as db:
        from app.services.listings import backfill_image_fingerprints

        backfill_image_fingerprints(db)  # photos from before duplicate detection get their fingerprint
    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
    closer = sender = None
    if settings.closer_interval_seconds > 0:
        closer = asyncio.create_task(run_closer(SessionLocal, settings.closer_interval_seconds))
        sender = asyncio.create_task(run_mail_sender(SessionLocal))
    yield
    for task in (closer, sender):
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


# The interactive docs/schema are for development; a deployed server shouldn't advertise its whole API surface.
_docs = {} if settings.dev_mode else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="CampusBid", version="0.1.0", lifespan=lifespan, **_docs)
app.add_middleware(SecurityMiddleware)

# Vite dev server; in production the built frontend is served from the same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assistant.router)
app.include_router(auth.router)
app.include_router(listings.router)
app.include_router(bids.router)
app.include_router(sale.router)
app.include_router(notifications.router)
app.include_router(me.router)
app.include_router(watchlist.router)
app.include_router(wants.router)
app.include_router(pricing.router)
app.include_router(questions.router)
app.include_router(analytics.router)


class CachedStaticFiles(StaticFiles):
    """Static file handler with aggressive, permanent caching for immutable media assets."""

    async def check_config(self) -> None:
        """Ensure media directory exists before Starlette verifies it, even in ephemeral test/CI runs."""
        if self.directory is not None:
            Path(self.directory).mkdir(parents=True, exist_ok=True)
        await super().check_config()

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        # Media filenames are unique UUID hashes: they never mutate in-place.
        # Cache for 1 year in browser disk cache, with 304 revalidation support.
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


# Uploaded photos. Ensure directory exists and check_dir=False for startup resilience.
Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
app.mount("/media", CachedStaticFiles(directory=settings.media_dir, check_dir=False), name="media")



@app.get("/health", tags=["meta"])
def health():
    # Doubles as the server-clock source clients can use to calibrate countdowns.
    return {"status": "ok", "server_time": utcnow()}


# Production: one process serves the pages and the API (see app/spa.py). Everything above stays the plain API app.
if settings.serve_frontend:
    from app.spa import build_production_app

    api = app
    app = build_production_app(api, Path(settings.frontend_dist))
