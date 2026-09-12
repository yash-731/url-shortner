from .conftest import register_and_login


async def test_create_link_returns_short_url(client):
    headers = await register_and_login(client)
    response = await client.post(
        "/api/links", json={"target_url": "https://example.com/docs"}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["short_url"] == f"http://test/{body['code']}"
    assert len(body["code"]) == 7
    assert body["click_count"] == 0


async def test_custom_alias_and_conflict(client):
    headers = await register_and_login(client)
    payload = {"target_url": "https://example.com", "custom_alias": "my-link"}
    first = await client.post("/api/links", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["code"] == "my-link"
    assert (await client.post("/api/links", json=payload, headers=headers)).status_code == 409


async def test_reserved_alias_rejected(client):
    headers = await register_and_login(client)
    response = await client.post(
        "/api/links",
        json={"target_url": "https://example.com", "custom_alias": "api"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_invalid_target_url_rejected(client):
    headers = await register_and_login(client)
    response = await client.post(
        "/api/links", json={"target_url": "not-a-url"}, headers=headers
    )
    assert response.status_code == 422


async def test_links_are_private_to_their_owner(client):
    owner = await register_and_login(client, "owner@example.com")
    created = await client.post(
        "/api/links", json={"target_url": "https://example.com"}, headers=owner
    )
    code = created.json()["code"]

    intruder = await register_and_login(client, "intruder@example.com")
    assert (await client.get(f"/api/links/{code}", headers=intruder)).status_code == 404
    assert (await client.get("/api/links", headers=intruder)).json() == []
    assert (await client.delete(f"/api/links/{code}", headers=intruder)).status_code == 404


async def test_delete_link_stops_redirecting(client):
    headers = await register_and_login(client)
    code = (
        await client.post(
            "/api/links", json={"target_url": "https://example.com"}, headers=headers
        )
    ).json()["code"]

    assert (await client.get(f"/{code}")).status_code == 307
    assert (await client.delete(f"/api/links/{code}", headers=headers)).status_code == 204
    assert (await client.get(f"/{code}")).status_code == 404
