"""In-memory stand-ins for RedisService, used via dependency override."""

import time


class FakeRedis:
    """In-memory implementation matching the RedisService interface.

    Links are stored as Redis hashes, so the backing store maps each key to a
    dict of string fields, mirroring redis-py with decode_responses=True.
    TTLs are tracked with wall-clock deadlines and purged lazily on access, so
    the expiry contract can be tested without a real Redis.
    """

    def __init__(self) -> None:
        self.store: dict[str, dict[str, str]] = {}
        self.expiry: dict[str, float] = {}

    def _purge_if_expired(self, key: str) -> None:
        deadline = self.expiry.get(key)
        if deadline is not None and time.monotonic() >= deadline:
            self.store.pop(key, None)
            self.expiry.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        hash_ = self.store.setdefault(key, {})
        hash_.update({k: str(v) for k, v in mapping.items()})
        return len(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        self._purge_if_expired(key)
        return dict(self.store.get(key, {}))

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        self._purge_if_expired(key)
        hash_ = self.store.setdefault(key, {})
        new_value = int(hash_.get(field, 0)) + amount
        hash_[field] = str(new_value)
        return new_value

    async def exists(self, key: str) -> int:
        self._purge_if_expired(key)
        return 1 if key in self.store else 0

    async def expire(self, key: str, seconds: int) -> bool:
        if key not in self.store:
            return False
        self.expiry[key] = time.monotonic() + seconds
        return True

    async def delete(self, key: str) -> int:
        self.expiry.pop(key, None)
        return 1 if self.store.pop(key, None) is not None else 0


class UnavailableRedis(FakeRedis):
    """Simulates an unreachable Redis: ping() raises."""

    async def ping(self) -> bool:
        raise ConnectionError("redis unavailable")
