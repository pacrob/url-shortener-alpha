from app.services.redis import get_redis
from tests.fakes import UnavailableRedis


async def test_liveness(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readiness_ok(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readiness_redis_down(app, client):
    app.dependency_overrides[get_redis] = lambda: UnavailableRedis()
    resp = await client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
