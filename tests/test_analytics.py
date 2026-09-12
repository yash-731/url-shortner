from .conftest import register_and_login


async def test_clicks_are_counted_and_broken_down(client):
    headers = await register_and_login(client)
    code = (
        await client.post(
            "/api/links", json={"target_url": "https://example.com"}, headers=headers
        )
    ).json()["code"]

    for _ in range(3):
        await client.get(
            f"/{code}",
            headers={
                "referer": "https://news.ycombinator.com/item?id=1",
                "user-agent": "Chrome/120",
            },
        )
    await client.get(f"/{code}", headers={"user-agent": "Firefox/121"})

    report = (await client.get(f"/api/links/{code}/analytics", headers=headers)).json()
    assert report["total_clicks"] == 4
    assert report["clicks_in_window"] == 4
    assert report["unique_visitors"] == 1
    assert len(report["clicks_by_day"]) == 1
    assert report["clicks_by_day"][0]["clicks"] == 4
    assert {row["name"]: row["clicks"] for row in report["top_referrers"]} == {
        "news.ycombinator.com": 3,
        "Direct": 1,
    }
    assert {row["name"]: row["clicks"] for row in report["top_browsers"]} == {
        "Chrome": 3,
        "Firefox": 1,
    }


async def test_click_count_visible_on_link_record(client):
    headers = await register_and_login(client)
    code = (
        await client.post(
            "/api/links", json={"target_url": "https://example.com"}, headers=headers
        )
    ).json()["code"]

    await client.get(f"/{code}")
    assert (await client.get(f"/api/links/{code}", headers=headers)).json()["click_count"] == 1


async def test_analytics_requires_ownership(client):
    owner = await register_and_login(client, "owner@example.com")
    code = (
        await client.post(
            "/api/links", json={"target_url": "https://example.com"}, headers=owner
        )
    ).json()["code"]

    intruder = await register_and_login(client, "intruder@example.com")
    response = await client.get(f"/api/links/{code}/analytics", headers=intruder)
    assert response.status_code == 404
