"""Data access layer. v1 skeleton serves mock data; swap for the Postgres repo without touching routes.

Every read is scoped to the caller's tenant_id. Strategies, signals, and
backtests with tenant_id NULL are a shared catalog visible to every tenant.
A backtest is served only when a backtest_approvals row matches both the
report's run_id and data_hash.

Approvals with tenant_id NULL are global and may calibrate any tenant's
signals; otherwise the approval's tenant must match. On ingest, a signal with
confidence_calibrated=True is rejected unless such an approval exists for
calibration_run_id. On read, a missing approval forces confidence_calibrated
to False while leaving calibration_run_id visible.

Live (non-mock) signals are stored even without a QA-approved backtest for
that exact strategy+version+symbol+timeframe, but they are not served,
broadcast, or alerted unless that market is approved (or a dev-only override
is on).
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from signal_shared import (
    BacktestIndexItem,
    BacktestIndexPage,
    BacktestReport,
    Signal,
    SignalPage,
    Strategy,
    StrategyPage,
    TenantConfig,
)

from .claims import require_clean_tagline, sanitize_tagline
from .cursors import decode_signal_cursor, encode_signal_cursor
from .mock_data import mock_signals, mock_strategies

# Mock signals belong to the dev-key tenant ("demo").
MOCK_TENANT_ID = "demo"
# Dev default Host -> tenant mapping (also used when the DB has no row yet).
DEV_TENANT_DOMAINS = {"localhost": MOCK_TENANT_ID, "127.0.0.1": MOCK_TENANT_ID}


@dataclass
class Approval:
    run_id: str
    data_hash: str
    reviewer: str
    approved_at: datetime
    notes: str = ""
    tenant_id: str | None = None  # None = global, visible to every tenant


@dataclass
class AlertChannelRecord:
    id: str
    tenant_id: str
    channel_type: str
    config: dict = field(default_factory=dict)
    enabled: bool = True


class Repository(Protocol):
    def list_signals(
        self, *, tenant_id: str, symbol: str | None, timeframe: str | None,
        status: str | None, limit: int, cursor: str | None,
        include_mock: bool = False, include_unapproved: bool = False,
    ) -> SignalPage: ...
    def get_signal(
        self, signal_id: str, *, tenant_id: str,
        include_mock: bool = False, include_unapproved: bool = False,
    ) -> Signal | None: ...
    def list_strategies(self, *, tenant_id: str) -> StrategyPage: ...
    def get_backtest(self, run_id: str, *, tenant_id: str) -> BacktestReport | None: ...
    def list_backtests(
        self, *, tenant_id: str, strategy_id: str, version: str,
    ) -> BacktestIndexPage: ...
    def get_tenant_config(self, host: str) -> TenantConfig | None: ...


class MockRepository:
    def __init__(self, *, seed_mocks: bool | None = None) -> None:
        if seed_mocks is None:
            from app.core.config import get_settings
            seed_mocks = get_settings().use_mock_data
        seeds = mock_signals() if seed_mocks else []
        strats = mock_strategies() if seed_mocks else []
        self._signals = {s.id: s for s in seeds}
        self._signal_tenant = {s.id: MOCK_TENANT_ID for s in self._signals.values()}
        self._strategies = strats
        # None = shared catalog
        self._strategy_tenant: dict[tuple[str, str], str | None] = {
            (s.id, s.version): None for s in self._strategies
        }
        self._backtests: dict[str, BacktestReport] = {}
        self._backtest_tenant: dict[str, str | None] = {}
        self._approvals: dict[tuple[str, str], Approval] = {}
        self._tenants: dict[str, TenantConfig] = {
            MOCK_TENANT_ID: TenantConfig(tenant_id=MOCK_TENANT_ID, name="Demo"),
        }
        self._tenant_domains: dict[str, str] = dict(DEV_TENANT_DOMAINS)
        self._cursors: dict[tuple[str, str], datetime] = {}
        self._alert_channels: dict[str, AlertChannelRecord] = {}

    def _visible_to(self, owner: str | None, tenant_id: str) -> bool:
        return owner in (None, tenant_id)

    def _has_calibration_approval(self, run_id: str | None, tenant_id: str | None) -> bool:
        if not run_id:
            return False
        return any(
            ap.run_id == run_id and ap.tenant_id in (None, tenant_id)
            for ap in self._approvals.values()
        )

    def _for_read(self, s: Signal, tenant_id: str) -> Signal:
        if s.confidence_calibrated and not self._has_calibration_approval(
            s.calibration_run_id, tenant_id
        ):
            return s.model_copy(update={"confidence_calibrated": False})
        return s

    def market_is_approved(
        self, strategy_id: str, version: str, symbol: str, timeframe: str,
        *, tenant_id: str,
    ) -> bool:
        for r in self._backtests.values():
            if (
                r.strategy_id == strategy_id
                and r.version == version
                and r.symbol == symbol
                and r.timeframe == timeframe
                and self._visible_to(self._backtest_tenant.get(r.run_id), tenant_id)
                and (r.run_id, r.data_hash) in self._approvals
            ):
                return True
        return False

    def _signal_is_servable(
        self, s: Signal, *, tenant_id: str, include_mock: bool, include_unapproved: bool,
    ) -> bool:
        # Query-layer gate: with include_mock=False, no is_mock row is returned
        # from list/get (or any count/summary built from those methods).
        if s.is_mock:
            return include_mock
        if include_unapproved:
            return True
        return self.market_is_approved(
            s.strategy_id, s.strategy_version, s.symbol, s.timeframe, tenant_id=tenant_id,
        )

    def list_signals(
        self, *, tenant_id, symbol=None, timeframe=None, status=None,
        limit=100, cursor=None, include_mock=False, include_unapproved=False,
    ):
        out = [
            self._for_read(s, tenant_id)
            for s in self._signals.values()
            if self._visible_to(self._signal_tenant.get(s.id), tenant_id)
            and (not symbol or s.symbol == symbol)
            and (not timeframe or s.timeframe == timeframe)
            and (not status or s.status.value == status)
            and self._signal_is_servable(
                s, tenant_id=tenant_id, include_mock=include_mock,
                include_unapproved=include_unapproved,
            )
        ]
        out.sort(key=lambda s: (s.generated_at, s.id), reverse=True)
        if cursor:
            ts, sid = decode_signal_cursor(cursor)
            out = [s for s in out if (s.generated_at, s.id) < (ts, sid)]
        page, rest = out[:limit], out[limit:]
        next_cursor = (
            encode_signal_cursor(page[-1].generated_at, page[-1].id) if rest and page else None
        )
        return SignalPage(items=page, next_cursor=next_cursor)

    def get_signal(
        self, signal_id, *, tenant_id, include_mock=False, include_unapproved=False,
    ):
        s = self._signals.get(signal_id)
        if not s or not self._visible_to(self._signal_tenant.get(signal_id), tenant_id):
            return None
        if not self._signal_is_servable(
            s, tenant_id=tenant_id, include_mock=include_mock,
            include_unapproved=include_unapproved,
        ):
            return None
        return self._for_read(s, tenant_id)

    def list_strategies(self, *, tenant_id):
        items = [
            s for s in self._strategies
            if self._strategy_tenant.get((s.id, s.version)) in (None, tenant_id)
        ]
        return StrategyPage(items=items, next_cursor=None)

    def upsert_strategy(self, strategy: Strategy, *, tenant_id: str | None = None) -> bool:
        """Idempotent catalog upsert. Preserves latest_run_id; invents no metrics."""
        key = (strategy.id, strategy.version)
        if key in self._strategy_tenant:
            current_owner = self._strategy_tenant[key]
            if current_owner not in (None, tenant_id):
                # Do not overwrite a tenant-private row with a global seed.
                return False
        existing = next((s for s in self._strategies if (s.id, s.version) == key), None)
        if existing is not None:
            kept = existing.latest_run_id
            updated = strategy.model_copy(update={"latest_run_id": kept})
            self._strategies = [
                updated if (s.id, s.version) == key else s for s in self._strategies
            ]
        else:
            self._strategies.append(strategy)
        self._strategy_tenant[key] = tenant_id
        return True

    def get_backtest(self, run_id, *, tenant_id):
        r = self._backtests.get(run_id)
        if not r or not self._visible_to(self._backtest_tenant.get(run_id), tenant_id):
            return None
        if (r.run_id, r.data_hash) not in self._approvals:
            return None
        return r

    def list_backtests(self, *, tenant_id, strategy_id, version):
        items: list[BacktestIndexItem] = []
        for r in self._backtests.values():
            if r.strategy_id != strategy_id or r.version != version:
                continue
            if r.symbol is None or r.timeframe is None:
                continue
            if not self._visible_to(self._backtest_tenant.get(r.run_id), tenant_id):
                continue
            items.append(BacktestIndexItem(
                symbol=r.symbol,
                timeframe=r.timeframe,
                run_id=r.run_id,
                flags=r.flags,
                approved=(r.run_id, r.data_hash) in self._approvals,
            ))
        items.sort(key=lambda i: (i.symbol, i.timeframe, i.run_id))
        return BacktestIndexPage(items=items, next_cursor=None)

    def get_tenant_config(self, host: str) -> TenantConfig | None:
        hostname = (host or "").split("/")[0].split(":")[0].strip().lower()
        tid = self._tenant_domains.get(hostname)
        if not tid:
            return None
        cfg = self._tenants.get(tid)
        if not cfg:
            return None
        return cfg.model_copy(update={
            "tagline": sanitize_tagline(cfg.tagline),
            "licensed_data_sources": [],  # platform-only; stamped by the API
        })

    def get_tenant_config_by_id(self, tenant_id: str) -> TenantConfig | None:
        cfg = self._tenants.get(tenant_id)
        if not cfg:
            return None
        return cfg.model_copy(update={
            "tagline": sanitize_tagline(cfg.tagline),
            "licensed_data_sources": [],
        })

    def set_tenant_tagline(self, tenant_id: str, tagline: str | None) -> TenantConfig:
        require_clean_tagline(tagline)
        cfg = self._tenants.get(tenant_id)
        if not cfg:
            raise KeyError(f"unknown tenant {tenant_id}")
        updated = cfg.model_copy(update={"tagline": tagline, "licensed_data_sources": []})
        self._tenants[tenant_id] = updated
        return updated

    def add_domain(self, host: str, tenant_id: str) -> None:
        self._tenant_domains[host.strip().lower()] = tenant_id

    def list_tenant_ids(self) -> list[str]:
        return list(self._tenants)

    def add_signal(self, s: Signal, *, tenant_id: str | None) -> bool:
        """Store a signal. Returns False if it is a duplicate (id or market+bar)."""
        if s.confidence_calibrated and not self._has_calibration_approval(
            s.calibration_run_id, tenant_id
        ):
            raise ValueError(
                "confidence_calibrated requires an approved calibration run "
                "for this tenant (or a global approval)"
            )
        if s.id in self._signals:
            return False
        if self.find_duplicate(
            s.strategy_id, s.strategy_version, s.symbol, s.timeframe, s.bar_close_time,
        ):
            return False
        self._signals[s.id] = s
        self._signal_tenant[s.id] = tenant_id
        return True

    def find_duplicate(
        self, strategy_id: str, version: str, symbol: str, timeframe: str,
        bar_close_time: datetime,
    ) -> Signal | None:
        for s in self._signals.values():
            if (
                s.strategy_id == strategy_id
                and s.strategy_version == version
                and s.symbol == symbol
                and s.timeframe == timeframe
                and s.bar_close_time == bar_close_time
            ):
                return s
        return None

    def update_signal(self, s: Signal) -> None:
        if s.id not in self._signals:
            return
        self._signals[s.id] = s

    def list_active_signals(self) -> list[Signal]:
        return [s for s in self._signals.values() if s.status.value == "active" and not s.is_mock]

    def remove_signal(self, signal_id: str) -> None:
        self._signals.pop(signal_id, None)
        self._signal_tenant.pop(signal_id, None)

    def add_backtest(self, report: BacktestReport, *, tenant_id: str | None) -> None:
        self._backtests[report.run_id] = report
        self._backtest_tenant[report.run_id] = tenant_id

    def add_approval(
        self, run_id: str, data_hash: str, reviewer: str = "qa", notes: str = "",
        tenant_id: str | None = None,
    ) -> None:
        self._approvals[(run_id, data_hash)] = Approval(
            run_id=run_id, data_hash=data_hash, reviewer=reviewer,
            approved_at=datetime.now(UTC), notes=notes, tenant_id=tenant_id,
        )

    def remove_approval(self, run_id: str, data_hash: str | None = None) -> None:
        if data_hash is not None:
            self._approvals.pop((run_id, data_hash), None)
            return
        for key in [k for k in self._approvals if k[0] == run_id]:
            self._approvals.pop(key)

    def remove_backtest(self, run_id: str) -> None:
        self._backtests.pop(run_id, None)
        self._backtest_tenant.pop(run_id, None)
        self.remove_approval(run_id)

    def get_cursor(self, symbol: str, timeframe: str) -> datetime | None:
        return self._cursors.get((symbol, timeframe))

    def set_cursor(self, symbol: str, timeframe: str, last_close_time: datetime) -> None:
        self._cursors[(symbol, timeframe)] = last_close_time

    def add_alert_channel(self, channel: AlertChannelRecord) -> None:
        self._alert_channels[channel.id] = channel

    def list_alert_channels(self, *, tenant_id: str | None = None) -> list[AlertChannelRecord]:
        out = [ch for ch in self._alert_channels.values() if ch.enabled]
        if tenant_id is not None:
            out = [ch for ch in out if ch.tenant_id == tenant_id]
        return out

    def remove_alert_channel(self, channel_id: str) -> None:
        self._alert_channels.pop(channel_id, None)
