import asyncio
import json
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, ConfigDict
from signal_shared import (
    BacktestIndexPage,
    BacktestReport,
    Candle,
    Signal,
    SignalPage,
    StrategyPage,
    StreamToken,
    TenantConfig,
    normalize_symbol,
)

from app.core.config import Settings, get_settings
from app.core.host import branding_host
from app.core.security import Principal, decode_token, get_principal, principal_from_api_key
from app.services.candles import BadCandleRequest, CandleNotFound, load_candles
from app.services.claims import BannedClaimError
from app.services.cursors import decode_signal_cursor
from app.services.stream_tokens import StreamTokenError

from .deps import get_broadcaster, get_repo, get_stream_tokens

router = APIRouter(prefix="/v1")

# First-message WebSocket auth must arrive within this window.
WS_AUTH_TIMEOUT_SECONDS = 5.0

_WS_AUTH_ERRORS = (
    TimeoutError, WebSocketDisconnect, ValueError, TypeError,
    json.JSONDecodeError, HTTPException, RuntimeError, StreamTokenError,
)


class TenantConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tagline: str | None = None
    # Accepted only so a tenant-supplied value can be stripped, never stored.
    licensed_data_sources: list[str] | None = None



def _with_platform(cfg: TenantConfig, s: Settings) -> TenantConfig:
    """Stamp platform fields. Tenant rows can never set licensed_data_sources."""
    return cfg.model_copy(update={"licensed_data_sources": list(s.licensed_data_sources)})


def _normalize_filter_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    try:
        return normalize_symbol(symbol)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


def _visibility(s: Settings) -> dict:
    return {"include_mock": s.use_mock_data, "include_unapproved": s.allow_unapproved()}


@router.get("/health")
def health(s: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "env": s.env, "mock_data": s.use_mock_data}


@router.get("/tenant/config", response_model=TenantConfig)
def tenant_config(request: Request, repo=Depends(get_repo), s: Settings = Depends(get_settings)):
    """Public white-label config. Branding host only — never used for data tenancy."""
    client_ip = request.client.host if request.client else None
    host = branding_host(
        host=request.headers.get("host"),
        forwarded_host=request.headers.get("x-forwarded-host"),
        client_ip=client_ip,
        trusted_proxies=s.trusted_proxies,
    )
    cfg = repo.get_tenant_config(host)
    if not cfg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant host")
    return _with_platform(cfg, s)


@router.patch("/tenant/config", response_model=TenantConfig)
def patch_tenant_config(
    body: TenantConfigUpdate,
    principal: Principal = Depends(get_principal),
    repo=Depends(get_repo),
    s: Settings = Depends(get_settings),
):
    # body.licensed_data_sources is ignored; the platform list is stamped below.
    try:
        cfg = repo.set_tenant_tagline(principal.tenant_id, body.tagline)
    except BannedClaimError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except KeyError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant") from e
    return _with_platform(cfg, s)


@router.get("/signals", response_model=SignalPage)
def list_signals(symbol: str | None = None, timeframe: str | None = None,
                 status_: str | None = Query(default=None, alias="status"),
                 limit: int = Query(default=100, ge=1, le=500),
                 cursor: str | None = None,
                 principal: Principal = Depends(get_principal), repo=Depends(get_repo),
                 s: Settings = Depends(get_settings)):
    symbol = _normalize_filter_symbol(symbol)
    if cursor:
        try:
            decode_signal_cursor(cursor)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return repo.list_signals(
        tenant_id=principal.tenant_id, symbol=symbol, timeframe=timeframe,
        status=status_, limit=limit, cursor=cursor, **_visibility(s),
    )


@router.get("/signals/{signal_id}", response_model=Signal)
def get_signal(signal_id: str, principal: Principal = Depends(get_principal),
               repo=Depends(get_repo), s: Settings = Depends(get_settings)):
    sig = repo.get_signal(signal_id, tenant_id=principal.tenant_id, **_visibility(s))
    if not sig:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "signal not found")
    return sig


@router.get("/strategies", response_model=StrategyPage)
def list_strategies(principal: Principal = Depends(get_principal), repo=Depends(get_repo)):
    return repo.list_strategies(tenant_id=principal.tenant_id)


@router.get("/backtests", response_model=BacktestIndexPage)
def list_backtests(
    strategy_id: str,
    version: str,
    principal: Principal = Depends(get_principal),
    repo=Depends(get_repo),
):
    """Per-market approval index. Metrics stay behind GET /v1/backtests/{run_id}."""
    return repo.list_backtests(
        tenant_id=principal.tenant_id, strategy_id=strategy_id, version=version,
    )


@router.get("/backtests/{run_id}", response_model=BacktestReport)
def get_backtest(run_id: str, principal: Principal = Depends(get_principal),
                 repo=Depends(get_repo)):
    r = repo.get_backtest(run_id, tenant_id=principal.tenant_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest not found or not QA-approved")
    return r


@router.get("/candles", response_model=list[Candle])
def list_candles(symbol: str, timeframe: str,
                 limit: int = Query(default=500, ge=1, le=5000),
                 end: datetime | None = None,
                 asset_class: str | None = None,
                 _: Principal = Depends(get_principal),
                 s: Settings = Depends(get_settings)):
    try:
        return load_candles(
            symbol=symbol, timeframe=timeframe, limit=limit, end=end,
            data_dir=s.data_dir, asset_class=asset_class,
        )
    except BadCandleRequest as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except CandleNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post("/stream/token", response_model=StreamToken)
def create_stream_token(
    principal: Principal = Depends(get_principal),
    store=Depends(get_stream_tokens),
) -> StreamToken:
    """Mint a 60s, single-use, tenant-scoped token for first-message WebSocket auth."""
    rec = store.issue(principal)
    return StreamToken(token=rec.token, expires_at=rec.expires_at)


async def _authenticate_ws(ws: WebSocket, s: Settings) -> Principal | None:
    """First-message auth within 5s.

    Accepted payloads (all require ``type":"auth"``):
    ``{"type":"auth","token":"<JWT>"}``, ``{"type":"auth","api_key":"..."}``,
    or ``{"type":"auth","token":"<stream-token>"}``.
    """
    await ws.accept()
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=WS_AUTH_TIMEOUT_SECONDS)
    except _WS_AUTH_ERRORS:
        await ws.close(code=4401)
        return None
    if not isinstance(msg, dict) or msg.get("type") != "auth":
        await ws.close(code=4401)
        return None
    try:
        if msg.get("token"):
            try:
                return get_stream_tokens().consume(msg["token"])
            except StreamTokenError:
                return decode_token(msg["token"], s)
        if msg.get("api_key"):
            return principal_from_api_key(msg["api_key"], s)
        raise ValueError("auth message needs token or api_key")
    except _WS_AUTH_ERRORS:
        await ws.close(code=4401)
        return None


@router.websocket("/stream/signals")
async def stream_signals(ws: WebSocket):
    """Live signal stream.

    Auth: after connect, send a first message within 5 seconds:
    `{"type":"auth","token":"<JWT>"}`, `{"type":"auth","api_key":"..."}`,
    or `{"type":"auth","token":"<stream-token>"}` from POST /v1/stream/token.
    Query-string tokens are not accepted.
    """
    principal = await _authenticate_ws(ws, get_settings())
    if principal is None:
        return
    b = get_broadcaster()
    q = b.subscribe(principal.tenant_id)
    try:
        while True:
            await ws.send_text(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        b.unsubscribe(q)
