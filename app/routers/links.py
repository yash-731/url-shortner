from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import shortcode
from ..cache import cache, link_key
from ..config import get_settings
from ..database import get_session
from ..models import Link, User
from ..ratelimit import RateLimiter
from ..schemas import LinkCreate, LinkOut, serialize_link
from ..security import get_current_user

router = APIRouter(prefix="/api/links", tags=["links"])
limit = RateLimiter("api")


async def _owned_link(code: str, user: User, session: AsyncSession) -> Link:
    link = await session.scalar(
        select(Link).where(Link.code == code, Link.owner_id == user.id)
    )
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link


@router.post("", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def create_link(
    payload: LinkCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(limit),
) -> LinkOut:
    settings = get_settings()

    if payload.custom_alias:
        taken = await session.scalar(select(Link.id).where(Link.code == payload.custom_alias))
        if taken is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "That alias is already taken")
        candidates = [payload.custom_alias]
    else:
        candidates = [
            shortcode.generate(settings.shortcode_length)
            for _ in range(settings.shortcode_max_attempts)
        ]

    for candidate in candidates:
        link = Link(
            code=candidate,
            target_url=str(payload.target_url),
            owner_id=user.id,
            expires_at=payload.expires_at,
        )
        session.add(link)
        try:
            await session.commit()
        except IntegrityError:
            # Another request claimed this code between generation and insert; try the next one.
            await session.rollback()
            continue
        await session.refresh(link)
        return serialize_link(link)

    raise HTTPException(status.HTTP_409_CONFLICT, "Could not allocate a short code, retry")


@router.get("", response_model=list[LinkOut])
async def list_links(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(limit),
) -> list[LinkOut]:
    links = await session.scalars(
        select(Link).where(Link.owner_id == user.id).order_by(Link.created_at.desc())
    )
    return [serialize_link(link) for link in links]


@router.get("/{code}", response_model=LinkOut)
async def get_link(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(limit),
) -> LinkOut:
    return serialize_link(await _owned_link(code, user, session))


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(limit),
) -> None:
    link = await _owned_link(code, user, session)
    await session.delete(link)
    await session.commit()
    await cache.backend.delete(link_key(code))
