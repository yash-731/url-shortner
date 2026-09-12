from collections import Counter
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import ClickEvent, User, utcnow
from ..ratelimit import RateLimiter
from ..schemas import LinkAnalytics, NamedCount, TimeBucket
from ..security import get_current_user
from .links import _owned_link

router = APIRouter(prefix="/api/links", tags=["analytics"])
limit = RateLimiter("api")

BROWSERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Chrome/", "Chrome"),
    ("Firefox/", "Firefox"),
    ("Safari/", "Safari"),
    ("curl/", "curl"),
    ("bot", "Bot"),
)


def _browser_family(user_agent: str | None) -> str:
    if not user_agent:
        return "Unknown"
    for token, name in BROWSERS:
        if token.lower() in user_agent.lower():
            return name
    return "Other"


def _referrer_source(referrer: str | None) -> str:
    if not referrer:
        return "Direct"
    return urlsplit(referrer).netloc or "Direct"


def _top(counter: Counter, size: int = 5) -> list[NamedCount]:
    return [NamedCount(name=name, clicks=count) for name, count in counter.most_common(size)]


@router.get("/{code}/analytics", response_model=LinkAnalytics)
async def link_analytics(
    code: str,
    days: int = Query(7, ge=1, le=365),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(limit),
) -> LinkAnalytics:
    link = await _owned_link(code, user, session)
    cutoff = utcnow() - timedelta(days=days)
    in_window = (ClickEvent.link_id == link.id, ClickEvent.clicked_at >= cutoff)

    unique_visitors = await session.scalar(
        select(func.count(func.distinct(ClickEvent.ip_hash))).where(
            ClickEvent.link_id == link.id
        )
    )
    clicks_in_window = await session.scalar(select(func.count()).where(*in_window))

    day = func.date(ClickEvent.clicked_at)
    by_day = await session.execute(
        select(day.label("day"), func.count().label("clicks"))
        .where(*in_window)
        .group_by(day)
        .order_by(day)
    )

    # Grouped in SQL to keep the row count small, then folded to host/browser in Python
    # because neither bucket maps cleanly onto portable SQL.
    referrers = await session.execute(
        select(ClickEvent.referrer, func.count().label("clicks"))
        .where(*in_window)
        .group_by(ClickEvent.referrer)
        .order_by(desc("clicks"))
    )
    agents = await session.execute(
        select(ClickEvent.user_agent, func.count().label("clicks"))
        .where(*in_window)
        .group_by(ClickEvent.user_agent)
        .order_by(desc("clicks"))
    )

    referrer_counts: Counter = Counter()
    for referrer, clicks in referrers:
        referrer_counts[_referrer_source(referrer)] += clicks

    browser_counts: Counter = Counter()
    for user_agent, clicks in agents:
        browser_counts[_browser_family(user_agent)] += clicks

    return LinkAnalytics(
        code=link.code,
        target_url=link.target_url,
        total_clicks=link.click_count,
        unique_visitors=unique_visitors or 0,
        clicks_in_window=clicks_in_window or 0,
        window_days=days,
        clicks_by_day=[TimeBucket(date=str(row.day), clicks=row.clicks) for row in by_day],
        top_referrers=_top(referrer_counts),
        top_browsers=_top(browser_counts),
    )
