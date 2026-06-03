from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}
