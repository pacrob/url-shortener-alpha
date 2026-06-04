import secrets
import string
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl

from app.config import Settings, get_settings
from app.services.redis import RedisService, get_redis

router = APIRouter(tags=["links"])

RedisDep = Annotated[RedisService, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_ALPHABET = string.ascii_letters + string.digits
_CODE_LENGTH = 6


class LinkCreate(BaseModel):
    url: HttpUrl
    ttl_seconds: int | None = Field(default=None, gt=0)


class LinkCreated(BaseModel):
    code: str
    short_url: str


class LinkMetadata(BaseModel):
    url: str
    created_at: str
    clicks: int


def _key(code: str) -> str:
    return f"snip:{code}"


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


@router.post("/links", status_code=status.HTTP_201_CREATED)
async def create_link(
    payload: LinkCreate, redis: RedisDep, settings: SettingsDep
) -> LinkCreated:
    code = _generate_code()
    while await redis.exists(_key(code)):
        code = _generate_code()

    await redis.hset(
        _key(code),
        mapping={
            "url": str(payload.url),
            "created_at": datetime.now(UTC).isoformat(),
            "clicks": "0",
        },
    )

    ttl = (
        payload.ttl_seconds
        if payload.ttl_seconds is not None
        else settings.default_ttl_seconds
    )
    if ttl is not None:
        await redis.expire(_key(code), ttl)

    return LinkCreated(code=code, short_url=f"{settings.base_url}/{code}")


@router.get("/links/{code}")
async def get_metadata(code: str, redis: RedisDep) -> LinkMetadata:
    data = await redis.hgetall(_key(code))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return LinkMetadata(
        url=data["url"],
        created_at=data["created_at"],
        clicks=int(data["clicks"]),
    )


@router.delete("/links/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(code: str, redis: RedisDep) -> Response:
    await redis.delete(_key(code))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{code}")
async def redirect(code: str, redis: RedisDep) -> RedirectResponse:
    data = await redis.hgetall(_key(code))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await redis.hincrby(_key(code), "clicks", 1)
    return RedirectResponse(
        url=data["url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
