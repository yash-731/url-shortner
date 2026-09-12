import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .cache import cache, close_cache, init_cache
from .config import get_settings
from .database import close_db, db, init_db
from .routers import analytics, auth, links, redirect

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_cache()
    yield
    await close_cache()
    await close_db()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Short links with click analytics, Redis-backed caching and rate limiting.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(analytics.router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {
        "status": "ok",
        "database": db.engine.dialect.name if db.engine is not None else "down",
        "database_fell_back": db.is_fallback,
        "cache": cache.backend.name,
    }


# Registered last so /api and /health win the match against the catch-all short code.
app.include_router(redirect.router)
