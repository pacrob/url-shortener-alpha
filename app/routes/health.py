from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.services.redis import RedisService, get_redis

router = APIRouter(tags=["health"])

RedisDep = Annotated[RedisService, Depends(get_redis)]


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(redis: RedisDep):
    try:
        await redis.ping()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )
    return {"status": "ok"}
