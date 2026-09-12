import asyncio
import logging
import time

import redis.asyncio as redis

from .config import get_settings

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Process-local stand-in for Redis. Fine for one dev process, not for multiple workers."""

    name = "in-memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    def _live(self, key: str) -> str | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> str | None:
        async with self._lock:
            return self._live(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        async with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def incr_in_window(self, key: str, ttl: int) -> int:
        async with self._lock:
            current = int(self._live(key) or 0) + 1
            expires_at = self._data[key][1] if key in self._data else time.monotonic() + ttl
            self._data[key] = (str(current), expires_at)
            return current

    async def close(self) -> None:
        self._data.clear()


class RedisCache:
    name = "redis"

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def incr_in_window(self, key: str, ttl: int) -> int:
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, remaining = await pipe.execute()
        if remaining < 0:
            await self._client.expire(key, ttl)
        return int(count)

    async def close(self) -> None:
        await self._client.aclose()


class CacheProxy:
    backend: InMemoryCache | RedisCache = InMemoryCache()


cache = CacheProxy()


async def init_cache() -> None:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        logger.warning("Redis unavailable (%s); using in-memory cache", exc)
        cache.backend = InMemoryCache()
        return
    cache.backend = RedisCache(client)
    logger.info("Connected to Redis at %s", settings.redis_url)


async def close_cache() -> None:
    await cache.backend.close()
    cache.backend = InMemoryCache()


def link_key(code: str) -> str:
    return f"link:{code}"
