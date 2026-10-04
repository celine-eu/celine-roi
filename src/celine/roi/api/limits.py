"""Per-client request limits for the public API (REQ-1302, REQ-1303).

The calculators take no token, so the only thing that tells two callers apart is
the client address — the connection's peer as uvicorn resolved it, never a request
header (REQ-1301). Limits are kept in this process: with one replica that is the
whole service, and the edge limit in front of it is the first line anyway.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

WINDOW_SECONDS = 60.0

API_PREFIX = "/api/v1/"
FEEDBACK_PATHS = frozenset({"/api/v1/feedback"})


class FixedWindowLimiter:
    """At most ``limit`` hits per key in each window of ``WINDOW_SECONDS``."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str) -> int | None:
        """Count one hit; return ``None`` if allowed, else seconds until the next window."""
        now = self._clock()
        if len(self._windows) > 10_000:
            self._windows = {
                k: w for k, w in self._windows.items() if now - w[0] < WINDOW_SECONDS
            }
        start, count = self._windows.get(key, (now, 0))
        if now - start >= WINDOW_SECONDS:
            start, count = now, 0
        if count >= self.limit:
            return max(1, math.ceil(start + WINDOW_SECONDS - now))
        self._windows[key] = (start, count + 1)
        return None


def client_address(scope: Scope) -> str:
    client = scope.get("client")
    return client[0] if client else "unknown"


class PublicLimitsMiddleware:
    """Rate-limit and size-limit the POSTs an anonymous caller can make.

    Two groups, each with its own per-address limit and body cap: the feedback
    submission, and every other POST under ``/api/v1/`` (the calculators). Reads
    pass through untouched.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        calculators_per_minute: int,
        feedback_per_minute: int,
        calculators_max_body: int,
        feedback_max_body: int,
    ) -> None:
        self.app = app
        self._groups = {
            "calculators": (FixedWindowLimiter(calculators_per_minute), calculators_max_body),
            "feedback": (FixedWindowLimiter(feedback_per_minute), feedback_max_body),
        }

    def _group(self, scope: Scope) -> str | None:
        if scope["type"] != "http" or scope["method"] != "POST":
            return None
        path = scope["path"].rstrip("/")
        if path in FEEDBACK_PATHS:
            return "feedback"
        # Every other POST of the API is a calculator; a new one is limited
        # without anyone having to list it.
        if path.startswith(API_PREFIX):
            return "calculators"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        group = self._group(scope)
        if group is None:
            await self.app(scope, receive, send)
            return
        limiter, max_body = self._groups[group]

        retry_after = limiter.hit(client_address(scope))
        if retry_after is not None:
            await _reply(send, 429, "Too many requests", {"retry-after": str(retry_after)})
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_body:
            await _reply(send, 413, "Request body too large")
            return

        # Read the bounded body here and replay it: a body without Content-Length
        # (chunked) is capped too, and FastAPI never sees more than the cap.
        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # the client went away mid-body
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > max_body:
                await _reply(send, 413, "Request body too large")
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        await self.app(scope, _replay(b"".join(chunks), receive), send)


def _replay(body: bytes, receive: Receive) -> Receive:
    """Hand the buffered body over once, then defer to the real channel."""
    replayed = False

    async def replay() -> Message:
        nonlocal replayed
        if not replayed:
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


async def _reply(
    send: Send, status: int, detail: str, headers: dict[str, str] | None = None
) -> None:
    body = json.dumps({"detail": detail}).encode()
    raw = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    raw += [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": body})
