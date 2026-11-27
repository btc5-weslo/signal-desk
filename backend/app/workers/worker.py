"""arq worker: validate/publish signals, alert fan-out, live pipeline cron.

Run (Redis required): uv run arq app.workers.worker.WorkerSettings
Redis URL: SIGNAL_REDIS_URL (required in prod; default redis://localhost:6379/0
for the worker process only).

`publish_signal` validates the payload and routes through
`emit._publish_if_visible` so unapproved markets never fan out. Redis
envelopes always carry `tenant_id` (None = global). Do not publish raw
signals onto the `signals` channel.

The pipeline is also a plain callable (`app.pipeline.runner.run_pipeline`)
so tests do not need Redis or the cron scheduler. Cron is the poll fallback;
when Data ships `signal_data.live.update` / Redis `bars:closed`, trigger from
that and keep this cron as a backup.
"""
from typing import ClassVar

from arq.connections import RedisSettings
from arq.cron import cron
from signal_shared import Signal

from app.core.config import get_settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")


async def publish_signal(ctx: dict, payload: dict) -> dict:
    """Validate and publish only to tenants that can see the signal."""
    signal = Signal.model_validate(payload)
    from app.api.deps import get_broadcaster, get_repo
    from app.pipeline.emit import _publish_if_visible

    _publish_if_visible(
        signal,
        repo=get_repo(),
        settings=get_settings(),
        broadcaster=get_broadcaster(),
        alert_fn=None,
    )
    return {"id": signal.id, "published": True}


async def fanout_alerts(ctx: dict, payload: dict) -> list[str] | None:
    """Fan out a signal to configured alert channels. Empty payload is a no-op."""
    if not payload:
        return None
    from app.api.deps import get_repo
    from app.pipeline.visibility import is_live_signal_visible
    from app.services.alerts import send_alerts

    signal = Signal.model_validate(payload)
    settings = get_settings()
    repo = get_repo()
    failed: list[str] = []
    for tid in repo.list_tenant_ids():
        if not is_live_signal_visible(signal, repo=repo, tenant_id=tid, settings=settings):
            continue
        cfg = repo.get_tenant_config_by_id(tid)
        extras = list(cfg.extra_disclaimers) if cfg else []
        failed.extend(send_alerts(signal, repo.list_alert_channels(tenant_id=tid), extras))
    return failed


async def scan_pipeline(ctx: dict) -> dict:
    """Cron entrypoint; delegates to the plain `run_pipeline` callable."""
    from app.api.deps import get_broadcaster, get_repo
    from app.pipeline.runner import run_pipeline
    from app.services.alerts import send_alerts

    return run_pipeline(
        repo=get_repo(),
        settings=get_settings(),
        broadcaster=get_broadcaster(),
        alert_fn=send_alerts,
    )


class WorkerSettings:
    functions: ClassVar = [publish_signal, fanout_alerts, scan_pipeline]
    cron_jobs: ClassVar = [
        cron(scan_pipeline, minute=set(range(60)), unique=True, run_at_startup=False),
    ]
    redis_settings = _redis_settings()
