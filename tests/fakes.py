"""In-memory stand-ins for RedisService, used via dependency override."""


class FakeRedis:
    """In-memory implementation matching the RedisService interface."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0


class UnavailableRedis(FakeRedis):
    """Simulates an unreachable Redis: ping() raises."""

    async def ping(self) -> bool:
        raise ConnectionError("redis unavailable")
