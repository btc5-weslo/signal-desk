"""Fan-out of new signals to WebSocket clients, scoped by tenant.

When SIGNAL_REDIS_URL is set, publish() writes an envelope
``{tenant_id, signal}`` to the ``signals`` Redis channel and each API
instance's subscriber fans that out to its local WebSocket queues.
``tenant_id`` of None is global and is delivered to every local subscriber.

When Redis is unset (local dev and unit tests), publish() stays in-process
and only delivers to queues on this Broadcaster.

Publisher-side visibility (``emit._publish_if_visible``) is the production
gate: unapproved markets must not be published onto the channel. The
broadcaster still drops ``is_mock`` signals when mock data is off.
"""

from __future__ import annotations

import asyncio
import json
import logging

from signal_shared import Signal

log = logging.getLogger(__name__)

SIGNALS_CHANNEL = "signals"


def encode_signal_envelope(signal: Signal, tenant_id: str | None) -> str:
    return json.dumps({
        "tenant_id": tenant_id,
        "signal": signal.model_dump(mode="json"),
    })


def decode_signal_envelope(raw: str | bytes) -> tuple[str | None, Signal]:
    if isinstance(raw, bytes):
        raw = raw.decode()
    body = json.loads(raw)
    if not isinstance(body, dict) or "tenant_id" not in body or "signal" not in body:
        raise ValueError("Redis signal envelope must include tenant_id and signal")
    return body["tenant_id"], Signal.model_validate(body["signal"])


class Broadcaster:
    def __init__(self, redis_client=None) -> None:
        self._subs: dict[asyncio.Queue[str], str] = {}
        self._redis = redis_client
        self._task: asyncio.Task | None = None
        self._pubsub = None

    def subscribe(self, tenant_id: str) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._subs[q] = tenant_id
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subs.pop(q, None)

    def _deliver_local(self, signal: Signal, *, tenant_id: str | None) -> int:
        if signal.is_mock:
            from app.core.config import get_settings
            if not get_settings().use_mock_data:
                return 0
        msg = signal.model_dump_json()
        n = 0
        for q, tid in list(self._subs.items()):
            if tenant_id is not None and tid != tenant_id:
                continue
            if q.full():
                q.get_nowait()  # drop oldest for slow consumers
            q.put_nowait(msg)
            n += 1
        return n

    async def publish(self, signal: Signal, *, tenant_id: str | None) -> int:
        if signal.is_mock:
            from app.core.config import get_settings
            if not get_settings().use_mock_data:
                return 0
        if self._redis is not None:
            await self._redis.publish(
                SIGNALS_CHANNEL, encode_signal_envelope(signal, tenant_id),
            )
            return 1
        return self._deliver_local(signal, tenant_id=tenant_id)

    async def start(self) -> None:
        if self._redis is None or self._task is not None:
            return
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(SIGNALS_CHANNEL)
        self._task = asyncio.create_task(self._listen(), name="signals-redis-subscriber")
        await asyncio.sleep(0)

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        pubsub = self._pubsub
        self._pubsub = None
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(SIGNALS_CHANNEL)
            except (ConnectionError, OSError, RuntimeError):
                pass
            try:
                await pubsub.aclose()
            except (ConnectionError, OSError, RuntimeError, AttributeError):
                close = getattr(pubsub, "close", None)
                if callable(close):
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result

    async def _listen(self) -> None:
        pubsub = self._pubsub
        if pubsub is None:
            return
        try:
            async for raw in pubsub.listen():
                if not raw or raw.get("type") != "message":
                    continue
                try:
                    tenant_id, signal = decode_signal_envelope(raw.get("data"))
                except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
                    log.warning("dropping malformed Redis signal envelope: %s", exc)
                    continue
                self._deliver_local(signal, tenant_id=tenant_id)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError, RuntimeError) as exc:
            log.warning("Redis signal subscriber stopped: %s", exc)
