import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, bids, listings, me, notifications, sale
from app.core.clock import utcnow
from app.core.config import settings
from app.db.session import SessionLocal, init_db
from app.services.closer import run_closer


def check_startup_settings() -> None:
    """Refuse to start without a campus-domain allow-list, unless in dev mode."""
    if not settings.email_domains and not settings.dev_mode:
        raise RuntimeError(
            "ALLOWED_EMAIL_DOMAINS is required (e.g. college.edu). "
            "Set DEV_MODE=true to run without it for local development."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_startup_settings()
    init_db()
    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
    closer = None
    if settings.closer_interval_seconds > 0:
        closer = asyncio.create_task(run_closer(SessionLocal, settings.closer_interval_seconds))
    yield
    if closer is not None:
        closer.cancel()
        with suppress(asyncio.CancelledError):
            await closer


app = FastAPI(title="CampusBid", version="0.1.0", lifespan=lifespan)

# Vite dev server; in production the built frontend is served from the same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(listings.router)
app.include_router(bids.router)
app.include_router(sale.router)
app.include_router(notifications.router)
app.include_router(me.router)
# Uploaded photos. check_dir=False because the folder is created at startup, not import time.
app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")


@app.get("/health", tags=["meta"])
def health():
    # Doubles as the server-clock source clients can use to calibrate countdowns.
    return {"status": "ok", "server_time": utcnow()}
