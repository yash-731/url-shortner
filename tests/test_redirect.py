from .conftest import register_and_login


async def test_redirect_sends_visitor_to_target(client):
    headers = await register_and_login(client)
    code = (
        await client.post(
            "/api/links", json={"target_url": "https://example.com/page"}, headers=headers
        )
    ).json()["code"]

    response = await client.get(f"/{code}")
    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com/page"


async def test_unknown_code_is_404(client):
    assert (await client.get("/nosuchcode")).status_code == 404


async def test_second_hit_is_served_from_cache(client):
    from app.cache import cache, link_key

    headers = await register_and_login(client)
    code = (
        await client.post(
            "/api/links", json={"target_url": "https://example.com"}, headers=headers
        )
    ).json()["code"]

    assert await cache.backend.get(link_key(code)) is None
    await client.get(f"/{code}")
    assert await cache.backend.get(link_key(code)) is not None
    assert (await client.get(f"/{code}")).status_code == 307


async def test_expired_link_is_not_followed(client):
    headers = await register_and_login(client)
    code = (
        await client.post(
            "/api/links",
            json={"target_url": "https://example.com", "expires_at": "2020-01-01T00:00:00Z"},
            headers=headers,
        )
    ).json()["code"]

    assert (await client.get(f"/{code}")).status_code == 404
