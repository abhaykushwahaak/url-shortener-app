"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, auth, redirect, urls
from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.database import Base, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

API_DESCRIPTION = """
A URL shortener with JWT authentication, Redis caching and click analytics.

**How to authenticate:** call `POST /api/auth/register` or `POST /api/auth/login`,
copy the `access_token` from the response, then click **Authorize** above and paste
it in. All `/api/urls/*` and `/api/analytics/*` endpoints then work.

**Flow:** creating a URL returns a short link such as `http://localhost:8000/Ab7xK2`.
Requesting that path issues a redirect and records a click asynchronously, so every
redirect stays fast.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables are normally created by Alembic; this is a convenience for a fresh
    # SQLite file so `uvicorn app.main:app` works with zero extra steps.
    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=API_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Auth", "description": "Registration, login and the current user."},
        {"name": "URLs", "description": "Create, list, update and delete short links."},
        {"name": "Analytics", "description": "Click totals, breakdowns and timelines."},
        {"name": "Redirect", "description": "Following a short link."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["Health"], summary="Health check")
def health() -> dict:
    """Used by Docker Compose health checks. Reports Redis reachability without failing."""
    redis_ok = True
    try:
        get_redis().ping()
    except Exception:  # noqa: BLE001 - health must not raise
        redis_ok = False
    return {"status": "ok", "redis": redis_ok}


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": settings.PROJECT_NAME, "docs": "/docs"}


app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(urls.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(analytics.account_router, prefix=settings.API_PREFIX)

# Registered last, and this ordering is load-bearing: /{short_code} matches any
# single path segment, so every fixed route above (/health, /, /api/*) must be
# declared first or this one would swallow it.
app.include_router(redirect.router)