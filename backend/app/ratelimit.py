"""A small fixed-window rate limiter for the unauthenticated student route.

``/t/{class_code}/start`` takes no API key by design — a student has no account. That
makes it the one route a stranger can drive, so it needs a ceiling. In-process is enough
for a single instance; point ``backend`` at Redis when the service scales out.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status


@dataclass
class FixedWindowLimiter:
    limit: int
    window_seconds: int = 3600
    _hits: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def check(self, key: str, *, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        cutoff = now - self.window_seconds
        recent = [t for t in self._hits[key] if t > cutoff]
        if len(recent) >= self.limit:
            retry = int(recent[0] + self.window_seconds - now) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts from this network. Please try again shortly.",
                headers={"Retry-After": str(retry)},
            )
        recent.append(now)
        self._hits[key] = recent

    def reset(self) -> None:
        self._hits.clear()


def client_key(request: Request) -> str:
    """Render and most proxies terminate TLS upstream, so trust the forwarded chain."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
