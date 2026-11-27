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
