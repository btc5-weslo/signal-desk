import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    tenant_id: str
    subject: str
    kind: str  # "user" | "api_key"


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_access_token(sub: str, tenant_id: str, s: Settings) -> str:
    now = datetime.now(UTC)
    payload = {"sub": sub, "tid": tenant_id, "iat": now,
               "exp": now + timedelta(minutes=s.jwt_ttl_minutes), "typ": "access"}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def _principal_from_payload(p: dict, *, kind: str) -> Principal:
    return Principal(tenant_id=p["tid"], subject=p["sub"], kind=kind)


def decode_token(token: str, s: Settings) -> Principal:
    try:
        p = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from e
    typ = p.get("typ", "access")
    if typ != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return _principal_from_payload(p, kind="user")


# Dev API keys (hash -> tenant). Prod resolves against the api_keys table.
DEV_API_KEYS: dict[str, str] = {hash_api_key("dev-key"): "demo"}


def principal_from_api_key(raw: str, s: Settings) -> Principal:
    tid = DEV_API_KEYS.get(hash_api_key(raw)) if s.env != "prod" else None
    if not tid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")
    return Principal(tenant_id=tid, subject="api_key", kind="api_key")


def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_api_key: str | None = Header(default=None),
    s: Settings = Depends(get_settings),
) -> Principal:
    if creds:
        return decode_token(creds.credentials, s)
    if x_api_key:
        return principal_from_api_key(x_api_key, s)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "auth required (Bearer JWT or X-API-Key)")
