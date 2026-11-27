"""Brand-host resolution. Never use this for data tenancy (always JWT/API key)."""

from __future__ import annotations

import ipaddress


def hostname_of(value: str | None) -> str:
    return (value or "").split("/")[0].split(":")[0].strip().lower()


def client_is_trusted(client_ip: str | None, trusted_proxies: list[str]) -> bool:
    raw = (client_ip or "").strip().lower()
    if not raw:
        return False
    addrs: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    if raw == "localhost":
        addrs = [ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")]
    else:
        try:
            addrs = [ipaddress.ip_address(raw)]
        except ValueError:
            addrs = []
    for entry in trusted_proxies:
        token = entry.strip().lower()
        if not token:
            continue
        if token == "localhost":
            if raw == "localhost" or any(a.is_loopback for a in addrs):
                return True
            continue
        if token == raw:
            return True
        try:
            net = ipaddress.ip_network(token, strict=False)
        except ValueError:
            continue
        if any(a in net for a in addrs):
            return True
    return False


def branding_host(
    *,
    host: str | None,
    forwarded_host: str | None,
    client_ip: str | None,
    trusted_proxies: list[str],
) -> str:
    """Prefer X-Forwarded-Host only when the peer is a trusted proxy; else Host."""
    if forwarded_host and client_is_trusted(client_ip, trusted_proxies):
        name = hostname_of(forwarded_host.split(",")[0])
        if name:
            return name
    return hostname_of(host)
