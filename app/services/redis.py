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

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        return await self._client.set(key, value, ex=ex)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def delete(self, key: str) -> int:
        return await self._client.delete(key)

    async def close(self) -> None:
        await self._client.aclose()


def get_redis(request: Request) -> RedisService:
    """FastAPI dependency: return the app's RedisService.

    Set up in the app lifespan and stored on app.state. Overridden in tests.
    """
    return request.app.state.redis
