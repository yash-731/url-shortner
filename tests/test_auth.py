from .conftest import register_and_login


async def test_health_reports_backends(client):
    body = (await client.get("/health")).json()
    assert body["status"] == "ok"
    assert body["cache"] == "in-memory"
    assert body["database"] == "sqlite"


async def test_register_then_fetch_profile(client):
    headers = await register_and_login(client)
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


async def test_duplicate_email_rejected(client):
    payload = {"email": "dupe@example.com", "password": "supersecret"}
    assert (await client.post("/auth/register", json=payload)).status_code == 201
    assert (await client.post("/auth/register", json=payload)).status_code == 409


async def test_wrong_password_rejected(client):
    await register_and_login(client, "x@example.com")
    response = await client.post(
        "/auth/login", json={"email": "x@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401


async def test_protected_route_requires_token(client):
    assert (await client.get("/auth/me")).status_code == 401


async def test_rate_limit_returns_429(client):
    payload = {"email": "ghost@example.com", "password": "whatever1"}
    codes = [(await client.post("/auth/login", json=payload)).status_code for _ in range(22)]
    assert 429 in codes
