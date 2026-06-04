import asyncio

import pytest


async def test_create_link(client):
    resp = await client.post("/links", json={"url": "https://example.com/page"})
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["code"]) == 6
    assert data["code"].isalnum()
    assert data["short_url"] == f"http://localhost/{data['code']}"


async def test_create_link_invalid_url(client):
    resp = await client.post("/links", json={"url": "not-a-url"})
    assert resp.status_code == 422


async def test_redirect(client):
    created = await client.post("/links", json={"url": "https://example.com/page"})
    code = created.json()["code"]
    resp = await client.get(f"/{code}")
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example.com/page"


async def test_redirect_not_found(client):
    resp = await client.get("/nope123")
    assert resp.status_code == 404


async def test_get_metadata(client):
    created = await client.post("/links", json={"url": "https://example.com/page"})
    code = created.json()["code"]
    resp = await client.get(f"/links/{code}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com/page"
    assert data["clicks"] == 0
    assert "created_at" in data


async def test_clicks_increment(client):
    created = await client.post("/links", json={"url": "https://example.com/page"})
    code = created.json()["code"]
    await client.get(f"/{code}")
    await client.get(f"/{code}")
    resp = await client.get(f"/links/{code}")
    assert resp.json()["clicks"] == 2


async def test_delete_link(client):
    created = await client.post("/links", json={"url": "https://example.com/page"})
    code = created.json()["code"]
    resp = await client.delete(f"/links/{code}")
    assert resp.status_code == 204
    resp = await client.get(f"/{code}")
    assert resp.status_code == 404


async def test_create_link_without_ttl(client):
    created = await client.post("/links", json={"url": "https://example.com/page"})
    code = created.json()["code"]
    resp = await client.get(f"/links/{code}")
    assert resp.status_code == 200


@pytest.mark.slow
async def test_create_link_with_ttl(client):
    created = await client.post(
        "/links", json={"url": "https://example.com/page", "ttl_seconds": 1}
    )
    code = created.json()["code"]
    await asyncio.sleep(2)
    resp = await client.get(f"/{code}")
    assert resp.status_code == 404
