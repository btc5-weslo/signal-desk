import asyncio
import logging
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
    s = get_settings()
    task = asyncio.create_task(_pipeline_loop(s)) if s.inprocess_scheduler else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        await broadcaster.stop()


async def _pipeline_loop(s: Settings) -> None:
    """Top up the newest bars, then run the same pass as the arq `scan_pipeline` cron.

    For hosts without a worker. Cycles run back to back, never overlapping: a
    cycle that overruns the interval makes the next one start right after it.
    """
    import time

    from app.api.deps import get_broadcaster, get_repo
    from app.pipeline.runner import run_pipeline
    from app.pipeline.topup import topup_store

    log = logging.getLogger("app.pipeline.inprocess")
    await asyncio.sleep(s.inprocess_first_delay_s)
    while True:
        t0 = time.monotonic()
        try:
            top = await asyncio.to_thread(
                topup_store, list(s.pipeline_symbols), list(s.pipeline_timeframes),
                data_dir=s.data_dir,
            )
            result = run_pipeline(repo=get_repo(), settings=s, broadcaster=get_broadcaster())
            log.warning("cycle %.1fs topup=%s pipeline=%s", time.monotonic() - t0, top, result)
        except Exception:  # logged with traceback; the next cycle retries
            log.exception("in-process cycle failed")
        elapsed = time.monotonic() - t0
        if elapsed > s.scheduler_interval_sec:
            log.warning("cycle took %.1fs (> %ss); next cycle starts now", elapsed,
                        s.scheduler_interval_sec)
        await asyncio.sleep(max(0.0, s.scheduler_interval_sec - elapsed))


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Signal API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, **cors_kwargs(s))
    app.include_router(router)
    return app


app = create_app()
