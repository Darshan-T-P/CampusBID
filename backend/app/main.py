from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, listings, me
from app.core.clock import utcnow
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
    yield


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
app.include_router(me.router)
# Uploaded photos. check_dir=False because the folder is created at startup, not import time.
app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")


@app.get("/health", tags=["meta"])
def health():
    # Doubles as the server-clock source clients can use to calibrate countdowns.
    return {"status": "ok", "server_time": utcnow()}
