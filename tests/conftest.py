import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    # Nothing listens here, so the cache layer exercises its in-memory fallback.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("BASE_URL", "http://test")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "20")

    from app.cache import close_cache, init_cache
    from app.config import get_settings
    from app.database import close_db, init_db

    get_settings.cache_clear()
    from app.main import app

    await init_db()
    await init_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    await close_cache()
    await close_db()
    get_settings.cache_clear()


async def register_and_login(client, email="user@example.com", password="supersecret"):
    await client.post("/auth/register", json={"email": email, "password": password})
    response = await client.post("/auth/login", json={"email": email, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
