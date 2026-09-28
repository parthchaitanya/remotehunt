"""RemoteHunt API."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import auth, demo, scheduler
from .config import get_settings
from .db import init_db
from .logging_setup import setup_logging
from .routers import gmail, jobs, profiles, resume, sources, stats, tracker

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("remotehunt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.frontend_url.startswith("https://") and not settings.app_password and not settings.demo_mode:
        # Refuse to run a public instance without a login: it holds your resume and Gmail access.
        raise RuntimeError("APP_PASSWORD must be set when FRONTEND_URL is https (public deployment)")
    init_db()
    if settings.demo_mode:
        demo.seed()
    if settings.scheduler_enabled and not settings.demo_mode:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="RemoteHunt", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.middleware("http")(auth.middleware)
app.middleware("http")(demo.middleware)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Log the type only: exception text can contain personal data.
    log.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse({"detail": f"Internal error ({type(exc).__name__})"}, status_code=500)


for r in (auth.router, resume.router, jobs.router, tracker.router, sources.router, gmail.router, profiles.router,
          stats.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "demo": settings.demo_mode}


# Single-service deploys (e.g. the public demo): serve the built React app from the API process.
if settings.static_dir and Path(settings.static_dir).is_dir():
    STATIC = Path(settings.static_dir).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        target = (STATIC / path).resolve()
        if path and target.is_file() and STATIC in target.parents:
            return FileResponse(target)
        return FileResponse(STATIC / "index.html")
