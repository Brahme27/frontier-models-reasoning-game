"""Admin passcode, client identity for rate limiting, and resource guards."""

from __future__ import annotations

import hmac
import ipaddress
from collections import Counter
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi import HTTPException, Request, status
from slowapi import Limiter
from starlette.requests import HTTPConnection

from app.config import Settings, get_settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _settings(conn: HTTPConnection) -> Settings:
    return getattr(conn.app.state, "settings", None) or get_settings()


def _normalise(address: str) -> str:
    """Group IPv6 clients by /64 (one subscriber's allocation) so they can't rotate past limits."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def client_ip(request: HTTPConnection) -> str:
    """The viewer's address.

    In production CloudFront is the only way in, and it sets ``CloudFront-Viewer-Address``
    itself, so that header is trusted there (``TRUST_CLOUDFRONT_HEADERS=true``). Anywhere else
    it is attacker-controlled and ignored in favour of the socket peer.
    """
    if _settings(request).trust_cloudfront_headers:
        viewer = request.headers.get("cloudfront-viewer-address")
        if viewer:
            return _normalise(viewer.rsplit(":", 1)[0].strip("[]"))
    return _normalise(request.client.host) if request.client else "unknown"


limiter = Limiter(key_func=client_ip)


def passcode_ok(settings: Settings, supplied: str | None) -> bool:
    expected = settings.admin_passcode.get_secret_value() if settings.admin_passcode else ""
    if not expected:
        # No passcode configured: open in local dev/test, locked shut in production.
        return settings.app_env != "prod"
    return supplied is not None and hmac.compare_digest(supplied.encode(), expected.encode())


def ensure_admin(request: Request, supplied: str | None) -> None:
    """Call *inside* a rate-limited endpoint so wrong guesses count against the limit."""
    if not passcode_ok(_settings(request), supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing admin passcode"
        )


class ConnectionLimiter:
    """Caps concurrent WebSocket viewers, globally and per client."""

    def __init__(self, total: int, per_client: int) -> None:
        self.total = total
        self.per_client = per_client
        self._open: Counter[str] = Counter()

    def acquire(self, client: str) -> bool:
        if sum(self._open.values()) >= self.total or self._open[client] >= self.per_client:
            return False
        self._open[client] += 1
        return True

    def release(self, client: str) -> None:
        self._open[client] -= 1
        if self._open[client] <= 0:
            del self._open[client]


class BodySizeLimit:
    """Reject request bodies over ``max_bytes`` before anything parses them."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await _reject(send)
            return
        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _TooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLarge:
            await _reject(send)


class _TooLarge(Exception):
    pass


async def _reject(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"detail":"request body too large"}'})
