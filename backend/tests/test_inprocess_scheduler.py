import asyncio

from app import main
from app.core.config import Settings


def test_pipeline_loop_runs_the_real_pipeline(monkeypatch):
    calls = []

    def fake_run_pipeline(**kwargs):
        calls.append(kwargs)
        raise asyncio.CancelledError  # stop after one pass

    monkeypatch.setattr("app.pipeline.runner.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr("app.pipeline.topup.topup_store", lambda *a, **k: {"new_bars": 0})
    s = Settings(env="dev", inprocess_scheduler=True, inprocess_first_delay_s=0)
    try:
        asyncio.run(main._pipeline_loop(s))
    except asyncio.CancelledError:
        pass
    assert len(calls) == 1
    assert calls[0]["settings"] is s


def test_scheduler_is_off_by_default():
    s = Settings(env="dev")
    assert s.inprocess_scheduler is False
    assert s.scheduler_interval_sec == 60


def test_loop_broadcaster_publishes_on_the_owning_loop():
    seen = []

    class B:
        async def publish(self, signal, *, tenant_id):
            seen.append((signal, tenant_id, asyncio.get_running_loop()))
            return 1

    async def run():
        loop = asyncio.get_running_loop()
        lb = main._LoopBroadcaster(B(), loop)
        fut = await asyncio.to_thread(lb.publish, "sig", tenant_id=None)
        assert await asyncio.wrap_future(fut) == 1
        return loop

    loop = asyncio.run(run())
    assert seen == [("sig", None, loop)]
