import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

logger = logging.getLogger(__name__)

FALLBACK_URL = "sqlite+aiosqlite:///./shortener.db"
_CREDENTIALS = re.compile(r"://[^/@]*@")


class Base(DeclarativeBase):
    pass


class Database:
    """Holds the live engine so startup can swap Postgres for SQLite without re-importing."""

    engine = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    url = ""
    is_fallback = False


db = Database()


def _redact(url: str) -> str:
    return _CREDENTIALS.sub("://***@", url)


async def init_db() -> None:
    settings = get_settings()
    candidates = [settings.database_url]
    if settings.database_url != FALLBACK_URL:
        candidates.append(FALLBACK_URL)

    for index, url in enumerate(candidates):
        is_last = index == len(candidates) - 1
        engine = create_async_engine(url, pool_pre_ping=True, future=True)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as exc:
            await engine.dispose()
            if is_last:
                raise
            logger.warning(
                "Database %s unavailable (%s); falling back to SQLite", _redact(url), exc
            )
            continue

        db.engine = engine
        db.sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        db.url = url
        db.is_fallback = index > 0
        logger.info("Connected to database %s", _redact(url))
        return


async def close_db() -> None:
    if db.engine is not None:
        await db.engine.dispose()
        db.engine = None
        db.sessionmaker = None


async def get_session():
    async with db.sessionmaker() as session:
        yield session
