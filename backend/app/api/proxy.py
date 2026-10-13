"""Believe X-Forwarded-Proto and X-Forwarded-Host only from a trusted proxy.

Adapted from Engineering Tools (backend/maec_auth/proxy.py). Behind the host's Caddy and
this stack's own Caddy (the frontend container) this process sees plain http and the
internal hop's Host. The host's Caddy sets X-Forwarded-Proto: https and X-Forwarded-Host to
the address the browser used, and the frontend container passes both through unchanged.
This layer applies them to the request (scheme and Host), but only when the request's
SOCKET PEER is in TRUSTED_PROXIES. From anyone else they are ignored, because anyone can
send them.

Why here and not uvicorn's --proxy-headers: uvicorn replaces the peer address with
X-Forwarded-For's before the app runs, so nothing in the app could ask which peer a header
came from, and uvicorn does not read X-Forwarded-Host at all. The backend also sits on MAEC
One Core's shared network, where Core (and other apps) can reach it directly; a per-peer
check is what keeps their requests from choosing a scheme or host. uvicorn runs with
--no-proxy-headers so this is the only list.

The gate (app/api/gate.py) reads the result: X-Original-URL must be the public address,
because Core only follows a sign-in's `next` back to an app's own address.
"""

import ipaddress
import re
from functools import lru_cache

from app.core.config import get_settings

# A host as a proxy may forward it: name or address, optional port. Anything else (a path,
# a user@, a space) is not applied.
_HOST = re.compile(r"^[A-Za-z0-9.-]+(:[0-9]{1,5})?$")


class ProxyConfigError(RuntimeError):
    """TRUSTED_PROXIES names something that cannot be a proxy list."""


@lru_cache(maxsize=8)
def _parse(raw: str) -> tuple[frozenset, tuple, frozenset]:
    addresses, networks, literals = set(), [], set()
    for entry in (item.strip() for item in raw.split(",")):
        if not entry:
            continue
        if entry == "*":
            raise ProxyConfigError(
                "TRUSTED_PROXIES may not be '*': that believes X-Forwarded-Proto and X-Forwarded-Host from anyone."
            )
        try:
            if "/" in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                addresses.add(ipaddress.ip_address(entry))
        except ValueError:
            literals.add(entry)  # not an address: a name, as the test client's "testclient"
    return frozenset(addresses), tuple(networks), frozenset(literals)


def check() -> None:
    """Raise at startup if TRUSTED_PROXIES is unusable (e.g. '*')."""
    _parse(get_settings().trusted_proxies)


def trusts(peer: str | None) -> bool:
    if not peer:
        return False
    addresses, networks, literals = _parse(get_settings().trusted_proxies)
    if peer in literals:
        return True
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return address in addresses or any(address in network for network in networks)


def _last(value: bytes) -> str:
    """The value the nearest proxy wrote, if several hops each added one."""
    return value.decode("latin-1").split(",")[-1].strip()


class TrustedProxyHeaders:
    """Pure ASGI: apply a trusted peer's X-Forwarded-Proto and -Host."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            client = scope.get("client")
            if client and trusts(client[0]):
                scope = self._apply(scope)
        await self.app(scope, receive, send)

    @staticmethod
    def _apply(scope):
        forwarded = {
            name: value for name, value in scope["headers"] if name in (b"x-forwarded-proto", b"x-forwarded-host")
        }
        changed = dict(scope)
        proto = _last(forwarded.get(b"x-forwarded-proto", b"")).lower()
        if proto in ("http", "https"):
            changed["scheme"] = proto
        host = _last(forwarded.get(b"x-forwarded-host", b""))
        if host and _HOST.match(host):
            changed["headers"] = [(name, value) for name, value in scope["headers"] if name != b"host"] + [
                (b"host", host.encode("latin-1"))
            ]
        return changed
