import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import cache, link_key
from ..config import get_settings
from ..database import db, get_session
from ..models import ClickEvent, Link, as_utc, utcnow
from ..ratelimit import RateLimiter, client_identity
from ..security import hash_ip

router = APIRouter(tags=["redirect"])
limit = RateLimiter("redirect", "redirect_rate_limit_requests")


def _trim(value: str | None, length: int) -> str | None:
    return value[:length] if value else None


def _cache_ttl(link: Link) -> int:
    """Never let a cached entry outlive the link it points at."""
    ttl = get_settings().cache_ttl_seconds
    if link.expires_at is not None:
        remaining = int((as_utc(link.expires_at) - utcnow()).total_seconds())
        ttl = min(ttl, max(remaining, 0))
    return ttl


async def record_click(
    link_id: int, referrer: str | None, user_agent: str | None, ip_hash: str
) -> None:
    async with db.sessionmaker() as session:
        session.add(
            ClickEvent(
                link_id=link_id, referrer=referrer, user_agent=user_agent, ip_hash=ip_hash
            )
        )
        await session.execute(
            update(Link).where(Link.id == link_id).values(click_count=Link.click_count + 1)
        )
        await session.commit()


@router.get("/{code}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def follow(
    code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(limit),
) -> RedirectResponse:
    cached = await cache.backend.get(link_key(code))
    if cached is not None:
        entry = json.loads(cached)
        link_id, target_url = entry["id"], entry["url"]
    else:
        link = await session.scalar(select(Link).where(Link.code == code))
        if link is None or not link.is_live():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Short link not found")
        link_id, target_url = link.id, link.target_url
        ttl = _cache_ttl(link)
        if ttl > 0:
            await cache.backend.set(
                link_key(code), json.dumps({"id": link_id, "url": target_url}), ttl
            )

    # Writing the click inline would put a DB round-trip in front of every redirect.
    background_tasks.add_task(
        record_click,
        link_id,
        _trim(request.headers.get("referer"), 512),
        _trim(request.headers.get("user-agent"), 512),
        hash_ip(client_identity(request)),
    )
    return RedirectResponse(target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
