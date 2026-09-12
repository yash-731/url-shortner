from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from .shortcode import is_valid_alias


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt silently ignores bytes past 72, so reject long passwords instead of truncating.
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LinkCreate(BaseModel):
    target_url: HttpUrl
    custom_alias: str | None = Field(default=None, max_length=32)
    expires_at: datetime | None = None

    @field_validator("custom_alias")
    @classmethod
    def _check_alias(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_alias(value):
            raise ValueError(
                "alias must be 3-32 characters of letters, digits, '-' or '_', and not reserved"
            )
        return value


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_url: str
    target_url: str
    created_at: datetime
    expires_at: datetime | None
    is_active: bool
    click_count: int


class TimeBucket(BaseModel):
    date: str
    clicks: int


class NamedCount(BaseModel):
    name: str
    clicks: int


class LinkAnalytics(BaseModel):
    code: str
    target_url: str
    total_clicks: int
    unique_visitors: int
    clicks_in_window: int
    window_days: int
    clicks_by_day: list[TimeBucket]
    top_referrers: list[NamedCount]
    top_browsers: list[NamedCount]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def serialize_link(link) -> LinkOut:
    from .config import get_settings

    base = get_settings().base_url.rstrip("/")
    return LinkOut(
        code=link.code,
        short_url=f"{base}/{link.code}",
        target_url=link.target_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        is_active=link.is_active,
        click_count=link.click_count,
    )
