from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router
from app.core.config import Settings, get_settings


def cors_kwargs(s: Settings) -> dict:
    """CORS policy: credentials only when origins are an explicit list, never '*'."""
    origins = [o.strip() for o in s.cors_origins if o and o.strip()]
    wildcard = any(o == "*" for o in origins)
    return {
        "allow_origins": ["*"] if wildcard else origins,
        "allow_methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type", "X-API-Key"],
        "allow_credentials": bool(origins) and not wildcard,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.api.deps import get_broadcaster, get_repo
    from app.services.strategy_sync import sync_strategies

    sync_strategies(get_repo())
    broadcaster = get_broadcaster()
    await broadcaster.start()
    try:
        yield
    finally:
        await broadcaster.stop()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Signal API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, **cors_kwargs(s))
    app.include_router(router)
    return app


app = create_app()
