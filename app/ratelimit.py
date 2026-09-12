from fastapi import HTTPException, Request, status

from .cache import cache
from .config import get_settings


def client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Fixed-window counter keyed by caller IP, shared across workers when Redis is up."""

    def __init__(self, bucket: str, limit_setting: str = "rate_limit_requests") -> None:
        self.bucket = bucket
        self.limit_setting = limit_setting

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        limit = getattr(settings, self.limit_setting)
        window = settings.rate_limit_window_seconds
        key = f"ratelimit:{self.bucket}:{client_identity(request)}"

        count = await cache.backend.incr_in_window(key, window)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {limit} requests per {window}s",
                headers={"Retry-After": str(window)},
            )
