from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes import health, links
from app.services.redis import RedisService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = RedisService.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.redis.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(links.router)
    return app


app = create_app()
