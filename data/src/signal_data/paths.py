"""Repo-relative paths. The package lives at /workspace/signal-app/data.

``SIGNAL_DATA_DIR`` (and the ``data_dir=`` argument) is the *store root*:
the directory that directly contains ``crypto/``, ``equity/`` and ``fx/``.
Files resolve to ``$SIGNAL_DATA_DIR/{asset_class}/{symbol}/{timeframe}.parquet``.

The repo default (``/workspace/signal-app/data/store``) is used only when
``SIGNAL_ENV`` is unset or is ``dev`` / ``test``. In ``staging`` / ``prod``,
a missing ``SIGNAL_DATA_DIR`` raises — there is no silent hard-coded fallback.

Staging is a separate optional root, ``SIGNAL_DATA_STAGING_DIR``.
There is no ``SIGNAL_DATA_STORE_DIR``.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # .../data
DEFAULT_STORE_DIR = PACKAGE_ROOT / "store"
DEFAULT_STAGING_DIR = PACKAGE_ROOT / "staging"
CATALOG_DIR = PACKAGE_ROOT / "catalog"
CATALOG_DB = CATALOG_DIR / "catalog.duckdb"
REPORTS_DIR = PACKAGE_ROOT / "reports"
QUALITY_DIR = REPORTS_DIR / "quality"
TRACKER_DIR = PACKAGE_ROOT / "tracker"
SCHEMAS_DIR = PACKAGE_ROOT / "schemas"

# Environments that may use the repo default store path.
_DEV_ENVS = frozenset({"", "dev", "test"})

# Locked v1 Parquet layout (Backend reads these files directly).
#   {store_root}/{asset_class}/{symbol}/{timeframe}.parquet
ASSET_CLASSES = ("crypto", "equity", "fx")
TIMEFRAMES = ("15m", "1h", "4h", "1d")

# Raw store keeps stale bars and flags them. get_candles/load_closed drop them
# by default.
PARQUET_COLUMNS = (
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "is_stale",
    "source_seam",
)


class MissingDataDir(RuntimeError):
    """SIGNAL_DATA_DIR is required when SIGNAL_ENV is staging or prod."""


def signal_env() -> str:
    """Lowercased SIGNAL_ENV, or '' if unset."""
    return (os.environ.get("SIGNAL_ENV") or "").strip().lower()


def _require_or_default(kind: str, env_name: str, default: Path, *, optional: bool = False) -> Path:
    value = (os.environ.get(env_name) or "").strip()
    if value:
        return Path(value)
    env = signal_env()
    if env in _DEV_ENVS:
        return default
    if optional:
        return default
    raise MissingDataDir(
        f"{env_name} is not set and SIGNAL_ENV={env!r} does not allow the "
        f"repo default {kind} path ({default}). Set {env_name} to the "
        f"{kind} root (the directory that contains crypto/, equity/, fx/)."
    )


def get_store_dir(data_dir: Path | str | None = None) -> Path:
    """Store root, resolved at call time (never frozen at import).

    Precedence: explicit ``data_dir`` argument, then ``SIGNAL_DATA_DIR``,
    then the repo default only when ``SIGNAL_ENV`` is unset or dev/test.
    """
    if data_dir is not None:
        return Path(data_dir)
    return _require_or_default("store", "SIGNAL_DATA_DIR", DEFAULT_STORE_DIR)


def get_staging_dir(staging_dir: Path | str | None = None) -> Path:
    """Staging root, resolved at call time.

    Precedence: explicit argument, then ``SIGNAL_DATA_STAGING_DIR``,
    then the repo default (staging is optional; the default is allowed
    in every environment, but backfills should still set the env in prod).
    """
    if staging_dir is not None:
        return Path(staging_dir)
    value = (os.environ.get("SIGNAL_DATA_STAGING_DIR") or "").strip()
    if value:
        return Path(value)
    return DEFAULT_STAGING_DIR


class _LazyDir:
    """Path-like proxy so STORE_DIR / STAGING_DIR resolve at use time, not import time."""

    def __init__(self, getter):
        self._getter = getter

    def _p(self) -> Path:
        return self._getter()

    def __fspath__(self) -> str:
        return str(self._p())

    def __str__(self) -> str:
        return str(self._p())

    def __repr__(self) -> str:
        return repr(self._p())

    def __truediv__(self, other):
        return self._p() / other

    def __eq__(self, other) -> bool:
        return self._p() == Path(other) if other is not None else False

    def __hash__(self):
        return hash(self._p())

    def __getattr__(self, name):
        return getattr(self._p(), name)


# Resolved at use time. Prefer get_store_dir() / get_staging_dir() in new code.
STORE_DIR = _LazyDir(get_store_dir)
STAGING_DIR = _LazyDir(get_staging_dir)


def _validate_env_at_import() -> None:
    # In staging/prod, fail fast if the store root is not configured.
    env = signal_env()
    if env not in _DEV_ENVS and not (os.environ.get("SIGNAL_DATA_DIR") or "").strip():
        raise MissingDataDir(
            "SIGNAL_DATA_DIR is not set and SIGNAL_ENV="
            f"{env!r} does not allow the repo default store path "
            f"({DEFAULT_STORE_DIR}). Set SIGNAL_DATA_DIR to the store root "
            "(the directory that contains crypto/, equity/, fx/)."
        )


_validate_env_at_import()


def _check_coords(asset_class: str, symbol: str, timeframe: str) -> None:
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"asset_class must be one of {ASSET_CLASSES}, got {asset_class!r}")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    if "/" in symbol or "\\" in symbol:
        raise ValueError(f"symbol must not contain slashes: {symbol!r}")


def series_path(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    data_dir: Path | str | None = None,
) -> Path:
    _check_coords(asset_class, symbol, timeframe)
    return get_store_dir(data_dir) / asset_class / symbol / f"{timeframe}.parquet"


def staging_path(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    staging_dir: Path | str | None = None,
) -> Path:
    """Backfill destination. Never write a backfill straight into the store root."""
    _check_coords(asset_class, symbol, timeframe)
    return get_staging_dir(staging_dir) / asset_class / symbol / f"{timeframe}.parquet"
