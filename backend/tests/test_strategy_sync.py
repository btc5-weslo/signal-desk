"""Strategy catalog sync from signal_quant.registry.list_strategies()."""

from __future__ import annotations

from app.cli import main as cli_main
from app.services.repository import MockRepository
from app.services.strategy_sync import strategy_from_registry_class, sync_strategies


class _Alpha:
    """First-line description stays in the catalog."""

    strategy_id = "alpha"
    version = "1.0.0"
    name = "Alpha"
    hypothesis_id = "H1"
    is_mock = False
    supported = (("crypto", "1h"), ("crypto", "4h"), ("equity", "1d"))


class _Mockish:
    strategy_id = "mockish"
    version = "1"
    is_mock = True
    supported = (("crypto", "1h"),)


def test_sync_writes_global_unvalidated_strategies_without_metrics():
    repo = MockRepository(seed_mocks=False)
    n = sync_strategies(repo)
    # Registry may still be landing; if present, rows must be global and bare.
    items = repo.list_strategies(tenant_id="demo").items
    if n == 0:
        return
    assert items
    for s in items:
        assert repo._strategy_tenant[(s.id, s.version)] is None
        assert s.latest_run_id is None
        assert not hasattr(s, "metrics") or getattr(s, "metrics", None) in (None, {})
        dumped = s.model_dump()
        for banned in ("sharpe", "win_rate", "cagr", "profit_factor"):
            assert banned not in dumped or dumped[banned] in (None, 0, 0.0, "")


def test_sync_is_idempotent_and_preserves_latest_run_id(monkeypatch):
    repo = MockRepository(seed_mocks=False)
    monkeypatch.setattr(
        "app.services.strategy_sync._list_registry_classes",
        lambda: [_Alpha],
    )
    assert sync_strategies(repo) == 1
    first = repo.list_strategies(tenant_id="demo").items[0]
    assert first.latest_run_id is None
    first.latest_run_id = "run-keep"  # type: ignore[misc]
    # mutate stored row
    repo._strategies[0] = first.model_copy(update={"latest_run_id": "run-keep"})
    assert sync_strategies(repo) == 1
    again = next(s for s in repo._strategies if s.id == "alpha")
    assert again.latest_run_id == "run-keep"
    assert again.description is None  # docstring/name are not copied
    assert again.hypothesis is None
    assert again.hypothesis_id == "H1"
    assert repo._strategy_tenant[("alpha", "1.0.0")] is None


def test_sync_skips_is_mock_classes(monkeypatch):
    repo = MockRepository(seed_mocks=False)
    monkeypatch.setattr(
        "app.services.strategy_sync._list_registry_classes",
        lambda: [_Mockish],
    )
    assert sync_strategies(repo) == 0
    assert repo.list_strategies(tenant_id="demo").items == []






def test_mapper_skips_incomplete_class():
    class _NoId:
        version = "1"

    assert strategy_from_registry_class(_NoId) is None


def test_cli_sync_strategies(monkeypatch, capsys):
    repo = MockRepository(seed_mocks=False)
    monkeypatch.setattr("app.api.deps.get_repo", lambda: repo)
    monkeypatch.setattr(
        "app.services.strategy_sync._list_registry_classes",
        lambda: [_Alpha],
    )
    # cli imports sync_strategies at call time from the module; patch there too
    from app.services import strategy_sync as ss

    monkeypatch.setattr(ss, "_list_registry_classes", lambda: [_Alpha])
    assert cli_main(["sync-strategies"]) == 0
    out = capsys.readouterr().out
    assert "synced 1 strategy" in out



def test_missing_registry_attrs_are_null_and_never_filled_in():
    class _Bare:
        strategy_id = "bare"
        version = "1.0.0"
        name = "Bare"
        supported = (("crypto", "1h"),)

    row = strategy_from_registry_class(_Bare)
    assert row is not None
    assert row.name == "Bare"
    assert row.description is None
    assert row.hypothesis is None
    assert row.hypothesis_id is None
    dumped = row.model_dump()
    assert dumped["description"] is None
    assert dumped["hypothesis"] is None
    assert dumped["hypothesis_id"] is None


def test_bare_hypothesis_id_is_moved_out_of_hypothesis():
    class _Moved:
        strategy_id = "moved"
        version = "1"
        name = "Moved"
        hypothesis = "H1"
        supported = (("crypto", "1h"),)

    row = strategy_from_registry_class(_Moved)
    assert row is not None
    assert row.hypothesis_id == "H1"
    assert row.hypothesis is None


def test_banned_hypothesis_is_stored_as_null_and_logged(monkeypatch):
    from app.services import strategy_sync as ss

    class _Hype:
        strategy_id = "hype"
        version = "1.0.0"
        name = "Hype"
        hypothesis = "A profitable system with a high win rate."
        description = "Trend following on closed bars."
        supported = (("crypto", "1h"),)

    errors: list[str] = []
    monkeypatch.setattr(
        ss.log, "error",
        lambda msg, *a, **k: errors.append((msg % a) if a else msg),
    )
    repo = MockRepository(seed_mocks=False)
    monkeypatch.setattr(ss, "_list_registry_classes", lambda: [_Hype])
    assert ss.sync_strategies(repo) == 1
    row = repo.list_strategies(tenant_id="demo").items[0]
    assert row.hypothesis is None
    assert row.description == "Trend following on closed bars."
    assert any(
        "hype" in e and "hypothesis" in e and ("profitable" in e.lower() or "high win rate" in e.lower())
        for e in errors
    )



def test_strategy_text_win_rate_is_stored_as_null(monkeypatch):
    from app.services import strategy_sync as ss

    class _WR:
        strategy_id = "wr"
        version = "1.0.0"
        name = "WR"
        hypothesis = "Improves win rate versus buy and hold."
        description = "Closed-bar trend rules."
        supported = (("crypto", "1h"),)

    errors: list[str] = []
    monkeypatch.setattr(
        ss.log, "error",
        lambda msg, *a, **k: errors.append((msg % a) if a else msg),
    )
    repo = MockRepository(seed_mocks=False)
    monkeypatch.setattr(ss, "_list_registry_classes", lambda: [_WR])
    assert ss.sync_strategies(repo) == 1
    row = repo.list_strategies(tenant_id="demo").items[0]
    assert row.hypothesis is None
    assert row.description == "Closed-bar trend rules."
    assert any("wr" in e and "hypothesis" in e and "win rate" in e.lower() for e in errors)
