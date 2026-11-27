"""Canonical symbol mapping for the v1 universe.

Stable public names: ``from signal_data.symbols import to_canonical, to_source, SYMBOLS``.

Canonical forms (used in the store, signals, API, and reports):

- crypto: BTC-USDT, ETH-USDT, SOL-USDT, BNB-USDT, XRP-USDT
- equity: SPY, QQQ, AAPL, MSFT, NVDA, TSLA, AMZN, META
- fx:     EURUSD, GBPUSD, USDJPY, AUDUSD

``to_canonical(raw)`` accepts ccxt pairs (BTC/USDT), compact forms (BTCUSDT),
Coinbase USD quotes (BTC-USD, BTC/USD), yfinance FX tickers (EURUSD=X),
Stooq suffixes (aapl.us), and already-canonical names.

``to_source(canonical, source)`` returns the ticker that source expects
(ccxt pair, yfinance ticker, Stooq code, or Frankfurter base/quote).
"""

from __future__ import annotations

CRYPTO_SYMBOLS: tuple[str, ...] = (
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "BNB-USDT",
    "XRP-USDT",
)
EQUITY_SYMBOLS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "META",
)
FX_SYMBOLS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
)

# Exported v1 universe list (canonical symbols, stable order).
SYMBOLS: tuple[str, ...] = CRYPTO_SYMBOLS + EQUITY_SYMBOLS + FX_SYMBOLS

CRYPTO_BASES = frozenset(s.split("-")[0] for s in CRYPTO_SYMBOLS)
FX_SET = frozenset(FX_SYMBOLS)
EQUITY_SET = frozenset(EQUITY_SYMBOLS)
CANONICAL_SET = frozenset(SYMBOLS)

__all__ = ["SYMBOLS", "to_canonical", "to_source", "universe_symbols", "asset_class_of", "SymbolError"]

# Longer quotes first so USDT wins over USD when splitting compact names.
_CRYPTO_QUOTES = ("USDT", "USDC", "USD", "EUR", "GBP")
_FX_QUOTES = ("USD", "JPY", "EUR", "GBP", "AUD", "CHF", "CAD", "NZD")
_FX_BASES = ("EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY")

_CCXT_EXCHANGES = frozenset(
    {
        "ccxt",
        "binance",
        "binanceus",
        "kraken",
        "coinbase",
        "coinbaseexchange",
        "coinbaseinternational",
        "coinbaseadvanced",
    }
)
_COINBASE = frozenset({"coinbase", "coinbaseexchange", "coinbaseinternational", "coinbaseadvanced"})


class SymbolError(ValueError):
    """Raised when a symbol cannot be mapped into the v1 universe."""


def asset_class_of(canonical: str) -> str:
    c = to_canonical(canonical)
    if c in CRYPTO_SYMBOLS:
        return "crypto"
    if c in EQUITY_SET:
        return "equity"
    if c in FX_SET:
        return "fx"
    raise SymbolError(f"{canonical!r} is not in the v1 universe")


def _strip_wrappers(raw: str) -> str:
    s = raw.strip()
    # yfinance FX / index suffix
    if s.upper().endswith("=X"):
        s = s[:-2]
    # Stooq equity suffix
    if s.lower().endswith(".us"):
        s = s[:-3]
    return s.strip()


def _compact_crypto(body: str) -> str | None:
    """Split BTCUSDT / BTCUSD into a canonical crypto symbol when the base is in universe."""
    u = body.upper()
    for quote in _CRYPTO_QUOTES:
        if u.endswith(quote) and len(u) > len(quote):
            base = u[: -len(quote)]
            if base in CRYPTO_BASES:
                return f"{base}-USDT"
    return None


def _compact_fx(body: str) -> str | None:
    u = body.upper().replace("-", "").replace("/", "").replace("_", "")
    if u in FX_SET:
        return u
    for quote in _FX_QUOTES:
        if u.endswith(quote) and len(u) > len(quote):
            base = u[: -len(quote)]
            if base in _FX_BASES:
                cand = f"{base}{quote}"
                if cand in FX_SET:
                    return cand
    return None


def to_canonical(raw: str) -> str:
    """Map a raw ticker from any supported source to the canonical v1 symbol.

    Raises SymbolError if the string cannot be mapped into the locked universe.
    """
    if raw is None or not str(raw).strip():
        raise SymbolError("empty symbol")
    s = _strip_wrappers(str(raw))
    s = s.replace(" ", "")
    # Already canonical (case-insensitive).
    upper = s.upper()
    if upper in CANONICAL_SET:
        return upper
    # Equity passthrough (AAPL, spy, ...)
    if upper in EQUITY_SET:
        return upper

    dashed = upper.replace("/", "-").replace("_", "-")

    # Crypto with a separator: BTC/USDT, BTC-USD, ETH-USD (Coinbase).
    if "-" in dashed and dashed.count("-") == 1:
        base, quote = dashed.split("-")
        if base in CRYPTO_BASES and quote in {"USDT", "USD", "USDC"}:
            return f"{base}-USDT"
        # FX written as EUR-USD
        fx = _compact_fx(dashed)
        if fx:
            return fx

    # Compact crypto: BTCUSDT, BTCUSD, ETHUSD
    crypto = _compact_crypto(upper.replace("-", "").replace("/", "").replace("_", ""))
    if crypto:
        return crypto

    # Compact or dashed FX: EURUSD, EUR/USD, EURUSD=X (suffix already stripped)
    fx = _compact_fx(upper)
    if fx:
        return fx

    # ccxt-style with no hyphen after slash replace already handled; try remaining
    if dashed in CANONICAL_SET:
        return dashed

    raise SymbolError(f"cannot map {raw!r} to a v1 canonical symbol")


def to_source(canonical: str, source: str) -> str:
    """Map a canonical symbol to the ticker ``source`` expects.

    ``source`` is a vendor or exchange id: ccxt, binance, coinbase, kraken,
    yfinance, stooq, frankfurter (case-insensitive; ``ccxt:binance`` is ok).
    """
    if not source or not str(source).strip():
        raise SymbolError("empty source")
    canon = to_canonical(canonical)
    src = str(source).strip().lower()
    if ":" in src:
        # allow "ccxt:binance" or "yfinance:default"
        prefix, _, rest = src.partition(":")
        src = rest or prefix

    cls = asset_class_of(canon)

    if src in _CCXT_EXCHANGES or src == "ccxt":
        if cls != "crypto":
            raise SymbolError(f"{source!r} is a crypto exchange; {canon} is {cls}")
        base = canon.split("-")[0]
        # Coinbase spot books are typically USD, not USDT.
        if src in _COINBASE:
            return f"{base}/USD"
        return f"{base}/USDT"

    if src in {"yfinance", "yahoo"}:
        if cls == "equity":
            return canon
        if cls == "fx":
            return f"{canon}=X"
        # yfinance crypto tickers are typically BASE-USD
        return f"{canon.split('-')[0]}-USD"

    if src == "stooq":
        if cls != "equity":
            raise SymbolError(f"stooq mapping is defined for equities; got {canon}")
        return f"{canon.lower()}.us"

    if src in {"frankfurter", "ecb"}:
        if cls != "fx":
            raise SymbolError(f"frankfurter mapping is defined for FX; got {canon}")
        return f"{canon[:3]}/{canon[3:]}"

    raise SymbolError(f"unknown source {source!r}")


def universe_symbols() -> list[str]:
    """Return the v1 canonical symbol list (copy)."""
    return list(SYMBOLS)
