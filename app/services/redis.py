from __future__ import annotations

from fastapi import Request
from redis.asyncio import Redis


class RedisService:
    """Thin async wrapper around redis.asyncio.Redis.

    Exposes only the operations the app needs, so it can be swapped for an
    in-memory fake in tests via a FastAPI dependency override.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisService:
        return cls(Redis.from_url(url, decode_responses=True))

    async def ping(self) -> bool:
        return await self._client.ping()

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        return await self._client.hset(key, mapping=mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return await self._client.hgetall(key)

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        return await self._client.hincrby(key, field, amount)

    async def exists(self, key: str) -> int:
        return await self._client.exists(key)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self._client.expire(key, seconds)

    async def delete(self, key: str) -> int:
        return await self._client.delete(key)

    async def close(self) -> None:
        await self._client.aclose()


def get_redis(request: Request) -> RedisService:
    """FastAPI dependency: return the app's RedisService.

    Set up in the app lifespan and stored on app.state. Overridden in tests.
    """
    return request.app.state.redis
